"""ID generation for Trace - collision-resistant hash-based IDs."""

import hashlib
import os
import time
from typing import Optional, Set

from trace_core.exceptions import IDCollisionError
from trace_core.constants import MAX_ID_RETRIES, HASH_LENGTH, BASE36_CHARS

__all__ = [
    "generate_id",
]


def generate_id(
    title: str,
    project: str,
    existing_ids: Optional[Set[str]] = None,
    max_retries: int = MAX_ID_RETRIES,
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
        hash_b36 = _to_base36(hash_int)[:HASH_LENGTH].zfill(HASH_LENGTH)

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

    result = []

    while num > 0:
        num, remainder = divmod(num, 36)
        result.append(BASE36_CHARS[remainder])

    return "".join(reversed(result))
