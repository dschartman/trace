"""Reorganization for Trace - move, reparent operations."""

import sqlite3
from typing import Optional

from trace_core.ids import generate_id
from trace_core.issues import get_issue
from trace_core.dependencies import get_dependencies
from trace_core.utils import get_iso_timestamp

__all__ = [
    "detect_cycle",
    "reparent_issue",
    "move_issue",
]


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
        now = get_iso_timestamp()
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
        now = get_iso_timestamp()
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
