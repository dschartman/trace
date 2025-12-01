"""Tests for project resolution by name or path."""

import pytest
from pathlib import Path
from typer.testing import CliRunner
from trc_main import app


def extract_issue_id(output: str) -> str:
    """Extract issue ID from CLI output."""
    import re
    match = re.search(r"([\w-]+)-([a-z0-9]{6})", output)
    if match:
        return match.group(0)
    raise ValueError(f"Could not extract issue ID from: {output}")


def test_resolve_project_by_name(tmp_path, tmp_trace_dir, monkeypatch):
    """--project flag should accept project name."""
    runner = CliRunner()

    # Create project
    project_path = tmp_path / "myapp"
    project_path.mkdir()
    git_dir = project_path / ".git"
    git_dir.mkdir()
    config = git_dir / "config"
    config.write_text('[remote "origin"]\n\turl = https://github.com/user/myapp.git\n')

    monkeypatch.chdir(project_path)
    runner.invoke(app, ["init"])

    # Create issue in project
    result = runner.invoke(app, ["create", "Test issue", "--description", ""])
    assert result.exit_code == 0
    issue_id = extract_issue_id(result.output)

    # List issues using project name
    result = runner.invoke(app, ["list", "--project", "myapp"])

    assert result.exit_code == 0
    assert "Test issue" in result.output


def test_resolve_project_by_absolute_path(tmp_path, tmp_trace_dir, monkeypatch):
    """--project flag should accept absolute path."""
    runner = CliRunner()

    # Create project
    project_path = tmp_path / "myapp"
    project_path.mkdir()
    git_dir = project_path / ".git"
    git_dir.mkdir()
    config = git_dir / "config"
    config.write_text('[remote "origin"]\n\turl = https://github.com/user/myapp.git\n')

    monkeypatch.chdir(project_path)
    runner.invoke(app, ["init"])

    # Create issue in project
    result = runner.invoke(app, ["create", "Test issue", "--description", ""])
    assert result.exit_code == 0

    # List issues using absolute path
    absolute_path = str(project_path.resolve())
    result = runner.invoke(app, ["list", "--project", absolute_path])

    assert result.exit_code == 0
    assert "Test issue" in result.output


def test_resolve_project_by_relative_path(tmp_path, tmp_trace_dir, monkeypatch):
    """--project flag should accept relative path."""
    runner = CliRunner()

    # Create project
    project_path = tmp_path / "myapp"
    project_path.mkdir()
    git_dir = project_path / ".git"
    git_dir.mkdir()
    config = git_dir / "config"
    config.write_text('[remote "origin"]\n\turl = https://github.com/user/myapp.git\n')

    monkeypatch.chdir(project_path)
    runner.invoke(app, ["init"])

    # Create issue in project
    result = runner.invoke(app, ["create", "Test issue", "--description", ""])
    assert result.exit_code == 0

    # Change to parent directory
    monkeypatch.chdir(tmp_path)

    # List issues using relative path
    result = runner.invoke(app, ["list", "--project", "./myapp"])

    assert result.exit_code == 0
    assert "Test issue" in result.output


def test_resolve_project_by_tilde_path(tmp_path, tmp_trace_dir, monkeypatch):
    """--project flag should expand ~ in paths."""
    runner = CliRunner()

    # Create project in fake home directory
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    project_path = home_dir / "myapp"
    project_path.mkdir()
    git_dir = project_path / ".git"
    git_dir.mkdir()
    config = git_dir / "config"
    config.write_text('[remote "origin"]\n\turl = https://github.com/user/myapp.git\n')

    # Set HOME to fake home directory
    monkeypatch.setenv("HOME", str(home_dir))

    monkeypatch.chdir(project_path)
    runner.invoke(app, ["init"])

    # Create issue in project
    result = runner.invoke(app, ["create", "Test issue", "--description", ""])
    assert result.exit_code == 0

    # List issues using ~ path
    result = runner.invoke(app, ["list", "--project", "~/myapp"])

    assert result.exit_code == 0
    assert "Test issue" in result.output


def test_resolve_project_not_found_by_name(tmp_path, tmp_trace_dir, monkeypatch):
    """--project flag should error when project name not found."""
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["list", "--project", "nonexistent"])

    assert result.exit_code == 1
    assert "not found" in result.output.lower()


def test_resolve_project_not_found_by_path(tmp_path, tmp_trace_dir, monkeypatch):
    """--project flag should error when project path not found."""
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)

    fake_path = str(tmp_path / "nonexistent")
    result = runner.invoke(app, ["list", "--project", fake_path])

    assert result.exit_code == 1
    assert "not found" in result.output.lower()


def test_create_with_project_flag_by_name(tmp_path, tmp_trace_dir, monkeypatch):
    """create command --project flag should accept project name."""
    runner = CliRunner()

    # Create project
    project_path = tmp_path / "myapp"
    project_path.mkdir()
    git_dir = project_path / ".git"
    git_dir.mkdir()
    config = git_dir / "config"
    config.write_text('[remote "origin"]\n\turl = https://github.com/user/myapp.git\n')

    monkeypatch.chdir(project_path)
    runner.invoke(app, ["init"])

    # Change to different directory
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)

    # Create issue using project name
    result = runner.invoke(app, ["create", "Test issue", "--description", "", "--project", "myapp"])

    assert result.exit_code == 0
    assert "Created" in result.output
    assert "myapp" in result.output


def test_create_with_project_flag_by_path(tmp_path, tmp_trace_dir, monkeypatch):
    """create command --project flag should accept project path."""
    runner = CliRunner()

    # Create project
    project_path = tmp_path / "myapp"
    project_path.mkdir()
    git_dir = project_path / ".git"
    git_dir.mkdir()
    config = git_dir / "config"
    config.write_text('[remote "origin"]\n\turl = https://github.com/user/myapp.git\n')

    monkeypatch.chdir(project_path)
    runner.invoke(app, ["init"])

    # Change to different directory
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)

    # Create issue using project path
    absolute_path = str(project_path.resolve())
    result = runner.invoke(app, ["create", "Test issue", "--description", "", "--project", absolute_path])

    assert result.exit_code == 0
    assert "Created" in result.output
    assert "myapp" in result.output


def test_ready_with_project_flag_by_path(tmp_path, tmp_trace_dir, monkeypatch):
    """ready command --project flag should accept project path."""
    runner = CliRunner()

    # Create project
    project_path = tmp_path / "myapp"
    project_path.mkdir()
    git_dir = project_path / ".git"
    git_dir.mkdir()
    config = git_dir / "config"
    config.write_text('[remote "origin"]\n\turl = https://github.com/user/myapp.git\n')

    monkeypatch.chdir(project_path)
    runner.invoke(app, ["init"])

    # Create an open issue
    runner.invoke(app, ["create", "Ready issue", "--description", ""])

    # Change to different directory
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)

    # Check ready issues using project path
    absolute_path = str(project_path.resolve())
    result = runner.invoke(app, ["ready", "--project", absolute_path])

    assert result.exit_code == 0
    assert "Ready issue" in result.output
