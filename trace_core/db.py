"""Database module for Trace - schema, initialization, migrations."""

import os
import sqlite3
from pathlib import Path

__all__ = [
    "init_database",
    "get_trace_home",
    "get_db_path",
    "get_db",
    "get_lock_path",
]

# SQL schema for issues table
ISSUES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS issues (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT DEFAULT 'open',
    priority INTEGER DEFAULT 2,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    closed_at TEXT,

    CHECK (priority >= 0 AND priority <= 4),
    CHECK (status IN ('open', 'in_progress', 'closed', 'blocked'))
);
"""

# SQL schema for projects table
PROJECTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,           -- Remote URL (e.g., github.com/user/repo) or absolute path
    name TEXT NOT NULL,            -- Project name
    current_path TEXT NOT NULL,    -- Absolute path to current location
    uuid TEXT                      -- Stable UUID from .trace/id file (NULL until populated)
);
"""

# SQL schema for dependencies table
DEPENDENCIES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS dependencies (
    issue_id TEXT NOT NULL,
    depends_on_id TEXT NOT NULL,
    type TEXT NOT NULL,
    created_at TEXT NOT NULL,

    PRIMARY KEY (issue_id, depends_on_id),
    FOREIGN KEY (issue_id) REFERENCES issues(id) ON DELETE CASCADE,
    FOREIGN KEY (depends_on_id) REFERENCES issues(id) ON DELETE CASCADE,
    CHECK (type IN ('parent', 'blocks', 'related'))
);
"""

# SQL schema for metadata table
METADATA_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# SQL schema for comments table
COMMENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL,

    FOREIGN KEY (issue_id) REFERENCES issues(id) ON DELETE CASCADE
);
"""

# SQL for creating indexes
# Note: idx_projects_uuid is created in _migrate_schema_v3_to_v4 or during fresh init
INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_issues_project ON issues(project_id);
CREATE INDEX IF NOT EXISTS idx_issues_status ON issues(status);
CREATE INDEX IF NOT EXISTS idx_issues_priority ON issues(priority);
CREATE INDEX IF NOT EXISTS idx_deps_issue ON dependencies(issue_id);
CREATE INDEX IF NOT EXISTS idx_deps_depends ON dependencies(depends_on_id);
CREATE INDEX IF NOT EXISTS idx_comments_issue ON comments(issue_id);
"""

# Current schema version
SCHEMA_VERSION = 4


def get_trace_home() -> Path:
    """Get the trace home directory (~/.trace).

    Can be overridden via TRACE_HOME environment variable.
    This is primarily used for test isolation to prevent tests
    from modifying real user data.
    """
    trace_home = os.environ.get("TRACE_HOME")
    if trace_home:
        return Path(trace_home)
    return Path.home() / ".trace"


def get_db_path() -> Path:
    """Get the central database path."""
    return get_trace_home() / "trace.db"


def get_lock_path() -> Path:
    """Get the file lock path (~/.trace/.lock)."""
    return get_trace_home() / ".lock"


def get_db() -> sqlite3.Connection:
    """Get database connection, initializing if needed."""
    trace_home = get_trace_home()
    trace_home.mkdir(exist_ok=True)
    db_path = get_db_path()
    return init_database(str(db_path))


def init_database(db_path: str) -> sqlite3.Connection:
    """Initialize trace database with schema.

    Creates all tables, indexes, and metadata if they don't exist.
    Safe to call multiple times (idempotent).

    Args:
        db_path: Path to SQLite database file

    Returns:
        SQLite database connection

    Schema:
        - issues: Work items across all projects
        - projects: Project registry (name, path, git remote)
        - dependencies: Relationships between issues
        - metadata: System state (schema version, etc.)
    """
    # Create connection with row factory for dict-like access
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON")

    # Create tables
    conn.executescript(
        f"""
        -- Issues: Work items across all projects
        {ISSUES_TABLE_SQL}

        -- Projects: Registry of all tracked projects (NEW SCHEMA)
        {PROJECTS_TABLE_SQL}

        -- Dependencies: Relationships between issues
        {DEPENDENCIES_TABLE_SQL}

        -- Metadata: System state
        {METADATA_TABLE_SQL}

        -- Comments: Annotations on issues
        {COMMENTS_TABLE_SQL}

        -- Indexes for performance
        {INDEXES_SQL}
        """
    )

    # Set initial metadata if not exists
    cursor = conn.execute("SELECT COUNT(*) FROM metadata WHERE key = 'schema_version'")
    if cursor.fetchone()[0] == 0:
        conn.execute(
            "INSERT INTO metadata (key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),)
        )
        # Create uuid index for fresh databases
        conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_uuid ON projects(uuid)")
        conn.commit()
    else:
        # Check if migration is needed
        cursor = conn.execute("SELECT value FROM metadata WHERE key = 'schema_version'")
        version = int(cursor.fetchone()[0])

        if version == 1:
            # Migrate from schema version 1 to 2
            _migrate_schema_v1_to_v2(conn)
            version = 2

        if version == 2:
            # Migrate from schema version 2 to 3
            _migrate_schema_v2_to_v3(conn)
            version = 3

        if version == 3:
            # Migrate from schema version 3 to 4
            _migrate_schema_v3_to_v4(conn)

    return conn


def _migrate_schema_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Migrate database schema from version 1 to version 2.

    Changes:
    - Projects table: (name PK, path UNIQUE, git_remote) -> (id PK, name, current_path)
    - project_id in issues: stays as-is (will be migrated when projects are synced)

    Args:
        conn: Database connection
    """
    # Check if migration needed (detect old schema by checking for 'path' column)
    cursor = conn.execute("PRAGMA table_info(projects)")
    columns = {row[1] for row in cursor.fetchall()}

    if "path" in columns and "id" not in columns:
        # Old schema detected, run migration
        conn.executescript("""
            -- Rename old table
            ALTER TABLE projects RENAME TO projects_old;

            -- Create new table with new schema
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                current_path TEXT NOT NULL
            );

            -- Migrate data: use path as id for local-only projects
            -- (When we sync with git repos, these will be updated to use remote URLs)
            INSERT INTO projects (id, name, current_path)
            SELECT path, name, path FROM projects_old;

            -- Drop old table
            DROP TABLE projects_old;
        """)

        # Update schema version
        conn.execute("UPDATE metadata SET value = '2' WHERE key = 'schema_version'")
        conn.commit()


def _migrate_schema_v2_to_v3(conn: sqlite3.Connection) -> None:
    """Migrate database schema from version 2 to version 3.

    Changes:
    - Add comments table for issue annotations

    Args:
        conn: Database connection
    """
    # Check if comments table already exists
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='comments'"
    )
    if cursor.fetchone() is None:
        # Create comments table
        conn.executescript(f"""
            {COMMENTS_TABLE_SQL}

            -- Add index for comments
            CREATE INDEX IF NOT EXISTS idx_comments_issue ON comments(issue_id);
        """)

    # Update schema version
    conn.execute("UPDATE metadata SET value = '3' WHERE key = 'schema_version'")
    conn.commit()


def _migrate_schema_v3_to_v4(conn: sqlite3.Connection) -> None:
    """Migrate database schema from version 3 to version 4.

    Changes:
    - Add uuid column to projects table for UUID-based project identification
    - Add index on projects.uuid for efficient lookups

    Args:
        conn: Database connection
    """
    # Check if uuid column already exists
    cursor = conn.execute("PRAGMA table_info(projects)")
    columns = {row[1] for row in cursor.fetchall()}

    if "uuid" not in columns:
        # Add uuid column (nullable for existing projects)
        conn.execute("ALTER TABLE projects ADD COLUMN uuid TEXT")

        # Create index for efficient lookups
        conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_uuid ON projects(uuid)")

    # Update schema version
    conn.execute("UPDATE metadata SET value = '4' WHERE key = 'schema_version'")
    conn.commit()
