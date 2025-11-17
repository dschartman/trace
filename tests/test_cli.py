"""Tests for CLI commands."""

import os
import re
from pathlib import Path
import subprocess

import pytest


def extract_issue_id(output: str) -> str:
    """Extract issue ID from CLI output."""
    match = re.search(r"([\w-]+)-([a-z0-9]{6})", output)
    if match:
        return match.group(0)
    raise ValueError(f"Could not extract issue ID from: {output}")


def test_cli_init_creates_trace_directory(sample_project, tmp_trace_dir, monkeypatch):
    """cli_init should create .trace directory."""
    from trc_main import cli_init

    monkeypatch.chdir(sample_project["path"])

    result = cli_init()

    assert result == 0
    assert (sample_project["trace_dir"]).exists()
    assert (sample_project["trace_dir"] / "issues.jsonl").exists()


def test_cli_init_outside_git_repo(tmp_path, tmp_trace_dir, monkeypatch):
    """cli_init should fail outside git repo."""
    from trc_main import cli_init

    non_git_dir = tmp_path / "not-a-repo"
    non_git_dir.mkdir()
    monkeypatch.chdir(non_git_dir)

    result = cli_init()

    assert result == 1  # Error code


def test_cli_create_basic_issue(sample_project, tmp_trace_dir, monkeypatch, capsys):
    """cli_create should create issue with title."""
    from trc_main import cli_init, cli_create

    monkeypatch.chdir(sample_project["path"])
    cli_init()

    result = cli_create("Test issue")

    assert result == 0

    captured = capsys.readouterr()
    assert "Created" in captured.out
    assert "Test issue" in captured.out


def test_cli_create_with_parent(sample_project, tmp_trace_dir, monkeypatch, capsys):
    """cli_create should link to parent."""
    from trc_main import cli_init, cli_create, get_db, get_dependencies

    monkeypatch.chdir(sample_project["path"])
    cli_init()

    # Create parent
    cli_create("Parent")
    captured = capsys.readouterr()
    parent_id = extract_issue_id(captured.out)

    # Create child with parent
    result = cli_create("Child", parent=parent_id)

    assert result == 0

    # Verify parent link
    db = get_db()
    captured = capsys.readouterr()
    child_id = extract_issue_id(captured.out)

    deps = get_dependencies(db, child_id)
    parent_deps = [d for d in deps if d["type"] == "parent"]

    assert len(parent_deps) == 1
    assert parent_deps[0]["depends_on_id"] == parent_id

    db.close()


def test_cli_list_shows_issues(sample_project, tmp_trace_dir, monkeypatch, capsys):
    """cli_list should display issues."""
    from trc_main import cli_init, cli_create, cli_list

    monkeypatch.chdir(sample_project["path"])
    cli_init()

    cli_create("Issue 1")
    cli_create("Issue 2")
    capsys.readouterr()  # Clear

    result = cli_list()

    assert result == 0

    captured = capsys.readouterr()
    assert "Issue 1" in captured.out
    assert "Issue 2" in captured.out


def test_cli_list_empty_project(sample_project, tmp_trace_dir, monkeypatch, capsys):
    """cli_list should handle empty project."""
    from trc_main import cli_init, cli_list

    monkeypatch.chdir(sample_project["path"])
    cli_init()

    result = cli_list()

    assert result == 0

    captured = capsys.readouterr()
    assert "No issues found" in captured.out


def test_cli_show_displays_issue_details(sample_project, tmp_trace_dir, monkeypatch, capsys):
    """cli_show should display issue details."""
    from trc_main import cli_init, cli_create, cli_show

    monkeypatch.chdir(sample_project["path"])
    cli_init()

    cli_create("Test issue")
    captured = capsys.readouterr()
    issue_id = extract_issue_id(captured.out)

    result = cli_show(issue_id)

    assert result == 0

    captured = capsys.readouterr()
    assert issue_id in captured.out
    assert "Test issue" in captured.out
    assert "Status:" in captured.out
    assert "Priority:" in captured.out


def test_cli_show_nonexistent_issue(sample_project, tmp_trace_dir, monkeypatch, capsys):
    """cli_show should error on nonexistent issue."""
    from trc_main import cli_init, cli_show

    monkeypatch.chdir(sample_project["path"])
    cli_init()

    result = cli_show("nonexistent-123")

    assert result == 1

    captured = capsys.readouterr()
    assert "not found" in captured.out.lower()


def test_cli_close_closes_issue(sample_project, tmp_trace_dir, monkeypatch, capsys):
    """cli_close should close an issue."""
    from trc_main import cli_init, cli_create, cli_close, get_db, get_issue

    monkeypatch.chdir(sample_project["path"])
    cli_init()

    cli_create("Test issue")
    captured = capsys.readouterr()
    issue_id = extract_issue_id(captured.out)

    result = cli_close(issue_id)

    assert result == 0

    # Verify closed
    db = get_db()
    issue = get_issue(db, issue_id)
    assert issue["status"] == "closed"
    assert issue["closed_at"] is not None
    db.close()


def test_cli_update_changes_fields(sample_project, tmp_trace_dir, monkeypatch, capsys):
    """cli_update should modify issue fields."""
    from trc_main import cli_init, cli_create, cli_update, get_db, get_issue

    monkeypatch.chdir(sample_project["path"])
    cli_init()

    cli_create("Test issue")
    captured = capsys.readouterr()
    issue_id = extract_issue_id(captured.out)

    result = cli_update(issue_id, title="Updated title", priority=0, status="in_progress")

    assert result == 0

    # Verify updates
    db = get_db()
    issue = get_issue(db, issue_id)
    assert issue["title"] == "Updated title"
    assert issue["priority"] == 0
    assert issue["status"] == "in_progress"
    db.close()


def test_cli_reparent_changes_parent(sample_project, tmp_trace_dir, monkeypatch, capsys):
    """cli_reparent should change parent."""
    from trc_main import cli_init, cli_create, cli_reparent, get_db, get_dependencies

    monkeypatch.chdir(sample_project["path"])
    cli_init()

    cli_create("Parent 1")
    captured = capsys.readouterr()
    parent1_id = extract_issue_id(captured.out)

    cli_create("Parent 2")
    captured = capsys.readouterr()
    parent2_id = extract_issue_id(captured.out)

    cli_create("Child")
    captured = capsys.readouterr()
    child_id = extract_issue_id(captured.out)

    # Set initial parent
    cli_reparent(child_id, parent1_id)
    capsys.readouterr()  # Clear

    # Reparent to parent2
    result = cli_reparent(child_id, parent2_id)

    assert result == 0

    # Verify new parent
    db = get_db()
    deps = get_dependencies(db, child_id)
    parent_deps = [d for d in deps if d["type"] == "parent"]

    assert len(parent_deps) == 1
    assert parent_deps[0]["depends_on_id"] == parent2_id
    db.close()


def test_cli_reparent_detects_cycle(sample_project, tmp_trace_dir, monkeypatch, capsys):
    """cli_reparent should prevent cycles."""
    from trc_main import cli_init, cli_create, cli_reparent

    monkeypatch.chdir(sample_project["path"])
    cli_init()

    cli_create("Parent")
    captured = capsys.readouterr()
    parent_id = extract_issue_id(captured.out)

    cli_create("Child")
    captured = capsys.readouterr()
    child_id = extract_issue_id(captured.out)

    # Set parent
    cli_reparent(child_id, parent_id)
    capsys.readouterr()  # Clear

    # Try to create cycle (parent -> child)
    result = cli_reparent(parent_id, child_id)

    assert result == 1  # Error

    captured = capsys.readouterr()
    assert "cycle" in captured.out.lower()


def test_cli_reparent_remove_parent(sample_project, tmp_trace_dir, monkeypatch, capsys):
    """cli_reparent with None should remove parent."""
    from trc_main import cli_init, cli_create, cli_reparent, get_db, get_dependencies

    monkeypatch.chdir(sample_project["path"])
    cli_init()

    cli_create("Parent")
    captured = capsys.readouterr()
    parent_id = extract_issue_id(captured.out)

    cli_create("Child")
    captured = capsys.readouterr()
    child_id = extract_issue_id(captured.out)

    # Set parent
    cli_reparent(child_id, parent_id)
    capsys.readouterr()

    # Remove parent
    result = cli_reparent(child_id, None)

    assert result == 0

    # Verify no parent
    db = get_db()
    deps = get_dependencies(db, child_id)
    parent_deps = [d for d in deps if d["type"] == "parent"]
    assert len(parent_deps) == 0
    db.close()


def test_cli_move_changes_project(sample_project, tmp_trace_dir, tmp_path, monkeypatch, capsys):
    """cli_move should move issue to different project."""
    from trc_main import cli_init, cli_create, cli_move, get_db, get_issue

    # Create two projects
    proj1 = sample_project
    proj2_path = tmp_path / "proj2"
    proj2_path.mkdir()
    subprocess.run(["git", "init"], cwd=proj2_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/test/proj2.git"],
        cwd=proj2_path,
        check=True,
        capture_output=True,
    )

    # Init both projects
    monkeypatch.chdir(proj1["path"])
    cli_init()

    monkeypatch.chdir(proj2_path)
    cli_init()

    # Create issue in proj1
    monkeypatch.chdir(proj1["path"])
    cli_create("Test issue")
    captured = capsys.readouterr()
    old_id = extract_issue_id(captured.out)

    # Move to proj2
    result = cli_move(old_id, "proj2")

    assert result == 0

    captured = capsys.readouterr()
    assert "Moved" in captured.out
    assert old_id in captured.out
    assert "proj2-" in captured.out

    # Extract new ID from output like "Moved myapp-abc123 → proj2-xyz789"
    new_id_match = re.search(r"→\s+([\w-]+-[a-z0-9]{6})", captured.out)
    new_id = new_id_match.group(1) if new_id_match else None
    assert new_id is not None

    # Verify moved
    db = get_db()
    old_issue = get_issue(db, old_id)
    assert old_issue is None  # Old issue deleted

    new_issue = get_issue(db, new_id)
    assert new_issue is not None
    assert new_issue["title"] == "Test issue"
    # Project ID should be proj2 (may be resolved differently)
    assert "proj2" in new_issue["project_id"] or new_issue["id"].startswith("proj2-")
    db.close()


def test_cli_ready_shows_unblocked_work(sample_project, tmp_trace_dir, monkeypatch, capsys):
    """cli_ready should show only unblocked issues."""
    from trc_main import cli_init, cli_create, cli_ready, get_db, add_dependency

    monkeypatch.chdir(sample_project["path"])
    cli_init()

    cli_create("Ready issue")
    capsys.readouterr()

    cli_create("Blocker")
    captured = capsys.readouterr()
    blocker_id = extract_issue_id(captured.out)

    cli_create("Blocked issue")
    captured = capsys.readouterr()
    blocked_id = extract_issue_id(captured.out)

    # Add blocking dependency
    db = get_db()
    add_dependency(db, blocked_id, blocker_id, "blocks")
    db.commit()

    # Export to JSONL so cli_ready can see the dependencies
    from trc_main import export_to_jsonl
    from pathlib import Path
    trace_dir = Path(sample_project["path"]) / ".trace"
    export_to_jsonl(db, sample_project["path"], str(trace_dir / "issues.jsonl"))
    db.close()

    # Check ready work
    result = cli_ready()

    assert result == 0

    captured = capsys.readouterr()
    assert "Ready issue" in captured.out
    assert "Blocker" in captured.out
    assert "Blocked issue" not in captured.out


def test_cli_tree_shows_hierarchy(sample_project, tmp_trace_dir, monkeypatch, capsys):
    """cli_tree should display parent-child hierarchy."""
    from trc_main import cli_init, cli_create, cli_tree

    monkeypatch.chdir(sample_project["path"])
    cli_init()

    cli_create("Parent")
    captured = capsys.readouterr()
    parent_id = extract_issue_id(captured.out)

    cli_create("Child 1", parent=parent_id)
    cli_create("Child 2", parent=parent_id)
    capsys.readouterr()

    result = cli_tree(parent_id)

    assert result == 0

    captured = capsys.readouterr()
    assert "Parent" in captured.out
    assert "Child 1" in captured.out
    assert "Child 2" in captured.out
    # Check for tree structure characters
    assert any(char in captured.out for char in ["├", "└", "─"])


def test_cli_list_all_projects(sample_project, tmp_trace_dir, tmp_path, monkeypatch, capsys):
    """cli_list --all should show issues from all projects."""
    from trc_main import cli_init, cli_create, cli_list

    # Create second project
    proj2_path = tmp_path / "proj2"
    proj2_path.mkdir()
    subprocess.run(["git", "init"], cwd=proj2_path, check=True, capture_output=True)

    # Init and create issue in proj1
    monkeypatch.chdir(sample_project["path"])
    cli_init()
    cli_create("Proj1 issue")

    # Init and create issue in proj2
    monkeypatch.chdir(proj2_path)
    cli_init()
    cli_create("Proj2 issue")

    capsys.readouterr()  # Clear

    # List all
    result = cli_list(all_projects=True)

    assert result == 0

    captured = capsys.readouterr()
    assert "Proj1 issue" in captured.out
    assert "Proj2 issue" in captured.out


def test_cli_create_with_description_flag(sample_project, tmp_trace_dir, monkeypatch, capsys):
    """cli_create should accept --description flag."""
    from trc_main import cli_init, cli_create, get_db, get_issue

    monkeypatch.chdir(sample_project["path"])
    cli_init()

    result = cli_create("Test issue", description="This is a detailed description")

    assert result == 0

    captured = capsys.readouterr()
    issue_id = extract_issue_id(captured.out)

    # Verify issue was created with description
    db = get_db()
    issue = get_issue(db, issue_id)
    assert issue["description"] == "This is a detailed description"
    db.close()


def test_cli_create_with_priority_flag(sample_project, tmp_trace_dir, monkeypatch, capsys):
    """cli_create should accept --priority flag."""
    from trc_main import cli_init, cli_create, get_db, get_issue

    monkeypatch.chdir(sample_project["path"])
    cli_init()

    result = cli_create("High priority issue", priority=0)

    assert result == 0

    captured = capsys.readouterr()
    issue_id = extract_issue_id(captured.out)

    # Verify issue was created with correct priority
    db = get_db()
    issue = get_issue(db, issue_id)
    assert issue["priority"] == 0
    db.close()


def test_cli_create_with_status_flag(sample_project, tmp_trace_dir, monkeypatch, capsys):
    """cli_create should accept --status flag."""
    from trc_main import cli_init, cli_create, get_db, get_issue

    monkeypatch.chdir(sample_project["path"])
    cli_init()

    result = cli_create("In progress issue", status="in_progress")

    assert result == 0

    captured = capsys.readouterr()
    issue_id = extract_issue_id(captured.out)

    # Verify issue was created with correct status
    db = get_db()
    issue = get_issue(db, issue_id)
    assert issue["status"] == "in_progress"
    db.close()


def test_cli_create_with_depends_on_flag(sample_project, tmp_trace_dir, monkeypatch, capsys):
    """cli_create should accept --depends-on flag."""
    from trc_main import cli_init, cli_create, get_db, get_dependencies

    monkeypatch.chdir(sample_project["path"])
    cli_init()

    # Create blocker issue first
    capsys.readouterr()
    cli_create("Blocker issue")
    captured = capsys.readouterr()
    blocker_id = extract_issue_id(captured.out)

    # Create issue that depends on blocker
    result = cli_create("Dependent issue", depends_on=blocker_id)

    assert result == 0

    captured = capsys.readouterr()
    dependent_id = extract_issue_id(captured.out)
    assert f"Depends-on: {blocker_id}" in captured.out

    # Verify dependency was created
    db = get_db()
    deps = get_dependencies(db, dependent_id)
    assert len(deps) == 1
    assert deps[0]["depends_on_id"] == blocker_id
    assert deps[0]["type"] == "blocks"
    db.close()


def test_cli_create_with_all_flags(sample_project, tmp_trace_dir, monkeypatch, capsys):
    """cli_create should accept all flags together."""
    from trc_main import cli_init, cli_create, get_db, get_issue, get_dependencies

    monkeypatch.chdir(sample_project["path"])
    cli_init()

    # Create parent and blocker first
    capsys.readouterr()
    cli_create("Parent issue")
    captured = capsys.readouterr()
    parent_id = extract_issue_id(captured.out)

    capsys.readouterr()
    cli_create("Blocker issue")
    captured = capsys.readouterr()
    blocker_id = extract_issue_id(captured.out)

    # Create issue with all flags
    result = cli_create(
        "Complex issue",
        description="Detailed description",
        priority=1,
        status="in_progress",
        parent=parent_id,
        depends_on=blocker_id
    )

    assert result == 0

    captured = capsys.readouterr()
    issue_id = extract_issue_id(captured.out)
    assert f"Parent: {parent_id}" in captured.out
    assert f"Depends-on: {blocker_id}" in captured.out

    # Verify all properties
    db = get_db()
    issue = get_issue(db, issue_id)
    assert issue["title"] == "Complex issue"
    assert issue["description"] == "Detailed description"
    assert issue["priority"] == 1
    assert issue["status"] == "in_progress"

    deps = get_dependencies(db, issue_id)
    assert len(deps) == 2
    dep_types = {d["type"]: d["depends_on_id"] for d in deps}
    assert dep_types["parent"] == parent_id
    assert dep_types["blocks"] == blocker_id
    db.close()
