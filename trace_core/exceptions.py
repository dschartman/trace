"""Custom exceptions for Trace."""

__all__ = ["IDCollisionError", "LockError"]


class IDCollisionError(Exception):
    """Raised when unable to generate unique ID after max retries."""

    pass


class LockError(Exception):
    """Raised when unable to acquire file lock."""

    pass
