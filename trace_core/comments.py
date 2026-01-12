"""Comments module for Trace - add and retrieve issue comments."""

import sqlite3
from typing import Any, Dict, List

from trace_core.utils import get_iso_timestamp

__all__ = [
    "add_comment",
    "get_comments",
]


def add_comment(
    db: sqlite3.Connection,
    issue_id: str,
    content: str,
    source: str = "user",
) -> Dict[str, Any]:
    """Add a comment to an issue.

    Args:
        db: Database connection
        issue_id: Issue ID to comment on
        content: Comment text
        source: Who/what made the comment (e.g., "user", "executor", "verifier")

    Returns:
        Dict with created comment data

    Note:
        Comments are append-only - no edit or delete operations.
    """
    now = get_iso_timestamp()

    cursor = db.execute(
        """INSERT INTO comments (issue_id, content, source, created_at)
           VALUES (?, ?, ?, ?)""",
        (issue_id, content, source, now),
    )
    db.commit()

    # Return created comment
    comment_id = cursor.lastrowid
    return {
        "id": comment_id,
        "issue_id": issue_id,
        "content": content,
        "source": source,
        "created_at": now,
    }


def get_comments(db: sqlite3.Connection, issue_id: str) -> List[Dict[str, Any]]:
    """Get all comments for an issue.

    Args:
        db: Database connection
        issue_id: Issue ID

    Returns:
        List of comment dicts, sorted by created_at ascending (oldest first)
    """
    cursor = db.execute(
        """SELECT id, issue_id, content, source, created_at
           FROM comments
           WHERE issue_id = ?
           ORDER BY created_at ASC""",
        (issue_id,),
    )

    return [
        {
            "id": row[0],
            "issue_id": row[1],
            "content": row[2],
            "source": row[3],
            "created_at": row[4],
        }
        for row in cursor.fetchall()
    ]
