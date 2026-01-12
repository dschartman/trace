"""Project management for Trace - detection, registration, resolution."""

import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

from trace_core.utils import sanitize_project_name

__all__ = [
    "detect_project",
    "is_project_initialized",
    "register_project",
    "resolve_project",
    "get_project_path",
]


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


def register_project(db: sqlite3.Connection, name: str, path: str) -> None:
    """Register a project in the database.

    Used primarily for testing. In normal use, projects are registered
    via `trc init` which calls detect_project().

    Args:
        db: Database connection
        name: Project name
        path: Absolute path to project directory
    """
    db.execute(
        "INSERT OR REPLACE INTO projects (id, name, current_path) VALUES (?, ?, ?)",
        (path, name, path),
    )
    db.commit()


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


def _extract_project_id_from_git_remote(git_dir: Path) -> Optional[str]:
    """Extract project ID from git remote URL.

    Parses .git/config to find remote "origin" URL and converts it to
    a portable project identifier.

    Args:
        git_dir: Path to .git directory

    Returns:
        Project ID from remote URL, or None if not found

    Handles various git URL formats:
        - https://github.com/user/repo.git -> github.com/user/repo
        - git@github.com:user/repo.git -> github.com/user/repo
        - https://gitlab.com/group/subgroup/project.git -> gitlab.com/group/subgroup/project
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
            # https://github.com/user/repo -> github.com/user/repo
            url = url.replace("https://", "").replace("http://", "")
        elif url.startswith("git@"):
            # git@github.com:user/repo -> github.com/user/repo
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
        - https://github.com/user/repo.git -> repo
        - git@github.com:user/repo.git -> repo
        - https://gitlab.com/group/subgroup/project.git -> project
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
