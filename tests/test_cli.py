"""Tests for CLI commands."""

import re
import subprocess
from typer.testing import CliRunner
from trc_main import app


def extract_issue_id(output: str) -> str:
    """Extract issue ID from CLI output."""
    match = re.search(r"([\w-]+)-([a-z0-9]{6})", output)
    if match:
        return match.group(0)
    raise ValueError(f"Could not extract issue ID from: {output}")


def test_cli_init_creates_trace_directory(sample_project, tmp_trace_dir, monkeypatch):
    """init command should create .trace directory."""
    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0
    assert (sample_project["trace_dir"]).exists()
    assert (sample_project["trace_dir"] / "issues.jsonl").exists()


def test_cli_init_outside_git_repo(tmp_path, tmp_trace_dir, monkeypatch):
    """init command should fail outside git repo."""
    runner = CliRunner()
    non_git_dir = tmp_path / "not-a-repo"
    non_git_dir.mkdir()
    monkeypatch.chdir(non_git_dir)

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 1  # Error code


def test_cli_init_generates_uuid(sample_project, tmp_trace_dir, monkeypatch):
    """init command should generate and store UUID in .trace/id file."""
    import uuid as uuid_module
    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0

    # Check .trace/id file exists and contains valid UUID
    id_file = sample_project["trace_dir"] / "id"
    assert id_file.exists()
    uuid_content = id_file.read_text().strip()
    # Should be valid UUID
    parsed = uuid_module.UUID(uuid_content)
    assert parsed.version == 4


def test_cli_init_stores_uuid_in_database(sample_project, tmp_trace_dir, monkeypatch):
    """init command should store UUID in projects table."""
    from trc_main import get_db
    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0

    # Read UUID from file
    id_file = sample_project["trace_dir"] / "id"
    stored_uuid = id_file.read_text().strip()

    # Check database has the UUID
    db = get_db()
    cursor = db.execute("SELECT uuid FROM projects WHERE name = ?", ("myapp",))
    row = cursor.fetchone()
    db.close()

    assert row is not None
    assert row[0] == stored_uuid


def test_cli_init_preserves_existing_uuid(sample_project, tmp_trace_dir, monkeypatch):
    """init command should preserve existing UUID if .trace/id already exists."""
    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    # Pre-create UUID file
    id_file = sample_project["trace_dir"] / "id"
    existing_uuid = "550e8400-e29b-41d4-a716-446655440000"
    id_file.write_text(existing_uuid + "\n")

    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0

    # UUID should be preserved
    assert id_file.read_text().strip() == existing_uuid


def test_cli_init_displays_uuid(sample_project, tmp_trace_dir, monkeypatch):
    """init command should display UUID in output."""
    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0
    # Output should mention UUID
    assert "UUID:" in result.output


def test_cli_create_basic_issue(sample_project, tmp_trace_dir, monkeypatch):
    """cli_create should create issue with title."""
    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0

    result = runner.invoke(app, ["create", "Test issue", "--description", ""])

    assert result.exit_code == 0
    assert "Created" in result.output
    assert "Test issue" in result.output


def test_cli_create_stores_uuid_as_project_id(sample_project, tmp_trace_dir, monkeypatch):
    """cli_create should store UUID as project_id in database."""
    import uuid as uuid_module
    from trc_main import get_db
    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0

    # Read UUID from .trace/id
    id_file = sample_project["trace_dir"] / "id"
    stored_uuid = id_file.read_text().strip()
    # Verify it's a valid UUID
    uuid_module.UUID(stored_uuid)

    result = runner.invoke(app, ["create", "Test issue", "--description", ""])
    assert result.exit_code == 0

    # Extract issue ID
    issue_id = extract_issue_id(result.output)

    # Check database - project_id should be the UUID
    db = get_db()
    cursor = db.execute("SELECT project_id FROM issues WHERE id = ?", (issue_id,))
    row = cursor.fetchone()
    db.close()

    assert row is not None
    assert row[0] == stored_uuid


def test_cli_create_with_parent(sample_project, tmp_trace_dir, monkeypatch):
    """cli_create should link to parent."""
    from trc_main import get_db, get_dependencies

    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    # Create parent
    result = runner.invoke(app, ["create", "Parent", "--description", ""])
    parent_id = extract_issue_id(result.output)

    # Create child with parent
    result = runner.invoke(app, ["create", "Child", "--description", "", "--parent", parent_id])

    assert result.exit_code == 0

    # Verify parent link
    db = get_db()
    child_id = extract_issue_id(result.output)

    deps = get_dependencies(db, child_id)
    parent_deps = [d for d in deps if d["type"] == "parent"]

    assert len(parent_deps) == 1
    assert parent_deps[0]["depends_on_id"] == parent_id

    db.close()


def test_cli_list_shows_issues(sample_project, tmp_trace_dir, monkeypatch):
    """cli_list should display issues."""
    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    runner.invoke(app, ["create", "Issue 1", "--description", ""])
    runner.invoke(app, ["create", "Issue 2", "--description", ""])

    result = runner.invoke(app, ["list"])

    assert result.exit_code == 0
    assert "Issue 1" in result.output
    assert "Issue 2" in result.output


def test_cli_list_empty_project(sample_project, tmp_trace_dir, monkeypatch):
    """cli_list should handle empty project."""
    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    result = runner.invoke(app, ["list"])

    assert result.exit_code == 0
    assert "No issues found" in result.output


def test_cli_show_displays_issue_details(sample_project, tmp_trace_dir, monkeypatch):
    """cli_show should display issue details."""
    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    result = runner.invoke(app, ["create", "Test issue", "--description", ""])
    issue_id = extract_issue_id(result.output)

    result = runner.invoke(app, ["show", issue_id])

    assert result.exit_code == 0
    assert issue_id in result.output
    assert "Test issue" in result.output
    assert "Status:" in result.output
    assert "Priority:" in result.output


def test_cli_show_displays_project_name_and_uuid(sample_project, tmp_trace_dir, monkeypatch):
    """cli_show should display project name and UUID."""
    import uuid as uuid_module
    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    # Get UUID from .trace/id
    id_file = sample_project["trace_dir"] / "id"
    project_uuid = id_file.read_text().strip()

    result = runner.invoke(app, ["create", "Test issue", "--description", ""])
    issue_id = extract_issue_id(result.output)

    result = runner.invoke(app, ["show", issue_id])

    assert result.exit_code == 0
    # Should show project name and UUID
    assert "myapp" in result.output
    assert project_uuid in result.output
    # Should NOT show absolute path
    assert sample_project["path"] not in result.output


def test_cli_show_nonexistent_issue(sample_project, tmp_trace_dir, monkeypatch):
    """cli_show should error on nonexistent issue."""
    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    result = runner.invoke(app, ["show", "nonexistent-123"])

    assert result.exit_code == 1
    assert "not found" in result.output.lower()


def test_cli_close_closes_issue(sample_project, tmp_trace_dir, monkeypatch):
    """cli_close should close an issue."""
    from trc_main import get_db, get_issue

    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    result = runner.invoke(app, ["create", "Test issue", "--description", ""])
    issue_id = extract_issue_id(result.output)

    result = runner.invoke(app, ["close", issue_id])

    assert result.exit_code == 0

    # Verify closed
    db = get_db()
    issue = get_issue(db, issue_id)
    assert issue is not None
    assert issue["status"] == "closed"
    assert issue["closed_at"] is not None
    db.close()


def test_cli_close_batch_closes_multiple_issues(sample_project, tmp_trace_dir, monkeypatch):
    """cli_close should close multiple issues when given multiple IDs."""
    from trc_main import get_db, get_issue

    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    # Create three issues
    result1 = runner.invoke(app, ["create", "Issue 1", "--description", ""])
    issue_id1 = extract_issue_id(result1.output)

    result2 = runner.invoke(app, ["create", "Issue 2", "--description", ""])
    issue_id2 = extract_issue_id(result2.output)

    result3 = runner.invoke(app, ["create", "Issue 3", "--description", ""])
    issue_id3 = extract_issue_id(result3.output)

    # Close all three at once
    result = runner.invoke(app, ["close", issue_id1, issue_id2, issue_id3])

    assert result.exit_code == 0
    # Verify all three IDs are mentioned in output
    assert issue_id1 in result.output
    assert issue_id2 in result.output
    assert issue_id3 in result.output

    # Verify all are closed
    db = get_db()
    issue1 = get_issue(db, issue_id1)
    issue2 = get_issue(db, issue_id2)
    issue3 = get_issue(db, issue_id3)

    assert issue1 is not None
    assert issue2 is not None
    assert issue3 is not None
    assert issue1["status"] == "closed"
    assert issue1["closed_at"] is not None
    assert issue2["status"] == "closed"
    assert issue2["closed_at"] is not None
    assert issue3["status"] == "closed"
    assert issue3["closed_at"] is not None
    db.close()


def test_cli_close_batch_with_nonexistent_id_continues(sample_project, tmp_trace_dir, monkeypatch):
    """cli_close should warn about nonexistent IDs but close valid ones."""
    from trc_main import get_db, get_issue

    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    # Create two valid issues
    result1 = runner.invoke(app, ["create", "Issue 1", "--description", ""])
    issue_id1 = extract_issue_id(result1.output)

    result2 = runner.invoke(app, ["create", "Issue 2", "--description", ""])
    issue_id2 = extract_issue_id(result2.output)

    # Close with one nonexistent ID in the middle
    result = runner.invoke(app, ["close", issue_id1, "nonexistent-123", issue_id2])

    # Should succeed but warn
    assert result.exit_code == 0
    assert "nonexistent-123" in result.output
    assert "not found" in result.output.lower() or "warning" in result.output.lower()

    # Verify valid issues are still closed
    db = get_db()
    issue1 = get_issue(db, issue_id1)
    issue2 = get_issue(db, issue_id2)

    assert issue1 is not None
    assert issue2 is not None
    assert issue1["status"] == "closed"
    assert issue2["status"] == "closed"
    db.close()


def test_cli_close_batch_exports_to_jsonl(sample_project, tmp_trace_dir, monkeypatch):
    """cli_close batch should export all closed issues to JSONL."""
    import json

    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    # Create two issues
    result1 = runner.invoke(app, ["create", "Issue 1", "--description", ""])
    issue_id1 = extract_issue_id(result1.output)

    result2 = runner.invoke(app, ["create", "Issue 2", "--description", ""])
    issue_id2 = extract_issue_id(result2.output)

    # Close both
    runner.invoke(app, ["close", issue_id1, issue_id2])

    # Check JSONL file
    jsonl_path = sample_project["trace_dir"] / "issues.jsonl"
    assert jsonl_path.exists()

    # Parse JSONL and verify both are closed
    closed_issues = []
    with jsonl_path.open("r") as f:
        for line in f:
            issue_data = json.loads(line)
            if issue_data["id"] in [issue_id1, issue_id2]:
                closed_issues.append(issue_data)

    assert len(closed_issues) == 2
    for issue_data in closed_issues:
        assert issue_data["status"] == "closed"
        assert issue_data["closed_at"] is not None


def test_cli_close_batch_with_already_closed_issue(sample_project, tmp_trace_dir, monkeypatch):
    """cli_close batch should handle already closed issues gracefully."""
    from trc_main import get_db, get_issue

    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    # Create two issues
    result1 = runner.invoke(app, ["create", "Issue 1", "--description", ""])
    issue_id1 = extract_issue_id(result1.output)

    result2 = runner.invoke(app, ["create", "Issue 2", "--description", ""])
    issue_id2 = extract_issue_id(result2.output)

    # Close first issue
    runner.invoke(app, ["close", issue_id1])

    # Try to close both (one already closed)
    result = runner.invoke(app, ["close", issue_id1, issue_id2])

    # Should succeed
    assert result.exit_code == 0

    # Verify both are closed
    db = get_db()
    issue1 = get_issue(db, issue_id1)
    issue2 = get_issue(db, issue_id2)

    assert issue1 is not None
    assert issue2 is not None
    assert issue1["status"] == "closed"
    assert issue2["status"] == "closed"
    db.close()


def test_cli_update_changes_fields(sample_project, tmp_trace_dir, monkeypatch):
    """cli_update should modify issue fields."""
    from trc_main import get_db, get_issue

    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    result = runner.invoke(app, ["create", "Test issue", "--description", ""])
    issue_id = extract_issue_id(result.output)

    result = runner.invoke(app, ["update", issue_id, "--title", "Updated title", "--priority", "0", "--status", "in_progress"])

    assert result.exit_code == 0

    # Verify updates
    db = get_db()
    issue = get_issue(db, issue_id)
    assert issue is not None
    assert issue["title"] == "Updated title"
    assert issue["priority"] == 0
    assert issue["status"] == "in_progress"
    db.close()


def test_cli_update_description(sample_project, tmp_trace_dir, monkeypatch):
    """cli_update should modify issue description."""
    from trc_main import get_db, get_issue

    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    result = runner.invoke(app, ["create", "Test issue", "--description", "Original description"])
    issue_id = extract_issue_id(result.output)

    result = runner.invoke(app, ["update", issue_id, "--description", "Updated description"])

    assert result.exit_code == 0

    # Verify description was updated
    db = get_db()
    issue = get_issue(db, issue_id)
    assert issue is not None
    assert issue["description"] == "Updated description"
    db.close()


def test_cli_reparent_changes_parent(sample_project, tmp_trace_dir, monkeypatch):
    """cli_reparent should change parent."""
    from trc_main import get_db, get_dependencies

    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    result = runner.invoke(app, ["create", "Parent 1", "--description", ""])
    parent1_id = extract_issue_id(result.output)

    result = runner.invoke(app, ["create", "Parent 2", "--description", ""])
    parent2_id = extract_issue_id(result.output)

    result = runner.invoke(app, ["create", "Child", "--description", ""])
    child_id = extract_issue_id(result.output)

    # Set initial parent
    runner.invoke(app, ["reparent", child_id, parent1_id])

    # Reparent to parent2
    result = runner.invoke(app, ["reparent", child_id, parent2_id])

    assert result.exit_code == 0

    # Verify new parent
    db = get_db()
    deps = get_dependencies(db, child_id)
    parent_deps = [d for d in deps if d["type"] == "parent"]

    assert len(parent_deps) == 1
    assert parent_deps[0]["depends_on_id"] == parent2_id
    db.close()


def test_cli_reparent_detects_cycle(sample_project, tmp_trace_dir, monkeypatch):
    """cli_reparent should prevent cycles."""
    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    result = runner.invoke(app, ["create", "Parent", "--description", ""])
    parent_id = extract_issue_id(result.output)

    result = runner.invoke(app, ["create", "Child", "--description", ""])
    child_id = extract_issue_id(result.output)

    # Set parent
    runner.invoke(app, ["reparent", child_id, parent_id])

    # Try to create cycle (parent -> child)
    result = runner.invoke(app, ["reparent", parent_id, child_id])

    assert result.exit_code == 1  # Error
    assert "cycle" in result.output.lower()


def test_cli_reparent_remove_parent(sample_project, tmp_trace_dir, monkeypatch):
    """cli_reparent with None should remove parent."""
    from trc_main import get_db, get_dependencies

    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    result = runner.invoke(app, ["create", "Parent", "--description", ""])
    parent_id = extract_issue_id(result.output)

    result = runner.invoke(app, ["create", "Child", "--description", ""])
    child_id = extract_issue_id(result.output)

    # Set parent
    runner.invoke(app, ["reparent", child_id, parent_id])

    # Remove parent
    result = runner.invoke(app, ["reparent", child_id, "none"])

    assert result.exit_code == 0

    # Verify no parent
    db = get_db()
    deps = get_dependencies(db, child_id)
    parent_deps = [d for d in deps if d["type"] == "parent"]
    assert len(parent_deps) == 0
    db.close()


def test_cli_move_changes_project(sample_project, tmp_trace_dir, tmp_path, monkeypatch):
    """cli_move should move issue to different project."""
    from trc_main import get_db, get_issue

    runner = CliRunner()

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
    runner.invoke(app, ["init"])

    monkeypatch.chdir(proj2_path)
    runner.invoke(app, ["init"])

    # Create issue in proj1
    monkeypatch.chdir(proj1["path"])
    result = runner.invoke(app, ["create", "Test issue", "--description", ""])
    old_id = extract_issue_id(result.output)

    # Move to proj2
    result = runner.invoke(app, ["move", old_id, "proj2"])

    assert result.exit_code == 0
    assert "Moved" in result.output
    assert old_id in result.output
    assert "proj2-" in result.output

    # Extract new ID from output like "Moved myapp-abc123 → proj2-xyz789"
    new_id_match = re.search(r"→\s+([\w-]+-[a-z0-9]{6})", result.output)
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


def test_cli_ready_shows_unblocked_work(sample_project, tmp_trace_dir, monkeypatch):
    """cli_ready should show only unblocked issues."""
    from trc_main import get_db, add_dependency, export_to_jsonl
    from pathlib import Path

    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    runner.invoke(app, ["create", "Ready issue", "--description", ""])

    result = runner.invoke(app, ["create", "Blocker", "--description", ""])
    blocker_id = extract_issue_id(result.output)

    result = runner.invoke(app, ["create", "Blocked issue", "--description", ""])
    blocked_id = extract_issue_id(result.output)

    # Add blocking dependency
    db = get_db()
    add_dependency(db, blocked_id, blocker_id, "blocks")
    db.commit()

    # Export to JSONL so cli_ready can see the dependencies
    trace_dir = Path(sample_project["path"]) / ".trace"
    export_to_jsonl(db, sample_project["path"], str(trace_dir / "issues.jsonl"))
    db.close()

    # Check ready work
    result = runner.invoke(app, ["ready"])

    assert result.exit_code == 0
    assert "Ready issue" in result.output
    assert "Blocker" in result.output
    assert "Blocked issue" not in result.output


def test_cli_tree_shows_hierarchy(sample_project, tmp_trace_dir, monkeypatch):
    """cli_tree should display parent-child hierarchy."""
    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    result = runner.invoke(app, ["create", "Parent", "--description", ""])
    parent_id = extract_issue_id(result.output)

    runner.invoke(app, ["create", "Child 1", "--description", "", "--parent", parent_id])
    runner.invoke(app, ["create", "Child 2", "--description", "", "--parent", parent_id])

    result = runner.invoke(app, ["tree", parent_id])

    assert result.exit_code == 0
    assert "Parent" in result.output
    assert "Child 1" in result.output
    assert "Child 2" in result.output
    # Check for tree structure characters
    assert any(char in result.output for char in ["├", "└", "─"])


def test_cli_list_all_projects(sample_project, tmp_trace_dir, tmp_path, monkeypatch):
    """cli_list --project any should show issues from all projects (legacy test)."""
    runner = CliRunner()

    # Create second project
    proj2_path = tmp_path / "proj2"
    proj2_path.mkdir()
    subprocess.run(["git", "init"], cwd=proj2_path, check=True, capture_output=True)

    # Init and create issue in proj1
    monkeypatch.chdir(sample_project["path"])
    runner.invoke(app, ["init"])
    runner.invoke(app, ["create", "Proj1 issue", "--description", ""])

    # Init and create issue in proj2
    monkeypatch.chdir(proj2_path)
    runner.invoke(app, ["init"])
    runner.invoke(app, ["create", "Proj2 issue", "--description", ""])

    # List all with new flag
    result = runner.invoke(app, ["list", "--project", "any"])

    assert result.exit_code == 0
    assert "Proj1 issue" in result.output
    assert "Proj2 issue" in result.output


def test_cli_create_with_description_flag(sample_project, tmp_trace_dir, monkeypatch):
    """cli_create should accept --description flag."""
    from trc_main import get_db, get_issue

    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    result = runner.invoke(app, ["create", "Test issue", "--description", "This is a detailed description"])

    assert result.exit_code == 0

    issue_id = extract_issue_id(result.output)

    # Verify issue was created with description
    db = get_db()
    issue = get_issue(db, issue_id)
    assert issue is not None
    assert issue["description"] == "This is a detailed description"
    db.close()


def test_cli_create_with_priority_flag(sample_project, tmp_trace_dir, monkeypatch):
    """cli_create should accept --priority flag."""
    from trc_main import get_db, get_issue

    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    result = runner.invoke(app, ["create", "High priority issue", "--description", "", "--priority", "0"])

    assert result.exit_code == 0

    issue_id = extract_issue_id(result.output)

    # Verify issue was created with correct priority
    db = get_db()
    issue = get_issue(db, issue_id)
    assert issue is not None
    assert issue["priority"] == 0
    db.close()


def test_cli_create_with_status_flag(sample_project, tmp_trace_dir, monkeypatch):
    """cli_create should accept --status flag."""
    from trc_main import get_db, get_issue

    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    result = runner.invoke(app, ["create", "In progress issue", "--description", "", "--status", "in_progress"])

    assert result.exit_code == 0

    issue_id = extract_issue_id(result.output)

    # Verify issue was created with correct status
    db = get_db()
    issue = get_issue(db, issue_id)
    assert issue is not None
    assert issue["status"] == "in_progress"
    db.close()


def test_cli_create_with_depends_on_flag(sample_project, tmp_trace_dir, monkeypatch):
    """cli_create should accept --depends-on flag."""
    from trc_main import get_db, get_dependencies

    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    # Create blocker issue first
    result = runner.invoke(app, ["create", "Blocker issue", "--description", ""])
    blocker_id = extract_issue_id(result.output)

    # Create issue that depends on blocker
    result = runner.invoke(app, ["create", "Dependent issue", "--description", "", "--depends-on", blocker_id])

    assert result.exit_code == 0

    dependent_id = extract_issue_id(result.output)
    assert f"Depends-on: {blocker_id}" in result.output

    # Verify dependency was created
    db = get_db()
    deps = get_dependencies(db, dependent_id)
    assert len(deps) == 1
    assert deps[0]["depends_on_id"] == blocker_id
    assert deps[0]["type"] == "blocks"
    db.close()


def test_cli_create_with_all_flags(sample_project, tmp_trace_dir, monkeypatch):
    """cli_create should accept all flags together."""
    from trc_main import get_db, get_issue, get_dependencies

    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    # Create parent and blocker first
    result = runner.invoke(app, ["create", "Parent issue", "--description", ""])
    parent_id = extract_issue_id(result.output)

    result = runner.invoke(app, ["create", "Blocker issue", "--description", ""])
    blocker_id = extract_issue_id(result.output)

    # Create issue with all flags
    result = runner.invoke(app, [
        "create",
        "Complex issue",
        "--description", "Detailed description",
        "--priority", "1",
        "--status", "in_progress",
        "--parent", parent_id,
        "--depends-on", blocker_id
    ])

    assert result.exit_code == 0

    issue_id = extract_issue_id(result.output)
    assert f"Parent: {parent_id}" in result.output
    assert f"Depends-on: {blocker_id}" in result.output

    # Verify all properties
    db = get_db()
    issue = get_issue(db, issue_id)
    assert issue is not None
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


def test_cli_add_dependency_blocks_type(sample_project, tmp_trace_dir, monkeypatch):
    """cli_add_dependency should add a blocking dependency."""
    from trc_main import get_db, get_dependencies

    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    # Create two issues
    result = runner.invoke(app, ["create", "Blocker issue", "--description", ""])
    blocker_id = extract_issue_id(result.output)

    result = runner.invoke(app, ["create", "Blocked issue", "--description", ""])
    blocked_id = extract_issue_id(result.output)

    # Add blocking dependency
    result = runner.invoke(app, ["add-dependency", blocked_id, blocker_id, "--type", "blocks"])

    assert result.exit_code == 0
    # Check for clearer message format
    assert "is blocked by" in result.output or "blocked by" in result.output.lower()

    # Verify dependency was created
    db = get_db()
    deps = get_dependencies(db, blocked_id)
    assert len(deps) == 1
    assert deps[0]["depends_on_id"] == blocker_id
    assert deps[0]["type"] == "blocks"
    db.close()


def test_cli_add_dependency_parent_type(sample_project, tmp_trace_dir, monkeypatch):
    """cli_add_dependency should add a parent dependency."""
    from trc_main import get_db, get_dependencies

    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    # Create two issues
    result = runner.invoke(app, ["create", "Parent issue", "--description", ""])
    parent_id = extract_issue_id(result.output)

    result = runner.invoke(app, ["create", "Child issue", "--description", ""])
    child_id = extract_issue_id(result.output)

    # Add parent dependency
    result = runner.invoke(app, ["add-dependency", child_id, parent_id, "--type", "parent"])

    assert result.exit_code == 0

    # Verify dependency was created
    db = get_db()
    deps = get_dependencies(db, child_id)
    assert len(deps) == 1
    assert deps[0]["depends_on_id"] == parent_id
    assert deps[0]["type"] == "parent"
    db.close()


def test_cli_add_dependency_related_type(sample_project, tmp_trace_dir, monkeypatch):
    """cli_add_dependency should add a related dependency."""
    from trc_main import get_db, get_dependencies

    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    # Create two issues
    result = runner.invoke(app, ["create", "Issue 1", "--description", ""])
    issue1_id = extract_issue_id(result.output)

    result = runner.invoke(app, ["create", "Issue 2", "--description", ""])
    issue2_id = extract_issue_id(result.output)

    # Add related dependency
    result = runner.invoke(app, ["add-dependency", issue1_id, issue2_id, "--type", "related"])

    assert result.exit_code == 0

    # Verify dependency was created
    db = get_db()
    deps = get_dependencies(db, issue1_id)
    assert len(deps) == 1
    assert deps[0]["depends_on_id"] == issue2_id
    assert deps[0]["type"] == "related"
    db.close()


def test_cli_add_dependency_default_type_is_blocks(sample_project, tmp_trace_dir, monkeypatch):
    """cli_add_dependency should default to blocks type."""
    from trc_main import get_db, get_dependencies

    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    # Create two issues
    result = runner.invoke(app, ["create", "Issue 1", "--description", ""])
    issue1_id = extract_issue_id(result.output)

    result = runner.invoke(app, ["create", "Issue 2", "--description", ""])
    issue2_id = extract_issue_id(result.output)

    # Add dependency without specifying type (should default to blocks)
    result = runner.invoke(app, ["add-dependency", issue1_id, issue2_id])

    assert result.exit_code == 0

    # Verify dependency was created with blocks type
    db = get_db()
    deps = get_dependencies(db, issue1_id)
    assert len(deps) == 1
    assert deps[0]["type"] == "blocks"
    db.close()


def test_cli_add_dependency_nonexistent_issue(sample_project, tmp_trace_dir, monkeypatch):
    """cli_add_dependency should error on nonexistent issue."""
    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    result = runner.invoke(app, ["create", "Valid issue", "--description", ""])
    valid_id = extract_issue_id(result.output)

    # Try to add dependency with nonexistent issue
    result = runner.invoke(app, ["add-dependency", valid_id, "nonexistent-123", "--type", "blocks"])

    assert result.exit_code == 1
    assert "not found" in result.output.lower() or "error" in result.output.lower()


def test_cli_add_dependency_nonexistent_depends_on(sample_project, tmp_trace_dir, monkeypatch):
    """cli_add_dependency should error when depends_on issue doesn't exist."""
    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    # Try to add dependency from nonexistent issue
    result = runner.invoke(app, ["add-dependency", "nonexistent-123", "also-nonexistent-456", "--type", "blocks"])

    assert result.exit_code == 1
    assert "not found" in result.output.lower() or "error" in result.output.lower()


def test_cli_add_dependency_invalid_type(sample_project, tmp_trace_dir, monkeypatch):
    """cli_add_dependency should error on invalid type."""
    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    result = runner.invoke(app, ["create", "Issue 1", "--description", ""])
    issue1_id = extract_issue_id(result.output)

    result = runner.invoke(app, ["create", "Issue 2", "--description", ""])
    issue2_id = extract_issue_id(result.output)

    # Try to add dependency with invalid type
    result = runner.invoke(app, ["add-dependency", issue1_id, issue2_id, "--type", "invalid_type"])

    assert result.exit_code == 1
    assert "invalid" in result.output.lower() or "error" in result.output.lower()


def test_cli_add_dependency_exports_to_jsonl(sample_project, tmp_trace_dir, monkeypatch):
    """cli_add_dependency should export changes to JSONL."""
    import json

    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    result = runner.invoke(app, ["create", "Issue 1", "--description", ""])
    issue1_id = extract_issue_id(result.output)

    result = runner.invoke(app, ["create", "Issue 2", "--description", ""])
    issue2_id = extract_issue_id(result.output)

    # Add dependency
    runner.invoke(app, ["add-dependency", issue1_id, issue2_id, "--type", "blocks"])

    # Check JSONL file
    jsonl_path = sample_project["trace_dir"] / "issues.jsonl"
    assert jsonl_path.exists()

    # Parse JSONL and find the issue
    found_dependency = False
    with jsonl_path.open("r") as f:
        for line in f:
            issue_data = json.loads(line)
            if issue_data["id"] == issue1_id:
                deps = issue_data.get("dependencies", [])
                for dep in deps:
                    if dep["depends_on_id"] == issue2_id and dep["type"] == "blocks":
                        found_dependency = True
                        break

    assert found_dependency, "Dependency not found in JSONL file"


def test_cli_create_without_description_fails(sample_project, tmp_trace_dir, monkeypatch):
    """cli_create should fail when --description is not provided."""
    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    # Try to create issue without description (should fail)
    result = runner.invoke(app, ["create", "Issue without description"])

    assert result.exit_code != 0  # Should fail with any non-zero exit code
    assert "description" in result.output.lower() or "required" in result.output.lower()


def test_cli_create_with_description_succeeds(sample_project, tmp_trace_dir, monkeypatch):
    """cli_create should succeed when --description is provided."""
    from trc_main import get_db, get_issue

    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    # Create issue with description (should succeed)
    result = runner.invoke(app, ["create", "Issue with description", "--description", "This is a valid description"])

    assert result.exit_code == 0
    assert "Created" in result.output
    issue_id = extract_issue_id(result.output)

    # Verify issue was created with description
    db = get_db()
    issue = get_issue(db, issue_id)
    assert issue is not None
    assert issue["description"] == "This is a valid description"
    db.close()


def test_cli_create_with_empty_description_succeeds(sample_project, tmp_trace_dir, monkeypatch):
    """cli_create should succeed when --description is empty string (explicit opt-out)."""
    from trc_main import get_db, get_issue

    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    # Create issue with empty description (should succeed as opt-out)
    result = runner.invoke(app, ["create", "Issue with empty description", "--description", ""])

    assert result.exit_code == 0
    assert "Created" in result.output
    issue_id = extract_issue_id(result.output)

    # Verify issue was created with empty description
    db = get_db()
    issue = get_issue(db, issue_id)
    assert issue is not None
    assert issue["description"] == ""
    db.close()


def test_cli_list_project_any_shows_all_projects(sample_project, tmp_trace_dir, tmp_path, monkeypatch):
    """cli_list --project any should show issues from all projects."""
    runner = CliRunner()

    # Create second project
    proj2_path = tmp_path / "proj2"
    proj2_path.mkdir()
    subprocess.run(["git", "init"], cwd=proj2_path, check=True, capture_output=True)

    # Init and create issue in proj1
    monkeypatch.chdir(sample_project["path"])
    runner.invoke(app, ["init"])
    runner.invoke(app, ["create", "Proj1 issue", "--description", ""])

    # Init and create issue in proj2
    monkeypatch.chdir(proj2_path)
    runner.invoke(app, ["init"])
    runner.invoke(app, ["create", "Proj2 issue", "--description", ""])

    # List with --project any
    result = runner.invoke(app, ["list", "--project", "any"])

    assert result.exit_code == 0
    assert "Proj1 issue" in result.output
    assert "Proj2 issue" in result.output


def test_cli_list_project_any_without_git_repo_succeeds(tmp_path, tmp_trace_dir, monkeypatch):
    """cli_list --project any should work outside git repo."""
    runner = CliRunner()

    # Create a non-git directory
    non_git_dir = tmp_path / "not-a-repo"
    non_git_dir.mkdir()
    monkeypatch.chdir(non_git_dir)

    # List with --project any (should work even outside git repo)
    result = runner.invoke(app, ["list", "--project", "any"])

    assert result.exit_code == 0


def test_cli_ready_project_any_shows_all_projects(sample_project, tmp_trace_dir, tmp_path, monkeypatch):
    """cli_ready --project any should show ready work from all projects."""
    runner = CliRunner()

    # Create second project
    proj2_path = tmp_path / "proj2"
    proj2_path.mkdir()
    subprocess.run(["git", "init"], cwd=proj2_path, check=True, capture_output=True)

    # Init and create issues in proj1
    monkeypatch.chdir(sample_project["path"])
    runner.invoke(app, ["init"])
    runner.invoke(app, ["create", "Proj1 ready issue", "--description", ""])

    # Init and create issues in proj2
    monkeypatch.chdir(proj2_path)
    runner.invoke(app, ["init"])
    runner.invoke(app, ["create", "Proj2 ready issue", "--description", ""])

    # Check ready work with --project any
    result = runner.invoke(app, ["ready", "--project", "any"])

    assert result.exit_code == 0
    assert "Proj1 ready issue" in result.output
    assert "Proj2 ready issue" in result.output


def test_cli_list_status_any_shows_all_statuses(sample_project, tmp_trace_dir, monkeypatch):
    """cli_list --status any should show issues with all statuses."""
    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    # Create issues with different statuses
    runner.invoke(app, ["create", "Open issue", "--description", ""])
    runner.invoke(app, ["create", "In progress issue", "--description", "", "--status", "in_progress"])
    runner.invoke(app, ["create", "Closed issue", "--description", "", "--status", "closed"])

    # List with --status any
    result = runner.invoke(app, ["list", "--status", "any"])

    assert result.exit_code == 0
    assert "Open issue" in result.output
    assert "In progress issue" in result.output
    assert "Closed issue" in result.output


def test_cli_list_status_open_filters_correctly(sample_project, tmp_trace_dir, monkeypatch):
    """cli_list --status open should show only open issues."""
    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    # Create issues with different statuses
    runner.invoke(app, ["create", "Open issue", "--description", ""])
    runner.invoke(app, ["create", "In progress issue", "--description", "", "--status", "in_progress"])
    result = runner.invoke(app, ["create", "To be closed", "--description", ""])
    closed_id = extract_issue_id(result.output)
    runner.invoke(app, ["close", closed_id])

    # List with --status open
    result = runner.invoke(app, ["list", "--status", "open"])

    assert result.exit_code == 0
    assert "Open issue" in result.output
    assert "In progress issue" not in result.output
    assert "To be closed" not in result.output


def test_cli_list_status_closed_filters_correctly(sample_project, tmp_trace_dir, monkeypatch):
    """cli_list --status closed should show only closed issues."""
    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    # Create issues with different statuses
    runner.invoke(app, ["create", "Open issue", "--description", ""])
    result = runner.invoke(app, ["create", "To be closed", "--description", ""])
    closed_id = extract_issue_id(result.output)
    runner.invoke(app, ["close", closed_id])

    # List with --status closed
    result = runner.invoke(app, ["list", "--status", "closed"])

    assert result.exit_code == 0
    assert "To be closed" in result.output
    assert "Open issue" not in result.output


def test_cli_list_status_in_progress_filters_correctly(sample_project, tmp_trace_dir, monkeypatch):
    """cli_list --status in_progress should show only in_progress issues."""
    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    # Create issues with different statuses
    runner.invoke(app, ["create", "Open issue", "--description", ""])
    runner.invoke(app, ["create", "In progress issue", "--description", "", "--status", "in_progress"])

    # List with --status in_progress
    result = runner.invoke(app, ["list", "--status", "in_progress"])

    assert result.exit_code == 0
    assert "In progress issue" in result.output
    assert "Open issue" not in result.output


def test_cli_list_default_excludes_closed(sample_project, tmp_trace_dir, monkeypatch):
    """cli_list without --status should show backlog (exclude closed)."""
    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    # Create issues with different statuses
    runner.invoke(app, ["create", "Open issue", "--description", ""])
    runner.invoke(app, ["create", "In progress issue", "--description", "", "--status", "in_progress"])
    runner.invoke(app, ["create", "Blocked issue", "--description", "", "--status", "blocked"])
    result = runner.invoke(app, ["create", "To be closed", "--description", ""])
    closed_id = extract_issue_id(result.output)
    runner.invoke(app, ["close", closed_id])

    # List without --status flag (should show backlog: open, in_progress, blocked)
    result = runner.invoke(app, ["list"])

    assert result.exit_code == 0
    assert "Open issue" in result.output
    assert "In progress issue" in result.output
    assert "Blocked issue" in result.output
    assert "To be closed" not in result.output  # Closed should be excluded


def test_cli_list_multiple_status_flags(sample_project, tmp_trace_dir, monkeypatch):
    """cli_list with multiple --status flags should show all specified statuses."""
    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    # Create issues with different statuses
    runner.invoke(app, ["create", "Open issue", "--description", ""])
    runner.invoke(app, ["create", "In progress issue", "--description", "", "--status", "in_progress"])
    runner.invoke(app, ["create", "Blocked issue", "--description", "", "--status", "blocked"])
    result = runner.invoke(app, ["create", "To be closed", "--description", ""])
    closed_id = extract_issue_id(result.output)
    runner.invoke(app, ["close", closed_id])

    # List with multiple --status flags (open and closed)
    result = runner.invoke(app, ["list", "--status", "open", "--status", "closed"])

    assert result.exit_code == 0
    assert "Open issue" in result.output
    assert "To be closed" in result.output
    assert "In progress issue" not in result.output  # Should not show in_progress
    assert "Blocked issue" not in result.output  # Should not show blocked


def test_cli_ready_status_any_shows_all_statuses(sample_project, tmp_trace_dir, monkeypatch):
    """cli_ready --status any should show ready issues with all statuses."""
    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    # Create issues with different statuses
    runner.invoke(app, ["create", "Open issue", "--description", ""])
    runner.invoke(app, ["create", "In progress issue", "--description", "", "--status", "in_progress"])

    # Ready with --status any
    result = runner.invoke(app, ["ready", "--status", "any"])

    assert result.exit_code == 0
    assert "Open issue" in result.output
    assert "In progress issue" in result.output


def test_cli_ready_defaults_to_open_status(sample_project, tmp_trace_dir, monkeypatch):
    """cli_ready without --status should default to open issues only."""
    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    # Create issues with different statuses
    runner.invoke(app, ["create", "Open issue", "--description", ""])
    runner.invoke(app, ["create", "In progress issue", "--description", "", "--status", "in_progress"])

    # Ready without --status flag
    result = runner.invoke(app, ["ready"])

    assert result.exit_code == 0
    assert "Open issue" in result.output
    # Should not show in_progress issues by default
    assert "In progress issue" not in result.output


def test_cli_create_with_project_flag(sample_project, tmp_trace_dir, tmp_path, monkeypatch):
    """cli_create --project should create issue in specified project."""
    from trc_main import get_db, get_issue

    runner = CliRunner()

    # Create second project
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
    monkeypatch.chdir(sample_project["path"])
    runner.invoke(app, ["init"])

    monkeypatch.chdir(proj2_path)
    runner.invoke(app, ["init"])

    # Create issue in proj2 from proj1 directory using --project
    monkeypatch.chdir(sample_project["path"])
    result = runner.invoke(app, ["create", "Issue for proj2", "--description", "test", "--project", "proj2"])

    assert result.exit_code == 0
    assert "Created" in result.output
    assert "proj2-" in result.output

    issue_id = extract_issue_id(result.output)

    # Verify issue was created in proj2
    db = get_db()
    issue = get_issue(db, issue_id)
    assert issue is not None
    assert issue["title"] == "Issue for proj2"
    # New behavior: project_id is UUID
    import uuid as uuid_module
    uuid_module.UUID(issue["project_id"])  # Should be valid UUID
    assert issue["id"].startswith("proj2-")
    db.close()


def test_cli_create_with_project_flag_not_found(sample_project, tmp_trace_dir, monkeypatch):
    """cli_create --project should error when project not in registry."""
    runner = CliRunner()

    monkeypatch.chdir(sample_project["path"])
    runner.invoke(app, ["init"])

    # Try to create issue in non-existent project
    result = runner.invoke(app, ["create", "Test issue", "--description", "test", "--project", "nonexistent"])

    assert result.exit_code == 1
    assert "not found" in result.output.lower()
    assert "trc init" in result.output.lower()


def test_cli_create_with_project_flag_outside_git_repo(sample_project, tmp_trace_dir, tmp_path, monkeypatch):
    """cli_create --project should work when not in a git repo."""
    from trc_main import get_db, get_issue

    runner = CliRunner()

    # Init the project first
    monkeypatch.chdir(sample_project["path"])
    runner.invoke(app, ["init"])

    # Switch to non-git directory
    non_git_dir = tmp_path / "not-a-repo"
    non_git_dir.mkdir()
    monkeypatch.chdir(non_git_dir)

    # Create issue using --project flag (should work even outside git repo)
    result = runner.invoke(app, [
        "create",
        "Issue from nowhere",
        "--description", "test",
        "--project", sample_project["name"]
    ])

    assert result.exit_code == 0
    assert "Created" in result.output

    issue_id = extract_issue_id(result.output)

    # Verify issue was created in correct project
    db = get_db()
    issue = get_issue(db, issue_id)
    assert issue is not None
    assert issue["title"] == "Issue from nowhere"
    # New behavior: project_id is UUID
    import uuid as uuid_module
    uuid_module.UUID(issue["project_id"])  # Should be valid UUID
    db.close()


def test_cli_create_with_project_flag_and_parent(sample_project, tmp_trace_dir, tmp_path, monkeypatch):
    """cli_create --project should work with --parent from different project."""
    from trc_main import get_db, get_issue, get_dependencies

    runner = CliRunner()

    # Create second project
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
    monkeypatch.chdir(sample_project["path"])
    runner.invoke(app, ["init"])

    monkeypatch.chdir(proj2_path)
    runner.invoke(app, ["init"])

    # Create parent in proj1
    monkeypatch.chdir(sample_project["path"])
    result = runner.invoke(app, ["create", "Parent in proj1", "--description", ""])
    parent_id = extract_issue_id(result.output)

    # Create child in proj2 with parent from proj1
    result = runner.invoke(app, [
        "create",
        "Child in proj2",
        "--description", "test",
        "--project", "proj2",
        "--parent", parent_id
    ])

    assert result.exit_code == 0
    assert "Created" in result.output
    assert f"Parent: {parent_id}" in result.output

    child_id = extract_issue_id(result.output)

    # Verify cross-project parent link
    db = get_db()
    issue = get_issue(db, child_id)
    assert issue is not None
    # New behavior: project_id is UUID
    import uuid as uuid_module
    uuid_module.UUID(issue["project_id"])  # Should be valid UUID

    deps = get_dependencies(db, child_id)
    parent_deps = [d for d in deps if d["type"] == "parent"]
    assert len(parent_deps) == 1
    assert parent_deps[0]["depends_on_id"] == parent_id
    db.close()


def test_cli_list_project_filters_to_specific_project(sample_project, tmp_trace_dir, tmp_path, monkeypatch):
    """cli_list --project <name> should filter to that specific project."""
    runner = CliRunner()

    # Create second project
    proj2_path = tmp_path / "proj2"
    proj2_path.mkdir()
    subprocess.run(["git", "init"], cwd=proj2_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/test/proj2.git"],
        cwd=proj2_path,
        check=True,
        capture_output=True,
    )

    # Init and create issue in proj1 (myapp)
    monkeypatch.chdir(sample_project["path"])
    runner.invoke(app, ["init"])
    runner.invoke(app, ["create", "Myapp issue", "--description", ""])

    # Init and create issue in proj2
    monkeypatch.chdir(proj2_path)
    runner.invoke(app, ["init"])
    runner.invoke(app, ["create", "Proj2 issue", "--description", ""])

    # From myapp directory, list proj2 issues using --project
    monkeypatch.chdir(sample_project["path"])
    result = runner.invoke(app, ["list", "--project", "proj2"])

    assert result.exit_code == 0
    # Should show proj2 issue
    assert "Proj2 issue" in result.output
    # Should NOT show myapp issue
    assert "Myapp issue" not in result.output


def test_cli_ready_project_filters_to_specific_project(sample_project, tmp_trace_dir, tmp_path, monkeypatch):
    """cli_ready --project <name> should filter to that specific project."""
    runner = CliRunner()

    # Create second project
    proj2_path = tmp_path / "proj2"
    proj2_path.mkdir()
    subprocess.run(["git", "init"], cwd=proj2_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/test/proj2.git"],
        cwd=proj2_path,
        check=True,
        capture_output=True,
    )

    # Init and create issue in proj1 (myapp)
    monkeypatch.chdir(sample_project["path"])
    runner.invoke(app, ["init"])
    runner.invoke(app, ["create", "Myapp ready work", "--description", ""])

    # Init and create issue in proj2
    monkeypatch.chdir(proj2_path)
    runner.invoke(app, ["init"])
    runner.invoke(app, ["create", "Proj2 ready work", "--description", ""])

    # From myapp directory, check ready work for proj2 using --project
    monkeypatch.chdir(sample_project["path"])
    result = runner.invoke(app, ["ready", "--project", "proj2"])

    assert result.exit_code == 0
    # Should show proj2 ready work
    assert "Proj2 ready work" in result.output
    # Should NOT show myapp ready work
    assert "Myapp ready work" not in result.output


def test_cli_show_cross_project_does_not_corrupt_projects_table(sample_project, tmp_trace_dir, tmp_path, monkeypatch):
    """show command on cross-project issue should not corrupt projects table.

    Bug trace-noekf7: When running 'trc show' on an issue from a different project,
    the show command was passing issue["project_id"] (a URL like github.com/user/proj1)
    directly to sync_project() instead of the filesystem path. This caused
    detect_project() to walk up from CWD and find the wrong project's .git,
    triggering auto-merge logic that corrupted the projects table.
    """
    from trc_main import get_db

    runner = CliRunner()

    # Create two separate projects with URL-based project IDs
    proj1_path = tmp_path / "proj1"
    proj1_path.mkdir()
    subprocess.run(["git", "init"], cwd=proj1_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/test/proj1.git"],
        cwd=proj1_path,
        check=True,
        capture_output=True,
    )

    proj2_path = tmp_path / "proj2"
    proj2_path.mkdir()
    subprocess.run(["git", "init"], cwd=proj2_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/test/proj2.git"],
        cwd=proj2_path,
        check=True,
        capture_output=True,
    )

    # Init proj1 and create an issue
    monkeypatch.chdir(proj1_path)
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["create", "Issue in proj1", "--description", "test"])
    assert result.exit_code == 0
    proj1_issue_id = extract_issue_id(result.output)

    # Init proj2
    monkeypatch.chdir(proj2_path)
    runner.invoke(app, ["init"])

    # Record the correct state of projects table before show
    db = get_db()
    cursor = db.execute("SELECT id, current_path FROM projects ORDER BY id")
    projects_before = {row[0]: row[1] for row in cursor.fetchall()}
    db.close()

    # From proj2 directory, run show on proj1's issue
    # BUG: This used to pass issue["project_id"] (github.com/test/proj1) to sync_project
    # which expected a filesystem path, causing corruption
    result = runner.invoke(app, ["show", proj1_issue_id])
    assert result.exit_code == 0
    assert "Issue in proj1" in result.output

    # Verify projects table is NOT corrupted
    db = get_db()
    cursor = db.execute("SELECT id, current_path FROM projects ORDER BY id")
    projects_after = {row[0]: row[1] for row in cursor.fetchall()}
    db.close()

    # The projects table should be unchanged
    # Specifically: current_path should still be filesystem paths, not URLs
    assert projects_before == projects_after, (
        f"Projects table was corrupted!\n"
        f"Before: {projects_before}\n"
        f"After: {projects_after}"
    )

    # Extra check: all current_path values should be filesystem paths (not URLs)
    for project_id, current_path in projects_after.items():
        assert current_path.startswith("/"), (
            f"current_path for {project_id} should be absolute path, got: {current_path}"
        )


def test_cli_update_cross_project_issue_works(sample_project, tmp_trace_dir, tmp_path, monkeypatch):
    """update command should work on issues from other projects.

    Bug trace-y47npx: When a trace is created in project A while working in project B
    (using --project flag), subsequent trc update commands failed with
    'Project not initialized' error.
    """
    runner = CliRunner()

    # Create two separate projects
    proj1_path = tmp_path / "proj1"
    proj1_path.mkdir()
    subprocess.run(["git", "init"], cwd=proj1_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/test/proj1.git"],
        cwd=proj1_path,
        check=True,
        capture_output=True,
    )

    proj2_path = tmp_path / "proj2"
    proj2_path.mkdir()
    subprocess.run(["git", "init"], cwd=proj2_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/test/proj2.git"],
        cwd=proj2_path,
        check=True,
        capture_output=True,
    )

    # Init proj1 and create an issue
    monkeypatch.chdir(proj1_path)
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["create", "Issue in proj1", "--description", "test"])
    assert result.exit_code == 0
    proj1_issue_id = extract_issue_id(result.output)

    # Init proj2
    monkeypatch.chdir(proj2_path)
    runner.invoke(app, ["init"])

    # From proj2 directory, update the proj1 issue
    # BUG: This used to fail with "Project not initialized"
    result = runner.invoke(app, ["update", proj1_issue_id, "--status", "in_progress"])
    assert result.exit_code == 0, f"update failed: {result.output}"
    assert "in_progress" in result.output or "Updated" in result.output


def test_cli_close_cross_project_issue_works(sample_project, tmp_trace_dir, tmp_path, monkeypatch):
    """close command should work on issues from other projects.

    Bug trace-y47npx: When a trace is created in project A while working in project B,
    subsequent trc close commands failed with 'Project not initialized' error.
    """
    runner = CliRunner()

    # Create two separate projects
    proj1_path = tmp_path / "proj1"
    proj1_path.mkdir()
    subprocess.run(["git", "init"], cwd=proj1_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/test/proj1.git"],
        cwd=proj1_path,
        check=True,
        capture_output=True,
    )

    proj2_path = tmp_path / "proj2"
    proj2_path.mkdir()
    subprocess.run(["git", "init"], cwd=proj2_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/test/proj2.git"],
        cwd=proj2_path,
        check=True,
        capture_output=True,
    )

    # Init proj1 and create an issue
    monkeypatch.chdir(proj1_path)
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["create", "Issue in proj1", "--description", "test"])
    assert result.exit_code == 0
    proj1_issue_id = extract_issue_id(result.output)

    # Init proj2
    monkeypatch.chdir(proj2_path)
    runner.invoke(app, ["init"])

    # From proj2 directory, close the proj1 issue
    # BUG: This used to fail with "Project not initialized"
    result = runner.invoke(app, ["close", proj1_issue_id])
    assert result.exit_code == 0, f"close failed: {result.output}"
    assert "Closed" in result.output


def test_cli_update_with_cross_project_related_dependency(sample_project, tmp_trace_dir, tmp_path, monkeypatch):
    """update should work when issue has related dependency to non-initialized project.

    Bug trace-1vp9ml: When a trace has a 'related' dependency to a trace in another
    project that is not initialized locally, trc update fails with
    'Project not initialized' error.

    Related dependencies are informational only and should not require the
    related project to be initialized.
    """
    runner = CliRunner()

    # Create two separate projects
    proj1_path = tmp_path / "proj1"
    proj1_path.mkdir()
    subprocess.run(["git", "init"], cwd=proj1_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/test/proj1.git"],
        cwd=proj1_path,
        check=True,
        capture_output=True,
    )

    proj2_path = tmp_path / "proj2"
    proj2_path.mkdir()
    subprocess.run(["git", "init"], cwd=proj2_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/test/proj2.git"],
        cwd=proj2_path,
        check=True,
        capture_output=True,
    )

    # Init proj1 and create issues
    monkeypatch.chdir(proj1_path)
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["create", "Issue A in proj1", "--description", "test"])
    assert result.exit_code == 0
    issue_a_id = extract_issue_id(result.output)

    # Init proj2 and create an issue
    monkeypatch.chdir(proj2_path)
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["create", "Issue B in proj2", "--description", "test"])
    assert result.exit_code == 0
    issue_b_id = extract_issue_id(result.output)

    # Add a cross-project 'related' dependency from issue_a to issue_b
    monkeypatch.chdir(proj1_path)
    result = runner.invoke(app, ["add-dependency", issue_a_id, issue_b_id, "--type", "related"])
    assert result.exit_code == 0

    # Now simulate proj2 being "not initialized" by removing its .trace directory
    # (This simulates the scenario where the related project was cloned elsewhere
    # or is on a different machine)
    import shutil
    shutil.rmtree(proj2_path / ".trace")

    # From proj1 directory, update issue_a which has a related dependency to proj2
    # BUG: This used to fail with "Project not initialized" for proj2
    # but related dependencies should not require the target project to be initialized
    result = runner.invoke(app, ["update", issue_a_id, "--status", "in_progress"])
    assert result.exit_code == 0, f"update failed: {result.output}"
    assert "in_progress" in result.output or "Updated" in result.output


def test_cli_update_recovers_from_corrupted_project_path(sample_project, tmp_trace_dir, tmp_path, monkeypatch):
    """update should recover when projects table has corrupted current_path.

    Bug trace-scxxay: When projects table has a URL in current_path instead of
    a filesystem path (due to earlier bug trace-noekf7), trc close/update fail
    with 'Project not initialized' even though the project IS initialized.

    The fix should detect this corruption and recover by looking up the correct
    path from the current working directory.
    """
    from trc_main import get_db

    runner = CliRunner()

    # Create and init a project
    proj_path = tmp_path / "myproject"
    proj_path.mkdir()
    subprocess.run(["git", "init"], cwd=proj_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/test/myproject.git"],
        cwd=proj_path,
        check=True,
        capture_output=True,
    )

    monkeypatch.chdir(proj_path)
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["create", "Test issue", "--description", "test"])
    assert result.exit_code == 0
    issue_id = extract_issue_id(result.output)

    # Get the issue's project_id (which is now UUID)
    db = get_db()
    cursor = db.execute("SELECT project_id FROM issues WHERE id = ?", (issue_id,))
    row = cursor.fetchone()
    project_uuid = row[0]

    # Simulate corruption: set current_path to a URL instead of filesystem path
    db.execute(
        "UPDATE projects SET current_path = ? WHERE uuid = ?",
        ("github.com/wrong/project", project_uuid)
    )
    db.commit()
    db.close()

    # Now try to update - this should detect corruption and recover
    # by using the current working directory to find the correct path
    result = runner.invoke(app, ["update", issue_id, "--status", "in_progress"])
    assert result.exit_code == 0, f"update failed with corrupted project path: {result.output}"
    assert "in_progress" in result.output or "Updated" in result.output


def test_cli_close_recovers_from_corrupted_project_path(sample_project, tmp_trace_dir, tmp_path, monkeypatch):
    """close should recover when projects table has corrupted current_path.

    Bug trace-scxxay: Same as update test - close should handle corrupted
    project paths gracefully.
    """
    from trc_main import get_db

    runner = CliRunner()

    # Create and init a project
    proj_path = tmp_path / "myproject"
    proj_path.mkdir()
    subprocess.run(["git", "init"], cwd=proj_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/test/myproject.git"],
        cwd=proj_path,
        check=True,
        capture_output=True,
    )

    monkeypatch.chdir(proj_path)
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["create", "Test issue", "--description", "test"])
    assert result.exit_code == 0
    issue_id = extract_issue_id(result.output)

    # Get the issue's project_id (which is now UUID)
    db = get_db()
    cursor = db.execute("SELECT project_id FROM issues WHERE id = ?", (issue_id,))
    row = cursor.fetchone()
    project_uuid = row[0]

    # Simulate corruption: set current_path to a URL instead of filesystem path
    db.execute(
        "UPDATE projects SET current_path = ? WHERE uuid = ?",
        ("github.com/wrong/project", project_uuid)
    )
    db.commit()
    db.close()

    # Now try to close - this should detect corruption and recover
    result = runner.invoke(app, ["close", issue_id])
    assert result.exit_code == 0, f"close failed with corrupted project path: {result.output}"
    assert "Closed" in result.output


def test_cli_create_with_project_flag_detects_corrupted_path(sample_project, tmp_trace_dir, tmp_path, monkeypatch):
    """create --project should detect corrupted current_path and give helpful error.

    When using --project flag to create an issue in another project,
    if that project's current_path is corrupted (contains URL instead of
    filesystem path), we can't auto-recover (don't know the correct path).
    Instead, we detect the corruption and give a helpful error message
    telling the user to re-run 'trc init' in the target project.
    """
    from trc_main import get_db

    runner = CliRunner()

    # Create and init target project (change-capture)
    target_path = tmp_path / "change-capture"
    target_path.mkdir()
    subprocess.run(["git", "init"], cwd=target_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/test/change-capture.git"],
        cwd=target_path,
        check=True,
        capture_output=True,
    )
    monkeypatch.chdir(target_path)
    runner.invoke(app, ["init"])

    # Create source project (mr-reviewer)
    source_path = tmp_path / "mr-reviewer"
    source_path.mkdir()
    subprocess.run(["git", "init"], cwd=source_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/test/mr-reviewer.git"],
        cwd=source_path,
        check=True,
        capture_output=True,
    )
    monkeypatch.chdir(source_path)
    runner.invoke(app, ["init"])

    # Corrupt the target project's current_path in the database
    db = get_db()
    db.execute(
        "UPDATE projects SET current_path = ? WHERE name = ?",
        ("github.com/corrupted/path", "change-capture")
    )
    db.commit()
    db.close()

    # From mr-reviewer, try to create an issue in change-capture using --project flag
    # Should fail with helpful error (can't auto-recover without knowing correct path)
    result = runner.invoke(app, ["create", "Test from mr-reviewer", "--description", "test", "--project", "change-capture"])
    assert result.exit_code == 1
    assert "not found" in result.output.lower()
    assert "trc init" in result.output.lower()

    # Now re-init the target project to fix corruption
    monkeypatch.chdir(target_path)
    runner.invoke(app, ["init"])

    # Now create should work from mr-reviewer
    monkeypatch.chdir(source_path)
    result = runner.invoke(app, ["create", "Test from mr-reviewer", "--description", "test", "--project", "change-capture"])
    assert result.exit_code == 0, f"create --project failed after re-init: {result.output}"
    assert "Created" in result.output


def test_cli_guide_displays_integration_guide(tmp_trace_dir):
    """guide command should display AI agent integration guide."""
    runner = CliRunner()

    result = runner.invoke(app, ["guide"])

    assert result.exit_code == 0
    assert "Trace (trc) - AI Agent Integration Guide" in result.output
    assert "trc init" in result.output
    assert "trc create" in result.output
    assert "trc ready" in result.output
    assert "trc list" in result.output
    assert "trc close" in result.output
    assert "--description" in result.output


def test_cli_repair_dry_run_no_contamination(sample_project, tmp_trace_dir, monkeypatch):
    """repair command with --dry-run should report no contamination in clean project."""
    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    # Initialize project
    runner.invoke(app, ["init"])

    # Create a normal issue
    runner.invoke(app, ["create", "Test issue", "--description", "test"])

    # Run repair in dry-run mode
    result = runner.invoke(app, ["repair", "--dry-run"])

    assert result.exit_code == 0
    assert "No contamination found" in result.output
    assert "Examined:" in result.output


def test_cli_repair_json_output(sample_project, tmp_trace_dir, monkeypatch):
    """repair command should support --json output."""
    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    # Initialize project
    runner.invoke(app, ["init"])

    # Create a normal issue
    runner.invoke(app, ["create", "Test issue", "--description", "test"])

    # Run repair with JSON output
    result = runner.invoke(app, ["repair", "--json"])

    assert result.exit_code == 0
    # Should be valid JSON
    import json
    output_data = json.loads(result.output)
    assert "examined" in output_data
    assert "contaminated" in output_data
    assert "repaired" in output_data
    assert output_data["examined"] >= 1
    assert output_data["contaminated"] == 0


def test_cli_repair_with_project_flag(sample_project, tmp_trace_dir, tmp_path, monkeypatch):
    """repair command should accept --project flag."""
    runner = CliRunner()

    # Set up first project
    proj1_path = sample_project["path"]
    monkeypatch.chdir(proj1_path)
    runner.invoke(app, ["init"])
    runner.invoke(app, ["create", "Issue in proj1", "--description", "test"])

    # Set up second project
    proj2_path = tmp_path / "proj2"
    proj2_path.mkdir()
    subprocess.run(["git", "init"], cwd=proj2_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/test/proj2.git"],
        cwd=proj2_path,
        check=True,
        capture_output=True,
    )
    monkeypatch.chdir(proj2_path)
    runner.invoke(app, ["init"])
    runner.invoke(app, ["create", "Issue in proj2", "--description", "test"])

    # Run repair from proj1 with --project flag targeting proj2
    monkeypatch.chdir(proj1_path)
    result = runner.invoke(app, ["repair", "--project", "proj2", "--dry-run"])

    assert result.exit_code == 0
    assert "Examined:" in result.output


def test_cli_repair_project_not_found(sample_project, tmp_trace_dir, monkeypatch):
    """repair command should error if --project not found."""
    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    # Try to repair a non-existent project
    result = runner.invoke(app, ["repair", "--project", "nonexistent"])

    assert result.exit_code == 1
    assert "not found" in result.output.lower()


# ============================================
# Close with comment tests
# ============================================


def test_cli_close_with_message_adds_comment(sample_project, tmp_trace_dir, monkeypatch):
    """close --message should add a comment to the issue when closing."""
    from trc_main import get_db, get_issue, get_comments

    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    # Create an issue
    result = runner.invoke(app, ["create", "Test issue", "--description", ""])
    issue_id = extract_issue_id(result.output)

    # Close with a message
    result = runner.invoke(app, ["close", issue_id, "--message", "Fixed the bug"])

    assert result.exit_code == 0

    # Verify issue is closed and has a comment
    db = get_db()
    issue = get_issue(db, issue_id)
    assert issue is not None
    assert issue["status"] == "closed"
    assert issue["closed_at"] is not None

    comments = get_comments(db, issue_id)
    assert len(comments) == 1
    assert comments[0]["content"] == "Fixed the bug"
    assert comments[0]["source"] == "user"  # default source
    db.close()


def test_cli_close_batch_with_message_adds_comment_to_all(
    sample_project, tmp_trace_dir, monkeypatch
):
    """close --message should add same comment to all closed issues in batch."""
    from trc_main import get_db, get_issue, get_comments

    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    # Create three issues
    result1 = runner.invoke(app, ["create", "Issue 1", "--description", ""])
    issue_id1 = extract_issue_id(result1.output)

    result2 = runner.invoke(app, ["create", "Issue 2", "--description", ""])
    issue_id2 = extract_issue_id(result2.output)

    result3 = runner.invoke(app, ["create", "Issue 3", "--description", ""])
    issue_id3 = extract_issue_id(result3.output)

    # Close all three with a message
    result = runner.invoke(
        app, ["close", issue_id1, issue_id2, issue_id3, "--message", "Batch fix applied"]
    )

    assert result.exit_code == 0

    # Verify all are closed with comments
    db = get_db()
    for issue_id in [issue_id1, issue_id2, issue_id3]:
        issue = get_issue(db, issue_id)
        assert issue is not None
        assert issue["status"] == "closed"

        comments = get_comments(db, issue_id)
        assert len(comments) == 1
        assert comments[0]["content"] == "Batch fix applied"
    db.close()


def test_cli_close_with_message_and_custom_source(
    sample_project, tmp_trace_dir, monkeypatch
):
    """close --message --source should use the custom source identifier."""
    from trc_main import get_db, get_comments

    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    # Create an issue
    result = runner.invoke(app, ["create", "Test issue", "--description", ""])
    issue_id = extract_issue_id(result.output)

    # Close with a message and custom source
    result = runner.invoke(
        app,
        ["close", issue_id, "--message", "Completed by executor", "--source", "executor"],
    )

    assert result.exit_code == 0

    # Verify comment has custom source
    db = get_db()
    comments = get_comments(db, issue_id)
    assert len(comments) == 1
    assert comments[0]["content"] == "Completed by executor"
    assert comments[0]["source"] == "executor"
    db.close()


def test_cli_close_with_message_exports_comment_to_jsonl(
    sample_project, tmp_trace_dir, monkeypatch
):
    """close --message should export the comment to JSONL."""
    import json

    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    # Create an issue
    result = runner.invoke(app, ["create", "Test issue", "--description", ""])
    issue_id = extract_issue_id(result.output)

    # Close with a message
    runner.invoke(app, ["close", issue_id, "--message", "All tests passing"])

    # Check JSONL file contains the comment
    jsonl_path = sample_project["trace_dir"] / "issues.jsonl"
    assert jsonl_path.exists()

    with jsonl_path.open("r") as f:
        for line in f:
            issue_data = json.loads(line)
            if issue_data["id"] == issue_id:
                assert "comments" in issue_data
                assert len(issue_data["comments"]) == 1
                assert issue_data["comments"][0]["content"] == "All tests passing"
                assert issue_data["comments"][0]["source"] == "user"
                break
        else:
            pytest.fail(f"Issue {issue_id} not found in JSONL")


def test_cli_close_without_message_still_works(sample_project, tmp_trace_dir, monkeypatch):
    """close without --message should work as before (backwards compatibility)."""
    from trc_main import get_db, get_issue, get_comments

    runner = CliRunner()
    monkeypatch.chdir(sample_project["path"])

    runner.invoke(app, ["init"])

    # Create an issue
    result = runner.invoke(app, ["create", "Test issue", "--description", ""])
    issue_id = extract_issue_id(result.output)

    # Close without message
    result = runner.invoke(app, ["close", issue_id])

    assert result.exit_code == 0

    # Verify issue is closed but has no comments
    db = get_db()
    issue = get_issue(db, issue_id)
    assert issue is not None
    assert issue["status"] == "closed"

    comments = get_comments(db, issue_id)
    assert len(comments) == 0
    db.close()
