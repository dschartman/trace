"""Dependency management for Trace - relationships between issues."""

import sqlite3
from typing import Any, Dict, List

from trace_core.constants import VALID_DEPENDENCY_TYPES
from trace_core.utils import get_iso_timestamp

__all__ = [
    "add_dependency",
    "remove_dependency",
    "get_dependencies",
    "get_children",
    "get_blockers",
    "is_blocked",
    "has_open_children",
]


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
    if dep_type not in VALID_DEPENDENCY_TYPES:
        raise ValueError(f"Invalid dependency type: {dep_type}. Must be one of {VALID_DEPENDENCY_TYPES}")

    now = get_iso_timestamp()

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
) -> List[Dict[str, Any]]:
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
) -> List[Dict[str, Any]]:
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
) -> List[Dict[str, Any]]:
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
