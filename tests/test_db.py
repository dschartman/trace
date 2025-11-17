"""Tests for database schema and initialization."""

import sqlite3
from pathlib import Path

import pytest


def test_init_db_creates_all_tables(tmp_trace_dir):
    """Should create all required tables."""
    from trace import init_database

    db = init_database(str(tmp_trace_dir["db"]))

    cursor = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]

    assert "issues" in tables
    assert "projects" in tables
    assert "dependencies" in tables
    assert "metadata" in tables


def test_init_db_creates_issues_table_with_correct_schema(tmp_trace_dir):
    """Issues table should have all required columns with correct types."""
    from trace import init_database

    db = init_database(str(tmp_trace_dir["db"]))

    cursor = db.execute("PRAGMA table_info(issues)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}  # name: type

    assert columns["id"] == "TEXT"
    assert columns["project_id"] == "TEXT"
    assert columns["title"] == "TEXT"
    assert columns["description"] == "TEXT"
    assert columns["status"] == "TEXT"
    assert columns["priority"] == "INTEGER"
    assert columns["created_at"] == "TEXT"
    assert columns["updated_at"] == "TEXT"
    assert columns["closed_at"] == "TEXT"


def test_init_db_creates_projects_table_with_correct_schema(tmp_trace_dir):
    """Projects table should have all required columns."""
    from trace import init_database

    db = init_database(str(tmp_trace_dir["db"]))

    cursor = db.execute("PRAGMA table_info(projects)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}

    assert columns["name"] == "TEXT"
    assert columns["path"] == "TEXT"
    assert columns["git_remote"] == "TEXT"


def test_init_db_creates_dependencies_table_with_correct_schema(tmp_trace_dir):
    """Dependencies table should support cross-project links."""
    from trace import init_database

    db = init_database(str(tmp_trace_dir["db"]))

    cursor = db.execute("PRAGMA table_info(dependencies)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}

    assert columns["issue_id"] == "TEXT"
    assert columns["depends_on_id"] == "TEXT"
    assert columns["type"] == "TEXT"
    assert columns["created_at"] == "TEXT"


def test_init_db_creates_metadata_table_with_correct_schema(tmp_trace_dir):
    """Metadata table should store key-value pairs."""
    from trace import init_database

    db = init_database(str(tmp_trace_dir["db"]))

    cursor = db.execute("PRAGMA table_info(metadata)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}

    assert columns["key"] == "TEXT"
    assert columns["value"] == "TEXT"


def test_init_db_creates_indexes(tmp_trace_dir):
    """Should create indexes for common queries."""
    from trace import init_database

    db = init_database(str(tmp_trace_dir["db"]))

    cursor = db.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL ORDER BY name"
    )
    indexes = [row[0] for row in cursor.fetchall()]

    # Issues indexes
    assert "idx_issues_project" in indexes
    assert "idx_issues_status" in indexes
    assert "idx_issues_priority" in indexes

    # Dependencies indexes
    assert "idx_deps_issue" in indexes
    assert "idx_deps_depends" in indexes


def test_init_db_sets_schema_version(tmp_trace_dir):
    """Should record schema version in metadata."""
    from trace import init_database

    db = init_database(str(tmp_trace_dir["db"]))

    cursor = db.execute("SELECT value FROM metadata WHERE key = 'schema_version'")
    row = cursor.fetchone()

    assert row is not None
    assert row[0] == "1"


def test_init_db_enforces_status_constraint(tmp_trace_dir):
    """Should only allow valid status values."""
    from trace import init_database

    db = init_database(str(tmp_trace_dir["db"]))

    # Valid status should work
    db.execute(
        """INSERT INTO issues (id, project_id, title, status, created_at, updated_at)
           VALUES ('test-123', '/path', 'Test', 'open', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z')"""
    )

    # Invalid status should fail
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """INSERT INTO issues (id, project_id, title, status, created_at, updated_at)
               VALUES ('test-456', '/path', 'Test', 'invalid', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z')"""
        )


def test_init_db_enforces_priority_constraint(tmp_trace_dir):
    """Should only allow priority values 0-4."""
    from trace import init_database

    db = init_database(str(tmp_trace_dir["db"]))

    # Valid priorities should work
    for priority in [0, 1, 2, 3, 4]:
        db.execute(
            """INSERT INTO issues (id, project_id, title, priority, created_at, updated_at)
               VALUES (?, '/path', 'Test', ?, '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z')""",
            (f"test-{priority}", priority),
        )

    # Invalid priority should fail
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """INSERT INTO issues (id, project_id, title, priority, created_at, updated_at)
               VALUES ('test-999', '/path', 'Test', 5, '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z')"""
        )


def test_init_db_enforces_dependency_type_constraint(tmp_trace_dir):
    """Should only allow valid dependency types."""
    from trace import init_database

    db = init_database(str(tmp_trace_dir["db"]))

    # Create test issues first
    for i in range(3):
        db.execute(
            """INSERT INTO issues (id, project_id, title, created_at, updated_at)
               VALUES (?, '/path', 'Test', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z')""",
            (f"test-{i}",),
        )

    # Valid dependency types should work
    for dep_type in ["parent", "blocks", "related"]:
        db.execute(
            """INSERT INTO dependencies (issue_id, depends_on_id, type, created_at)
               VALUES ('test-0', 'test-1', ?, '2025-01-01T00:00:00Z')""",
            (dep_type,),
        )
        db.execute("DELETE FROM dependencies")  # Clean up for next iteration

    # Invalid type should fail
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """INSERT INTO dependencies (issue_id, depends_on_id, type, created_at)
               VALUES ('test-0', 'test-1', 'invalid', '2025-01-01T00:00:00Z')"""
        )


def test_init_db_sets_default_values(tmp_trace_dir):
    """Should set default values for optional fields."""
    from trace import init_database

    db = init_database(str(tmp_trace_dir["db"]))

    # Insert minimal issue
    db.execute(
        """INSERT INTO issues (id, project_id, title, created_at, updated_at)
           VALUES ('test-123', '/path', 'Test', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z')"""
    )

    cursor = db.execute("SELECT description, status, priority, closed_at FROM issues WHERE id = 'test-123'")
    row = cursor.fetchone()

    assert row[0] == ""  # description default
    assert row[1] == "open"  # status default
    assert row[2] == 2  # priority default
    assert row[3] is None  # closed_at default


def test_init_db_cascade_deletes_dependencies(tmp_trace_dir):
    """Deleting an issue should cascade delete its dependencies."""
    from trace import init_database

    db = init_database(str(tmp_trace_dir["db"]))

    # Create issues and dependency
    db.execute(
        """INSERT INTO issues (id, project_id, title, created_at, updated_at)
           VALUES ('test-1', '/path', 'Test 1', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z')"""
    )
    db.execute(
        """INSERT INTO issues (id, project_id, title, created_at, updated_at)
           VALUES ('test-2', '/path', 'Test 2', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z')"""
    )
    db.execute(
        """INSERT INTO dependencies (issue_id, depends_on_id, type, created_at)
           VALUES ('test-1', 'test-2', 'blocks', '2025-01-01T00:00:00Z')"""
    )

    # Delete issue
    db.execute("DELETE FROM issues WHERE id = 'test-1'")

    # Dependency should be gone
    cursor = db.execute("SELECT COUNT(*) FROM dependencies WHERE issue_id = 'test-1'")
    assert cursor.fetchone()[0] == 0


def test_init_db_is_idempotent(tmp_trace_dir):
    """Calling init_database multiple times should be safe."""
    from trace import init_database

    # Initialize twice
    db1 = init_database(str(tmp_trace_dir["db"]))
    db1.close()

    db2 = init_database(str(tmp_trace_dir["db"]))

    # Should still have all tables
    cursor = db2.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]

    assert "issues" in tables
    assert "projects" in tables
    assert "dependencies" in tables
