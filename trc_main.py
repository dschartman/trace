"""Trace - Minimal distributed issue tracker for AI agent workflows."""

import fcntl
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Set, Dict


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
    then extracts project name from git remote or directory name.

    Args:
        cwd: Optional current working directory (defaults to os.getcwd())

    Returns:
        Dict with 'name' and 'path' keys, or None if not in a git repo

    Example:
        >>> project = detect_project()
        >>> if project:
        ...     print(f"{project['name']} at {project['path']}")
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

            # Try to extract name from git remote
            project_name = _extract_name_from_git_remote(git_dir)

            # Fall back to directory name if no remote found
            if not project_name:
                project_name = parent.name

            # Sanitize the project name
            project_name = sanitize_project_name(project_name)

            return {"name": project_name, "path": project_path}

    # Not in a git repository
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

        -- Projects: Registry of all tracked projects
        CREATE TABLE IF NOT EXISTS projects (
            name TEXT PRIMARY KEY,
            path TEXT NOT NULL UNIQUE,
            git_remote TEXT
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
        conn.execute("INSERT INTO metadata (key, value) VALUES ('schema_version', '1')")
        conn.commit()

    return conn


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
    """
    trace_dir = Path(project_path) / ".trace"
    jsonl_path = trace_dir / "issues.jsonl"

    if not jsonl_path.exists():
        return

    # Check if JSONL is newer than last sync
    jsonl_mtime = jsonl_path.stat().st_mtime
    last_sync = get_last_sync_time(db, project_path)

    if last_sync is None or jsonl_mtime > last_sync:
        # JSONL is newer, import it
        import_from_jsonl(db, str(jsonl_path))
        set_last_sync_time(db, project_path, jsonl_mtime)


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
    status: Optional[str] = None,
) -> list[Dict[str, Any]]:
    """List issues with optional filtering.

    Args:
        db: Database connection
        project_id: Filter by project (optional)
        status: Filter by status (optional)

    Returns:
        List of issue dicts, sorted by priority then created_at (desc)
    """
    query = "SELECT * FROM issues WHERE 1=1"
    params = []

    if project_id is not None:
        query += " AND project_id = ?"
        params.append(project_id)

    if status is not None:
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
        project_id: Project ID (absolute path)
        jsonl_path: Path to JSONL file to create

    Format:
        One JSON object per line, sorted by ID
        Includes dependencies inline
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

            # Add dependencies to issue dict
            issue_data = dict(issue)
            issue_data["dependencies"] = dependencies

            # Write as single JSON line
            f.write(json.dumps(issue_data) + "\n")


def import_from_jsonl(
    db: sqlite3.Connection,
    jsonl_path: str,
) -> Dict[str, int]:
    """Import issues from JSONL file.

    Args:
        db: Database connection
        jsonl_path: Path to JSONL file to import

    Returns:
        Dict with stats: created, updated, errors

    Notes:
        - Creates issues that don't exist
        - Updates issues that already exist
        - Skips malformed lines and continues
        - Creates dependencies after all issues imported
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
                db.execute(
                    """INSERT INTO issues
                       (id, project_id, title, description, status, priority, created_at, updated_at, closed_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        issue_data["id"],
                        issue_data["project_id"],
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
    """Get the trace home directory (~/.trace)."""
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


def cli_init():
    """Initialize trace in current directory."""
    project = detect_project()

    if project is None:
        print("Error: Not in a git repository")
        print("Run 'git init' first or use 'trc init' inside a git repo")
        return 1

    # Create .trace directory
    trace_dir = Path(project["path"]) / ".trace"
    trace_dir.mkdir(exist_ok=True)

    # Create empty issues.jsonl
    jsonl_path = trace_dir / "issues.jsonl"
    if not jsonl_path.exists():
        jsonl_path.write_text("")

    # Register project in central database
    db = get_db()
    db.execute(
        "INSERT OR IGNORE INTO projects (name, path) VALUES (?, ?)",
        (project["name"], project["path"]),
    )
    db.commit()
    db.close()

    print(f"Initialized trace for project: {project['name']}")
    print(f"Path: {project['path']}")
    print(f"JSONL: {jsonl_path}")

    return 0


def cli_create(title: str, description: str = "", priority: int = 2, status: str = "open",
               parent: Optional[str] = None, depends_on: Optional[str] = None):
    """Create a new issue."""
    project = detect_project()

    if project is None:
        print("Error: Not in a git repository")
        print("Run 'trc init' first")
        return 1

    lock_path = get_lock_path()

    with file_lock(lock_path):
        db = get_db()

        # Sync before operation
        sync_project(db, project["path"])

        # Create issue
        issue = create_issue(
            db,
            project["path"],
            project["name"],
            title,
            description=description,
            priority=priority,
            status=status,
        )

        if not issue:
            print("Error: Failed to create issue")
            db.close()
            return 1

        # Add parent dependency if specified
        if parent:
            add_dependency(db, issue["id"], parent, "parent")

        # Add blocking dependency if specified
        if depends_on:
            add_dependency(db, issue["id"], depends_on, "blocks")

        # Export to JSONL
        trace_dir = Path(project["path"]) / ".trace"
        jsonl_path = trace_dir / "issues.jsonl"
        export_to_jsonl(db, project["path"], str(jsonl_path))
        set_last_sync_time(db, project["path"], time.time())

        print(f"Created {issue['id']}: {title}")
        if parent:
            print(f"  Parent: {parent}")
        if depends_on:
            print(f"  Depends-on: {depends_on}")

        db.close()

    return 0


def cli_list(all_projects: bool = False, status: Optional[str] = None):
    """List issues."""
    lock_path = get_lock_path()

    with file_lock(lock_path):
        db = get_db()

        if all_projects:
            # List all issues across all projects
            issues = list_issues(db, status=status)
        else:
            # List issues for current project
            project = detect_project()
            if project is None:
                print("Error: Not in a git repository. Use --all to list all issues.")
                db.close()
                return 1

            # Sync before operation
            sync_project(db, project["path"])

            issues = list_issues(db, project_id=project["path"], status=status)

        if not issues:
            print("No issues found")
            db.close()
            return 0

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

    return 0


def cli_show(issue_id: str):
    """Show issue details."""
    lock_path = get_lock_path()

    with file_lock(lock_path):
        db = get_db()

        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            return 1

        # Sync before operation
        sync_project(db, issue["project_id"])

        # Re-fetch after sync
        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            return 1

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

    return 0


def cli_close(issue_id: str):
    """Close an issue."""
    lock_path = get_lock_path()

    with file_lock(lock_path):
        db = get_db()

        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            return 1

        # Sync before operation
        sync_project(db, issue["project_id"])

        # Re-fetch after sync
        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            return 1

        # Check for open children
        if has_open_children(db, issue_id):
            children = get_children(db, issue_id)
            open_children = [c for c in children if c["status"] != "closed"]
            print("Error: Cannot close issue with open children:")
            for child in open_children:
                print(f"  - {child['id']}: {child['title']} [{child['status']}]")
            db.close()
            return 1

        # Close the issue
        close_issue(db, issue_id)

        # Export to JSONL
        project_path = issue["project_id"]
        trace_dir = Path(project_path) / ".trace"
        jsonl_path = trace_dir / "issues.jsonl"
        export_to_jsonl(db, project_path, str(jsonl_path))
        set_last_sync_time(db, project_path, time.time())

        print(f"Closed {issue_id}: {issue['title']}")

        db.close()

    return 0


def cli_ready(all_projects: bool = False):
    """Show ready work (not blocked)."""
    lock_path = get_lock_path()

    with file_lock(lock_path):
        db = get_db()

        if all_projects:
            # Get all open issues
            issues = list_issues(db, status="open")
        else:
            project = detect_project()
            if project is None:
                print("Error: Not in a git repository. Use --all to see all ready work.")
                db.close()
                return 1

            # Sync before operation
            sync_project(db, project["path"])

            issues = list_issues(db, project_id=project["path"], status="open")

        if not issues:
            print("No open issues found")
            db.close()
            return 0

        # Filter to only ready (not blocked) issues
        ready_issues = []
        for issue in issues:
            if not is_blocked(db, issue["id"]):
                ready_issues.append(issue)

        if not ready_issues:
            print("No ready work (all issues are blocked)")
            db.close()
            return 0

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

    return 0


def cli_tree(issue_id: str, max_depth: int = 10):
    """Show issue tree (parent-child hierarchy)."""
    lock_path = get_lock_path()

    with file_lock(lock_path):
        db = get_db()

        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            return 1

        # Sync before operation
        sync_project(db, issue["project_id"])

        # Re-fetch after sync
        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            return 1

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

    return 0


def cli_update(issue_id: str, title: Optional[str] = None, description: Optional[str] = None,
               priority: Optional[int] = None, status: Optional[str] = None):
    """Update an issue."""
    lock_path = get_lock_path()

    with file_lock(lock_path):
        db = get_db()

        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            return 1

        # Sync before operation
        sync_project(db, issue["project_id"])

        # Re-fetch after sync
        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            return 1

        # Update issue
        try:
            update_issue(db, issue_id, title=title, description=description, priority=priority, status=status)
        except ValueError as e:
            print(f"Error: {e}")
            db.close()
            return 1

        # Export to JSONL
        project_path = issue["project_id"]
        trace_dir = Path(project_path) / ".trace"
        jsonl_path = trace_dir / "issues.jsonl"
        export_to_jsonl(db, project_path, str(jsonl_path))
        set_last_sync_time(db, project_path, time.time())

        updated = get_issue(db, issue_id)
        if updated:
            print(f"Updated {issue_id}:")
            if title:
                print(f"  Title: {updated['title']}")
            if priority is not None:
                print(f"  Priority: {updated['priority']}")
            if status:
                print(f"  Status: {updated['status']}")

        db.close()

    return 0


def cli_reparent(issue_id: str, new_parent_id: Optional[str]):
    """Change parent of an issue."""
    lock_path = get_lock_path()

    with file_lock(lock_path):
        db = get_db()

        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            return 1

        # Sync before operation
        sync_project(db, issue["project_id"])

        # Re-fetch after sync
        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            return 1

        # Validate new parent exists if provided
        if new_parent_id is not None:
            new_parent = get_issue(db, new_parent_id)
            if new_parent is None:
                print(f"Error: Parent issue {new_parent_id} not found")
                db.close()
                return 1

        # Reparent with cycle detection
        try:
            reparent_issue(db, issue_id, new_parent_id)
        except ValueError as e:
            print(f"Error: {e}")
            db.close()
            return 1

        # Export to JSONL for the issue's project
        project_path = issue["project_id"]
        trace_dir = Path(project_path) / ".trace"
        jsonl_path = trace_dir / "issues.jsonl"
        export_to_jsonl(db, project_path, str(jsonl_path))
        set_last_sync_time(db, project_path, time.time())

        # Print confirmation
        if new_parent_id is None:
            print(f"Removed parent from {issue_id}")
        else:
            print(f"Reparented {issue_id} to {new_parent_id}")

        db.close()

    return 0


def cli_move(issue_id: str, target_project_name: str):
    """Move issue to different project."""
    lock_path = get_lock_path()

    with file_lock(lock_path):
        db = get_db()

        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            return 1

        # Sync source project before operation
        sync_project(db, issue["project_id"])

        # Re-fetch after sync
        issue = get_issue(db, issue_id)
        if issue is None:
            print(f"Error: Issue {issue_id} not found")
            db.close()
            return 1

        # Get source project path
        old_project_path = issue["project_id"]

        # Try to detect target project by name from registry
        cursor = db.execute(
            "SELECT path, name FROM projects WHERE name = ?",
            (target_project_name,),
        )
        row = cursor.fetchone()

        if row is None:
            print(f"Error: Project '{target_project_name}' not found in registry")
            print("Hint: Run 'trc init' in the target project first")
            db.close()
            return 1

        new_project_id = row[0]
        new_project_name = row[1]

        # Sync target project before operation
        sync_project(db, new_project_id)

        # Move issue
        try:
            new_id = move_issue(db, issue_id, new_project_id, new_project_name)
        except ValueError as e:
            print(f"Error: {e}")
            db.close()
            return 1

        # Export to JSONL for both projects
        old_trace_dir = Path(old_project_path) / ".trace"
        old_jsonl = old_trace_dir / "issues.jsonl"
        export_to_jsonl(db, old_project_path, str(old_jsonl))
        set_last_sync_time(db, old_project_path, time.time())

        new_trace_dir = Path(new_project_id) / ".trace"
        new_trace_dir.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
        new_jsonl = new_trace_dir / "issues.jsonl"
        export_to_jsonl(db, new_project_id, str(new_jsonl))
        set_last_sync_time(db, new_project_id, time.time())

        print(f"Moved {issue_id} → {new_id}")
        print(f"  From: {old_project_path}")
        print(f"  To:   {new_project_id}")

        db.close()

    return 0


def main() -> int:
    """Main CLI entry point."""
    if len(sys.argv) < 2:
        print("trc - Minimal distributed issue tracker")
        print("\nUsage:")
        print("  trc init                        Initialize project")
        print("  trc create <title> [options]    Create issue")
        print("    --description <text>              Detailed description")
        print("    --priority <0-4>                  Priority level (default: 2)")
        print("    --parent <id>                     Parent issue ID")
        print("    --depends-on <id>                 Blocking dependency ID")
        print("    --status <status>                 Initial status (default: open)")
        print("  trc list [--all]                List issues")
        print("  trc show <id>                   Show issue details")
        print("  trc close <id>                  Close issue")
        print("  trc ready [--all]               Show ready work (not blocked)")
        print("  trc tree <id>                   Show issue tree")
        print("  trc update <id> [options]       Update issue")
        print("    --title <title>                   Set title")
        print("    --priority <0-4>                  Set priority")
        print("    --status <status>                 Set status")
        print("  trc reparent <id> <parent>      Change parent (use 'none' to remove)")
        print("  trc move <id> <project>         Move issue to different project")
        return 0

    command = sys.argv[1]

    if command == "init":
        return cli_init()
    elif command == "create":
        if len(sys.argv) < 3:
            print("Error: Title required")
            print("Usage: trccreate <title> [options]")
            return 1

        # Parse title (everything before first flag)
        title_parts = []
        i = 2
        while i < len(sys.argv) and not sys.argv[i].startswith("--"):
            title_parts.append(sys.argv[i])
            i += 1

        if not title_parts:
            print("Error: Title required")
            return 1

        title = " ".join(title_parts)

        # Parse flags
        description = ""
        priority = 2
        status = "open"
        parent = None
        depends_on = None

        while i < len(sys.argv):
            if sys.argv[i] == "--description" and i + 1 < len(sys.argv):
                description = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--priority" and i + 1 < len(sys.argv):
                try:
                    priority = int(sys.argv[i + 1])
                except ValueError:
                    print("Error: Priority must be a number 0-4")
                    return 1
                i += 2
            elif sys.argv[i] == "--status" and i + 1 < len(sys.argv):
                status = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--parent" and i + 1 < len(sys.argv):
                parent = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--depends-on" and i + 1 < len(sys.argv):
                depends_on = sys.argv[i + 1]
                i += 2
            else:
                print(f"Unknown option: {sys.argv[i]}")
                return 1

        # Pass to cli_create
        return cli_create(title, description=description, priority=priority,
                          status=status, parent=parent, depends_on=depends_on)
    elif command == "list":
        all_flag = "--all" in sys.argv
        return cli_list(all_projects=all_flag)
    elif command == "show":
        if len(sys.argv) < 3:
            print("Error: Issue ID required")
            print("Usage: trcshow <id>")
            return 1
        return cli_show(sys.argv[2])
    elif command == "close":
        if len(sys.argv) < 3:
            print("Error: Issue ID required")
            print("Usage: trcclose <id>")
            return 1
        return cli_close(sys.argv[2])
    elif command == "ready":
        all_flag = "--all" in sys.argv
        return cli_ready(all_projects=all_flag)
    elif command == "tree":
        if len(sys.argv) < 3:
            print("Error: Issue ID required")
            print("Usage: trctree <id>")
            return 1
        return cli_tree(sys.argv[2])
    elif command == "update":
        if len(sys.argv) < 3:
            print("Error: Issue ID required")
            print("Usage: trcupdate <id> [--title <title>] [--priority <0-4>] [--status <status>]")
            return 1

        issue_id = sys.argv[2]
        title = None
        priority = None
        status = None

        # Parse options
        i = 3
        while i < len(sys.argv):
            if sys.argv[i] == "--title" and i + 1 < len(sys.argv):
                title = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--priority" and i + 1 < len(sys.argv):
                try:
                    priority = int(sys.argv[i + 1])
                except ValueError:
                    print("Error: Priority must be a number 0-4")
                    return 1
                i += 2
            elif sys.argv[i] == "--status" and i + 1 < len(sys.argv):
                status = sys.argv[i + 1]
                i += 2
            else:
                print(f"Unknown option: {sys.argv[i]}")
                return 1

        return cli_update(issue_id, title=title, priority=priority, status=status)
    elif command == "reparent":
        if len(sys.argv) < 4:
            print("Error: Issue ID and parent ID required")
            print("Usage: trcreparent <id> <parent-id>")
            print("       tr reparent <id> none    (to remove parent)")
            return 1

        issue_id = sys.argv[2]
        parent_arg = sys.argv[3]

        # Handle 'none' as None
        if parent_arg.lower() == "none":
            new_parent_id = None
        else:
            new_parent_id = parent_arg

        return cli_reparent(issue_id, new_parent_id)
    elif command == "move":
        if len(sys.argv) < 4:
            print("Error: Issue ID and target project required")
            print("Usage: trcmove <id> <project-name>")
            return 1

        issue_id = sys.argv[2]
        target_project = sys.argv[3]

        return cli_move(issue_id, target_project)
    else:
        print(f"Unknown command: {command}")
        print("Run 'trc' for usage information")
        return 1


if __name__ == "__main__":
    sys.exit(main())
