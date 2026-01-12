"""Constants for Trace - magic strings, numbers, and configuration."""

__all__ = [
    "VALID_STATUSES",
    "VALID_DEPENDENCY_TYPES",
    "PRIORITY_RANGE",
    "MAX_ID_RETRIES",
    "LOCK_TIMEOUT",
    "HASH_LENGTH",
    "BASE36_CHARS",
]

# Issue statuses
VALID_STATUSES = {"open", "in_progress", "closed", "blocked"}

# Dependency relationship types
VALID_DEPENDENCY_TYPES = {"parent", "blocks", "related"}

# Priority range (inclusive)
PRIORITY_RANGE = (0, 4)

# ID generation
MAX_ID_RETRIES = 10
HASH_LENGTH = 6
BASE36_CHARS = "0123456789abcdefghijklmnopqrstuvwxyz"

# File locking
LOCK_TIMEOUT = 5.0
