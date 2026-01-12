"""Issue management for Trace - CRUD operations."""

import sqlite3
from typing import Any, Dict, List, Optional, Union

from trace_core.constants import VALID_STATUSES, PRIORITY_RANGE
from trace_core.ids import generate_id
from trace_core.utils import get_iso_timestamp

__all__ = [
    "create_issue",
    "get_issue",
    "list_issues",
    "update_issue",
    "close_issue",
]


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
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {status}. Must be one of {VALID_STATUSES}")

    min_priority, max_priority = PRIORITY_RANGE
    if not (min_priority <= priority <= max_priority):
        raise ValueError(f"Priority must be between {min_priority} and {max_priority}, got {priority}")

    # Get existing IDs for collision detection
    cursor = db.execute("SELECT id FROM issues WHERE id LIKE ?", (f"{project_name}-%",))
    existing_ids = {row[0] for row in cursor.fetchall()}

    # Generate unique ID
    issue_id = generate_id(title, project_name, existing_ids=existing_ids)

    # Generate timestamps
    now = get_iso_timestamp()

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
    status: Optional[Union[str, List[str]]] = None,
) -> List[Dict[str, Any]]:
    """List issues with optional filtering.

    Args:
        db: Database connection
        project_id: Filter by project (optional)
        status: Filter by status - single status string, list of statuses, or None for all (optional)

    Returns:
        List of issue dicts, sorted by priority then created_at (desc)
    """
    query = "SELECT * FROM issues WHERE 1=1"
    params: List[Any] = []

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
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}. Must be one of {VALID_STATUSES}")

    if priority is not None:
        min_priority, max_priority = PRIORITY_RANGE
        if not (min_priority <= priority <= max_priority):
            raise ValueError(f"Priority must be between {min_priority} and {max_priority}, got {priority}")

    # Build update query dynamically
    updates: List[str] = []
    params: List[Any] = []

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
    now = get_iso_timestamp()
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
    now = get_iso_timestamp()

    db.execute(
        """UPDATE issues
           SET status = 'closed', closed_at = ?, updated_at = ?
           WHERE id = ?""",
        (now, now, issue_id),
    )
    db.commit()
