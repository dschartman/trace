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
    assert "Added dependency" in result.output or "dependency" in result.output.lower()

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
