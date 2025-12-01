"""Tests for clear dependency message output."""

import pytest
from typer.testing import CliRunner
from trc_main import app


def extract_issue_id(output: str) -> str:
    """Extract issue ID from CLI output."""
    import re
    match = re.search(r"([\w-]+)-([a-z0-9]{6})", output)
    if match:
        return match.group(0)
    raise ValueError(f"Could not extract issue ID from: {output}")


def test_blocks_dependency_message_is_clear(tmp_path, tmp_trace_dir, monkeypatch):
    """blocks dependency message should clearly indicate which issue is blocked."""
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

    # Create two issues
    result1 = runner.invoke(app, ["create", "Issue A", "--description", "first"])
    issue_a = extract_issue_id(result1.output)

    result2 = runner.invoke(app, ["create", "Issue B", "--description", "second"])
    issue_b = extract_issue_id(result2.output)

    # Add blocks dependency: A is blocked by B
    result = runner.invoke(app, ["add-dependency", issue_a, issue_b, "--type", "blocks"])

    assert result.exit_code == 0
    # Message should clearly indicate A is blocked by B
    # Should NOT say "A blocks B" which is backwards
    assert "blocked by" in result.output.lower() or "depends on" in result.output.lower()
    # Should mention both issues
    assert issue_a in result.output
    assert issue_b in result.output


def test_parent_dependency_message_is_clear(tmp_path, tmp_trace_dir, monkeypatch):
    """parent dependency message should clearly indicate parent-child relationship."""
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

    # Create two issues
    result1 = runner.invoke(app, ["create", "Parent", "--description", "parent"])
    parent_id = extract_issue_id(result1.output)

    result2 = runner.invoke(app, ["create", "Child", "--description", "child"])
    child_id = extract_issue_id(result2.output)

    # Add parent dependency
    result = runner.invoke(app, ["add-dependency", child_id, parent_id, "--type", "parent"])

    assert result.exit_code == 0
    # Message should clearly indicate parent-child relationship
    assert "parent" in result.output.lower() or "child" in result.output.lower()
    assert child_id in result.output
    assert parent_id in result.output


def test_related_dependency_message_is_clear(tmp_path, tmp_trace_dir, monkeypatch):
    """related dependency message should clearly indicate related link."""
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

    # Create two issues
    result1 = runner.invoke(app, ["create", "Issue A", "--description", "first"])
    issue_a = extract_issue_id(result1.output)

    result2 = runner.invoke(app, ["create", "Issue B", "--description", "second"])
    issue_b = extract_issue_id(result2.output)

    # Add related dependency
    result = runner.invoke(app, ["add-dependency", issue_a, issue_b, "--type", "related"])

    assert result.exit_code == 0
    # Message should clearly indicate related link
    assert "related" in result.output.lower() or "linked" in result.output.lower()
    assert issue_a in result.output
    assert issue_b in result.output
