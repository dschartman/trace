"""Tests for issue CRUD operations."""

from datetime import datetime, timezone

import pytest


def test_create_issue_with_minimal_fields(db_connection, tmp_trace_dir):
    """Should create issue with only required fields."""
    from trc_main import create_issue

    issue = create_issue(
        db=db_connection,
        project_id="/path/to/myapp",
        project_name="myapp",
        title="Fix bug",
    )

    assert issue["id"].startswith("myapp-")
    assert issue["title"] == "Fix bug"
    assert issue["status"] == "open"
    assert issue["priority"] == 2
    assert issue["description"] == ""
    assert issue["created_at"] is not None
    assert issue["updated_at"] is not None
    assert issue["closed_at"] is None


def test_create_issue_with_all_fields(db_connection):
    """Should create issue with all optional fields."""
    from trc_main import create_issue

    issue = create_issue(
        db=db_connection,
        project_id="/path/to/myapp",
        project_name="myapp",
        title="Add feature",
        description="Detailed description",
        priority=1,
        status="in_progress",
    )

    assert issue["title"] == "Add feature"
    assert issue["description"] == "Detailed description"
    assert issue["priority"] == 1
    assert issue["status"] == "in_progress"


def test_create_issue_sets_utc_timestamps(db_connection):
    """Timestamps should be UTC ISO8601 format."""
    from trc_main import create_issue

    issue = create_issue(
        db=db_connection,
        project_id="/path/to/myapp",
        project_name="myapp",
        title="Test",
    )

    # Should be valid ISO8601
    created = datetime.fromisoformat(issue["created_at"].replace("Z", "+00:00"))
    updated = datetime.fromisoformat(issue["updated_at"].replace("Z", "+00:00"))

    assert created.tzinfo is not None
    assert updated.tzinfo is not None


def test_create_issue_validates_status(db_connection):
    """Should reject invalid status values."""
    from trc_main import create_issue

    with pytest.raises(ValueError, match="Invalid status"):
        create_issue(
            db=db_connection,
            project_id="/path/to/myapp",
            project_name="myapp",
            title="Test",
            status="invalid",
        )


def test_create_issue_validates_priority_range(db_connection):
    """Should reject priority outside 0-4 range."""
    from trc_main import create_issue

    with pytest.raises(ValueError, match="Priority must be between 0 and 4"):
        create_issue(
            db=db_connection,
            project_id="/path/to/myapp",
            project_name="myapp",
            title="Test",
            priority=5,
        )

    with pytest.raises(ValueError, match="Priority must be between 0 and 4"):
        create_issue(
            db=db_connection,
            project_id="/path/to/myapp",
            project_name="myapp",
            title="Test",
            priority=-1,
        )


def test_create_issue_generates_unique_ids(db_connection):
    """Each issue should get a unique ID."""
    from trc_main import create_issue

    issue1 = create_issue(db_connection, "/path/to/myapp", "myapp", "Issue 1")
    issue2 = create_issue(db_connection, "/path/to/myapp", "myapp", "Issue 2")

    assert issue1["id"] != issue2["id"]


def test_create_issue_persists_to_database(db_connection):
    """Created issue should be stored in database."""
    from trc_main import create_issue

    issue = create_issue(db_connection, "/path/to/myapp", "myapp", "Test")

    cursor = db_connection.execute("SELECT * FROM issues WHERE id = ?", (issue["id"],))
    row = cursor.fetchone()

    assert row is not None
    assert row["title"] == "Test"


def test_get_issue_by_id(db_connection):
    """Should retrieve issue by ID."""
    from trc_main import create_issue, get_issue

    created = create_issue(db_connection, "/path/to/myapp", "myapp", "Test")
    issue = get_issue(db_connection, created["id"])

    assert issue["id"] == created["id"]
    assert issue["title"] == "Test"


def test_get_issue_returns_none_for_nonexistent_id(db_connection):
    """Should return None if issue doesn't exist."""
    from trc_main import get_issue

    issue = get_issue(db_connection, "myapp-nonexistent")
    assert issue is None


def test_list_issues_returns_all_for_project(db_connection):
    """Should list all issues for a project."""
    from trc_main import create_issue, list_issues

    create_issue(db_connection, "/path/to/myapp", "myapp", "Issue 1")
    create_issue(db_connection, "/path/to/myapp", "myapp", "Issue 2")
    create_issue(db_connection, "/path/to/other", "other", "Issue 3")

    issues = list_issues(db_connection, project_id="/path/to/myapp")

    assert len(issues) == 2
    assert all(i["project_id"] == "/path/to/myapp" for i in issues)


def test_list_issues_filters_by_status(db_connection):
    """Should filter issues by status."""
    from trc_main import create_issue, list_issues

    create_issue(db_connection, "/path/to/myapp", "myapp", "Open", status="open")
    create_issue(db_connection, "/path/to/myapp", "myapp", "Closed", status="closed")

    open_issues = list_issues(db_connection, project_id="/path/to/myapp", status="open")

    assert len(open_issues) == 1
    assert open_issues[0]["status"] == "open"


def test_list_issues_sorts_by_priority_then_created(db_connection):
    """Should sort by priority (ascending) then created_at (descending)."""
    from trc_main import create_issue, list_issues
    import time

    # Create in specific order
    p2_old = create_issue(db_connection, "/path/to/myapp", "myapp", "P2 Old", priority=2)
    time.sleep(0.01)
    p1_new = create_issue(db_connection, "/path/to/myapp", "myapp", "P1 New", priority=1)
    time.sleep(0.01)
    p0_mid = create_issue(db_connection, "/path/to/myapp", "myapp", "P0 Mid", priority=0)

    issues = list_issues(db_connection, project_id="/path/to/myapp")

    # Should be sorted: P0, P1, P2 (priority ascending)
    assert issues[0]["id"] == p0_mid["id"]
    assert issues[1]["id"] == p1_new["id"]
    assert issues[2]["id"] == p2_old["id"]


def test_update_issue_modifies_fields(db_connection):
    """Should update issue fields."""
    from trc_main import create_issue, update_issue, get_issue

    issue = create_issue(db_connection, "/path/to/myapp", "myapp", "Original")

    update_issue(
        db_connection,
        issue["id"],
        title="Updated",
        description="New description",
        priority=0,
        status="in_progress",
    )

    updated = get_issue(db_connection, issue["id"])

    assert updated["title"] == "Updated"
    assert updated["description"] == "New description"
    assert updated["priority"] == 0
    assert updated["status"] == "in_progress"


def test_update_issue_updates_timestamp(db_connection):
    """Should update updated_at timestamp."""
    from trc_main import create_issue, update_issue, get_issue
    import time

    issue = create_issue(db_connection, "/path/to/myapp", "myapp", "Test")
    original_updated = issue["updated_at"]

    time.sleep(0.01)
    update_issue(db_connection, issue["id"], title="Modified")

    updated = get_issue(db_connection, issue["id"])

    assert updated["updated_at"] != original_updated


def test_update_issue_validates_status(db_connection):
    """Should reject invalid status in update."""
    from trc_main import create_issue, update_issue

    issue = create_issue(db_connection, "/path/to/myapp", "myapp", "Test")

    with pytest.raises(ValueError, match="Invalid status"):
        update_issue(db_connection, issue["id"], status="invalid")


def test_update_issue_validates_priority(db_connection):
    """Should reject invalid priority in update."""
    from trc_main import create_issue, update_issue

    issue = create_issue(db_connection, "/path/to/myapp", "myapp", "Test")

    with pytest.raises(ValueError, match="Priority must be between 0 and 4"):
        update_issue(db_connection, issue["id"], priority=10)


def test_close_issue_sets_status_and_timestamp(db_connection):
    """Should set status to closed and record closed_at."""
    from trc_main import create_issue, close_issue, get_issue

    issue = create_issue(db_connection, "/path/to/myapp", "myapp", "Test")

    close_issue(db_connection, issue["id"])

    closed = get_issue(db_connection, issue["id"])

    assert closed["status"] == "closed"
    assert closed["closed_at"] is not None


def test_close_issue_updates_updated_at(db_connection):
    """Closing should update the updated_at timestamp."""
    from trc_main import create_issue, close_issue, get_issue
    import time

    issue = create_issue(db_connection, "/path/to/myapp", "myapp", "Test")
    original_updated = issue["updated_at"]

    time.sleep(0.01)
    close_issue(db_connection, issue["id"])

    closed = get_issue(db_connection, issue["id"])

    assert closed["updated_at"] != original_updated


def test_reopen_issue_clears_closed_at(db_connection):
    """Reopening should clear closed_at timestamp."""
    from trc_main import create_issue, close_issue, update_issue, get_issue

    issue = create_issue(db_connection, "/path/to/myapp", "myapp", "Test")
    close_issue(db_connection, issue["id"])

    update_issue(db_connection, issue["id"], status="open")

    reopened = get_issue(db_connection, issue["id"])

    assert reopened["status"] == "open"
    assert reopened["closed_at"] is None


def test_list_issues_returns_empty_for_no_matches(db_connection):
    """Should return empty list when no issues match."""
    from trc_main import list_issues

    issues = list_issues(db_connection, project_id="/nonexistent")

    assert issues == []


def test_list_issues_filters_by_multiple_statuses(db_connection):
    """Should filter issues by multiple statuses when given a list."""
    from trc_main import create_issue, list_issues

    # Create issues with different statuses
    open_issue = create_issue(db_connection, "/path/to/myapp", "myapp", "Open", status="open")
    progress_issue = create_issue(db_connection, "/path/to/myapp", "myapp", "In Progress", status="in_progress")
    blocked_issue = create_issue(db_connection, "/path/to/myapp", "myapp", "Blocked", status="blocked")
    closed_issue = create_issue(db_connection, "/path/to/myapp", "myapp", "Closed", status="closed")

    # Filter by multiple statuses
    backlog_issues = list_issues(db_connection, project_id="/path/to/myapp", status=["open", "in_progress", "blocked"])

    assert len(backlog_issues) == 3
    issue_ids = [i["id"] for i in backlog_issues]
    assert open_issue["id"] in issue_ids
    assert progress_issue["id"] in issue_ids
    assert blocked_issue["id"] in issue_ids
    assert closed_issue["id"] not in issue_ids


def test_create_issue_handles_empty_description(db_connection):
    """Should accept empty description."""
    from trc_main import create_issue

    issue = create_issue(
        db_connection, "/path/to/myapp", "myapp", "Test", description=""
    )

    assert issue["description"] == ""


def test_update_issue_partial_update(db_connection):
    """Should update only specified fields."""
    from trc_main import create_issue, update_issue, get_issue

    issue = create_issue(
        db_connection,
        "/path/to/myapp",
        "myapp",
        "Original",
        description="Original desc",
        priority=2,
    )

    # Update only title
    update_issue(db_connection, issue["id"], title="New title")

    updated = get_issue(db_connection, issue["id"])

    assert updated["title"] == "New title"
    assert updated["description"] == "Original desc"  # Unchanged
    assert updated["priority"] == 2  # Unchanged
