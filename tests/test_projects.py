"""Tests for project detection and registry."""

import os
from pathlib import Path

import pytest


def test_detect_project_from_git_repo(sample_project):
    """Should detect project from git repository."""
    from trc_main import detect_project

    # Change to project directory
    original_cwd = os.getcwd()
    try:
        os.chdir(sample_project["path"])
        project = detect_project()

        assert project is not None
        assert project["name"] == "myapp"
        assert project["path"] == sample_project["path"]
    finally:
        os.chdir(original_cwd)


def test_detect_project_from_subdirectory(sample_project):
    """Should walk up to find .git from subdirectory."""
    from trc_main import detect_project

    # Create nested subdirectory
    subdir = Path(sample_project["path"]) / "src" / "components"
    subdir.mkdir(parents=True)

    original_cwd = os.getcwd()
    try:
        os.chdir(str(subdir))
        project = detect_project()

        assert project is not None
        assert project["name"] == "myapp"
        assert project["path"] == sample_project["path"]
    finally:
        os.chdir(original_cwd)


def test_detect_project_extracts_name_from_git_remote(tmp_path):
    """Should extract project name from git remote URL."""
    from trc_main import detect_project

    # Create project with different remote URL patterns
    project_path = tmp_path / "localname"
    project_path.mkdir()

    git_dir = project_path / ".git"
    git_dir.mkdir()

    # Test various git remote URL formats
    test_cases = [
        ("https://github.com/user/remotename.git", "remotename"),
        ("git@github.com:user/remotename.git", "remotename"),
        ("https://gitlab.com/group/subgroup/project.git", "project"),
    ]

    original_cwd = os.getcwd()
    try:
        for remote_url, expected_name in test_cases:
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

            assert project["name"] == expected_name, f"Failed for URL: {remote_url}"
    finally:
        os.chdir(original_cwd)


def test_detect_project_uses_directory_name_when_no_remote(tmp_path):
    """Should use directory name when no git remote configured."""
    from trc_main import detect_project

    project_path = tmp_path / "myproject"
    project_path.mkdir()

    git_dir = project_path / ".git"
    git_dir.mkdir()

    # Create minimal config without remote
    config = git_dir / "config"
    config.write_text("[core]\n\trepositoryformatversion = 0\n")

    original_cwd = os.getcwd()
    try:
        os.chdir(str(project_path))
        project = detect_project()

        assert project["name"] == "myproject"
        assert project["path"] == str(project_path.absolute())
    finally:
        os.chdir(original_cwd)


def test_detect_project_returns_none_outside_git_repo(tmp_path):
    """Should return None when not in a git repository."""
    from trc_main import detect_project

    # Create directory without .git
    no_git_dir = tmp_path / "nogit"
    no_git_dir.mkdir()

    original_cwd = os.getcwd()
    try:
        os.chdir(str(no_git_dir))
        project = detect_project()

        assert project is None
    finally:
        os.chdir(original_cwd)


def test_detect_project_uses_absolute_path(sample_project):
    """Project ID should be absolute path, not name."""
    from trc_main import detect_project

    original_cwd = os.getcwd()
    try:
        os.chdir(sample_project["path"])
        project = detect_project()

        # Path should be absolute
        assert os.path.isabs(project["path"])
        assert project["path"] == sample_project["path"]
    finally:
        os.chdir(original_cwd)


def test_detect_project_handles_symlinks(tmp_path):
    """Should resolve symlinks to real path."""
    from trc_main import detect_project

    # Create real project
    real_project = tmp_path / "real"
    real_project.mkdir()
    git_dir = real_project / ".git"
    git_dir.mkdir()

    # Create symlink
    symlink = tmp_path / "link"
    symlink.symlink_to(real_project)

    original_cwd = os.getcwd()
    try:
        os.chdir(str(symlink))
        project = detect_project()

        # Should resolve to real path
        assert project["path"] == str(real_project.absolute())
    finally:
        os.chdir(original_cwd)


def test_detect_project_sanitizes_project_name():
    """Project names should be sanitized for use in IDs."""
    from trc_main import sanitize_project_name

    assert sanitize_project_name("My Project") == "my-project"
    assert sanitize_project_name("my_project") == "my-project"
    assert sanitize_project_name("My-Project-123") == "my-project-123"
    assert sanitize_project_name("UPPERCASE") == "uppercase"
    assert sanitize_project_name("special!@#chars") == "special-chars"
    assert sanitize_project_name("multiple   spaces") == "multiple-spaces"
    assert sanitize_project_name("--leading-trailing--") == "leading-trailing"


def test_detect_project_stops_at_filesystem_root(tmp_path):
    """Should stop searching at filesystem root, not infinite loop."""
    from trc_main import detect_project

    # This test ensures we don't walk infinitely up the tree
    # In practice, we should stop at filesystem root or home directory
    original_cwd = os.getcwd()
    try:
        # Change to a known non-git location (tmp_path root)
        os.chdir(str(tmp_path))
        project = detect_project()

        # Should return None, not crash or hang
        assert project is None
    finally:
        os.chdir(original_cwd)


def test_detect_project_cwd_parameter(sample_project):
    """Should accept optional current working directory parameter."""
    from trc_main import detect_project

    # Don't change directory, pass path as parameter
    project = detect_project(cwd=sample_project["path"])

    assert project is not None
    assert project["name"] == "myapp"
    assert project["path"] == sample_project["path"]


def test_detect_project_nested_git_repos(tmp_path):
    """Should detect nearest git repo, not parent repo."""
    from trc_main import detect_project

    # Create outer repo
    outer = tmp_path / "outer"
    outer.mkdir()
    (outer / ".git").mkdir()

    # Create inner repo
    inner = outer / "submodule"
    inner.mkdir()
    (inner / ".git").mkdir()

    original_cwd = os.getcwd()
    try:
        # From inner repo, should detect inner, not outer
        os.chdir(str(inner))
        project = detect_project()

        assert project["path"] == str(inner.absolute())
    finally:
        os.chdir(original_cwd)


def test_detect_project_reads_uuid_from_trace_id(sample_project):
    """detect_project should read UUID from .trace/id file if it exists."""
    from trc_main import detect_project

    # Write a UUID to .trace/id
    id_file = sample_project["trace_dir"] / "id"
    test_uuid = "550e8400-e29b-41d4-a716-446655440000"
    id_file.write_text(test_uuid + "\n")

    original_cwd = os.getcwd()
    try:
        os.chdir(sample_project["path"])
        project = detect_project()

        assert project is not None
        assert "uuid" in project
        assert project["uuid"] == test_uuid
    finally:
        os.chdir(original_cwd)


def test_detect_project_returns_none_uuid_when_no_trace_id(sample_project):
    """detect_project should return None for uuid when .trace/id doesn't exist."""
    from trc_main import detect_project

    # Make sure no .trace/id file exists (delete if sample_project fixture created one)
    id_file = sample_project["trace_dir"] / "id"
    if id_file.exists():
        id_file.unlink()

    original_cwd = os.getcwd()
    try:
        os.chdir(sample_project["path"])
        project = detect_project()

        assert project is not None
        assert "uuid" in project
        assert project["uuid"] is None
    finally:
        os.chdir(original_cwd)


def test_detect_project_returns_none_uuid_when_no_trace_dir(tmp_path):
    """detect_project should return None for uuid when .trace directory doesn't exist."""
    from trc_main import detect_project

    # Create git repo without .trace directory
    project_path = tmp_path / "no-trace-dir"
    project_path.mkdir()
    git_dir = project_path / ".git"
    git_dir.mkdir()

    original_cwd = os.getcwd()
    try:
        os.chdir(str(project_path))
        project = detect_project()

        assert project is not None
        assert "uuid" in project
        assert project["uuid"] is None
    finally:
        os.chdir(original_cwd)
