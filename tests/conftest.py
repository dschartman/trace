"""Shared pytest fixtures for trace tests."""

import os
import pytest


def pytest_configure(config):
    """Set TRACE_TEST_MODE environment variable for all tests.

    This serves as an additional safeguard to prevent tests from
    accidentally modifying real user data.
    """
    os.environ["TRACE_TEST_MODE"] = "1"


@pytest.fixture
def tmp_trace_dir(tmp_path, monkeypatch):
    """Create a temporary trace directory structure.

    Sets TRACE_HOME environment variable to ensure test isolation.
    This prevents tests from modifying real user data in ~/.trace/

    Returns a dict with paths:
        - home: temporary home directory (~/.trace)
        - db: path to trace.db
        - lock: path to .lock file
        - default_project: path to default project directory
    """
    trace_home = tmp_path / ".trace"
    trace_home.mkdir()

    # Set TRACE_HOME env var to redirect all operations to temp directory
    monkeypatch.setenv("TRACE_HOME", str(trace_home))

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
    from trc_main import init_database

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


@pytest.fixture
def initialized_project(tmp_trace_dir, sample_project):
    """Create an initialized project with database.

    Combines tmp_trace_dir (for isolated db) and sample_project (for git repo),
    registering the project in the database.

    Returns a dict with:
        - db: database connection
        - project: dict with id, name, path
    """
    from trc_main import init_database

    db = init_database(str(tmp_trace_dir["db"]))

    # Register project in database
    project_id = "github.com/user/myapp"
    db.execute(
        "INSERT INTO projects (id, name, current_path) VALUES (?, ?, ?)",
        (project_id, sample_project["name"], sample_project["path"]),
    )
    db.commit()

    yield {
        "db": db,
        "project": {
            "id": project_id,
            "name": sample_project["name"],
            "path": sample_project["path"],
        },
    }

    db.close()
