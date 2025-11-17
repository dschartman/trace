"""Shared pytest fixtures for trace tests."""

import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_trace_dir(tmp_path):
    """Create a temporary trace directory structure.

    Returns a dict with paths:
        - home: temporary home directory (~/.trace)
        - db: path to trace.db
        - lock: path to .lock file
        - default_project: path to default project directory
    """
    trace_home = tmp_path / ".trace"
    trace_home.mkdir()

    default_project = trace_home / "default" / ".trace"
    default_project.mkdir(parents=True)

    return {
        "home": trace_home,
        "db": trace_home / "trace.db",
        "lock": trace_home / ".lock",
        "default_project": default_project,
    }


@pytest.fixture
def db_connection(tmp_trace_dir):
    """Create a fresh SQLite database connection for testing.

    Automatically initializes schema and closes connection after test completes.
    """
    from trace import init_database

    db_path = tmp_trace_dir["db"]
    conn = init_database(str(db_path))

    yield conn

    conn.close()


@pytest.fixture
def sample_project(tmp_path):
    """Create a sample git project for testing.

    Returns a dict with:
        - path: absolute path to project
        - name: project name
        - git_dir: path to .git directory
        - trace_dir: path to .trace directory
    """
    project_path = tmp_path / "myapp"
    project_path.mkdir()

    # Create .git directory
    git_dir = project_path / ".git"
    git_dir.mkdir()

    # Create basic git config with remote
    config = git_dir / "config"
    config.write_text("""[core]
	repositoryformatversion = 0
[remote "origin"]
	url = https://github.com/user/myapp.git
""")

    # Create .trace directory
    trace_dir = project_path / ".trace"
    trace_dir.mkdir()

    return {
        "path": str(project_path.absolute()),
        "name": "myapp",
        "git_dir": git_dir,
        "trace_dir": trace_dir,
    }


@pytest.fixture
def existing_ids():
    """Fixture providing a set of existing IDs for collision detection tests."""
    return {
        "myapp-abc123",
        "myapp-def456",
        "mylib-xyz789",
    }
