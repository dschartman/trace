"""Tests for test isolation - ensuring tests never touch real ~/.trace/trace.db"""

import os
from pathlib import Path


def test_get_trace_home_respects_env_var(monkeypatch, tmp_path):
    """Test that get_trace_home() respects TRACE_HOME environment variable."""
    from trc_main import get_trace_home

    # Set custom trace home via environment variable
    custom_home = tmp_path / "custom_trace"
    monkeypatch.setenv("TRACE_HOME", str(custom_home))

    # Get trace home should return the custom path
    result = get_trace_home()
    assert result == custom_home
    assert str(result) != str(Path.home() / ".trace")


def test_get_trace_home_defaults_to_home_when_no_env(monkeypatch):
    """Test that get_trace_home() defaults to ~/.trace when TRACE_HOME is not set."""
    from trc_main import get_trace_home

    # Ensure TRACE_HOME is not set
    monkeypatch.delenv("TRACE_HOME", raising=False)

    # Should return default ~/.trace
    result = get_trace_home()
    assert result == Path.home() / ".trace"


def test_tmp_trace_dir_fixture_sets_env_var(tmp_trace_dir):
    """Test that tmp_trace_dir fixture sets TRACE_HOME env var."""
    from trc_main import get_trace_home

    # The fixture should have set TRACE_HOME
    trace_home = get_trace_home()

    # Should be the temporary directory, not real home
    assert str(trace_home) != str(Path.home() / ".trace")
    assert trace_home == tmp_trace_dir["home"]


def test_db_connection_uses_temp_db(tmp_trace_dir, db_connection):
    """Test that db_connection fixture uses temporary database."""
    from trc_main import get_db_path

    # Get the database path being used
    db_path = get_db_path()

    # Should be in temporary directory, not real home
    assert str(db_path) != str(Path.home() / ".trace" / "trace.db")
    assert db_path == tmp_trace_dir["db"]


def test_real_trace_db_never_created_by_tests(tmp_trace_dir):
    """Test that running database operations never creates real ~/.trace/trace.db"""
    from trc_main import get_db, create_issue

    real_trace_db = Path.home() / ".trace" / "trace.db"

    # Record if it existed before test
    existed_before = real_trace_db.exists()

    # Perform database operations
    db = get_db()
    create_issue(
        db,
        project_id="/tmp/test_project",
        project_name="test",
        title="Test issue",
        description="This should not touch real DB"
    )
    db.close()

    # Real database should not have been created or modified
    if existed_before:
        # If it existed before, it should not have been modified
        # We can't easily check modification without storing mtime before,
        # but at least verify we used temp DB
        from trc_main import get_db_path
        assert str(get_db_path()) != str(real_trace_db)
    else:
        # If it didn't exist, it should still not exist
        assert not real_trace_db.exists(), "Test created real ~/.trace/trace.db - DATA LOSS BUG!"


def test_test_mode_environment_variable():
    """Test that TRACE_TEST_MODE environment variable is set during tests."""
    # This env var should be set by pytest configuration
    assert os.environ.get("TRACE_TEST_MODE") == "1", \
        "TRACE_TEST_MODE must be set to prevent accidental real DB usage"
