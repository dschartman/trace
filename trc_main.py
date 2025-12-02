"""Trace - Minimal distributed issue tracker for AI agent workflows."""

import fcntl
import hashlib
import json
import os
import re
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Set, Dict

import typer
from typing_extensions import Annotated

# Create Typer app
app = typer.Typer(help="Trace - Minimal distributed issue tracker for AI agent workflows")


class IDCollisionError(Exception):
    """Raised when unable to generate unique ID after max retries."""

    pass


class LockError(Exception):
    """Raised when unable to acquire file lock."""

    pass


def generate_id(
    title: str,
    project: str,
    existing_ids: Optional[Set[str]] = None,
    max_retries: int = 10,
) -> str:
    """Generate a collision-resistant hash-based ID.

    Format: {project}-{6-char-base36-hash}

    Args:
        title: Issue title (used for entropy)
        project: Project name (used as prefix)
        existing_ids: Set of existing IDs to check for collisions
        max_retries: Maximum attempts to generate unique ID

    Returns:
        Unique ID string in format "project-abc123"

    Raises:
        IDCollisionError: If unable to generate unique ID after max_retries

    Implementation notes:
        - Uses SHA256 hash of: title + nanosecond timestamp + random bytes
        - Truncates hash to 6 characters in base36 encoding
        - Retries with fresh entropy if collision detected
    """
    if existing_ids is None:
        existing_ids = set()

    for attempt in range(max_retries):
        # Generate entropy from multiple sources
        timestamp_ns = time.time_ns()
        random_bytes = os.urandom(16)

        # Combine entropy sources
        entropy = f"{title}|{timestamp_ns}|{random_bytes.hex()}".encode("utf-8")

        # Hash and convert to base36
        hash_digest = hashlib.sha256(entropy).digest()
        hash_int = int.from_bytes(hash_digest[:4], byteorder="big")

        # Convert to base36 (0-9a-z) and take first 6 chars
        hash_b36 = _to_base36(hash_int)[:6].zfill(6)

        # Format full ID
        id = f"{project}-{hash_b36}"

        # Check for collision
        if id not in existing_ids:
            return id

    # Failed to generate unique ID
    raise IDCollisionError(
        f"Unable to generate unique ID for project '{project}' after {max_retries} attempts"
    )


def _to_base36(num: int) -> str:
    """Convert integer to base36 string (0-9a-z).

    Args:
        num: Integer to convert

    Returns:
        Base36 string representation
    """
    if num == 0:
        return "0"

    base36_chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    result = []

    while num > 0:
        num, remainder = divmod(num, 36)
        result.append(base36_chars[remainder])

    return "".join(reversed(result))


# File Locking


@contextmanager
def file_lock(lock_path: Path, timeout: float = 5.0):
    """Acquire an exclusive file lock.

    Args:
        lock_path: Path to lock file
        timeout: Maximum time to wait for lock (seconds)

    Raises:
        LockError: If unable to acquire lock within timeout

    Usage:
        with file_lock(Path("~/.trace/.lock")):
            # Critical section
            pass
    """
    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    # Open/create lock file
    lock_file = open(lock_path, "w")

    try:
        # Try to acquire lock with timeout
        start_time = time.time()
        while True:
            try:
                # Non-blocking lock attempt
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break  # Lock acquired
            except BlockingIOError:
                # Lock held by another process
                if time.time() - start_time >= timeout:
                    raise LockError(
                        f"Could not acquire lock on {lock_path} within {timeout}s"
                    )
                time.sleep(0.01)  # Wait a bit before retrying

        yield lock_file

    finally:
        # Release lock and close file
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        lock_file.close()


def sanitize_project_name(name: str) -> str:
    """Sanitize project name for use in IDs.

    Converts to lowercase, replaces spaces/underscores with hyphens,
    removes special characters, and strips leading/trailing hyphens.

    Args:
        name: Raw project name

    Returns:
        Sanitized project name safe for use in IDs

    Examples:
        >>> sanitize_project_name("My Project")
        'my-project'
        >>> sanitize_project_name("my_project")
        'my-project'
        >>> sanitize_project_name("Special!@#Chars")
        'special-chars'
    """
    # Convert to lowercase
    name = name.lower()

    # Replace spaces and underscores with hyphens
    name = re.sub(r"[\s_]+", "-", name)

    # Replace any non-alphanumeric characters (except hyphens) with hyphens
    name = re.sub(r"[^a-z0-9-]+", "-", name)

    # Replace multiple consecutive hyphens with single hyphen
    name = re.sub(r"-+", "-", name)

    # Strip leading and trailing hyphens
    name = name.strip("-")

    return name


def detect_project(cwd: Optional[str] = None) -> Optional[Dict[str, str]]:
    """Detect project from git repository.

    Walks up directory tree from current working directory to find .git,
    then extracts project name and ID from git remote or directory name.

    Args:
        cwd: Optional current working directory (defaults to os.getcwd())

    Returns:
        Dict with 'id', 'name', and 'path' keys, or None if not in a git repo
        - id: Git remote URL (e.g., 'github.com/user/repo') or absolute path for local-only repos
        - name: Project name (extracted from remote or directory name)
        - path: Absolute path to project directory

    Example:
        >>> project = detect_project()
        >>> if project:
        ...     print(f"{project['name']} (id: {project['id']}) at {project['path']}")
    """
    if cwd is None:
        cwd = os.getcwd()

    # Resolve to absolute path and handle symlinks
    current_path = Path(cwd).resolve()

    # Walk up directory tree looking for .git
    for parent in [current_path] + list(current_path.parents):
        git_dir = parent / ".git"

        if git_dir.exists():
            # Found a git repository
            project_path = str(parent.absolute())

            # Try to extract project_id and name from git remote
            project_id = _extract_project_id_from_git_remote(git_dir)
            project_name = _extract_name_from_git_remote(git_dir)

            # Fall back to absolute path and directory name if no remote found
            if not project_id:
                project_id = project_path

            if not project_name:
                project_name = parent.name

            # Sanitize the project name
            project_name = sanitize_project_name(project_name)

            return {"id": project_id, "name": project_name, "path": project_path}

    # Not in a git repository
    return None


def is_project_initialized(project_path: str) -> bool:
    """Check if a project has been initialized with trc init.

    Args:
        project_path: Absolute path to project directory

    Returns:
        True if .trace/issues.jsonl exists, False otherwise
    """
    trace_dir = Path(project_path) / ".trace"
    jsonl_path = trace_dir / "issues.jsonl"
    return jsonl_path.exists()


def resolve_project(project_flag: str, db: sqlite3.Connection) -> Optional[Dict[str, str]]:
    """Resolve project by name or path.

    Accepts either a project name (e.g., 'myapp') or a path (e.g., '~/Repos/myapp',
    '/absolute/path', or './relative/path').

    Args:
        project_flag: Project identifier (name or path)
        db: Database connection

    Returns:
        Dict with 'id', 'name', and 'path' keys, or None if not found

    Notes:
        - Validates that current_path is a real filesystem path
        - If current_path is corrupted (URL instead of path), attempts recovery
          by searching for projects with matching name that have valid paths
    """
    # Check if the input looks like a path (contains / or starts with ~)
    if "/" in project_flag or project_flag.startswith("~"):
        # Treat as path - expand and resolve it
        expanded_path = str(Path(project_flag).expanduser().resolve())

        # Look up by path in database (id column contains the absolute path for local repos)
        cursor = db.execute(
            "SELECT id, name, current_path FROM projects WHERE current_path = ?",
            (expanded_path,)
        )
        row = cursor.fetchone()

        if row is not None:
            current_path = row[2]
            # Validate current_path is a real filesystem path
            if os.path.isabs(current_path):
                return {"id": row[0], "name": row[1], "path": current_path}
            # Corrupted - path in DB doesn't match reality, skip this result

        # If not found by current_path, try looking up by id (for cases where id is the path)
        cursor = db.execute(
            "SELECT id, name, current_path FROM projects WHERE id = ?",
            (expanded_path,)
        )
        row = cursor.fetchone()

        if row is not None:
            current_path = row[2]
            if os.path.isabs(current_path):
                return {"id": row[0], "name": row[1], "path": current_path}

        return None
    else:
        # Treat as project name
        cursor = db.execute(
            "SELECT id, name, current_path FROM projects WHERE name = ?",
            (project_flag,)
        )
        row = cursor.fetchone()

        if row is not None:
            current_path = row[2]
            # Validate current_path is a real filesystem path (not corrupted URL)
            if os.path.isabs(current_path):
                return {"id": row[0], "name": row[1], "path": current_path}

            # current_path is corrupted - try to find another project with same name
            # that has a valid path (in case of duplicate registrations)
            cursor = db.execute(
                "SELECT id, name, current_path FROM projects WHERE name = ?",
                (project_flag,)
            )
            for alt_row in cursor.fetchall():
                alt_path = alt_row[2]
                if os.path.isabs(alt_path):
                    return {"id": alt_row[0], "name": alt_row[1], "path": alt_path}

            # No valid path found - return None so caller gets helpful error
            return None

        return None


def _extract_project_id_from_git_remote(git_dir: Path) -> Optional[str]:
    """Extract project ID from git remote URL.

    Parses .git/config to find remote "origin" URL and converts it to
    a portable project identifier.

    Args:
        git_dir: Path to .git directory

    Returns:
        Project ID from remote URL, or None if not found

    Handles various git URL formats:
        - https://github.com/user/repo.git → github.com/user/repo
        - git@github.com:user/repo.git → github.com/user/repo
        - https://gitlab.com/group/subgroup/project.git → gitlab.com/group/subgroup/project
    """
    config_file = git_dir / "config"

    if not config_file.exists():
        return None

    try:
        config_content = config_file.read_text()

        # Look for remote "origin" url
        # Match pattern: url = <URL>
        match = re.search(r'url\s*=\s*(.+)', config_content)

        if not match:
            return None

        url = match.group(1).strip()

        # Remove .git suffix if present
        url = url.rstrip("/")
        if url.endswith(".git"):
            url = url[:-4]

        # Convert various URL formats to canonical form: host/path
        if url.startswith("https://") or url.startswith("http://"):
            # https://github.com/user/repo → github.com/user/repo
            url = url.replace("https://", "").replace("http://", "")
        elif url.startswith("git@"):
            # git@github.com:user/repo → github.com/user/repo
            url = url.replace("git@", "").replace(":", "/", 1)
        else:
            # Unknown format
            return None

        return url if url else None

    except Exception:
        # If anything goes wrong reading/parsing config, return None
        return None


def _extract_name_from_git_remote(git_dir: Path) -> Optional[str]:
    """Extract project name from git remote URL.

    Parses .git/config to find remote "origin" URL and extracts
    the repository name.

    Args:
        git_dir: Path to .git directory

    Returns:
        Project name from remote URL, or None if not found

    Handles various git URL formats:
        - https://github.com/user/repo.git → repo
        - git@github.com:user/repo.git → repo
        - https://gitlab.com/group/subgroup/project.git → project
    """
    config_file = git_dir / "config"

    if not config_file.exists():
        return None

    try:
        config_content = config_file.read_text()

        # Look for remote "origin" url
        # Match pattern: url = <URL>
        match = re.search(r'url\s*=\s*(.+)', config_content)

        if not match:
            return None

        url = match.group(1).strip()

        # Extract repository name from various URL formats
        # Remove .git suffix if present
        url = url.rstrip("/")
        if url.endswith(".git"):
            url = url[:-4]

        # Extract last component of path
        # Handle both https:// and git@ formats
        if "://" in url:
            # https://github.com/user/repo
            name = url.split("/")[-1]
        elif ":" in url:
            # git@github.com:user/repo
            name = url.split(":")[-1].split("/")[-1]
        else:
            return None

        return name if name else None

    except Exception:
        # If anything goes wrong reading/parsing config, return None
        return None


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
        """
        -- Issues: Work items across all projects
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

        -- Projects: Registry of all tracked projects (NEW SCHEMA)
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,           -- Remote URL (e.g., github.com/user/repo) or absolute path
            name TEXT NOT NULL,            -- Project name
            current_path TEXT NOT NULL     -- Absolute path to current location
        );

        -- Dependencies: Relationships between issues
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

        -- Metadata: System state
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        -- Indexes for performance
        CREATE INDEX IF NOT EXISTS idx_issues_project ON issues(project_id);
        CREATE INDEX IF NOT EXISTS idx_issues_status ON issues(status);
        CREATE INDEX IF NOT EXISTS idx_issues_priority ON issues(priority);
        CREATE INDEX IF NOT EXISTS idx_deps_issue ON dependencies(issue_id);
        CREATE INDEX IF NOT EXISTS idx_deps_depends ON dependencies(depends_on_id);
        """
    )

    # Set initial metadata if not exists
    cursor = conn.execute("SELECT COUNT(*) FROM metadata WHERE key = 'schema_version'")
    if cursor.fetchone()[0] == 0:
        conn.execute("INSERT INTO metadata (key, value) VALUES ('schema_version', '2')")
        conn.commit()
    else:
        # Check if migration is needed
        cursor = conn.execute("SELECT value FROM metadata WHERE key = 'schema_version'")
        version = int(cursor.fetchone()[0])

        if version == 1:
            # Migrate from schema version 1 to 2
            _migrate_schema_v1_to_v2(conn)

    return conn


def _migrate_schema_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Migrate database schema from version 1 to version 2.

    Changes:
    - Projects table: (name PK, path UNIQUE, git_remote) → (id PK, name, current_path)
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


def get_lock_path() -> Path:
    """Get the file lock path (~/.trace/.lock)."""
    return get_trace_home() / ".lock"


def get_last_sync_time(db: sqlite3.Connection, project_id: str) -> Optional[float]:
    """Get timestamp of last JSONL sync for project.

    Args:
        db: Database connection
        project_id: Project ID (absolute path)

    Returns:
        Timestamp of last sync, or None if never synced
    """
    cursor = db.execute(
        "SELECT value FROM metadata WHERE key = ?",
        (f"last_sync:{project_id}",)
    )
    row = cursor.fetchone()
    return float(row[0]) if row else None


def set_last_sync_time(db: sqlite3.Connection, project_id: str, timestamp: float) -> None:
    """Record timestamp of JSONL sync.

    Args:
        db: Database connection
        project_id: Project ID (absolute path)
        timestamp: Unix timestamp of sync
    """
    db.execute(
        "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
        (f"last_sync:{project_id}", str(timestamp))
    )
    db.commit()


def sync_project(db: sqlite3.Connection, project_path: str) -> None:
    """Sync project: import from JSONL if newer than last sync.

    Args:
        db: Database connection
        project_path: Absolute path to project

    Notes:
        - Checks JSONL modification time vs last sync timestamp
        - Imports only if JSONL is newer (e.g., after git pull)
        - Updates last sync timestamp after import
        - Detects project_id from git context for portable imports
    """
    # Detect project ID from git context
    project = detect_project(cwd=project_path)
    if not project:
        # Not a git repo, skip sync
        return

    project_id = project["id"]

    # AUTO-MERGE: Check if project_id changed (e.g., local path → URL)
    # Find issues with different project_id but for this same path
    cursor = db.execute(
        "SELECT DISTINCT project_id FROM issues"
    )
    all_project_ids = [row[0] for row in cursor.fetchall()]

    for old_project_id in all_project_ids:
        # Check if this is the same project with a different ID
        # (e.g., old_project_id is absolute path, new is URL)
        if old_project_id != project_id:
            # Check if old_project_id points to this same path
            is_same_project = False

            # Case 1: old_project_id is the absolute path itself
            if old_project_id == project_path:
                is_same_project = True

            # Case 2: old_project_id exists in projects table with this path
            else:
                cursor2 = db.execute(
                    "SELECT current_path FROM projects WHERE id = ?",
                    (old_project_id,)
                )
                row = cursor2.fetchone()
                if row and row[0] == project_path:
                    is_same_project = True

            if is_same_project:
                # Auto-merge: update all issues from old_project_id to new_project_id
                db.execute(
                    "UPDATE issues SET project_id = ? WHERE project_id = ?",
                    (project_id, old_project_id)
                )
                db.commit()

                # Update or remove old entry in projects table
                db.execute(
                    "DELETE FROM projects WHERE id = ?",
                    (old_project_id,)
                )
                # Ensure new project_id is registered
                db.execute(
                    "INSERT OR REPLACE INTO projects (id, name, current_path) VALUES (?, ?, ?)",
                    (project_id, project["name"], project_path)
                )
                db.commit()

    # Now handle JSONL sync if file exists
    trace_dir = Path(project_path) / ".trace"
    jsonl_path = trace_dir / "issues.jsonl"

    if not jsonl_path.exists():
        return

    # Check if JSONL is newer than last sync
    jsonl_mtime = jsonl_path.stat().st_mtime
    last_sync = get_last_sync_time(db, project_id)

    if last_sync is None or jsonl_mtime > last_sync:
        # JSONL is newer, import it
        import_from_jsonl(db, str(jsonl_path), project_id)
        set_last_sync_time(db, project_id, jsonl_mtime)


# Issue CRUD Operations


def create_issue(
    db: sqlite3.Connection,
    project_id: str,
    project_name: str,
    title: str,
    description: str = "",
    status: str = "open",
    priority: int = 2,
) -> Optional[Dict[str, Any]]:
    """Create a new issue.

    Args:
        db: Database connection
        project_id: Absolute path to project (unique identifier)
        project_name: Project name for ID generation
        title: Issue title
        description: Optional detailed description
        status: Status (open, in_progress, closed, blocked)
        priority: Priority 0-4 (0=critical, 4=backlog)

    Returns:
        Dict with created issue data

    Raises:
        ValueError: If status or priority is invalid
    """
    # Validate inputs
    valid_statuses = {"open", "in_progress", "closed", "blocked"}
    if status not in valid_statuses:
        raise ValueError(f"Invalid status: {status}. Must be one of {valid_statuses}")

    if not (0 <= priority <= 4):
        raise ValueError(f"Priority must be between 0 and 4, got {priority}")

    # Get existing IDs for collision detection
    cursor = db.execute("SELECT id FROM issues WHERE id LIKE ?", (f"{project_name}-%",))
    existing_ids = {row[0] for row in cursor.fetchall()}

    # Generate unique ID
    issue_id = generate_id(title, project_name, existing_ids=existing_ids)

    # Generate timestamps
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Insert issue
    db.execute(
        """INSERT INTO issues
           (id, project_id, title, description, status, priority, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (issue_id, project_id, title, description, status, priority, now, now),
    )
    db.commit()

    # Return created issue
    return get_issue(db, issue_id)


def get_issue(db: sqlite3.Connection, issue_id: str) -> Optional[Dict[str, Any]]:
    """Get issue by ID.

    Args:
        db: Database connection
        issue_id: Issue ID

    Returns:
        Dict with issue data, or None if not found
    """
    cursor = db.execute("SELECT * FROM issues WHERE id = ?", (issue_id,))
    row = cursor.fetchone()

    if row is None:
        return None

    return dict(row)


def list_issues(
    db: sqlite3.Connection,
    project_id: Optional[str] = None,
    status: Optional[str | list[str]] = None,
) -> list[Dict[str, Any]]:
    """List issues with optional filtering.

    Args:
        db: Database connection
        project_id: Filter by project (optional)
        status: Filter by status - single status string, list of statuses, or None for all (optional)

    Returns:
        List of issue dicts, sorted by priority then created_at (desc)
    """
    query = "SELECT * FROM issues WHERE 1=1"
    params = []

    if project_id is not None:
        query += " AND project_id = ?"
        params.append(project_id)

    if status is not None:
        if isinstance(status, list):
            # Multiple statuses - use IN clause
            placeholders = ",".join("?" * len(status))
            query += f" AND status IN ({placeholders})"
            params.extend(status)
        else:
            # Single status - use = clause
            query += " AND status = ?"
            params.append(status)

    # Sort by priority (ascending) then created_at (descending)
    query += " ORDER BY priority ASC, created_at DESC"

    cursor = db.execute(query, params)
    return [dict(row) for row in cursor.fetchall()]


def update_issue(
    db: sqlite3.Connection,
    issue_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[int] = None,
) -> None:
    """Update issue fields.

    Args:
        db: Database connection
        issue_id: Issue ID to update
        title: New title (optional)
        description: New description (optional)
        status: New status (optional)
        priority: New priority (optional)

    Raises:
        ValueError: If status or priority is invalid
    """
    # Validate inputs
    if status is not None:
        valid_statuses = {"open", "in_progress", "closed", "blocked"}
        if status not in valid_statuses:
            raise ValueError(f"Invalid status: {status}. Must be one of {valid_statuses}")

    if priority is not None:
        if not (0 <= priority <= 4):
            raise ValueError(f"Priority must be between 0 and 4, got {priority}")

    # Build update query dynamically
    updates = []
    params = []

    if title is not None:
        updates.append("title = ?")
        params.append(title)

    if description is not None:
        updates.append("description = ?")
        params.append(description)

    if status is not None:
        updates.append("status = ?")
        params.append(status)
        # Clear closed_at when reopening
        if status != "closed":
            updates.append("closed_at = NULL")

    if priority is not None:
        updates.append("priority = ?")
        params.append(priority)

    # Always update updated_at
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    updates.append("updated_at = ?")
    params.append(now)

    # Add issue_id to params
    params.append(issue_id)

    # Execute update
    query = f"UPDATE issues SET {', '.join(updates)} WHERE id = ?"
    db.execute(query, params)
    db.commit()


def close_issue(db: sqlite3.Connection, issue_id: str) -> None:
    """Close an issue.

    Args:
        db: Database connection
        issue_id: Issue ID to close
    """
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    db.execute(
        """UPDATE issues
           SET status = 'closed', closed_at = ?, updated_at = ?
           WHERE id = ?""",
        (now, now, issue_id),
    )
    db.commit()


# Dependency Management


def add_dependency(
    db: sqlite3.Connection,
    issue_id: str,
    depends_on_id: str,
    dep_type: str,
) -> None:
    """Add a dependency between two issues.

    Args:
        db: Database connection
        issue_id: Issue that has the dependency
        depends_on_id: Issue that is depended upon
        dep_type: Type of dependency (parent, blocks, related)

    Raises:
        ValueError: If dependency type is invalid
    """
    valid_types = {"parent", "blocks", "related"}
    if dep_type not in valid_types:
        raise ValueError(f"Invalid dependency type: {dep_type}. Must be one of {valid_types}")

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Use INSERT OR IGNORE to prevent duplicates
    db.execute(
        """INSERT OR IGNORE INTO dependencies (issue_id, depends_on_id, type, created_at)
           VALUES (?, ?, ?, ?)""",
        (issue_id, depends_on_id, dep_type, now),
    )
    db.commit()


def remove_dependency(
    db: sqlite3.Connection,
    issue_id: str,
    depends_on_id: str,
) -> None:
    """Remove a dependency between two issues.

    Args:
        db: Database connection
        issue_id: Issue that has the dependency
        depends_on_id: Issue that is depended upon
    """
    db.execute(
        "DELETE FROM dependencies WHERE issue_id = ? AND depends_on_id = ?",
        (issue_id, depends_on_id),
    )
    db.commit()


def get_dependencies(
    db: sqlite3.Connection,
    issue_id: str,
) -> list[Dict[str, Any]]:
    """Get all dependencies for an issue.

    Args:
        db: Database connection
        issue_id: Issue ID

    Returns:
        List of dependency dicts with depends_on_id and type
    """
    cursor = db.execute(
        "SELECT depends_on_id, type, created_at FROM dependencies WHERE issue_id = ?",
        (issue_id,),
    )
    return [dict(row) for row in cursor.fetchall()]


def get_children(
    db: sqlite3.Connection,
    parent_id: str,
) -> list[Dict[str, Any]]:
    """Get all child issues of a parent.

    Args:
        db: Database connection
        parent_id: Parent issue ID

    Returns:
        List of child issue dicts
    """
    cursor = db.execute(
        """SELECT i.* FROM issues i
           JOIN dependencies d ON i.id = d.issue_id
           WHERE d.depends_on_id = ? AND d.type = 'parent'
           ORDER BY i.created_at""",
        (parent_id,),
    )
    return [dict(row) for row in cursor.fetchall()]


def get_blockers(
    db: sqlite3.Connection,
    issue_id: str,
) -> list[Dict[str, Any]]:
    """Get all issues that block this issue.

    Args:
        db: Database connection
        issue_id: Issue ID

    Returns:
        List of blocker issue dicts
    """
    cursor = db.execute(
        """SELECT i.* FROM issues i
           JOIN dependencies d ON i.id = d.depends_on_id
           WHERE d.issue_id = ? AND d.type = 'blocks'""",
        (issue_id,),
    )
    return [dict(row) for row in cursor.fetchall()]


def is_blocked(
    db: sqlite3.Connection,
    issue_id: str,
) -> bool:
    """Check if issue is blocked by any open issues.

    Args:
        db: Database connection
        issue_id: Issue ID

    Returns:
        True if blocked by at least one open issue
    """
    cursor = db.execute(
        """SELECT COUNT(*) FROM dependencies d
           JOIN issues i ON d.depends_on_id = i.id
           WHERE d.issue_id = ? AND d.type = 'blocks' AND i.status != 'closed'""",
        (issue_id,),
    )
    count = cursor.fetchone()[0]
    return count > 0


def has_open_children(
    db: sqlite3.Connection,
    parent_id: str,
) -> bool:
    """Check if issue has any open children.

    Args:
        db: Database connection
        parent_id: Parent issue ID

    Returns:
        True if has at least one open child
    """
    cursor = db.execute(
        """SELECT COUNT(*) FROM dependencies d
           JOIN issues i ON d.issue_id = i.id
           WHERE d.depends_on_id = ? AND d.type = 'parent' AND i.status != 'closed'""",
        (parent_id,),
    )
    count = cursor.fetchone()[0]
    return count > 0


# Reorganization


def detect_cycle(db: sqlite3.Connection, issue_id: str, new_parent_id: str) -> bool:
    """Detect if reparenting would create a cycle.

    Args:
        db: Database connection
        issue_id: Issue to reparent
        new_parent_id: Proposed new parent

    Returns:
        True if cycle would be created
    """
    # Walk up from new_parent to see if we reach issue_id
    current = new_parent_id
    visited = set()

    while current:
        if current == issue_id:
            return True  # Cycle detected

        if current in visited:
            break  # Already checked this path

        visited.add(current)

        # Get parent of current issue
        deps = get_dependencies(db, current)
        parent_deps = [d for d in deps if d["type"] == "parent"]

        if not parent_deps:
            break  # No parent, end of chain

        current = parent_deps[0]["depends_on_id"]

    return False


def reparent_issue(
    db: sqlite3.Connection,
    issue_id: str,
    new_parent_id: Optional[str],
) -> None:
    """Change parent of an issue.

    Args:
        db: Database connection
        issue_id: Issue to reparent
        new_parent_id: New parent ID (None to remove parent)

    Raises:
        ValueError: If reparenting would create a cycle
    """
    # Check for cycle if setting a new parent
    if new_parent_id is not None:
        if detect_cycle(db, issue_id, new_parent_id):
            raise ValueError("Cannot reparent: would create a cycle")

    # Remove existing parent dependency
    db.execute(
        "DELETE FROM dependencies WHERE issue_id = ? AND type = 'parent'",
        (issue_id,),
    )

    # Add new parent dependency if specified
    if new_parent_id is not None:
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        db.execute(
            """INSERT INTO dependencies (issue_id, depends_on_id, type, created_at)
               VALUES (?, ?, 'parent', ?)""",
            (issue_id, new_parent_id, now),
        )

    db.commit()


def move_issue(
    db: sqlite3.Connection,
    old_id: str,
    new_project_id: str,
    new_project_name: str,
) -> str:
    """Move issue to different project.

    Args:
        db: Database connection
        old_id: Current issue ID
        new_project_id: Target project ID (path)
        new_project_name: Target project name

    Returns:
        New issue ID

    Notes:
        - Generates new ID in target project
        - Updates all dependencies pointing to old ID
        - Preserves all issue data and dependencies
        - Deletes old issue
    """
    # Get old issue
    old_issue = get_issue(db, old_id)
    if old_issue is None:
        raise ValueError(f"Issue {old_id} not found")

    # Get existing IDs in new project for collision detection
    cursor = db.execute(
        "SELECT id FROM issues WHERE id LIKE ?",
        (f"{new_project_name}-%",),
    )
    existing_ids = {row[0] for row in cursor.fetchall()}

    # Generate new ID
    new_id = generate_id(old_issue["title"], new_project_name, existing_ids=existing_ids)

    # Create new issue with same data
    db.execute(
        """INSERT INTO issues
           (id, project_id, title, description, status, priority, created_at, updated_at, closed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            new_id,
            new_project_id,
            old_issue["title"],
            old_issue["description"],
            old_issue["status"],
            old_issue["priority"],
            old_issue["created_at"],
            old_issue["updated_at"],
            old_issue["closed_at"],
        ),
    )

    # Copy dependencies (issue depends on others)
    old_deps = get_dependencies(db, old_id)
    for dep in old_deps:
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        db.execute(
            """INSERT INTO dependencies (issue_id, depends_on_id, type, created_at)
               VALUES (?, ?, ?, ?)""",
            (new_id, dep["depends_on_id"], dep["type"], now),
        )

    # Update dependencies where others depend on this issue
    db.execute(
        "UPDATE dependencies SET depends_on_id = ? WHERE depends_on_id = ?",
        (new_id, old_id),
    )

    # Delete old issue (cascade deletes its dependencies)
    db.execute("DELETE FROM issues WHERE id = ?", (old_id,))

    db.commit()

    return new_id


# JSONL Import/Export


def export_to_jsonl(
    db: sqlite3.Connection,
    project_id: str,
    jsonl_path: str,
) -> None:
    """Export project issues to JSONL file.

    Args:
        db: Database connection
        project_id: Project ID (URL or path)
        jsonl_path: Path to JSONL file to create

    Format:
        One JSON object per line, sorted by ID
        Includes dependencies inline
        DOES NOT include project_id (project identity from git context)
    """
    # Get all issues for project, sorted by ID
    cursor = db.execute(
        "SELECT * FROM issues WHERE project_id = ? ORDER BY id",
        (project_id,),
    )
    issues = [dict(row) for row in cursor.fetchall()]

    # Write to file
    path = Path(jsonl_path)
    with path.open("w") as f:
        for issue in issues:
            # Get dependencies for this issue
            deps_cursor = db.execute(
                "SELECT depends_on_id, type FROM dependencies WHERE issue_id = ? ORDER BY depends_on_id",
                (issue["id"],),
            )
            dependencies = [
                {"depends_on_id": row[0], "type": row[1]} for row in deps_cursor.fetchall()
            ]

            # Prepare issue data (exclude project_id for portability)
            issue_data = dict(issue)
            del issue_data["project_id"]  # Remove project_id for portability
            issue_data["dependencies"] = dependencies

            # Write as single JSON line
            f.write(json.dumps(issue_data) + "\n")


def import_from_jsonl(
    db: sqlite3.Connection,
    jsonl_path: str,
    project_id: str,
) -> Dict[str, int]:
    """Import issues from JSONL file.

    Args:
        db: Database connection
        jsonl_path: Path to JSONL file to import
        project_id: Project ID to assign to imported issues (from git context)

    Returns:
        Dict with stats: created, updated, errors

    Notes:
        - Creates issues that don't exist
        - Updates issues that already exist
        - Skips malformed lines and continues
        - Creates dependencies after all issues imported
        - Ignores project_id from JSONL if present (uses parameter instead)
    """
    stats = {"created": 0, "updated": 0, "errors": 0}
    path = Path(jsonl_path)

    if not path.exists():
        return stats

    # Read all issues first
    issues_to_import = []

    with path.open("r") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                issue_data = json.loads(line)
                issues_to_import.append(issue_data)
            except json.JSONDecodeError:
                stats["errors"] += 1
                # Continue processing other lines

    # Import issues (without dependencies first)
    for issue_data in issues_to_import:
        try:
            issue_id = issue_data["id"]

            # Check if issue exists
            existing = get_issue(db, issue_id)

            if existing is None:
                # Create new issue
                # Use project_id parameter, not from JSONL (for portability)
                db.execute(
                    """INSERT INTO issues
                       (id, project_id, title, description, status, priority, created_at, updated_at, closed_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        issue_data["id"],
                        project_id,  # Use parameter, not issue_data["project_id"]
                        issue_data["title"],
                        issue_data.get("description", ""),
                        issue_data.get("status", "open"),
                        issue_data.get("priority", 2),
                        issue_data["created_at"],
                        issue_data["updated_at"],
                        issue_data.get("closed_at"),
                    ),
                )
                stats["created"] += 1
            else:
                # Update existing issue
                db.execute(
                    """UPDATE issues
                       SET title = ?, description = ?, status = ?, priority = ?,
                           updated_at = ?, closed_at = ?
                       WHERE id = ?""",
                    (
                        issue_data["title"],
                        issue_data.get("description", ""),
                        issue_data.get("status", "open"),
                        issue_data.get("priority", 2),
                        issue_data["updated_at"],
                        issue_data.get("closed_at"),
                        issue_id,
                    ),
                )
                stats["updated"] += 1

        except Exception:
            stats["errors"] += 1

    db.commit()

    # Now import dependencies
    for issue_data in issues_to_import:
        try:
            issue_id = issue_data["id"]
            dependencies = issue_data.get("dependencies", [])

            # Clear existing dependencies for this issue
            db.execute("DELETE FROM dependencies WHERE issue_id = ?", (issue_id,))

            # Add new dependencies
            for dep in dependencies:
                now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                db.execute(
                    """INSERT OR IGNORE INTO dependencies (issue_id, depends_on_id, type, created_at)
                       VALUES (?, ?, ?, ?)""",
                    (issue_id, dep["depends_on_id"], dep["type"], now),
                )

        except Exception:
            # Dependency errors don't increment error count
            pass

    db.commit()

    return stats


# CLI


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


def get_db() -> sqlite3.Connection:
    """Get database connection, initializing if needed."""
    trace_home = get_trace_home()
    trace_home.mkdir(exist_ok=True)
    db_path = get_db_path()
    return init_database(str(db_path))


def get_project_path(db: sqlite3.Connection, project_id: str) -> Optional[str]:
    """Get filesystem path for a project_id.

    Args:
        db: Database connection
        project_id: Project ID (URL or path)

    Returns:
        Filesystem path, or None if not found

    Notes:
        - Looks up current_path from projects table
        - Falls back to project_id if it looks like a path (backward compat)
        - Detects and repairs corrupted current_path (URL instead of filesystem path)
    """
    cursor = db.execute(
        "SELECT current_path FROM projects WHERE id = ?",
        (project_id,)
    )
    row = cursor.fetchone()
    if row:
        current_path = row[0]
        # Validate that current_path is actually a filesystem path (not corrupted URL)
        if os.path.isabs(current_path):
            return current_path
        # current_path is corrupted (contains URL instead of path)
        # Try to recover by checking if CWD matches this project
        cwd_project = detect_project()
        if cwd_project and cwd_project["id"] == project_id:
            # CWD is this project - repair the DB and return correct path
            correct_path = cwd_project["path"]
            db.execute(
                "UPDATE projects SET current_path = ? WHERE id = ?",
                (correct_path, project_id)
            )
            db.commit()
            return correct_path
        # Can't recover - return None

    # Fallback: if project_id looks like an absolute path, use it
    if os.path.isabs(project_id) and Path(project_id).exists():
        return project_id

    return None


@app.command()
def init():
    """Initialize trace in current directory."""
    project = detect_project()

    if project is None:
        print("Error: Not in a git repository")
        print("Run 'git init' first or use 'trc init' inside a git repo")
        raise typer.Exit(code=1)

    # Create .trace directory
    trace_dir = Path(project["path"]) / ".trace"
    trace_dir.mkdir(exist_ok=True)

    # Create empty issues.jsonl
    jsonl_path = trace_dir / "issues.jsonl"
    if not jsonl_path.exists():
        jsonl_path.write_text("")

    # Register project in central database (new schema: id, name, current_path)
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO projects (id, name, current_path) VALUES (?, ?, ?)",
        (project["id"], project["name"], project["path"]),
    )
    db.commit()
    db.close()

    print(f"Initialized trace for project: {project['name']}")
    print(f"Project ID: {project['id']}")
    print(f"Path: {project['path']}")
    print(f"JSONL: {jsonl_path}")


@app.command()
def create(
    title: Annotated[str, typer.Argument(help="Issue title")],
    description: Annotated[str, typer.Option(help="Detailed description (required)")],
    priority: Annotated[int, typer.Option(help="Priority level (0-4)")] = 2,
    status: Annotated[str, typer.Option(help="Initial status")] = "open",
    parent: Annotated[Optional[str], typer.Option(help="Parent issue ID")] = None,
    depends_on: Annotated[Optional[str], typer.Option(help="Blocking dependency ID")] = None,
    project_flag: Annotated[Optional[str], typer.Option("--project", help="Target project (name or path)")] = None,
):
    """Create a new issue."""
    # Resolve target project
    if project_flag:
        # Look up in registry by name or path
        db = get_db()
        project = resolve_project(project_flag, db)

        if project is None:
            print(f"Error: Project '{project_flag}' not found in registry")
            print("Hint: Run 'trc init' in the target project first")
            db.close()
            raise typer.Exit(code=1)

        db.close()
    else:
        # Use current directory detection
        project = detect_project()

        if project is None:
            print("Error: Not in a git repository")
            print("Run 'trc init' first or use --project <name>")
            raise typer.Exit(code=1)

    # Check if project is initialized (TRANSACTION SAFETY)
    if not is_project_initialized(project["path"]):
        print("Error: Project not initialized")
        print(f"Run 'trc init' in {project['path']} first")
        raise typer.Exit(code=1)

    lock_path = get_lock_path()

    with file_lock(lock_path):
        db = get_db()

        # Sync before operation
        sync_project(db, project["path"])

        # Create issue (use project["id"] for database)
        issue = create_issue(
            db,
            project["id"],  # Use project_id (URL or path)
            project["name"],
            title,
            description=description,
            priority=priority,
            status=status,
        )

        if not issue:
            print("Error: Failed to create issue")
            db.close()
            raise typer.Exit(code=1)

        # Add parent dependency if specified
        if parent:
            add_dependency(db, issue["id"], parent, "parent")

        # Add blocking dependency if specified
        if depends_on:
            add_dependency(db, issue["id"], depends_on, "blocks")

        # Export to JSONL (use project["id"] for database, project["path"] for filesystem)
        trace_dir = Path(project["path"]) / ".trace"
        jsonl_path = trace_dir / "issues.jsonl"
        export_to_jsonl(db, project["id"], str(jsonl_path))
        set_last_sync_time(db, project["id"], time.time())

        print(f"Created {issue['id']}: {title}")
        if parent:
            print(f"  Parent: {parent}")
        if depends_on:
            print(f"  Depends-on: {depends_on}")

        db.close()


@app.command(name="list")
def list_cmd(
    project: Annotated[Optional[str], typer.Option(help="Filter by project - name or path (use 'any' for all projects)")] = None,
    status: Annotated[Optional[list[str]], typer.Option(help="Filter by status (can specify multiple times, use 'any' for all statuses)")] = None,
):
    """List issues."""
    lock_path = get_lock_path()

    with file_lock(lock_path):
        db = get_db()

        # Resolve status filter
        # Default to backlog (exclude closed) when no --status provided
        if status is None or len(status) == 0:
            status_filter = ["open", "in_progress", "blocked"]
        elif len(status) == 1 and status[0] == "any":
            # Special case: --status any means show all statuses
            status_filter = None
        else:
            # Use provided status(es)
            status_filter = status

        # Handle --project flag
        if project == "any":
            # List all issues across all projects
            issues = list_issues(db, status=status_filter)
        elif project is not None:
            # Look up specific project by name or path
            target_project = resolve_project(project, db)
            if target_project is None:
                print(f"Error: Project '{project}' not found in registry")
                print("Hint: Run 'trc list --project any' to see all projects")
                db.close()
                raise typer.Exit(code=1)

            sync_project(db, target_project["path"])
            issues = list_issues(db, project_id=target_project["id"], status=status_filter)
        else:
            # No --project flag, use current directory
            current_project = detect_project()
            if current_project is None:
                print("Error: Not in a git repository. Use --project any to list all issues.")
                db.close()
                raise typer.Exit(code=1)

            # Sync before operation
            sync_project(db, current_project["path"])

            # Use project["id"] for database query
            issues = list_issues(db, project_id=current_project["id"], status=status_filter)

        if not issues:
            print("No issues found")
            db.close()
            return

        # Print issues
        for issue in issues:
            status_marker = {
                "open": "○",
                "in_progress": "◐",
                "closed": "●",
                "blocked": "⊘",
            }.get(issue["status"], "?")

            priority_label = f"P{issue['priority']}"

            print(f"{status_marker} {issue['id']} [{priority_label}] {issue['title']}")

        db.close()


@app.command()
def show(issue_id: Annotated[str, typer.Argument(help="Issue ID")]):
    """Show issue details."""
    lock_path = get_lock_path()

    with file_lock(lock_path):
        db = get_db()

        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            raise typer.Exit(code=1)

        # Sync before operation - use get_project_path to convert project_id to filesystem path
        project_path = get_project_path(db, issue["project_id"])
        if project_path:
            sync_project(db, project_path)

        # Re-fetch after sync
        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            raise typer.Exit(code=1)

        # Get dependencies
        deps = get_dependencies(db, issue_id)
        children = get_children(db, issue_id)

        # Print issue details
        print(f"ID:          {issue['id']}")
        print(f"Title:       {issue['title']}")
        print(f"Status:      {issue['status']}")
        print(f"Priority:    {issue['priority']}")
        print(f"Project:     {issue['project_id']}")
        print(f"Created:     {issue['created_at']}")
        print(f"Updated:     {issue['updated_at']}")

        if issue["description"]:
            print(f"\nDescription:\n{issue['description']}")

        if deps:
            print("\nDependencies:")
            for dep in deps:
                dep_issue = get_issue(db, dep["depends_on_id"])
                dep_title = dep_issue["title"] if dep_issue else "(unknown)"
                print(f"  {dep['type']:8} {dep['depends_on_id']} - {dep_title}")

        if children:
            print("\nChildren:")
            for child in children:
                status_marker = {
                    "open": "○",
                    "in_progress": "◐",
                    "closed": "●",
                    "blocked": "⊘",
                }.get(child["status"], "?")
                print(f"  {status_marker} {child['id']} - {child['title']}")

        db.close()


@app.command()
def close(issue_ids: Annotated[list[str], typer.Argument(help="Issue ID(s) to close")]):
    """Close one or more issues."""
    lock_path = get_lock_path()

    with file_lock(lock_path):
        db = get_db()

        # Track which projects need JSONL export
        projects_to_export: Set[str] = set()
        closed_issues = []
        errors = []

        for issue_id in issue_ids:
            issue = get_issue(db, issue_id)
            if issue is None:
                errors.append(f"Warning: Issue {issue_id} not found")
                continue

            # Get project path for filesystem operations
            project_id = issue["project_id"]
            project_path = get_project_path(db, project_id)
            if not project_path:
                errors.append(f"Warning: Cannot find project path for {project_id}")
                continue

            # Check if project is initialized (TRANSACTION SAFETY)
            if not is_project_initialized(project_path):
                errors.append(f"Warning: Project not initialized for {issue_id}: {project_path}")
                continue

            # Sync before operation (once per project)
            if project_id not in projects_to_export:
                sync_project(db, project_path)

            # Re-fetch after sync
            issue = get_issue(db, issue_id)
            if issue is None:
                errors.append(f"Warning: Issue {issue_id} not found after sync")
                continue

            # Check for open children
            if has_open_children(db, issue_id):
                children = get_children(db, issue_id)
                open_children = [c for c in children if c["status"] != "closed"]
                error_msg = f"Warning: Cannot close {issue_id} with open children:"
                for child in open_children:
                    error_msg += f"\n  - {child['id']}: {child['title']} [{child['status']}]"
                errors.append(error_msg)
                continue

            # Close the issue
            close_issue(db, issue_id)
            closed_issues.append((issue_id, issue['title']))
            projects_to_export.add(project_id)

        # Export to JSONL for all affected projects
        for project_id in projects_to_export:
            project_path = get_project_path(db, project_id)
            if project_path:
                trace_dir = Path(project_path) / ".trace"
                jsonl_path = trace_dir / "issues.jsonl"
                export_to_jsonl(db, project_id, str(jsonl_path))
                set_last_sync_time(db, project_id, time.time())

        db.close()

        # Print errors first
        for error in errors:
            print(error)

        # Print successfully closed issues
        for issue_id, title in closed_issues:
            print(f"Closed {issue_id}: {title}")

        # Exit with error if nothing was closed
        if not closed_issues and errors:
            raise typer.Exit(code=1)


@app.command()
def ready(
    project: Annotated[Optional[str], typer.Option(help="Filter by project - name or path (use 'any' for all projects)")] = None,
    status: Annotated[Optional[str], typer.Option(help="Filter by status (defaults to 'open', use 'any' for all)")] = None,
):
    """Show ready work (not blocked)."""
    lock_path = get_lock_path()

    with file_lock(lock_path):
        db = get_db()

        # Default status to "open" if not specified
        if status is None:
            status = "open"

        # Resolve status filter
        status_filter = None if status == "any" else status

        # Handle --project flag
        if project == "any":
            # Get all issues across all projects
            issues = list_issues(db, status=status_filter)
        elif project is not None:
            # Look up specific project by name or path
            target_project = resolve_project(project, db)
            if target_project is None:
                print(f"Error: Project '{project}' not found in registry")
                print("Hint: Run 'trc ready --project any' to see all ready work")
                db.close()
                raise typer.Exit(code=1)

            sync_project(db, target_project["path"])
            issues = list_issues(db, project_id=target_project["id"], status=status_filter)
        else:
            # No --project flag, use current directory
            current_project = detect_project()
            if current_project is None:
                print("Error: Not in a git repository. Use --project any to see all ready work.")
                db.close()
                raise typer.Exit(code=1)

            # Sync before operation
            sync_project(db, current_project["path"])

            # Use project["id"] for database query
            issues = list_issues(db, project_id=current_project["id"], status=status_filter)

        if not issues:
            print("No open issues found")
            db.close()
            return

        # Filter to only ready (not blocked) issues
        ready_issues = []
        for issue in issues:
            if not is_blocked(db, issue["id"]):
                ready_issues.append(issue)

        if not ready_issues:
            print("No ready work (all issues are blocked)")
            db.close()
            return

        # Print ready issues
        print("Ready work (not blocked):\n")
        for issue in ready_issues:
            priority_label = f"P{issue['priority']}"
            print(f"○ {issue['id']} [{priority_label}] {issue['title']}")

            # Show what it depends on (parent)
            deps = get_dependencies(db, issue["id"])
            parent_deps = [d for d in deps if d["type"] == "parent"]
            if parent_deps:
                for dep in parent_deps:
                    parent = get_issue(db, dep["depends_on_id"])
                    if parent:
                        print(f"   └─ child of: {parent['id']} - {parent['title']}")

        db.close()


@app.command()
def tree(
    issue_id: Annotated[str, typer.Argument(help="Issue ID")],
    max_depth: Annotated[int, typer.Option(help="Maximum depth to display")] = 10,
):
    """Show issue tree (parent-child hierarchy)."""
    lock_path = get_lock_path()

    with file_lock(lock_path):
        db = get_db()

        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            raise typer.Exit(code=1)

        # Get project path and sync
        project_path = get_project_path(db, issue["project_id"])
        if project_path:
            sync_project(db, project_path)

        # Re-fetch after sync
        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            raise typer.Exit(code=1)

        def print_tree(issue_id, depth=0, prefix="", is_last=True):
            """Recursively print issue tree."""
            if depth > max_depth:
                return

            issue = get_issue(db, issue_id)
            if not issue:
                return

            # Status marker
            status_marker = {
                "open": "○",
                "in_progress": "◐",
                "closed": "●",
                "blocked": "⊘",
            }.get(issue["status"], "?")

            # Tree connector
            connector = "└─ " if is_last else "├─ "
            if depth == 0:
                connector = ""

            # Print issue
            indent = prefix
            print(f"{indent}{connector}{status_marker} {issue['id']} - {issue['title']} [{issue['status']}]")

            # Get children
            children = get_children(db, issue_id)

            if children:
                # Update prefix for children
                child_prefix = prefix + ("   " if is_last or depth == 0 else "│  ")

                for i, child in enumerate(children):
                    is_last_child = (i == len(children) - 1)
                    print_tree(child["id"], depth + 1, child_prefix, is_last_child)

        # Start printing from root
        print_tree(issue_id)

        db.close()


@app.command()
def update(
    issue_id: Annotated[str, typer.Argument(help="Issue ID")],
    title: Annotated[Optional[str], typer.Option(help="Set title")] = None,
    description: Annotated[Optional[str], typer.Option(help="Set description")] = None,
    priority: Annotated[Optional[int], typer.Option(help="Set priority (0-4)")] = None,
    status: Annotated[Optional[str], typer.Option(help="Set status")] = None,
):
    """Update an issue."""
    lock_path = get_lock_path()

    with file_lock(lock_path):
        db = get_db()

        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            raise typer.Exit(code=1)

        # Get project path and sync
        project_path = get_project_path(db, issue["project_id"])
        if project_path:
            # Check if project is initialized (TRANSACTION SAFETY)
            if not is_project_initialized(project_path):
                print("Error: Project not initialized")
                print(f"Run 'trc init' in {project_path} first")
                db.close()
                raise typer.Exit(code=1)

            sync_project(db, project_path)

        # Re-fetch after sync
        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            raise typer.Exit(code=1)

        # Update issue
        try:
            update_issue(db, issue_id, title=title, description=description, priority=priority, status=status)
        except ValueError as e:
            print(f"Error: {e}")
            db.close()
            raise typer.Exit(code=1)

        # Export to JSONL
        project_id = issue["project_id"]
        project_path = get_project_path(db, project_id)
        if not project_path:
            print(f"Error: Cannot find project path for {project_id}")
            db.close()
            raise typer.Exit(code=1)

        trace_dir = Path(project_path) / ".trace"
        jsonl_path = trace_dir / "issues.jsonl"
        export_to_jsonl(db, project_id, str(jsonl_path))
        set_last_sync_time(db, project_id, time.time())

        updated = get_issue(db, issue_id)
        if updated:
            print(f"Updated {issue_id}:")
            if title:
                print(f"  Title: {updated['title']}")
            if description is not None:
                print(f"  Description: {updated['description']}")
            if priority is not None:
                print(f"  Priority: {updated['priority']}")
            if status:
                print(f"  Status: {updated['status']}")

        db.close()


@app.command()
def reparent(
    issue_id: Annotated[str, typer.Argument(help="Issue ID")],
    new_parent_id: Annotated[str, typer.Argument(help="New parent ID (use 'none' to remove)")],
):
    """Change parent of an issue."""
    # Handle 'none' as None
    parent_id = None if new_parent_id.lower() == "none" else new_parent_id

    lock_path = get_lock_path()

    with file_lock(lock_path):
        db = get_db()

        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            raise typer.Exit(code=1)

        # Get project path and sync
        project_id = issue["project_id"]
        project_path = get_project_path(db, project_id)
        if not project_path:
            print(f"Error: Cannot find project path for {project_id}")
            db.close()
            raise typer.Exit(code=1)

        # Check if project is initialized (TRANSACTION SAFETY)
        if not is_project_initialized(project_path):
            print("Error: Project not initialized")
            print(f"Run 'trc init' in {project_path} first")
            db.close()
            raise typer.Exit(code=1)

        sync_project(db, project_path)

        # Re-fetch after sync
        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            raise typer.Exit(code=1)

        # Validate new parent exists if provided
        if parent_id is not None:
            new_parent = get_issue(db, parent_id)
            if new_parent is None:
                print(f"Error: Parent issue {parent_id} not found")
                db.close()
                raise typer.Exit(code=1)

        # Reparent with cycle detection
        try:
            reparent_issue(db, issue_id, parent_id)
        except ValueError as e:
            print(f"Error: {e}")
            db.close()
            raise typer.Exit(code=1)

        # Export to JSONL for the issue's project
        trace_dir = Path(project_path) / ".trace"
        jsonl_path = trace_dir / "issues.jsonl"
        export_to_jsonl(db, project_id, str(jsonl_path))
        set_last_sync_time(db, project_id, time.time())

        # Print confirmation
        if parent_id is None:
            print(f"Removed parent from {issue_id}")
        else:
            print(f"Reparented {issue_id} to {parent_id}")

        db.close()


@app.command(name="add-dependency")
def add_dependency_cmd(
    issue_id: Annotated[str, typer.Argument(help="Issue ID")],
    depends_on_id: Annotated[str, typer.Argument(help="Issue that is depended upon")],
    dep_type: Annotated[str, typer.Option("--type", help="Dependency type (blocks, parent, related)")] = "blocks",
):
    """Add a dependency between two existing issues."""
    lock_path = get_lock_path()

    with file_lock(lock_path):
        db = get_db()

        # Validate both issues exist
        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            raise typer.Exit(code=1)

        depends_on = get_issue(db, depends_on_id)
        if depends_on is None:
            print(f"Error: Issue {depends_on_id} not found")
            db.close()
            raise typer.Exit(code=1)

        # Get project paths for sync
        issue_project_id = issue["project_id"]
        issue_project_path = get_project_path(db, issue_project_id)
        if not issue_project_path:
            print(f"Error: Cannot find project path for {issue_project_id}")
            db.close()
            raise typer.Exit(code=1)

        # Check if issue project is initialized (TRANSACTION SAFETY)
        if not is_project_initialized(issue_project_path):
            print("Error: Project not initialized")
            print(f"Run 'trc init' in {issue_project_path} first")
            db.close()
            raise typer.Exit(code=1)

        depends_project_id = depends_on["project_id"]
        depends_project_path = get_project_path(db, depends_project_id)

        # Check if depends_on project is initialized (if different project)
        if depends_project_id != issue_project_id and depends_project_path:
            if not is_project_initialized(depends_project_path):
                print("Error: Dependency project not initialized")
                print(f"Run 'trc init' in {depends_project_path} first")
                db.close()
                raise typer.Exit(code=1)

        # Sync both projects before operation
        sync_project(db, issue_project_path)
        if depends_project_id != issue_project_id and depends_project_path:
            sync_project(db, depends_project_path)

        # Re-fetch after sync
        issue = get_issue(db, issue_id)
        depends_on = get_issue(db, depends_on_id)

        if issue is None or depends_on is None:
            print("Error: Issue not found after sync")
            db.close()
            raise typer.Exit(code=1)

        # Add dependency
        try:
            add_dependency(db, issue_id, depends_on_id, dep_type)
        except ValueError as e:
            print(f"Error: {e}")
            db.close()
            raise typer.Exit(code=1)

        # Export to JSONL for the issue's project
        trace_dir = Path(issue_project_path) / ".trace"
        jsonl_path = trace_dir / "issues.jsonl"
        export_to_jsonl(db, issue_project_id, str(jsonl_path))
        set_last_sync_time(db, issue_project_id, time.time())

        # Also export for depends_on project if different
        if depends_project_id != issue_project_id and depends_project_path:
            depends_trace_dir = Path(depends_project_path) / ".trace"
            depends_jsonl_path = depends_trace_dir / "issues.jsonl"
            export_to_jsonl(db, depends_project_id, str(depends_jsonl_path))
            set_last_sync_time(db, depends_project_id, time.time())

        # Print clear dependency message based on type
        if dep_type == "blocks":
            print(f"{issue_id} is blocked by {depends_on_id}")
        elif dep_type == "parent":
            print(f"Set {depends_on_id} as parent of {issue_id}")
        elif dep_type == "related":
            print(f"Linked {issue_id} ↔ {depends_on_id} (related)")
        else:
            # Fallback for unknown types
            print(f"Added {dep_type} dependency: {issue_id} → {depends_on_id}")

        db.close()


@app.command()
def move(
    issue_id: Annotated[str, typer.Argument(help="Issue ID")],
    target_project_name: Annotated[str, typer.Argument(help="Target project (name or path)")],
):
    """Move issue to different project."""
    lock_path = get_lock_path()

    with file_lock(lock_path):
        db = get_db()

        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            raise typer.Exit(code=1)

        # Get source project info (new schema: id, name, current_path)
        old_project_id = issue["project_id"]
        cursor = db.execute(
            "SELECT current_path FROM projects WHERE id = ?",
            (old_project_id,),
        )
        row = cursor.fetchone()
        if row:
            old_project_path = row[0]
            # Check if old project is initialized (TRANSACTION SAFETY)
            if not is_project_initialized(old_project_path):
                print("Error: Source project not initialized")
                print(f"Run 'trc init' in {old_project_path} first")
                db.close()
                raise typer.Exit(code=1)
            # Sync source project before operation
            sync_project(db, old_project_path)
        else:
            # Project not in registry, assume project_id is a path (backward compat)
            old_project_path = old_project_id
            if Path(old_project_path).exists():
                if not is_project_initialized(old_project_path):
                    print("Error: Source project not initialized")
                    print(f"Run 'trc init' in {old_project_path} first")
                    db.close()
                    raise typer.Exit(code=1)
                sync_project(db, old_project_path)

        # Re-fetch after sync
        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            raise typer.Exit(code=1)

        # Look up target project by name or path
        target_project = resolve_project(target_project_name, db)

        if target_project is None:
            print(f"Error: Project '{target_project_name}' not found in registry")
            print("Hint: Run 'trc init' in the target project first")
            db.close()
            raise typer.Exit(code=1)

        new_project_id = target_project["id"]
        new_project_name = target_project["name"]
        new_project_path = target_project["path"]

        # Check if target project is initialized (TRANSACTION SAFETY)
        if not is_project_initialized(new_project_path):
            print("Error: Target project not initialized")
            print(f"Run 'trc init' in {new_project_path} first")
            db.close()
            raise typer.Exit(code=1)

        # Sync target project before operation
        sync_project(db, new_project_path)

        # Move issue
        try:
            new_id = move_issue(db, issue_id, new_project_id, new_project_name)
        except ValueError as e:
            print(f"Error: {e}")
            db.close()
            raise typer.Exit(code=1)

        # Export to JSONL for both projects
        old_trace_dir = Path(old_project_path) / ".trace"
        old_jsonl = old_trace_dir / "issues.jsonl"
        export_to_jsonl(db, old_project_id, str(old_jsonl))
        set_last_sync_time(db, old_project_id, time.time())

        new_trace_dir = Path(new_project_path) / ".trace"
        new_trace_dir.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
        new_jsonl = new_trace_dir / "issues.jsonl"
        export_to_jsonl(db, new_project_id, str(new_jsonl))
        set_last_sync_time(db, new_project_id, time.time())

        print(f"Moved {issue_id} → {new_id}")
        print(f"  From: {old_project_id} ({old_project_path})")
        print(f"  To:   {new_project_id} ({new_project_path})")

        db.close()


@app.command()
def guide():
    """Display AI agent integration guide."""
    guide_text = """
═══════════════════════════════════════════════════════════════════════════════
                    Trace (trc) - AI Agent Integration Guide
═══════════════════════════════════════════════════════════════════════════════

Add this to your project's CLAUDE.md file for AI agent integration:

───────────────────────────────────────────────────────────────────────────────

## Using Trace for Work Tracking

This project uses [Trace](https://github.com/dschartman/trace) for persistent
work tracking across AI sessions.

**When to use trace vs TodoWrite:**

Use trace instead of TodoWrite for any non-trivial work. If it involves multiple
files, could span sessions, or needs to persist - use trace.

- **TodoWrite**: Single-session trivial tasks only
- **Trace**: Everything else (features, bugs, planning, multi-step work)
- **When in doubt**: Use trace

**Why this matters:** Trace persists across sessions and commits to git. TodoWrite
is ephemeral. For a tool designed around persistent work tracking, using TodoWrite
defeats the purpose.

**Setup (required once per project):**

```bash
trc init  # Run this first in your git repo
```

If you forget, you'll see: "Error: Project not initialized. Run 'trc init' first"

**Core workflow:**

```bash
# Create work
trc create "title" --description "context"
trc create "subtask" --description "details" --parent <id>

# Discover work
trc ready              # What's unblocked and ready to work on
trc list               # Current backlog (excludes closed)
trc show <id>          # Full details with dependencies

# Complete work
trc close <id> [...]   # Close one or more issues
```

**Essential details:**

- `--description` is required (preserves context across sessions for AI agents)
  - Use `--description ""` to explicitly skip if truly not needed
- Structure is fluid: Break down or reorganize as understanding evolves
- Use `--parent <id>` to create hierarchical breakdowns
- Cross-project: Add `--project <name>` to work across repositories
- Use `trc <command> --help` for full options

───────────────────────────────────────────────────────────────────────────────

For more details: https://github.com/dschartman/trace
"""
    print(guide_text)


def main():
    """Main CLI entry point."""
    app()


if __name__ == "__main__":
    main()
