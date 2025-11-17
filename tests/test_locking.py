"""Tests for file locking to prevent concurrent access."""

import os
import threading
import time
from pathlib import Path

import pytest


def test_file_lock_context_manager(tmp_path):
    """Should acquire and release lock using context manager."""
    from trace import file_lock

    lock_path = tmp_path / ".lock"

    with file_lock(lock_path):
        assert lock_path.exists()

    # Lock should still exist (we don't delete it)
    assert lock_path.exists()


def test_file_lock_prevents_concurrent_access(tmp_path):
    """Two processes should not acquire lock simultaneously."""
    from trace import file_lock, LockError

    lock_path = tmp_path / ".lock"

    # Acquire lock in main thread
    with file_lock(lock_path):
        # Try to acquire in non-blocking mode (should fail)
        with pytest.raises(LockError, match="Could not acquire lock"):
            with file_lock(lock_path, timeout=0.1):
                pass


def test_file_lock_releases_on_exit(tmp_path):
    """Lock should release when context exits."""
    from trace import file_lock

    lock_path = tmp_path / ".lock"

    with file_lock(lock_path):
        pass

    # Should be able to acquire again
    with file_lock(lock_path):
        pass


def test_file_lock_releases_on_exception(tmp_path):
    """Lock should release even if exception occurs."""
    from trace import file_lock

    lock_path = tmp_path / ".lock"

    try:
        with file_lock(lock_path):
            raise ValueError("Test error")
    except ValueError:
        pass

    # Should be able to acquire after exception
    with file_lock(lock_path):
        pass


def test_file_lock_creates_lock_file_if_missing(tmp_path):
    """Should create lock file if it doesn't exist."""
    from trace import file_lock

    lock_path = tmp_path / ".lock"
    assert not lock_path.exists()

    with file_lock(lock_path):
        assert lock_path.exists()


def test_file_lock_timeout(tmp_path):
    """Should timeout if can't acquire lock."""
    from trace import file_lock, LockError

    lock_path = tmp_path / ".lock"

    with file_lock(lock_path):
        # Try to acquire with short timeout
        start = time.time()
        with pytest.raises(LockError):
            with file_lock(lock_path, timeout=0.2):
                pass
        elapsed = time.time() - start

        # Should have waited approximately timeout duration
        assert 0.1 < elapsed < 0.5


def test_file_lock_concurrent_threads(tmp_path):
    """Should handle concurrent access from multiple threads."""
    from trace import file_lock

    lock_path = tmp_path / ".lock"
    counter = {"value": 0}
    errors = []

    def increment():
        try:
            with file_lock(lock_path, timeout=2.0):
                # Critical section
                current = counter["value"]
                time.sleep(0.01)  # Simulate work
                counter["value"] = current + 1
        except Exception as e:
            errors.append(e)

    # Start multiple threads
    threads = [threading.Thread(target=increment) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # All threads should have succeeded
    assert len(errors) == 0
    assert counter["value"] == 5


def test_file_lock_with_stale_lock(tmp_path):
    """Should handle stale lock files gracefully."""
    from trace import file_lock

    lock_path = tmp_path / ".lock"

    # Create a lock file
    lock_path.write_text("stale")

    # Should be able to acquire (file exists but not locked)
    with file_lock(lock_path):
        pass
