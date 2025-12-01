"""Tests for initialization safety and transaction integrity."""

import pytest
from pathlib import Path
from typer.testing import CliRunner
from trc_main import app, get_db, get_issue


def test_create_fails_without_init(tmp_path, tmp_trace_dir, monkeypatch):
    """create command should fail with clear error if project not initialized."""
    runner = CliRunner()

    # Create git repo WITHOUT running trc init
    project_path = tmp_path / "myapp"
    project_path.mkdir()
    git_dir = project_path / ".git"
    git_dir.mkdir()
    config = git_dir / "config"
    config.write_text('[remote "origin"]\n\turl = https://github.com/user/myapp.git\n')

    monkeypatch.chdir(project_path)

    # Try to create issue without init
    result = runner.invoke(app, ["create", "Test issue", "--description", "test"])

    # Should fail with helpful error
    assert result.exit_code == 1
    assert "not initialized" in result.output.lower() or "trc init" in result.output.lower()

    # Verify NO issue was created in DB (transaction safety)
    db = get_db()
    issue = get_issue(db, "myapp-" + "0" * 6)  # Any ID pattern
    # Should not find any issues for this project
    cursor = db.execute("SELECT COUNT(*) FROM issues WHERE project_id LIKE ?", ("github.com/user/myapp%",))
    count = cursor.fetchone()[0]
    assert count == 0, "No issues should be in DB if init failed"
    db.close()


def test_create_succeeds_after_init(tmp_path, tmp_trace_dir, monkeypatch):
    """create command should succeed after proper init."""
    runner = CliRunner()

    # Create git repo
    project_path = tmp_path / "myapp"
    project_path.mkdir()
    git_dir = project_path / ".git"
    git_dir.mkdir()
    config = git_dir / "config"
    config.write_text('[remote "origin"]\n\turl = https://github.com/user/myapp.git\n')

    monkeypatch.chdir(project_path)

    # Run init first
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0

    # Now create should work
    result = runner.invoke(app, ["create", "Test issue", "--description", "test"])
    assert result.exit_code == 0
    assert "Created" in result.output


def test_update_fails_without_init(tmp_path, tmp_trace_dir, monkeypatch):
    """update command should fail gracefully if project not initialized."""
    runner = CliRunner()

    # Create git repo WITHOUT init
    project_path = tmp_path / "myapp"
    project_path.mkdir()
    git_dir = project_path / ".git"
    git_dir.mkdir()
    config = git_dir / "config"
    config.write_text('[remote "origin"]\n\turl = https://github.com/user/myapp.git\n')

    monkeypatch.chdir(project_path)

    # Try to update a non-existent issue
    result = runner.invoke(app, ["update", "myapp-abc123", "--title", "New title"])

    # Should fail (either issue not found or not initialized)
    assert result.exit_code == 1


def test_close_fails_without_init(tmp_path, tmp_trace_dir, monkeypatch):
    """close command should fail gracefully if project not initialized."""
    runner = CliRunner()

    # Create git repo WITHOUT init
    project_path = tmp_path / "myapp"
    project_path.mkdir()
    git_dir = project_path / ".git"
    git_dir.mkdir()
    config = git_dir / "config"
    config.write_text('[remote "origin"]\n\turl = https://github.com/user/myapp.git\n')

    monkeypatch.chdir(project_path)

    # Try to close a non-existent issue
    result = runner.invoke(app, ["close", "myapp-abc123"])

    # Should fail (either issue not found or not initialized)
    assert result.exit_code == 1


def test_init_is_idempotent(tmp_path, tmp_trace_dir, monkeypatch):
    """init command should be safe to run multiple times."""
    runner = CliRunner()

    # Create git repo
    project_path = tmp_path / "myapp"
    project_path.mkdir()
    git_dir = project_path / ".git"
    git_dir.mkdir()
    config = git_dir / "config"
    config.write_text('[remote "origin"]\n\turl = https://github.com/user/myapp.git\n')

    monkeypatch.chdir(project_path)

    # Run init twice
    result1 = runner.invoke(app, ["init"])
    assert result1.exit_code == 0

    result2 = runner.invoke(app, ["init"])
    assert result2.exit_code == 0

    # .trace directory should exist
    assert (project_path / ".trace").exists()
    assert (project_path / ".trace" / "issues.jsonl").exists()


def test_create_with_project_flag_checks_initialization(tmp_path, tmp_trace_dir, monkeypatch):
    """create with --project flag should check if target project is initialized."""
    runner = CliRunner()

    # Create two projects
    project1 = tmp_path / "project1"
    project1.mkdir()
    git_dir1 = project1 / ".git"
    git_dir1.mkdir()
    config1 = git_dir1 / "config"
    config1.write_text('[remote "origin"]\n\turl = https://github.com/user/project1.git\n')

    project2 = tmp_path / "project2"
    project2.mkdir()
    git_dir2 = project2 / ".git"
    git_dir2.mkdir()
    config2 = git_dir2 / "config"
    config2.write_text('[remote "origin"]\n\turl = https://github.com/user/project2.git\n')

    # Initialize project1 only
    monkeypatch.chdir(project1)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0

    # Try to create in project2 (not initialized) from project1
    result = runner.invoke(app, ["create", "Test", "--description", "test", "--project", "project2"])

    # Should fail because project2 not in registry (never initialized)
    assert result.exit_code == 1
    assert "not found in registry" in result.output.lower() or "trc init" in result.output.lower()
