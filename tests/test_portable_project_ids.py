"""Tests for portable project IDs (git remote URL-based identification).

This test file covers the refactoring to make project_id portable across machines:
- Using git remote URL as project_id instead of absolute path
- Removing project_id from JSONL format
- Auto-merge when project identifier changes
- Migration from old format to new format
"""

import json
import os
from pathlib import Path

import pytest


# ==============================================================================
# Project Detection Tests (trace-151sj8)
# ==============================================================================


def test_detect_project_returns_url_as_project_id(tmp_path):
    """Should return git remote URL as project_id, not absolute path."""
    from trc_main import detect_project

    project_path = tmp_path / "myproject"
    project_path.mkdir()

    git_dir = project_path / ".git"
    git_dir.mkdir()

    # Create git config with remote
    config = git_dir / "config"
    config.write_text("""[core]
\trepositoryformatversion = 0
[remote "origin"]
\turl = https://github.com/user/myrepo.git
""")

    original_cwd = os.getcwd()
    try:
        os.chdir(str(project_path))
        project = detect_project()

        assert project is not None
        # TODO: After implementation, project_id should be the URL, not the path
        # For now, this test will fail - that's expected with TDD
        assert project["id"] == "github.com/user/myrepo"  # NOT the absolute path
        assert project["name"] == "myrepo"
        assert project["path"] == str(project_path.absolute())  # Still track current path
    finally:
        os.chdir(original_cwd)


def test_detect_project_returns_path_for_local_only_repo(tmp_path):
    """Should fall back to absolute path for repos without remotes."""
    from trc_main import detect_project

    project_path = tmp_path / "localproject"
    project_path.mkdir()

    git_dir = project_path / ".git"
    git_dir.mkdir()

    # Create git config WITHOUT remote
    config = git_dir / "config"
    config.write_text("[core]\n\trepositoryformatversion = 0\n")

    original_cwd = os.getcwd()
    try:
        os.chdir(str(project_path))
        project = detect_project()

        assert project is not None
        # For local-only repos, project_id should be absolute path
        assert project["id"] == str(project_path.absolute())
        assert project["name"] == "localproject"
        assert project["path"] == str(project_path.absolute())
    finally:
        os.chdir(original_cwd)


def test_extract_project_id_from_various_url_formats(tmp_path):
    """Should extract clean project_id from various git remote URL formats."""
    from trc_main import detect_project

    project_path = tmp_path / "test"
    project_path.mkdir()

    git_dir = project_path / ".git"
    git_dir.mkdir()

    # Test various URL formats and their expected project_ids
    test_cases = [
        ("https://github.com/user/repo.git", "github.com/user/repo", "repo"),
        ("git@github.com:user/repo.git", "github.com/user/repo", "repo"),
        ("https://gitlab.com/group/subgroup/project.git", "gitlab.com/group/subgroup/project", "project"),
        ("git@gitlab.com:group/project.git", "gitlab.com/group/project", "project"),
        ("https://bitbucket.org/user/repo.git", "bitbucket.org/user/repo", "repo"),
    ]

    original_cwd = os.getcwd()
    try:
        for remote_url, expected_id, expected_name in test_cases:
            config = git_dir / "config"
            config.write_text(
                f"""[core]
\trepositoryformatversion = 0
[remote "origin"]
\turl = {remote_url}
"""
            )

            os.chdir(str(project_path))
            project = detect_project()

            assert project is not None, f"Failed for URL: {remote_url}"
            assert project["id"] == expected_id, f"Wrong project_id for URL: {remote_url}"
            assert project["name"] == expected_name, f"Wrong name for URL: {remote_url}"
    finally:
        os.chdir(original_cwd)


def test_same_repo_cloned_to_different_paths_has_same_project_id(tmp_path):
    """Cross-machine portability: same repo cloned to different locations should have same project_id."""
    from trc_main import detect_project

    # Simulate same repo cloned to two different locations
    clone1 = tmp_path / "machine1" / "projects" / "myrepo"
    clone1.mkdir(parents=True)

    clone2 = tmp_path / "machine2" / "workspace" / "myrepo"
    clone2.mkdir(parents=True)

    # Both have the same git remote URL
    remote_url = "https://github.com/company/myrepo.git"

    for clone_path in [clone1, clone2]:
        git_dir = clone_path / ".git"
        git_dir.mkdir()

        config = git_dir / "config"
        config.write_text(f"""[core]
\trepositoryformatversion = 0
[remote "origin"]
\turl = {remote_url}
""")

    original_cwd = os.getcwd()
    try:
        # Detect from first clone
        os.chdir(str(clone1))
        project1 = detect_project()

        # Detect from second clone
        os.chdir(str(clone2))
        project2 = detect_project()

        # Same project_id despite different absolute paths
        assert project1["id"] == project2["id"]
        assert project1["id"] == "github.com/company/myrepo"

        # But different current paths
        assert project1["path"] != project2["path"]
        assert project1["path"] == str(clone1.absolute())
        assert project2["path"] == str(clone2.absolute())
    finally:
        os.chdir(original_cwd)


# ==============================================================================
# JSONL Format Tests (trace-qt70sl)
# ==============================================================================


def test_export_to_jsonl_excludes_project_id_field(db_connection, tmp_path):
    """JSONL export should NOT include project_id field."""
    from trc_main import create_issue, export_to_jsonl

    # Create issue with project_id
    issue = create_issue(
        db_connection,
        "github.com/user/repo",  # This is now a URL-based project_id
        "repo",
        "Test Issue"
    )

    jsonl_path = tmp_path / "issues.jsonl"
    export_to_jsonl(db_connection, "github.com/user/repo", str(jsonl_path))

    # Read and parse JSONL
    line = jsonl_path.read_text().strip()
    data = json.loads(line)

    # Should NOT have project_id field
    assert "project_id" not in data, "JSONL should not contain project_id field"

    # Should have all other fields
    assert "id" in data
    assert "title" in data
    assert "description" in data
    assert "status" in data
    assert "priority" in data
    assert "created_at" in data
    assert "updated_at" in data


def test_import_from_jsonl_works_without_project_id(db_connection, tmp_path):
    """Import should work when JSONL doesn't have project_id field."""
    from trc_main import import_from_jsonl, get_issue

    # Create JSONL without project_id field
    jsonl_path = tmp_path / "issues.jsonl"
    issue_data = {
        "id": "repo-abc123",
        "title": "Test Issue",
        "description": "Test description",
        "status": "open",
        "priority": 2,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
        "dependencies": []
    }

    with jsonl_path.open("w") as f:
        f.write(json.dumps(issue_data) + "\n")

    # Import should work (project_id will be inferred from context)
    # TODO: import_from_jsonl signature needs to be updated to accept project_id parameter
    stats = import_from_jsonl(db_connection, str(jsonl_path), project_id="github.com/user/repo")

    assert stats["created"] == 1
    assert stats["errors"] == 0

    # Verify issue was created with correct project_id
    issue = get_issue(db_connection, "repo-abc123")
    assert issue is not None
    assert issue["project_id"] == "github.com/user/repo"


def test_import_from_jsonl_migrates_old_format_with_project_id(db_connection, tmp_path):
    """Import should handle old JSONL format that includes project_id field."""
    from trc_main import import_from_jsonl, get_issue

    # Create JSONL with OLD format (includes project_id)
    jsonl_path = tmp_path / "issues.jsonl"
    old_issue_data = {
        "id": "repo-abc123",
        "project_id": "/old/absolute/path/to/repo",  # OLD format
        "title": "Test Issue",
        "description": "Test description",
        "status": "open",
        "priority": 2,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
        "dependencies": []
    }

    with jsonl_path.open("w") as f:
        f.write(json.dumps(old_issue_data) + "\n")

    # Import with new project_id (URL-based)
    stats = import_from_jsonl(db_connection, str(jsonl_path), project_id="github.com/user/repo")

    assert stats["created"] == 1
    assert stats["errors"] == 0

    # Verify issue was created with NEW project_id (ignoring old project_id from JSONL)
    issue = get_issue(db_connection, "repo-abc123")
    assert issue is not None
    assert issue["project_id"] == "github.com/user/repo"  # Should use new project_id
    assert issue["project_id"] != "/old/absolute/path/to/repo"  # Should NOT use old project_id


# ==============================================================================
# Auto-merge Tests (trace-1bbnww)
# ==============================================================================


def test_auto_merge_when_local_repo_adds_remote(db_connection, tmp_path):
    """When a local-only repo adds a remote, issues should auto-merge to URL-based project_id."""
    from trc_main import create_issue, sync_project, get_issue, list_issues

    project_path = tmp_path / "myrepo"
    project_path.mkdir()

    git_dir = project_path / ".git"
    git_dir.mkdir()

    # Initially: local-only repo (no remote)
    config = git_dir / "config"
    config.write_text("[core]\n\trepositoryformatversion = 0\n")

    # Create issue in local-only project (project_id = absolute path)
    local_project_id = str(project_path.absolute())
    issue = create_issue(db_connection, local_project_id, "myrepo", "Test Issue")
    assert issue["project_id"] == local_project_id

    # Simulate: user adds remote to repo
    config.write_text("""[core]
\trepositoryformatversion = 0
[remote "origin"]
\turl = https://github.com/user/myrepo.git
""")

    # Sync should detect identifier change and auto-merge
    # TODO: This will require new auto-merge logic in sync_project()
    sync_project(db_connection, str(project_path))

    # After merge, issue should have new project_id (URL-based)
    updated_issue = get_issue(db_connection, issue["id"])
    assert updated_issue["project_id"] == "github.com/user/myrepo"

    # Old project_id should have no issues
    old_issues = list_issues(db_connection, project_id=local_project_id)
    assert len(old_issues) == 0

    # New project_id should have the issue
    new_issues = list_issues(db_connection, project_id="github.com/user/myrepo")
    assert len(new_issues) == 1


def test_auto_merge_when_remote_url_changes(db_connection, tmp_path):
    """When remote URL changes, issues should auto-merge to new project_id."""
    from trc_main import create_issue, sync_project, get_issue

    project_path = tmp_path / "myrepo"
    project_path.mkdir()

    git_dir = project_path / ".git"
    git_dir.mkdir()

    # Initially: repo with old remote URL
    config = git_dir / "config"
    config.write_text("""[core]
\trepositoryformatversion = 0
[remote "origin"]
\turl = https://github.com/olduser/myrepo.git
""")

    # Create issue with old project_id
    old_project_id = "github.com/olduser/myrepo"
    issue = create_issue(db_connection, old_project_id, "myrepo", "Test Issue")

    # Register old project in projects table (so auto-merge can find it)
    db_connection.execute(
        "INSERT OR REPLACE INTO projects (id, name, current_path) VALUES (?, ?, ?)",
        (old_project_id, "myrepo", str(project_path.absolute()))
    )
    db_connection.commit()

    # Simulate: user changes remote URL (e.g., repo transferred to new owner)
    config.write_text("""[core]
\trepositoryformatversion = 0
[remote "origin"]
\turl = https://github.com/newuser/myrepo.git
""")

    # Sync should detect identifier change and auto-merge
    sync_project(db_connection, str(project_path))

    # After merge, issue should have new project_id
    updated_issue = get_issue(db_connection, issue["id"])
    assert updated_issue["project_id"] == "github.com/newuser/myrepo"


# ==============================================================================
# Projects Table Schema Tests (trace-pzgtro)
# ==============================================================================


def test_projects_table_has_correct_schema(db_connection):
    """Projects table should have new schema: id (URL/path), name, current_path."""
    # Query schema
    cursor = db_connection.execute("PRAGMA table_info(projects)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}  # name: type

    # TODO: After schema migration, this should pass
    # Current schema has: name (PK), path (UNIQUE), git_remote
    # New schema should have: id (PK), name, current_path

    # Expected columns in new schema
    assert "id" in columns, "Should have 'id' column (project_id: URL or path)"
    assert "name" in columns, "Should have 'name' column"
    assert "current_path" in columns, "Should have 'current_path' column"

    # Check primary key
    cursor = db_connection.execute("PRAGMA table_info(projects)")
    for row in cursor.fetchall():
        if row[1] == "id":  # column name
            assert row[5] == 1, "id column should be PRIMARY KEY"


def test_migrate_projects_from_old_schema_to_new(db_connection):
    """Should migrate existing projects from old schema (path-based) to new schema (URL-based)."""
    # TODO: This test verifies one-time migration logic
    # When we run migration, existing projects with:
    #   - name="myrepo", path="/abs/path", git_remote="https://github.com/user/myrepo.git"
    # Should become:
    #   - id="github.com/user/myrepo", name="myrepo", current_path="/abs/path"

    # This will be implemented as part of the schema migration script
    pytest.skip("Migration test - implement with migration code")


# ==============================================================================
# Integration Tests
# ==============================================================================


def test_cross_machine_workflow_with_git_pull(db_connection, tmp_path):
    """Integration test: JSONL created on one machine should work on another machine."""
    # Machine 1: Create repo with remote, create issue, export JSONL
    machine1_path = tmp_path / "machine1" / "myrepo"
    machine1_path.mkdir(parents=True)

    git_dir1 = machine1_path / ".git"
    git_dir1.mkdir()

    config1 = git_dir1 / "config"
    config1.write_text("""[core]
\trepositoryformatversion = 0
[remote "origin"]
\turl = https://github.com/user/myrepo.git
""")

    trace_dir1 = machine1_path / ".trace"
    trace_dir1.mkdir()

    from trc_main import create_issue, export_to_jsonl

    # Create issue on machine 1
    issue = create_issue(db_connection, "github.com/user/myrepo", "myrepo", "Test Issue")

    jsonl_path1 = trace_dir1 / "issues.jsonl"
    export_to_jsonl(db_connection, "github.com/user/myrepo", str(jsonl_path1))

    # Verify JSONL doesn't have project_id
    with jsonl_path1.open() as f:
        data = json.loads(f.read().strip())
        assert "project_id" not in data

    # Machine 2: Clone same repo to different path, import JSONL
    machine2_path = tmp_path / "machine2" / "workspace" / "myrepo"
    machine2_path.mkdir(parents=True)

    git_dir2 = machine2_path / ".git"
    git_dir2.mkdir()

    config2 = git_dir2 / "config"
    config2.write_text("""[core]
\trepositoryformatversion = 0
[remote "origin"]
\turl = https://github.com/user/myrepo.git
""")

    trace_dir2 = machine2_path / ".trace"
    trace_dir2.mkdir()

    # Copy JSONL from machine 1 to machine 2 (simulating git pull)
    jsonl_path2 = trace_dir2 / "issues.jsonl"
    jsonl_path2.write_text(jsonl_path1.read_text())

    # Import on machine 2
    from trc_main import import_from_jsonl, get_issue

    stats = import_from_jsonl(db_connection, str(jsonl_path2), project_id="github.com/user/myrepo")
    # Issue already exists from machine 1, so it should be updated
    assert stats["created"] + stats["updated"] == 1

    # Verify issue has correct project_id (URL-based, not path-based)
    imported_issue = get_issue(db_connection, issue["id"])
    assert imported_issue["project_id"] == "github.com/user/myrepo"
    # Should NOT be machine-specific path
    assert imported_issue["project_id"] != str(machine1_path.absolute())
    assert imported_issue["project_id"] != str(machine2_path.absolute())


def test_cross_project_dependencies_work_with_portable_ids(db_connection):
    """Cross-project dependencies should work with URL-based project IDs."""
    from trc_main import create_issue, add_dependency, get_dependencies

    # Create issues in two different projects
    issue1 = create_issue(db_connection, "github.com/user/repo1", "repo1", "Issue 1")
    issue2 = create_issue(db_connection, "github.com/user/repo2", "repo2", "Issue 2")

    # Add cross-project dependency
    add_dependency(db_connection, issue2["id"], issue1["id"], "blocks")

    # Verify dependency works
    deps = get_dependencies(db_connection, issue2["id"])
    assert len(deps) == 1
    assert deps[0]["depends_on_id"] == issue1["id"]
    assert deps[0]["type"] == "blocks"
