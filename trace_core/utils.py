"""Shared utilities for Trace - timestamps, paths, file locking."""

import fcntl
import re
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from trace_core.exceptions import LockError

__all__ = [
    "get_iso_timestamp",
    "file_lock",
    "sanitize_project_name",
]


def get_iso_timestamp() -> str:
    """Get current UTC timestamp in ISO format with Z suffix.

    Returns:
        ISO 8601 formatted timestamp string (e.g., "2024-01-15T10:30:00.123456Z")
    """
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@contextmanager
def file_lock(lock_path: Path, timeout: float = 5.0) -> Generator[object, None, None]:
    """Acquire an exclusive file lock.

    Args:
        lock_path: Path to lock file
        timeout: Maximum time to wait for lock (seconds)

    Yields:
        The lock file object

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
