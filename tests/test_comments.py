"""Tests for comments module."""

import pytest
from datetime import datetime


def test_add_comment_creates_comment(initialized_project):
    """Should create a comment on an issue."""
    from trc_main import create_issue, add_comment

    db = initialized_project["db"]
    project_id = initialized_project["project"]["id"]
    project_name = initialized_project["project"]["name"]

    # Create issue first
    issue = create_issue(db, project_id, project_name, "Test issue", description="Test")

    # Add comment
    comment = add_comment(db, issue["id"], "This is a test comment", source="user")

    assert comment["id"] is not None
    assert comment["issue_id"] == issue["id"]
    assert comment["content"] == "This is a test comment"
    assert comment["source"] == "user"
    assert comment["created_at"] is not None


def test_add_comment_uses_default_source(initialized_project):
    """Should use 'user' as default source."""
    from trc_main import create_issue, add_comment

    db = initialized_project["db"]
    project_id = initialized_project["project"]["id"]
    project_name = initialized_project["project"]["name"]

    issue = create_issue(db, project_id, project_name, "Test issue", description="Test")

    # Add comment without specifying source
    comment = add_comment(db, issue["id"], "Comment without source")

    assert comment["source"] == "user"


def test_add_comment_accepts_custom_source(initialized_project):
    """Should accept custom source identifiers."""
    from trc_main import create_issue, add_comment

    db = initialized_project["db"]
    project_id = initialized_project["project"]["id"]
    project_name = initialized_project["project"]["name"]

    issue = create_issue(db, project_id, project_name, "Test issue", description="Test")

    # Add comments with different sources
    c1 = add_comment(db, issue["id"], "From executor", source="executor")
    c2 = add_comment(db, issue["id"], "From verifier", source="verifier")
    c3 = add_comment(db, issue["id"], "From human", source="human")

    assert c1["source"] == "executor"
    assert c2["source"] == "verifier"
    assert c3["source"] == "human"


def test_get_comments_returns_empty_list_for_no_comments(initialized_project):
    """Should return empty list if issue has no comments."""
    from trc_main import create_issue, get_comments

    db = initialized_project["db"]
    project_id = initialized_project["project"]["id"]
    project_name = initialized_project["project"]["name"]

    issue = create_issue(db, project_id, project_name, "Test issue", description="Test")

    comments = get_comments(db, issue["id"])

    assert comments == []


def test_get_comments_returns_all_comments(initialized_project):
    """Should return all comments for an issue."""
    from trc_main import create_issue, add_comment, get_comments

    db = initialized_project["db"]
    project_id = initialized_project["project"]["id"]
    project_name = initialized_project["project"]["name"]

    issue = create_issue(db, project_id, project_name, "Test issue", description="Test")

    # Add multiple comments
    add_comment(db, issue["id"], "Comment 1", source="user")
    add_comment(db, issue["id"], "Comment 2", source="executor")
    add_comment(db, issue["id"], "Comment 3", source="verifier")

    comments = get_comments(db, issue["id"])

    assert len(comments) == 3
    assert comments[0]["content"] == "Comment 1"
    assert comments[1]["content"] == "Comment 2"
    assert comments[2]["content"] == "Comment 3"


def test_get_comments_ordered_by_created_at(initialized_project):
    """Should return comments in chronological order (oldest first)."""
    from trc_main import create_issue, add_comment, get_comments
    import time

    db = initialized_project["db"]
    project_id = initialized_project["project"]["id"]
    project_name = initialized_project["project"]["name"]

    issue = create_issue(db, project_id, project_name, "Test issue", description="Test")

    # Add comments with small delays to ensure ordering
    add_comment(db, issue["id"], "First", source="user")
    time.sleep(0.01)  # Small delay to ensure different timestamps
    add_comment(db, issue["id"], "Second", source="user")
    time.sleep(0.01)
    add_comment(db, issue["id"], "Third", source="user")

    comments = get_comments(db, issue["id"])

    # Should be in chronological order
    assert comments[0]["content"] == "First"
    assert comments[1]["content"] == "Second"
    assert comments[2]["content"] == "Third"

    # Verify timestamps are ascending
    assert comments[0]["created_at"] <= comments[1]["created_at"]
    assert comments[1]["created_at"] <= comments[2]["created_at"]


def test_get_comments_only_returns_comments_for_specified_issue(initialized_project):
    """Should not return comments from other issues."""
    from trc_main import create_issue, add_comment, get_comments

    db = initialized_project["db"]
    project_id = initialized_project["project"]["id"]
    project_name = initialized_project["project"]["name"]

    issue1 = create_issue(db, project_id, project_name, "Issue 1", description="Test")
    issue2 = create_issue(db, project_id, project_name, "Issue 2", description="Test")

    # Add comments to both issues
    add_comment(db, issue1["id"], "Comment on issue 1", source="user")
    add_comment(db, issue2["id"], "Comment on issue 2", source="user")

    # Get comments for issue 1
    comments1 = get_comments(db, issue1["id"])
    comments2 = get_comments(db, issue2["id"])

    assert len(comments1) == 1
    assert comments1[0]["content"] == "Comment on issue 1"
    assert len(comments2) == 1
    assert comments2[0]["content"] == "Comment on issue 2"


def test_comments_deleted_when_issue_deleted(initialized_project):
    """Comments should be deleted when parent issue is deleted (cascade)."""
    from trc_main import create_issue, add_comment, get_comments

    db = initialized_project["db"]
    project_id = initialized_project["project"]["id"]
    project_name = initialized_project["project"]["name"]

    issue = create_issue(db, project_id, project_name, "Test issue", description="Test")

    # Add comments
    add_comment(db, issue["id"], "Comment 1", source="user")
    add_comment(db, issue["id"], "Comment 2", source="executor")

    # Verify comments exist
    comments = get_comments(db, issue["id"])
    assert len(comments) == 2

    # Delete the issue
    db.execute("DELETE FROM issues WHERE id = ?", (issue["id"],))
    db.commit()

    # Verify comments are also deleted (cascade)
    cursor = db.execute("SELECT COUNT(*) FROM comments WHERE issue_id = ?", (issue["id"],))
    count = cursor.fetchone()[0]
    assert count == 0


# ============================================
# Sync tests for comments
# ============================================


def test_export_to_jsonl_includes_comments(initialized_project, tmp_path):
    """Export should include comments in JSONL output."""
    import json
    from trc_main import create_issue, add_comment, export_to_jsonl

    db = initialized_project["db"]
    project_id = initialized_project["project"]["id"]
    project_name = initialized_project["project"]["name"]

    # Create issue with comments
    issue = create_issue(db, project_id, project_name, "Test issue", description="Test")
    add_comment(db, issue["id"], "First comment", source="user")
    add_comment(db, issue["id"], "Second comment", source="executor")

    # Export to JSONL
    jsonl_path = tmp_path / "issues.jsonl"
    export_to_jsonl(db, project_id, str(jsonl_path))

    # Read and verify
    with jsonl_path.open("r") as f:
        exported = json.loads(f.readline())

    assert "comments" in exported
    assert len(exported["comments"]) == 2
    assert exported["comments"][0]["content"] == "First comment"
    assert exported["comments"][0]["source"] == "user"
    assert exported["comments"][1]["content"] == "Second comment"
    assert exported["comments"][1]["source"] == "executor"


def test_import_from_jsonl_restores_comments(initialized_project, tmp_path):
    """Import should restore comments from JSONL."""
    import json
    from trc_main import create_issue, add_comment, export_to_jsonl, import_from_jsonl, get_comments

    db = initialized_project["db"]
    project_id = initialized_project["project"]["id"]
    project_name = initialized_project["project"]["name"]

    # Create issue with comments
    issue = create_issue(db, project_id, project_name, "Test issue", description="Test")
    add_comment(db, issue["id"], "Original comment", source="user")

    # Export to JSONL
    jsonl_path = tmp_path / "issues.jsonl"
    export_to_jsonl(db, project_id, str(jsonl_path))

    # Clear comments from database
    db.execute("DELETE FROM comments WHERE issue_id = ?", (issue["id"],))
    db.commit()

    # Verify comments are gone
    assert len(get_comments(db, issue["id"])) == 0

    # Import from JSONL
    import_from_jsonl(db, str(jsonl_path), project_id)

    # Verify comments are restored
    comments = get_comments(db, issue["id"])
    assert len(comments) == 1
    assert comments[0]["content"] == "Original comment"
    assert comments[0]["source"] == "user"


def test_import_replaces_existing_comments(initialized_project, tmp_path):
    """Import should replace existing comments with JSONL contents."""
    import json
    from trc_main import create_issue, add_comment, get_comments, import_from_jsonl

    db = initialized_project["db"]
    project_id = initialized_project["project"]["id"]
    project_name = initialized_project["project"]["name"]

    # Create issue
    issue = create_issue(db, project_id, project_name, "Test issue", description="Test")

    # Add a comment to database (simulating local state)
    add_comment(db, issue["id"], "Local comment", source="local")

    # Create JSONL with different comments
    jsonl_path = tmp_path / "issues.jsonl"
    issue_data = {
        "id": issue["id"],
        "title": "Test issue",
        "description": "Test",
        "status": "open",
        "priority": 2,
        "created_at": issue["created_at"],
        "updated_at": issue["updated_at"],
        "closed_at": None,
        "dependencies": [],
        "comments": [
            {"content": "Remote comment 1", "source": "remote", "created_at": "2026-01-01T00:00:00Z"},
            {"content": "Remote comment 2", "source": "executor", "created_at": "2026-01-02T00:00:00Z"},
        ],
    }
    with jsonl_path.open("w") as f:
        f.write(json.dumps(issue_data) + "\n")

    # Import from JSONL
    import_from_jsonl(db, str(jsonl_path), project_id)

    # Verify comments are replaced (not merged)
    comments = get_comments(db, issue["id"])
    assert len(comments) == 2
    assert comments[0]["content"] == "Remote comment 1"
    assert comments[1]["content"] == "Remote comment 2"


def test_export_import_roundtrip_preserves_comments(initialized_project, tmp_path):
    """Comments should survive export/import roundtrip."""
    from trc_main import create_issue, add_comment, get_comments, export_to_jsonl, import_from_jsonl

    db = initialized_project["db"]
    project_id = initialized_project["project"]["id"]
    project_name = initialized_project["project"]["name"]

    # Create issue with multiple comments
    issue = create_issue(db, project_id, project_name, "Test issue", description="Test")
    add_comment(db, issue["id"], "Comment A", source="user")
    add_comment(db, issue["id"], "Comment B", source="executor")
    add_comment(db, issue["id"], "Comment C", source="verifier")

    # Get original comments
    original_comments = get_comments(db, issue["id"])

    # Export
    jsonl_path = tmp_path / "issues.jsonl"
    export_to_jsonl(db, project_id, str(jsonl_path))

    # Clear and reimport
    db.execute("DELETE FROM comments")
    db.commit()
    import_from_jsonl(db, str(jsonl_path), project_id)

    # Verify roundtrip
    restored_comments = get_comments(db, issue["id"])
    assert len(restored_comments) == 3
    assert restored_comments[0]["content"] == original_comments[0]["content"]
    assert restored_comments[0]["source"] == original_comments[0]["source"]
    assert restored_comments[0]["created_at"] == original_comments[0]["created_at"]
