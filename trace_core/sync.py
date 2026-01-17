"""Sync module for Trace - JSONL import/export, sync logic."""

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

from trace_core.projects import detect_project
from trace_core.issues import get_issue
from trace_core.contamination import (
    validate_issue_belongs_to_project,
    extract_project_name_from_id,
)
from trace_core.utils import get_iso_timestamp, get_project_uuid, generate_project_uuid, write_project_uuid

__all__ = [
    "get_last_sync_time",
    "set_last_sync_time",
    "sync_project",
    "export_to_jsonl",
    "import_from_jsonl",
]


def get_last_sync_time(db: sqlite3.Connection, project_id: str) -> Optional[float]:
    """Get timestamp of last JSONL sync for project.

    Args:
        db: Database connection
        project_id: Project ID (absolute path)

    Returns:
        Timestamp of last sync, or None if never synced
    """
    cursor = db.execute(
        "SELECT value FROM metadata WHERE key = ?",
        (f"last_sync:{project_id}",)
    )
    row = cursor.fetchone()
    return float(row[0]) if row else None


def set_last_sync_time(db: sqlite3.Connection, project_id: str, timestamp: float) -> None:
    """Record timestamp of JSONL sync.

    Args:
        db: Database connection
        project_id: Project ID (absolute path)
        timestamp: Unix timestamp of sync
    """
    db.execute(
        "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
        (f"last_sync:{project_id}", str(timestamp))
    )
    db.commit()


def sync_project(db: sqlite3.Connection, project_path: str) -> None:
    """Sync project: import from JSONL if newer than last sync.

    Args:
        db: Database connection
        project_path: Absolute path to project

    Notes:
        - Checks JSONL modification time vs last sync timestamp
        - Imports only if JSONL is newer (e.g., after git pull)
        - Updates last sync timestamp after import
        - Detects project_id from git context for portable imports
        - Auto-generates UUID if missing from .trace/id
    """
    # Detect project ID from git context
    project = detect_project(cwd=project_path)
    if not project:
        # Not a git repo, skip sync
        return

    project_id = project["id"]

    # Auto-generate UUID if .trace exists but .trace/id doesn't
    trace_dir = Path(project_path) / ".trace"
    if trace_dir.exists():
        project_uuid = get_project_uuid(trace_dir)
        if project_uuid is None:
            # Generate new UUID for existing project (auto-migration)
            project_uuid = generate_project_uuid()
            write_project_uuid(trace_dir, project_uuid)

        # Register/update project with UUID in database
        db.execute(
            "INSERT OR REPLACE INTO projects (id, name, current_path, uuid) VALUES (?, ?, ?, ?)",
            (project_id, project["name"], project_path, project_uuid)
        )
        db.commit()

    # AUTO-MERGE: Check if project_id changed (e.g., local path -> URL)
    # Find issues with different project_id but for this same path
    cursor = db.execute(
        "SELECT DISTINCT project_id FROM issues"
    )
    all_project_ids = [row[0] for row in cursor.fetchall()]

    for old_project_id in all_project_ids:
        # Check if this is the same project with a different ID
        # (e.g., old_project_id is absolute path, new is URL)
        if old_project_id != project_id:
            # Check if old_project_id points to this same path
            is_same_project = False

            # Case 1: old_project_id is the absolute path itself
            if old_project_id == project_path:
                is_same_project = True

            # Case 2: old_project_id exists in projects table with this path
            else:
                cursor2 = db.execute(
                    "SELECT current_path FROM projects WHERE id = ?",
                    (old_project_id,)
                )
                row = cursor2.fetchone()
                if row and row[0] == project_path:
                    is_same_project = True

            if is_same_project:
                # Auto-merge: update all issues from old_project_id to new_project_id
                db.execute(
                    "UPDATE issues SET project_id = ? WHERE project_id = ?",
                    (project_id, old_project_id)
                )
                db.commit()

                # Update or remove old entry in projects table
                db.execute(
                    "DELETE FROM projects WHERE id = ?",
                    (old_project_id,)
                )
                # Ensure new project_id is registered
                db.execute(
                    "INSERT OR REPLACE INTO projects (id, name, current_path) VALUES (?, ?, ?)",
                    (project_id, project["name"], project_path)
                )
                db.commit()

    # Now handle JSONL sync if file exists
    trace_dir = Path(project_path) / ".trace"
    jsonl_path = trace_dir / "issues.jsonl"

    if not jsonl_path.exists():
        return

    # Check if JSONL is newer than last sync
    jsonl_mtime = jsonl_path.stat().st_mtime
    last_sync = get_last_sync_time(db, project_id)

    if last_sync is None or jsonl_mtime > last_sync:
        # JSONL is newer, import it
        import_from_jsonl(db, str(jsonl_path), project_id)
        set_last_sync_time(db, project_id, jsonl_mtime)


def export_to_jsonl(
    db: sqlite3.Connection,
    project_id: str,
    jsonl_path: str,
) -> None:
    """Export project issues to JSONL file.

    Args:
        db: Database connection
        project_id: Project ID (UUID, URL, or path)
        jsonl_path: Path to JSONL file to create

    Format:
        One JSON object per line, sorted by ID
        Includes dependencies inline
        DOES NOT include project_id (project identity from git context)

    Note:
        Defense in depth: Only exports issues whose ID prefix matches
        the project name, filtering out any contaminated data.
    """
    # Get project name - first try from DB (for UUID-based lookup), then extract from ID
    cursor = db.execute(
        "SELECT name FROM projects WHERE uuid = ?",
        (project_id,)
    )
    row = cursor.fetchone()
    if row:
        project_name = row[0]
    else:
        # Fall back to extracting from ID (for backward compat with URL/path)
        project_name = extract_project_name_from_id(project_id)

    # Get all issues for project, sorted by ID
    cursor = db.execute(
        "SELECT * FROM issues WHERE project_id = ? ORDER BY id",
        (project_id,),
    )
    all_issues = [dict(row) for row in cursor.fetchall()]

    # Filter to only issues whose ID matches project name (defense in depth)
    issues = [
        issue
        for issue in all_issues
        if validate_issue_belongs_to_project(issue["id"], project_name)
    ]

    # Write to file
    path = Path(jsonl_path)
    with path.open("w") as f:
        for issue in issues:
            # Get dependencies for this issue
            deps_cursor = db.execute(
                "SELECT depends_on_id, type FROM dependencies WHERE issue_id = ? ORDER BY depends_on_id",
                (issue["id"],),
            )
            dependencies = [
                {"depends_on_id": row[0], "type": row[1]} for row in deps_cursor.fetchall()
            ]

            # Get comments for this issue
            comments_cursor = db.execute(
                "SELECT content, source, created_at FROM comments WHERE issue_id = ? ORDER BY created_at ASC",
                (issue["id"],),
            )
            comments = [
                {"content": row[0], "source": row[1], "created_at": row[2]}
                for row in comments_cursor.fetchall()
            ]

            # Prepare issue data (exclude project_id for portability)
            issue_data = dict(issue)
            del issue_data["project_id"]  # Remove project_id for portability
            issue_data["dependencies"] = dependencies
            issue_data["comments"] = comments

            # Write as single JSON line
            f.write(json.dumps(issue_data) + "\n")


def import_from_jsonl(
    db: sqlite3.Connection,
    jsonl_path: str,
    project_id: str,
) -> Dict[str, int]:
    """Import issues from JSONL file.

    Args:
        db: Database connection
        jsonl_path: Path to JSONL file to import
        project_id: Project ID to assign to imported issues (from git context)

    Returns:
        Dict with stats: created, updated, skipped, errors

    Notes:
        - Creates issues that don't exist
        - Updates issues that already exist
        - Skips issues whose ID prefix doesn't match project name
        - Skips malformed lines and continues
        - Creates dependencies after all issues imported
        - Ignores project_id from JSONL if present (uses parameter instead)
    """
    stats = {"created": 0, "updated": 0, "skipped": 0, "errors": 0}
    path = Path(jsonl_path)

    if not path.exists():
        return stats

    # Get project name for validation
    project_name = extract_project_name_from_id(project_id)

    # Read all issues first
    issues_to_import = []

    with path.open("r") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                issue_data = json.loads(line)
                issues_to_import.append(issue_data)
            except json.JSONDecodeError:
                stats["errors"] += 1
                # Continue processing other lines

    # Import issues (without dependencies first)
    for issue_data in issues_to_import:
        try:
            issue_id = issue_data["id"]

            # Validate issue belongs to this project
            if not validate_issue_belongs_to_project(issue_id, project_name):
                stats["skipped"] += 1
                continue

            # Check if issue exists
            existing = get_issue(db, issue_id)

            if existing is None:
                # Create new issue
                # Use project_id parameter, not from JSONL (for portability)
                db.execute(
                    """INSERT INTO issues
                       (id, project_id, title, description, status, priority, created_at, updated_at, closed_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        issue_data["id"],
                        project_id,  # Use parameter, not issue_data["project_id"]
                        issue_data["title"],
                        issue_data.get("description", ""),
                        issue_data.get("status", "open"),
                        issue_data.get("priority", 2),
                        issue_data["created_at"],
                        issue_data["updated_at"],
                        issue_data.get("closed_at"),
                    ),
                )
                stats["created"] += 1
            else:
                # Update existing issue
                db.execute(
                    """UPDATE issues
                       SET title = ?, description = ?, status = ?, priority = ?,
                           updated_at = ?, closed_at = ?
                       WHERE id = ?""",
                    (
                        issue_data["title"],
                        issue_data.get("description", ""),
                        issue_data.get("status", "open"),
                        issue_data.get("priority", 2),
                        issue_data["updated_at"],
                        issue_data.get("closed_at"),
                        issue_id,
                    ),
                )
                stats["updated"] += 1

        except Exception:
            stats["errors"] += 1

    db.commit()

    # Now import dependencies
    for issue_data in issues_to_import:
        try:
            issue_id = issue_data["id"]
            dependencies = issue_data.get("dependencies", [])

            # Clear existing dependencies for this issue
            db.execute("DELETE FROM dependencies WHERE issue_id = ?", (issue_id,))

            # Add new dependencies
            for dep in dependencies:
                now = get_iso_timestamp()
                db.execute(
                    """INSERT OR IGNORE INTO dependencies (issue_id, depends_on_id, type, created_at)
                       VALUES (?, ?, ?, ?)""",
                    (issue_id, dep["depends_on_id"], dep["type"], now),
                )

        except Exception:
            # Dependency errors don't increment error count
            pass

    db.commit()

    # Now import comments
    for issue_data in issues_to_import:
        try:
            issue_id = issue_data["id"]
            comments = issue_data.get("comments", [])

            # Clear existing comments for this issue
            db.execute("DELETE FROM comments WHERE issue_id = ?", (issue_id,))

            # Add comments from JSONL
            for comment in comments:
                db.execute(
                    """INSERT INTO comments (issue_id, content, source, created_at)
                       VALUES (?, ?, ?, ?)""",
                    (issue_id, comment["content"], comment["source"], comment["created_at"]),
                )

        except Exception:
            # Comment errors don't increment error count
            pass

    db.commit()

    return stats
