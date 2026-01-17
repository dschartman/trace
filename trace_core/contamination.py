"""Contamination prevention for Trace - cross-project validation and repair."""

import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

from trace_core.utils import sanitize_project_name

__all__ = [
    "validate_issue_belongs_to_project",
    "extract_project_name_from_id",
    "extract_project_name_from_issue_id",
    "find_project_by_name",
    "repair_contaminated_issues",
]


def validate_issue_belongs_to_project(issue_id: str, project_name: str) -> bool:
    """Check if issue ID prefix matches project name.

    This prevents cross-project contamination by ensuring issues
    are only imported/exported to their correct project.

    Issue IDs have format '{project_name}-{6_char_hash}', so we validate
    both the prefix AND that the suffix is a valid 6-character hash.

    Args:
        issue_id: Full issue ID (e.g., 'myapp-abc123')
        project_name: Project name (e.g., 'myapp')

    Returns:
        True if issue ID matches '{project_name}-{6_char_hash}' format

    Examples:
        validate_issue_belongs_to_project('myapp-abc123', 'myapp') -> True
        validate_issue_belongs_to_project('other-abc123', 'myapp') -> False
        validate_issue_belongs_to_project('change-capture-abc123', 'change-capture') -> True
        validate_issue_belongs_to_project('change-capture-abc123', 'change-capture-infra') -> False
        validate_issue_belongs_to_project('change-capture-infra-xyz789', 'change-capture') -> False
    """
    if not issue_id or not project_name:
        return False
    if "-" not in issue_id:
        return False

    expected_prefix = f"{project_name}-"
    if not issue_id.startswith(expected_prefix):
        return False

    # Extract the hash portion (should be exactly 6 alphanumeric characters)
    hash_portion = issue_id[len(expected_prefix):]
    if len(hash_portion) != 6:
        return False
    if not hash_portion.isalnum():
        return False

    return True


def extract_project_name_from_id(project_id: str) -> str:
    """Extract project name from project_id (URL or path).

    Args:
        project_id: Either a URL (github.com/user/repo) or absolute path

    Returns:
        Sanitized project name (last component)

    Examples:
        extract_project_name_from_id('github.com/user/myrepo') -> 'myrepo'
        extract_project_name_from_id('/Users/me/Repos/myrepo') -> 'myrepo'
        extract_project_name_from_id('/path/to/my_project') -> 'my-project'
    """
    if "/" in project_id and not project_id.startswith("/"):
        # URL format: github.com/user/repo
        name = project_id.split("/")[-1]
    else:
        # Path format
        name = Path(project_id).name
    # Sanitize to match how project names are stored
    return sanitize_project_name(name)


def extract_project_name_from_issue_id(issue_id: str) -> Optional[str]:
    """Extract the project name prefix from an issue ID.

    Issue IDs have format '{project_name}-{6_char_hash}'.
    This function extracts the project name portion.

    Args:
        issue_id: Full issue ID (e.g., 'myapp-abc123', 'change-capture-infra-xyz789')

    Returns:
        Project name or None if ID format is invalid

    Examples:
        extract_project_name_from_issue_id('myapp-abc123') -> 'myapp'
        extract_project_name_from_issue_id('change-capture-infra-xyz789') -> 'change-capture-infra'
        extract_project_name_from_issue_id('invalid') -> None
    """
    if not issue_id or "-" not in issue_id:
        return None

    # Issue ID format: {project_name}-{6_char_hash}
    # The hash is exactly 6 alphanumeric characters
    # Split from right to handle project names with hyphens
    parts = issue_id.rsplit("-", 1)
    if len(parts) != 2:
        return None

    project_name, hash_part = parts
    # Validate hash is 6 alphanumeric chars
    if len(hash_part) != 6 or not hash_part.isalnum():
        return None

    return project_name


def find_project_by_name(db: sqlite3.Connection, project_name: str) -> Optional[Dict[str, Any]]:
    """Find a project by name in the database.

    Args:
        db: Database connection
        project_name: Project name to search for

    Returns:
        Dict with 'id', 'name', 'path' or None if not found
    """
    cursor = db.execute(
        "SELECT id, name, current_path FROM projects WHERE name = ?",
        (project_name,),
    )
    row = cursor.fetchone()
    if row:
        return {"id": row[0], "name": row[1], "path": row[2]}
    return None


def repair_contaminated_issues(
    db: sqlite3.Connection,
    project_id: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Find and fix issues with mismatched project_id.

    Contamination occurs when an issue's ID prefix doesn't match the
    project it's assigned to. This function finds such issues and
    reassigns them to the correct project based on their ID prefix.

    Args:
        db: Database connection
        project_id: Optional - only examine issues in this project
        dry_run: If True, report what would be fixed without making changes

    Returns:
        Dict with stats:
            - examined: Number of issues examined
            - contaminated: Number of contaminated issues found
            - repaired: Number of issues reassigned
            - orphaned: Number of issues with no matching project
            - affected_projects: List of project paths that were affected
    """
    stats: Dict[str, Any] = {
        "examined": 0,
        "contaminated": 0,
        "repaired": 0,
        "orphaned": 0,
        "affected_projects": set(),
    }

    # Build query
    if project_id:
        cursor = db.execute(
            "SELECT id, project_id FROM issues WHERE project_id = ?",
            (project_id,),
        )
    else:
        cursor = db.execute("SELECT id, project_id FROM issues")

    issues = cursor.fetchall()

    for issue_id, current_project_id in issues:
        stats["examined"] += 1

        # Extract expected project name from issue ID
        expected_project_name = extract_project_name_from_issue_id(issue_id)
        if not expected_project_name:
            continue  # Malformed ID, skip

        # Get current project name from database (handles UUID-based project_id)
        # First try looking up by UUID
        cursor2 = db.execute(
            "SELECT name FROM projects WHERE uuid = ?",
            (current_project_id,)
        )
        row = cursor2.fetchone()
        if row:
            current_project_name = row[0]
        else:
            # Fall back to extracting from project_id (for backward compat with URL/path)
            current_project_name = extract_project_name_from_id(current_project_id)

        # Check if issue belongs to current project
        if validate_issue_belongs_to_project(issue_id, current_project_name):
            continue  # Issue is correctly assigned

        # Found contamination
        stats["contaminated"] += 1
        stats["affected_projects"].add(current_project_id)

        # Find the correct project for this issue
        correct_project = find_project_by_name(db, expected_project_name)

        if correct_project:
            if not dry_run:
                db.execute(
                    "UPDATE issues SET project_id = ? WHERE id = ?",
                    (correct_project["path"], issue_id),
                )
            stats["repaired"] += 1
            stats["affected_projects"].add(correct_project["path"])
        else:
            stats["orphaned"] += 1

    if not dry_run and stats["repaired"] > 0:
        db.commit()

    # Convert set to list for JSON serialization
    stats["affected_projects"] = list(stats["affected_projects"])

    return stats
