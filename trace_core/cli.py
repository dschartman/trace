"""CLI module for Trace - typer app and all commands."""

import json
import time
from pathlib import Path
from typing import Optional, Set

import typer
from typing_extensions import Annotated

from trace_core.db import get_db, get_lock_path
from trace_core.projects import (
    detect_project,
    is_project_initialized,
    resolve_project,
    get_project_path,
)
from trace_core.issues import (
    create_issue as _create_issue,
    get_issue,
    list_issues,
    update_issue as _update_issue,
    close_issue as _close_issue,
)
from trace_core.dependencies import (
    add_dependency as _add_dependency,
    get_dependencies,
    get_children,
    is_blocked,
    has_open_children,
)
from trace_core.sync import (
    sync_project,
    export_to_jsonl,
    set_last_sync_time,
)
from trace_core.reorganization import (
    reparent_issue as _reparent_issue,
    move_issue as _move_issue,
)
from trace_core.contamination import repair_contaminated_issues
from trace_core.comments import add_comment as _add_comment, get_comments
from trace_core.utils import file_lock

__all__ = ["app", "main"]

# Create Typer app
app = typer.Typer(help="Trace - Minimal distributed issue tracker for AI agent workflows")


@app.command()
def init():
    """Initialize trace in current directory."""
    project = detect_project()

    if project is None:
        print("Error: Not in a git repository")
        print("Run 'git init' first or use 'trc init' inside a git repo")
        raise typer.Exit(code=1)

    # Create .trace directory
    trace_dir = Path(project["path"]) / ".trace"
    trace_dir.mkdir(exist_ok=True)

    # Create empty issues.jsonl
    jsonl_path = trace_dir / "issues.jsonl"
    if not jsonl_path.exists():
        jsonl_path.write_text("")

    # Register project in central database (new schema: id, name, current_path)
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO projects (id, name, current_path) VALUES (?, ?, ?)",
        (project["id"], project["name"], project["path"]),
    )
    db.commit()
    db.close()

    print(f"Initialized trace for project: {project['name']}")
    print(f"Project ID: {project['id']}")
    print(f"Path: {project['path']}")
    print(f"JSONL: {jsonl_path}")


@app.command()
def create(
    title: Annotated[str, typer.Argument(help="Issue title")],
    description: Annotated[str, typer.Option(help="Detailed description (required)")],
    priority: Annotated[int, typer.Option(help="Priority level (0-4)")] = 2,
    status: Annotated[str, typer.Option(help="Initial status")] = "open",
    parent: Annotated[Optional[str], typer.Option(help="Parent issue ID")] = None,
    depends_on: Annotated[Optional[str], typer.Option(help="Blocking dependency ID")] = None,
    project_flag: Annotated[Optional[str], typer.Option("--project", help="Target project (name or path)")] = None,
):
    """Create a new issue."""
    # Resolve target project
    if project_flag:
        # Look up in registry by name or path
        db = get_db()
        project = resolve_project(project_flag, db)

        if project is None:
            print(f"Error: Project '{project_flag}' not found in registry")
            print("Hint: Run 'trc init' in the target project first")
            db.close()
            raise typer.Exit(code=1)

        db.close()
    else:
        # Use current directory detection
        project = detect_project()

        if project is None:
            print("Error: Not in a git repository")
            print("Run 'trc init' first or use --project <name>")
            raise typer.Exit(code=1)

    # Check if project is initialized (TRANSACTION SAFETY)
    if not is_project_initialized(project["path"]):
        print("Error: Project not initialized")
        print(f"Run 'trc init' in {project['path']} first")
        raise typer.Exit(code=1)

    lock_path = get_lock_path()

    with file_lock(lock_path):
        db = get_db()

        # Sync before operation
        sync_project(db, project["path"])

        # Create issue (use project["id"] for database)
        issue = _create_issue(
            db,
            project["id"],  # Use project_id (URL or path)
            project["name"],
            title,
            description=description,
            priority=priority,
            status=status,
        )

        if not issue:
            print("Error: Failed to create issue")
            db.close()
            raise typer.Exit(code=1)

        # Add parent dependency if specified
        if parent:
            _add_dependency(db, issue["id"], parent, "parent")

        # Add blocking dependency if specified
        if depends_on:
            _add_dependency(db, issue["id"], depends_on, "blocks")

        # Export to JSONL (use project["id"] for database, project["path"] for filesystem)
        trace_dir = Path(project["path"]) / ".trace"
        jsonl_path = trace_dir / "issues.jsonl"
        export_to_jsonl(db, project["id"], str(jsonl_path))
        set_last_sync_time(db, project["id"], time.time())

        print(f"Created {issue['id']}: {title}")
        if parent:
            print(f"  Parent: {parent}")
        if depends_on:
            print(f"  Depends-on: {depends_on}")

        db.close()


@app.command(name="list")
def list_cmd(
    project: Annotated[Optional[str], typer.Option(help="Filter by project - name or path (use 'any' for all projects)")] = None,
    status: Annotated[Optional[list[str]], typer.Option(help="Filter by status (can specify multiple times, use 'any' for all statuses)")] = None,
):
    """List issues."""
    lock_path = get_lock_path()

    with file_lock(lock_path):
        db = get_db()

        # Resolve status filter
        # Default to backlog (exclude closed) when no --status provided
        if status is None or len(status) == 0:
            status_filter = ["open", "in_progress", "blocked"]
        elif len(status) == 1 and status[0] == "any":
            # Special case: --status any means show all statuses
            status_filter = None
        else:
            # Use provided status(es)
            status_filter = status

        # Handle --project flag
        if project == "any":
            # List all issues across all projects
            issues = list_issues(db, status=status_filter)
        elif project is not None:
            # Look up specific project by name or path
            target_project = resolve_project(project, db)
            if target_project is None:
                print(f"Error: Project '{project}' not found in registry")
                print("Hint: Run 'trc list --project any' to see all projects")
                db.close()
                raise typer.Exit(code=1)

            sync_project(db, target_project["path"])
            issues = list_issues(db, project_id=target_project["id"], status=status_filter)
        else:
            # No --project flag, use current directory
            current_project = detect_project()
            if current_project is None:
                print("Error: Not in a git repository. Use --project any to list all issues.")
                db.close()
                raise typer.Exit(code=1)

            # Sync before operation
            sync_project(db, current_project["path"])

            # Use project["id"] for database query
            issues = list_issues(db, project_id=current_project["id"], status=status_filter)

        if not issues:
            print("No issues found")
            db.close()
            return

        # Print issues
        for issue in issues:
            status_marker = {
                "open": "○",
                "in_progress": "◐",
                "closed": "●",
                "blocked": "⊘",
            }.get(issue["status"], "?")

            priority_label = f"P{issue['priority']}"

            print(f"{status_marker} {issue['id']} [{priority_label}] {issue['title']}")

        db.close()


@app.command()
def show(issue_id: Annotated[str, typer.Argument(help="Issue ID")]):
    """Show issue details."""
    lock_path = get_lock_path()

    with file_lock(lock_path):
        db = get_db()

        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            raise typer.Exit(code=1)

        # Sync before operation - use get_project_path to convert project_id to filesystem path
        project_path = get_project_path(db, issue["project_id"])
        if project_path:
            sync_project(db, project_path)

        # Re-fetch after sync
        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            raise typer.Exit(code=1)

        # Get dependencies
        deps = get_dependencies(db, issue_id)
        children = get_children(db, issue_id)

        # Print issue details
        print(f"ID:          {issue['id']}")
        print(f"Title:       {issue['title']}")
        print(f"Status:      {issue['status']}")
        print(f"Priority:    {issue['priority']}")
        print(f"Project:     {issue['project_id']}")
        print(f"Created:     {issue['created_at']}")
        print(f"Updated:     {issue['updated_at']}")

        if issue["description"]:
            print(f"\nDescription:\n{issue['description']}")

        if deps:
            print("\nDependencies:")
            for dep in deps:
                dep_issue = get_issue(db, dep["depends_on_id"])
                dep_title = dep_issue["title"] if dep_issue else "(unknown)"
                print(f"  {dep['type']:8} {dep['depends_on_id']} - {dep_title}")

        if children:
            print("\nChildren:")
            for child in children:
                status_marker = {
                    "open": "○",
                    "in_progress": "◐",
                    "closed": "●",
                    "blocked": "⊘",
                }.get(child["status"], "?")
                print(f"  {status_marker} {child['id']} - {child['title']}")

        # Get and display comments
        comments = get_comments(db, issue_id)
        if comments:
            print("\nComments:")
            for c in comments:
                # Format timestamp for display (remove microseconds)
                timestamp = c["created_at"][:19].replace("T", " ")
                print(f"  [{timestamp}] {c['source']}: {c['content']}")

        db.close()


@app.command()
def close(issue_ids: Annotated[list[str], typer.Argument(help="Issue ID(s) to close")]):
    """Close one or more issues."""
    lock_path = get_lock_path()

    with file_lock(lock_path):
        db = get_db()

        # Track which projects need JSONL export
        projects_to_export: Set[str] = set()
        closed_issues = []
        errors = []

        for issue_id in issue_ids:
            issue = get_issue(db, issue_id)
            if issue is None:
                errors.append(f"Warning: Issue {issue_id} not found")
                continue

            # Get project path for filesystem operations
            project_id = issue["project_id"]
            project_path = get_project_path(db, project_id)
            if not project_path:
                errors.append(f"Warning: Cannot find project path for {project_id}")
                continue

            # Check if project is initialized (TRANSACTION SAFETY)
            if not is_project_initialized(project_path):
                errors.append(f"Warning: Project not initialized for {issue_id}: {project_path}")
                continue

            # Sync before operation (once per project)
            if project_id not in projects_to_export:
                sync_project(db, project_path)

            # Re-fetch after sync
            issue = get_issue(db, issue_id)
            if issue is None:
                errors.append(f"Warning: Issue {issue_id} not found after sync")
                continue

            # Check for open children
            if has_open_children(db, issue_id):
                children = get_children(db, issue_id)
                open_children = [c for c in children if c["status"] != "closed"]
                error_msg = f"Warning: Cannot close {issue_id} with open children:"
                for child in open_children:
                    error_msg += f"\n  - {child['id']}: {child['title']} [{child['status']}]"
                errors.append(error_msg)
                continue

            # Close the issue
            _close_issue(db, issue_id)
            closed_issues.append((issue_id, issue['title']))
            projects_to_export.add(project_id)

        # Export to JSONL for all affected projects
        for project_id in projects_to_export:
            project_path = get_project_path(db, project_id)
            if project_path:
                trace_dir = Path(project_path) / ".trace"
                jsonl_path = trace_dir / "issues.jsonl"
                export_to_jsonl(db, project_id, str(jsonl_path))
                set_last_sync_time(db, project_id, time.time())

        db.close()

        # Print errors first
        for error in errors:
            print(error)

        # Print successfully closed issues
        for issue_id, title in closed_issues:
            print(f"Closed {issue_id}: {title}")

        # Exit with error if nothing was closed
        if not closed_issues and errors:
            raise typer.Exit(code=1)


@app.command()
def ready(
    project: Annotated[Optional[str], typer.Option(help="Filter by project - name or path (use 'any' for all projects)")] = None,
    status: Annotated[Optional[str], typer.Option(help="Filter by status (defaults to 'open', use 'any' for all)")] = None,
):
    """Show ready work (not blocked)."""
    lock_path = get_lock_path()

    with file_lock(lock_path):
        db = get_db()

        # Default status to "open" if not specified
        if status is None:
            status = "open"

        # Resolve status filter
        status_filter = None if status == "any" else status

        # Handle --project flag
        if project == "any":
            # Get all issues across all projects
            issues = list_issues(db, status=status_filter)
        elif project is not None:
            # Look up specific project by name or path
            target_project = resolve_project(project, db)
            if target_project is None:
                print(f"Error: Project '{project}' not found in registry")
                print("Hint: Run 'trc ready --project any' to see all ready work")
                db.close()
                raise typer.Exit(code=1)

            sync_project(db, target_project["path"])
            issues = list_issues(db, project_id=target_project["id"], status=status_filter)
        else:
            # No --project flag, use current directory
            current_project = detect_project()
            if current_project is None:
                print("Error: Not in a git repository. Use --project any to see all ready work.")
                db.close()
                raise typer.Exit(code=1)

            # Sync before operation
            sync_project(db, current_project["path"])

            # Use project["id"] for database query
            issues = list_issues(db, project_id=current_project["id"], status=status_filter)

        if not issues:
            print("No open issues found")
            db.close()
            return

        # Filter to only ready (not blocked) issues
        ready_issues = []
        for issue in issues:
            if not is_blocked(db, issue["id"]):
                ready_issues.append(issue)

        if not ready_issues:
            print("No ready work (all issues are blocked)")
            db.close()
            return

        # Print ready issues
        print("Ready work (not blocked):\n")
        for issue in ready_issues:
            priority_label = f"P{issue['priority']}"
            print(f"○ {issue['id']} [{priority_label}] {issue['title']}")

            # Show what it depends on (parent)
            deps = get_dependencies(db, issue["id"])
            parent_deps = [d for d in deps if d["type"] == "parent"]
            if parent_deps:
                for dep in parent_deps:
                    parent_issue = get_issue(db, dep["depends_on_id"])
                    if parent_issue:
                        print(f"   └─ child of: {parent_issue['id']} - {parent_issue['title']}")

        db.close()


@app.command()
def tree(
    issue_id: Annotated[str, typer.Argument(help="Issue ID")],
    max_depth: Annotated[int, typer.Option(help="Maximum depth to display")] = 10,
):
    """Show issue tree (parent-child hierarchy)."""
    lock_path = get_lock_path()

    with file_lock(lock_path):
        db = get_db()

        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            raise typer.Exit(code=1)

        # Get project path and sync
        project_path = get_project_path(db, issue["project_id"])
        if project_path:
            sync_project(db, project_path)

        # Re-fetch after sync
        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            raise typer.Exit(code=1)

        def print_tree(issue_id, depth=0, prefix="", is_last=True):
            """Recursively print issue tree."""
            if depth > max_depth:
                return

            issue = get_issue(db, issue_id)
            if not issue:
                return

            # Status marker
            status_marker = {
                "open": "○",
                "in_progress": "◐",
                "closed": "●",
                "blocked": "⊘",
            }.get(issue["status"], "?")

            # Tree connector
            connector = "└─ " if is_last else "├─ "
            if depth == 0:
                connector = ""

            # Print issue
            indent = prefix
            print(f"{indent}{connector}{status_marker} {issue['id']} - {issue['title']} [{issue['status']}]")

            # Get children
            children = get_children(db, issue_id)

            if children:
                # Update prefix for children
                child_prefix = prefix + ("   " if is_last or depth == 0 else "│  ")

                for i, child in enumerate(children):
                    is_last_child = (i == len(children) - 1)
                    print_tree(child["id"], depth + 1, child_prefix, is_last_child)

        # Start printing from root
        print_tree(issue_id)

        db.close()


@app.command()
def update(
    issue_id: Annotated[str, typer.Argument(help="Issue ID")],
    title: Annotated[Optional[str], typer.Option(help="Set title")] = None,
    description: Annotated[Optional[str], typer.Option(help="Set description")] = None,
    priority: Annotated[Optional[int], typer.Option(help="Set priority (0-4)")] = None,
    status: Annotated[Optional[str], typer.Option(help="Set status")] = None,
):
    """Update an issue."""
    lock_path = get_lock_path()

    with file_lock(lock_path):
        db = get_db()

        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            raise typer.Exit(code=1)

        # Get project path and sync
        project_path = get_project_path(db, issue["project_id"])
        if project_path:
            # Check if project is initialized (TRANSACTION SAFETY)
            if not is_project_initialized(project_path):
                print("Error: Project not initialized")
                print(f"Run 'trc init' in {project_path} first")
                db.close()
                raise typer.Exit(code=1)

            sync_project(db, project_path)

        # Re-fetch after sync
        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            raise typer.Exit(code=1)

        # Update issue
        try:
            _update_issue(db, issue_id, title=title, description=description, priority=priority, status=status)
        except ValueError as e:
            print(f"Error: {e}")
            db.close()
            raise typer.Exit(code=1)

        # Export to JSONL
        project_id = issue["project_id"]
        project_path = get_project_path(db, project_id)
        if not project_path:
            print(f"Error: Cannot find project path for {project_id}")
            db.close()
            raise typer.Exit(code=1)

        trace_dir = Path(project_path) / ".trace"
        jsonl_path = trace_dir / "issues.jsonl"
        export_to_jsonl(db, project_id, str(jsonl_path))
        set_last_sync_time(db, project_id, time.time())

        updated = get_issue(db, issue_id)
        if updated:
            print(f"Updated {issue_id}:")
            if title:
                print(f"  Title: {updated['title']}")
            if description is not None:
                print(f"  Description: {updated['description']}")
            if priority is not None:
                print(f"  Priority: {updated['priority']}")
            if status:
                print(f"  Status: {updated['status']}")

        db.close()


@app.command()
def comment(
    issue_id: Annotated[str, typer.Argument(help="Issue ID")],
    text: Annotated[str, typer.Argument(help="Comment text")],
    source: Annotated[str, typer.Option(help="Source identifier (who made the comment)")] = "user",
):
    """Add a comment to an issue."""
    lock_path = get_lock_path()

    with file_lock(lock_path):
        db = get_db()

        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            raise typer.Exit(code=1)

        # Get project path and sync
        project_id = issue["project_id"]
        project_path = get_project_path(db, project_id)
        if project_path:
            # Check if project is initialized (TRANSACTION SAFETY)
            if not is_project_initialized(project_path):
                print("Error: Project not initialized")
                print(f"Run 'trc init' in {project_path} first")
                db.close()
                raise typer.Exit(code=1)

            sync_project(db, project_path)

        # Re-fetch after sync
        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            raise typer.Exit(code=1)

        # Add comment
        comment_data = _add_comment(db, issue_id, text, source=source)

        # Export to JSONL
        project_id = issue["project_id"]
        project_path = get_project_path(db, project_id)
        if not project_path:
            print(f"Error: Cannot find project path for {project_id}")
            db.close()
            raise typer.Exit(code=1)

        trace_dir = Path(project_path) / ".trace"
        jsonl_path = trace_dir / "issues.jsonl"
        export_to_jsonl(db, project_id, str(jsonl_path))
        set_last_sync_time(db, project_id, time.time())

        # Format timestamp for display
        timestamp = comment_data["created_at"][:19].replace("T", " ")
        print(f"Added comment to {issue_id}:")
        print(f"  [{timestamp}] {source}: {text}")

        db.close()


@app.command()
def reparent(
    issue_id: Annotated[str, typer.Argument(help="Issue ID")],
    new_parent_id: Annotated[str, typer.Argument(help="New parent ID (use 'none' to remove)")],
):
    """Change parent of an issue."""
    # Handle 'none' as None
    parent_id = None if new_parent_id.lower() == "none" else new_parent_id

    lock_path = get_lock_path()

    with file_lock(lock_path):
        db = get_db()

        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            raise typer.Exit(code=1)

        # Get project path and sync
        project_id = issue["project_id"]
        project_path = get_project_path(db, project_id)
        if not project_path:
            print(f"Error: Cannot find project path for {project_id}")
            db.close()
            raise typer.Exit(code=1)

        # Check if project is initialized (TRANSACTION SAFETY)
        if not is_project_initialized(project_path):
            print("Error: Project not initialized")
            print(f"Run 'trc init' in {project_path} first")
            db.close()
            raise typer.Exit(code=1)

        sync_project(db, project_path)

        # Re-fetch after sync
        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            raise typer.Exit(code=1)

        # Validate new parent exists if provided
        if parent_id is not None:
            new_parent = get_issue(db, parent_id)
            if new_parent is None:
                print(f"Error: Parent issue {parent_id} not found")
                db.close()
                raise typer.Exit(code=1)

        # Reparent with cycle detection
        try:
            _reparent_issue(db, issue_id, parent_id)
        except ValueError as e:
            print(f"Error: {e}")
            db.close()
            raise typer.Exit(code=1)

        # Export to JSONL for the issue's project
        trace_dir = Path(project_path) / ".trace"
        jsonl_path = trace_dir / "issues.jsonl"
        export_to_jsonl(db, project_id, str(jsonl_path))
        set_last_sync_time(db, project_id, time.time())

        # Print confirmation
        if parent_id is None:
            print(f"Removed parent from {issue_id}")
        else:
            print(f"Reparented {issue_id} to {parent_id}")

        db.close()


@app.command(name="add-dependency")
def add_dependency_cmd(
    issue_id: Annotated[str, typer.Argument(help="Issue ID")],
    depends_on_id: Annotated[str, typer.Argument(help="Issue that is depended upon")],
    dep_type: Annotated[str, typer.Option("--type", help="Dependency type (blocks, parent, related)")] = "blocks",
):
    """Add a dependency between two existing issues."""
    lock_path = get_lock_path()

    with file_lock(lock_path):
        db = get_db()

        # Validate both issues exist
        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            raise typer.Exit(code=1)

        depends_on = get_issue(db, depends_on_id)
        if depends_on is None:
            print(f"Error: Issue {depends_on_id} not found")
            db.close()
            raise typer.Exit(code=1)

        # Get project paths for sync
        issue_project_id = issue["project_id"]
        issue_project_path = get_project_path(db, issue_project_id)
        if not issue_project_path:
            print(f"Error: Cannot find project path for {issue_project_id}")
            db.close()
            raise typer.Exit(code=1)

        # Check if issue project is initialized (TRANSACTION SAFETY)
        if not is_project_initialized(issue_project_path):
            print("Error: Project not initialized")
            print(f"Run 'trc init' in {issue_project_path} first")
            db.close()
            raise typer.Exit(code=1)

        depends_project_id = depends_on["project_id"]
        depends_project_path = get_project_path(db, depends_project_id)

        # Check if depends_on project is initialized (if different project)
        if depends_project_id != issue_project_id and depends_project_path:
            if not is_project_initialized(depends_project_path):
                print("Error: Dependency project not initialized")
                print(f"Run 'trc init' in {depends_project_path} first")
                db.close()
                raise typer.Exit(code=1)

        # Sync both projects before operation
        sync_project(db, issue_project_path)
        if depends_project_id != issue_project_id and depends_project_path:
            sync_project(db, depends_project_path)

        # Re-fetch after sync
        issue = get_issue(db, issue_id)
        depends_on = get_issue(db, depends_on_id)

        if issue is None or depends_on is None:
            print("Error: Issue not found after sync")
            db.close()
            raise typer.Exit(code=1)

        # Add dependency
        try:
            _add_dependency(db, issue_id, depends_on_id, dep_type)
        except ValueError as e:
            print(f"Error: {e}")
            db.close()
            raise typer.Exit(code=1)

        # Export to JSONL for the issue's project
        trace_dir = Path(issue_project_path) / ".trace"
        jsonl_path = trace_dir / "issues.jsonl"
        export_to_jsonl(db, issue_project_id, str(jsonl_path))
        set_last_sync_time(db, issue_project_id, time.time())

        # Also export for depends_on project if different
        if depends_project_id != issue_project_id and depends_project_path:
            depends_trace_dir = Path(depends_project_path) / ".trace"
            depends_jsonl_path = depends_trace_dir / "issues.jsonl"
            export_to_jsonl(db, depends_project_id, str(depends_jsonl_path))
            set_last_sync_time(db, depends_project_id, time.time())

        # Print clear dependency message based on type
        if dep_type == "blocks":
            print(f"{issue_id} is blocked by {depends_on_id}")
        elif dep_type == "parent":
            print(f"Set {depends_on_id} as parent of {issue_id}")
        elif dep_type == "related":
            print(f"Linked {issue_id} <-> {depends_on_id} (related)")
        else:
            # Fallback for unknown types
            print(f"Added {dep_type} dependency: {issue_id} -> {depends_on_id}")

        db.close()


@app.command()
def move(
    issue_id: Annotated[str, typer.Argument(help="Issue ID")],
    target_project_name: Annotated[str, typer.Argument(help="Target project (name or path)")],
):
    """Move issue to different project."""
    lock_path = get_lock_path()

    with file_lock(lock_path):
        db = get_db()

        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            raise typer.Exit(code=1)

        # Get source project info (new schema: id, name, current_path)
        old_project_id = issue["project_id"]
        cursor = db.execute(
            "SELECT current_path FROM projects WHERE id = ?",
            (old_project_id,),
        )
        row = cursor.fetchone()
        if row:
            old_project_path = row[0]
            # Check if old project is initialized (TRANSACTION SAFETY)
            if not is_project_initialized(old_project_path):
                print("Error: Source project not initialized")
                print(f"Run 'trc init' in {old_project_path} first")
                db.close()
                raise typer.Exit(code=1)
            # Sync source project before operation
            sync_project(db, old_project_path)
        else:
            # Project not in registry, assume project_id is a path (backward compat)
            old_project_path = old_project_id
            if Path(old_project_path).exists():
                if not is_project_initialized(old_project_path):
                    print("Error: Source project not initialized")
                    print(f"Run 'trc init' in {old_project_path} first")
                    db.close()
                    raise typer.Exit(code=1)
                sync_project(db, old_project_path)

        # Re-fetch after sync
        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            raise typer.Exit(code=1)

        # Look up target project by name or path
        target_project = resolve_project(target_project_name, db)

        if target_project is None:
            print(f"Error: Project '{target_project_name}' not found in registry")
            print("Hint: Run 'trc init' in the target project first")
            db.close()
            raise typer.Exit(code=1)

        new_project_id = target_project["id"]
        new_project_name = target_project["name"]
        new_project_path = target_project["path"]

        # Check if target project is initialized (TRANSACTION SAFETY)
        if not is_project_initialized(new_project_path):
            print("Error: Target project not initialized")
            print(f"Run 'trc init' in {new_project_path} first")
            db.close()
            raise typer.Exit(code=1)

        # Sync target project before operation
        sync_project(db, new_project_path)

        # Move issue
        try:
            new_id = _move_issue(db, issue_id, new_project_id, new_project_name)
        except ValueError as e:
            print(f"Error: {e}")
            db.close()
            raise typer.Exit(code=1)

        # Export to JSONL for both projects
        old_trace_dir = Path(old_project_path) / ".trace"
        old_jsonl = old_trace_dir / "issues.jsonl"
        export_to_jsonl(db, old_project_id, str(old_jsonl))
        set_last_sync_time(db, old_project_id, time.time())

        new_trace_dir = Path(new_project_path) / ".trace"
        new_trace_dir.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
        new_jsonl = new_trace_dir / "issues.jsonl"
        export_to_jsonl(db, new_project_id, str(new_jsonl))
        set_last_sync_time(db, new_project_id, time.time())

        print(f"Moved {issue_id} → {new_id}")
        print(f"  From: {old_project_id} ({old_project_path})")
        print(f"  To:   {new_project_id} ({new_project_path})")

        db.close()


@app.command()
def repair(
    project_flag: Annotated[
        Optional[str], typer.Option("--project", "-p", help="Repair specific project only")
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show what would be repaired without making changes")
    ] = False,
    output_json: Annotated[
        bool, typer.Option("--json", help="Output results as JSON")
    ] = False,
):
    """Repair contaminated issue data.

    Finds issues where the ID prefix doesn't match the project assignment
    and reassigns them to the correct project based on their ID.

    Example:
        trc repair --dry-run    # Preview what would be fixed
        trc repair              # Actually fix contamination
        trc repair --project myapp  # Fix only in myapp project
    """
    db = get_db()

    # Resolve project if specified
    project_id = None
    if project_flag:
        resolved = resolve_project(project_flag, db)
        if resolved is None:
            print(f"Error: Project '{project_flag}' not found")
            db.close()
            raise typer.Exit(code=1)
        project_id = resolved["path"]

    # Run repair
    stats = repair_contaminated_issues(db, project_id=project_id, dry_run=dry_run)

    if output_json:
        print(json.dumps(stats, indent=2))
        db.close()
        return

    # Human-readable output
    if dry_run:
        print("Dry run - no changes made\n")

    print(f"Examined: {stats['examined']} issues")
    print(f"Contaminated: {stats['contaminated']} issues")

    if stats["contaminated"] == 0:
        print("\nNo contamination found.")
        db.close()
        return

    if dry_run:
        print(f"\nWould repair: {stats['repaired']} issues")
        if stats["orphaned"] > 0:
            print(f"Orphaned (no matching project): {stats['orphaned']} issues")
        print("\nRun 'trc repair' without --dry-run to apply changes.")
    else:
        print(f"\nRepaired: {stats['repaired']} issues")
        if stats["orphaned"] > 0:
            print(f"Orphaned (no matching project): {stats['orphaned']} issues")

        # Re-export affected projects
        if stats["affected_projects"]:
            print("\nRe-exporting affected projects:")
            for project_path in stats["affected_projects"]:
                trace_dir = Path(project_path) / ".trace"
                if trace_dir.exists():
                    jsonl_path = trace_dir / "issues.jsonl"
                    # Get project_id for this path
                    cursor = db.execute(
                        "SELECT id FROM projects WHERE current_path = ?",
                        (project_path,),
                    )
                    row = cursor.fetchone()
                    if row:
                        export_to_jsonl(db, row[0], str(jsonl_path))
                        set_last_sync_time(db, row[0], time.time())
                        # Count issues exported
                        cursor = db.execute(
                            "SELECT COUNT(*) FROM issues WHERE project_id = ?",
                            (row[0],),
                        )
                        count = cursor.fetchone()[0]
                        print(f"  - {jsonl_path} ({count} issues)")

            print("\nCommit the updated .trace/issues.jsonl files to git.")

    db.close()


@app.command()
def guide():
    """Display AI agent integration guide."""
    guide_text = """
===============================================================================
                    Trace (trc) - AI Agent Integration Guide
===============================================================================

Add this to your project's CLAUDE.md file for AI agent integration:

-------------------------------------------------------------------------------

## Using Trace for Work Tracking

This project uses [Trace](https://github.com/dschartman/trace) for persistent
work tracking across AI sessions.

**When to use trace vs TodoWrite:**

Use trace instead of TodoWrite for any non-trivial work. If it involves multiple
files, could span sessions, or needs to persist - use trace.

- **TodoWrite**: Single-session trivial tasks only
- **Trace**: Everything else (features, bugs, planning, multi-step work)
- **When in doubt**: Use trace

**Why this matters:** Trace persists across sessions and commits to git. TodoWrite
is ephemeral. For a tool designed around persistent work tracking, using TodoWrite
defeats the purpose.

**Setup (required once per project):**

```bash
trc init  # Run this first in your git repo
```

If you forget, you'll see: "Error: Project not initialized. Run 'trc init' first"

**Core workflow:**

```bash
# Create work
trc create "title" --description "context"
trc create "subtask" --description "details" --parent <id>

# Discover work
trc ready              # What's unblocked and ready to work on
trc list               # Current backlog (excludes closed)
trc show <id>          # Full details with dependencies

# Complete work
trc close <id> [...]   # Close one or more issues
```

**Essential details:**

- `--description` is required (preserves context across sessions for AI agents)
  - Use `--description ""` to explicitly skip if truly not needed
- Structure is fluid: Break down or reorganize as understanding evolves
- Use `--parent <id>` to create hierarchical breakdowns
- Cross-project: Add `--project <name>` to work across repositories
- Use `trc <command> --help` for full options

-------------------------------------------------------------------------------

For more details: https://github.com/dschartman/trace
"""
    print(guide_text)


def main():
    """Main CLI entry point."""
    app()
