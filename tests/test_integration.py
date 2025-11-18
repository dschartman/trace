"""Integration tests for end-to-end workflows."""

import subprocess
import re
from typer.testing import CliRunner
from trc_main import app


def extract_issue_id(output: str) -> str:
    """Extract issue ID from CLI output."""
    match = re.search(r"([\w-]+)-([a-z0-9]{6})", output)
    if match:
        return match.group(0)
    raise ValueError(f"Could not extract issue ID from: {output}")


def test_feature_planning_workflow(tmp_path, tmp_trace_dir, monkeypatch):
    """Test complete feature planning workflow.

    Workflow:
    1. Initialize trace in a project
    2. Create parent feature
    3. Break down into children
    4. View tree
    5. Check ready work
    6. Verify JSONL created
    """
    runner = CliRunner()

    # Setup project
    project = tmp_path / "myapp"
    project.mkdir()
    subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True)

    monkeypatch.chdir(project)

    # Initialize trace
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert (project / ".trace" / "issues.jsonl").exists()

    # Create parent feature
    result = runner.invoke(app, ["create", "Add authentication", "--description", ""])
    assert result.exit_code == 0
    parent_id = extract_issue_id(result.output)

    # Create child tasks
    result = runner.invoke(app, ["create", "Design auth flow", "--description", "", "--parent", parent_id])
    child1_id = extract_issue_id(result.output)

    result = runner.invoke(app, ["create", "Implement login", "--description", "", "--parent", parent_id])
    child2_id = extract_issue_id(result.output)

    result = runner.invoke(app, ["create", "Add logout", "--description", "", "--parent", parent_id])
    child3_id = extract_issue_id(result.output)

    # View tree
    result = runner.invoke(app, ["tree", parent_id])
    assert result.exit_code == 0
    assert parent_id in result.output
    assert child1_id in result.output
    assert child2_id in result.output
    assert child3_id in result.output
    # Check for tree structure characters
    assert any(char in result.output for char in ["├", "└", "─"])

    # Check ready work (all children should be ready)
    result = runner.invoke(app, ["ready"])
    assert result.exit_code == 0
    assert child1_id in result.output
    assert child2_id in result.output
    assert child3_id in result.output

    # Verify JSONL contents
    jsonl_path = project / ".trace" / "issues.jsonl"
    assert jsonl_path.exists()
    jsonl_content = jsonl_path.read_text()
    assert parent_id in jsonl_content
    assert child1_id in jsonl_content
    assert child2_id in jsonl_content
    assert child3_id in jsonl_content


def test_cross_project_dependencies(tmp_path, tmp_trace_dir, monkeypatch):
    """Test cross-project dependency workflow.

    Workflow:
    1. Create two projects (lib and app)
    2. Create issue in lib project
    3. Create issue in app project that depends on lib
    4. Check ready work across projects
    5. Verify cross-project blocking
    """
    from trc_main import get_db, is_blocked

    runner = CliRunner()

    # Create lib project
    lib_project = tmp_path / "mylib"
    lib_project.mkdir()
    subprocess.run(["git", "init"], cwd=lib_project, check=True, capture_output=True)

    # Create app project
    app_project = tmp_path / "myapp"
    app_project.mkdir()
    subprocess.run(["git", "init"], cwd=app_project, check=True, capture_output=True)

    # Initialize both
    monkeypatch.chdir(lib_project)
    runner.invoke(app, ["init"])

    monkeypatch.chdir(app_project)
    runner.invoke(app, ["init"])

    # Create lib issue
    monkeypatch.chdir(lib_project)
    result = runner.invoke(app, ["create", "Add WebSocket support", "--description", ""])
    lib_issue_id = extract_issue_id(result.output)

    # Create app issue that depends on lib
    monkeypatch.chdir(app_project)
    result = runner.invoke(app, ["create", "Use WebSocket in UI", "--description", "", "--depends-on", lib_issue_id])
    app_issue_id = extract_issue_id(result.output)

    # Verify dependency was created
    db = get_db()
    assert is_blocked(db, app_issue_id)

    # Check ready work - lib issue should be ready, app issue should not
    monkeypatch.chdir(lib_project)
    result = runner.invoke(app, ["ready"])
    assert result.exit_code == 0
    assert lib_issue_id in result.output

    monkeypatch.chdir(app_project)
    result = runner.invoke(app, ["ready"])
    # App issue should not appear because it's blocked
    assert app_issue_id not in result.output

    db.close()


def test_jsonl_roundtrip(tmp_path, tmp_trace_dir, monkeypatch):
    """Test JSONL export/import roundtrip.

    Workflow:
    1. Create project and issues
    2. Export to JSONL
    3. Wipe database
    4. Import from JSONL
    5. Verify all issues restored
    """
    from trc_main import get_db, get_issue, export_to_jsonl, import_from_jsonl, create_issue, add_dependency, get_dependencies

    runner = CliRunner()

    # Create project
    project = tmp_path / "myapp"
    project.mkdir()
    subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True)

    monkeypatch.chdir(project)
    runner.invoke(app, ["init"])

    # Create issues with dependencies
    db = get_db()

    parent = create_issue(db, str(project), "myapp", "Parent issue", priority=0)
    child = create_issue(
        db,
        str(project),
        "myapp",
        "Child issue",
        description="Child description",
        priority=1,
        status="in_progress"
    )
    assert parent is not None
    assert child is not None
    add_dependency(db, child["id"], parent["id"], "parent")

    # Export to JSONL
    jsonl_path = project / ".trace" / "issues.jsonl"
    export_to_jsonl(db, str(project), str(jsonl_path))

    # Get original IDs
    parent_id = parent["id"]
    child_id = child["id"]

    # Wipe database
    db.execute("DELETE FROM dependencies")
    db.execute("DELETE FROM issues")
    db.commit()

    # Verify deletion
    assert get_issue(db, parent_id) is None
    assert get_issue(db, child_id) is None

    # Import from JSONL
    import_from_jsonl(db, str(jsonl_path))

    # Verify restoration
    parent_restored = get_issue(db, parent_id)
    child_restored = get_issue(db, child_id)

    assert parent_restored is not None
    assert parent_restored["title"] == "Parent issue"
    assert parent_restored["priority"] == 0

    assert child_restored is not None
    assert child_restored["title"] == "Child issue"
    assert child_restored["description"] == "Child description"
    assert child_restored["priority"] == 1
    assert child_restored["status"] == "in_progress"

    # Verify dependencies restored
    deps = get_dependencies(db, child_id)
    assert len(deps) == 1
    assert deps[0]["depends_on_id"] == parent_id
    assert deps[0]["type"] == "parent"

    db.close()


def test_git_pull_simulation(tmp_path, tmp_trace_dir, monkeypatch):
    """Test sync after simulated git pull.

    Workflow:
    1. Create project and issue
    2. Save JSONL
    3. Modify JSONL externally (simulate git pull)
    4. Run any command
    5. Verify sync detected and imported changes
    """
    from trc_main import get_db, get_issue
    import json
    import time

    runner = CliRunner()

    # Create project
    project = tmp_path / "myapp"
    project.mkdir()
    subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True)

    monkeypatch.chdir(project)
    runner.invoke(app, ["init"])

    # Create initial issue
    result = runner.invoke(app, ["create", "Original issue", "--description", ""])
    issue_id = extract_issue_id(result.output)

    # Verify issue exists
    db = get_db()
    issue = get_issue(db, issue_id)
    assert issue is not None
    assert issue["title"] == "Original issue"

    # Simulate git pull by modifying JSONL externally
    jsonl_path = project / ".trace" / "issues.jsonl"

    # Read existing JSONL
    lines = jsonl_path.read_text().strip().split("\n")
    issues = [json.loads(line) for line in lines]

    # Modify the issue (simulate remote change)
    issues[0]["title"] = "Modified by git pull"
    issues[0]["description"] = "This was changed remotely"

    # Write back
    with jsonl_path.open("w") as f:
        for issue_data in issues:
            f.write(json.dumps(issue_data) + "\n")

    # Touch the file to ensure newer mtime
    time.sleep(0.1)
    jsonl_path.touch()

    # Close and reopen DB to simulate fresh session
    db.close()

    # Run list command (which should trigger sync)
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0

    # Verify changes were imported
    db = get_db()
    updated_issue = get_issue(db, issue_id)
    assert updated_issue is not None
    assert updated_issue["title"] == "Modified by git pull"
    assert updated_issue["description"] == "This was changed remotely"

    db.close()
