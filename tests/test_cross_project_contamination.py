"""Tests for cross-project contamination prevention.

These tests verify that issues cannot be incorrectly assigned to projects
based on ID prefix validation. The core bug is that import_from_jsonl
assigns ALL issues the provided project_id without checking if the
issue's ID prefix matches the project name.

Test Categories:
1. Bug Reproduction Tests - Demonstrate the contamination bug
2. Validation Logic Tests - Test the core validation function
3. Prevention Tests - Defense in depth
4. Edge Cases - Similar project names, partial contamination
"""

import json

import pytest


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def two_similar_projects(tmp_path, db_connection):
    """Create two projects with similar names for contamination testing.

    Projects:
    - change-capture: /tmp/xxx/change-capture
    - change-capture-infra: /tmp/xxx/change-capture-infra

    This is the exact scenario where contamination occurred.
    """
    # Project 1: change-capture
    proj1_path = tmp_path / "change-capture"
    proj1_path.mkdir()
    git1 = proj1_path / ".git"
    git1.mkdir()
    (git1 / "config").write_text(
        '[core]\n\trepositoryformatversion = 0\n'
        '[remote "origin"]\n\turl = https://gitlab.com/user/change-capture.git\n'
    )
    trace1 = proj1_path / ".trace"
    trace1.mkdir()

    # Project 2: change-capture-infra
    proj2_path = tmp_path / "change-capture-infra"
    proj2_path.mkdir()
    git2 = proj2_path / ".git"
    git2.mkdir()
    (git2 / "config").write_text(
        '[core]\n\trepositoryformatversion = 0\n'
        '[remote "origin"]\n\turl = https://gitlab.com/user/change-capture-infra.git\n'
    )
    trace2 = proj2_path / ".trace"
    trace2.mkdir()

    return {
        "proj1": {
            "path": str(proj1_path),
            "name": "change-capture",
            "trace_dir": trace1,
            "project_id": "gitlab.com/user/change-capture",
        },
        "proj2": {
            "path": str(proj2_path),
            "name": "change-capture-infra",
            "trace_dir": trace2,
            "project_id": "gitlab.com/user/change-capture-infra",
        },
    }


@pytest.fixture
def contaminated_jsonl_content():
    """JSONL content with issues from two different projects mixed together.

    This simulates the contamination bug where change-capture issues
    ended up in the change-capture-infra JSONL file.
    """
    return (
        # Issue from change-capture (WRONG - should not be in change-capture-infra)
        '{"id":"change-capture-abc123","title":"Issue from change-capture","description":"","status":"open","priority":2,"created_at":"2025-01-15T10:00:00Z","updated_at":"2025-01-15T10:00:00Z","closed_at":null,"dependencies":[]}\n'
        # Issue from change-capture-infra (CORRECT)
        '{"id":"change-capture-infra-xyz789","title":"Issue from change-capture-infra","description":"","status":"open","priority":2,"created_at":"2025-01-15T10:00:00Z","updated_at":"2025-01-15T10:00:00Z","closed_at":null,"dependencies":[]}\n'
    )


# =============================================================================
# Validation Logic Tests
# =============================================================================


class TestValidateIssueBelongsToProject:
    """Test the core validation function for issue-to-project matching."""

    def test_validate_issue_belongs_to_project_exact_match(self):
        """Issue ID prefix should match project name exactly."""
        from trc_main import validate_issue_belongs_to_project

        assert validate_issue_belongs_to_project("myapp-abc123", "myapp") is True

    def test_validate_issue_belongs_to_project_mismatch(self):
        """Issue ID with different prefix should not match."""
        from trc_main import validate_issue_belongs_to_project

        assert validate_issue_belongs_to_project("other-abc123", "myapp") is False

    def test_validate_similar_project_names_change_capture(self):
        """Critical: change-capture-xxx should NOT match change-capture-infra.

        This is the exact bug scenario - the project name 'change-capture-infra'
        starts with 'change-capture', but 'change-capture-xxx' issues should
        NOT be assigned to it.
        """
        from trc_main import validate_issue_belongs_to_project

        # change-capture-abc123 should match change-capture
        assert validate_issue_belongs_to_project("change-capture-abc123", "change-capture") is True

        # change-capture-abc123 should NOT match change-capture-infra
        assert validate_issue_belongs_to_project("change-capture-abc123", "change-capture-infra") is False

        # change-capture-infra-xyz789 should match change-capture-infra
        assert validate_issue_belongs_to_project("change-capture-infra-xyz789", "change-capture-infra") is True

        # change-capture-infra-xyz789 should NOT match change-capture
        assert validate_issue_belongs_to_project("change-capture-infra-xyz789", "change-capture") is False

    def test_validate_project_name_with_numbers(self):
        """Project names with numbers should be handled correctly."""
        from trc_main import validate_issue_belongs_to_project

        assert validate_issue_belongs_to_project("project123-abc456", "project123") is True
        assert validate_issue_belongs_to_project("project123-abc456", "project12") is False
        assert validate_issue_belongs_to_project("project123-abc456", "project1234") is False

    def test_validate_single_word_project(self):
        """Single word project names should work."""
        from trc_main import validate_issue_belongs_to_project

        assert validate_issue_belongs_to_project("trace-abc123", "trace") is True
        assert validate_issue_belongs_to_project("trace-abc123", "trac") is False

    def test_validate_empty_inputs(self):
        """Empty inputs should return False."""
        from trc_main import validate_issue_belongs_to_project

        assert validate_issue_belongs_to_project("", "myapp") is False
        assert validate_issue_belongs_to_project("myapp-abc123", "") is False
        assert validate_issue_belongs_to_project("", "") is False

    def test_validate_malformed_issue_id(self):
        """Issue IDs without hyphen should return False."""
        from trc_main import validate_issue_belongs_to_project

        assert validate_issue_belongs_to_project("noprefix", "noprefix") is False
        assert validate_issue_belongs_to_project("myappabc123", "myapp") is False


# =============================================================================
# Bug Reproduction Tests - These should FAIL with current code
# =============================================================================


class TestImportRejectsMismatchedIssues:
    """Test that import rejects issues with mismatched ID prefixes.

    These tests demonstrate the contamination bug:
    - Current behavior: imports all issues regardless of ID prefix (BUG)
    - Expected behavior: skips issues whose ID doesn't match project name
    """

    def test_import_rejects_mismatched_issue_id_prefix(self, db_connection, tmp_path):
        """Import should SKIP issues whose ID prefix doesn't match project.

        Setup: JSONL with change-capture-xxx issue
        Action: Import targeting change-capture-infra project
        Expected: Issue should be SKIPPED (not imported)
        """
        from trc_main import import_from_jsonl, get_issue

        jsonl_path = tmp_path / "issues.jsonl"
        jsonl_path.write_text(
            '{"id":"change-capture-abc123","title":"Wrong project issue","description":"","status":"open","priority":2,"created_at":"2025-01-15T10:00:00Z","updated_at":"2025-01-15T10:00:00Z","closed_at":null,"dependencies":[]}\n'
        )

        # Import with change-capture-infra as project
        stats = import_from_jsonl(
            db_connection,
            str(jsonl_path),
            project_id="gitlab.com/user/change-capture-infra",
        )

        # Should have skipped the issue (not created)
        assert stats["created"] == 0
        assert stats.get("skipped", 0) == 1

        # Issue should NOT exist in database
        issue = get_issue(db_connection, "change-capture-abc123")
        assert issue is None

    def test_import_contaminated_jsonl_only_imports_matching(
        self, db_connection, tmp_path, contaminated_jsonl_content
    ):
        """Import should only import issues matching the project.

        Setup: JSONL with issues from TWO projects mixed together
        Action: Import targeting change-capture-infra
        Expected: Only change-capture-infra-xxx imported, others skipped
        """
        from trc_main import import_from_jsonl, get_issue

        jsonl_path = tmp_path / "issues.jsonl"
        jsonl_path.write_text(contaminated_jsonl_content)

        stats = import_from_jsonl(
            db_connection,
            str(jsonl_path),
            project_id="gitlab.com/user/change-capture-infra",
        )

        # Should only import the matching issue
        assert stats["created"] == 1
        assert stats.get("skipped", 0) == 1

        # Only the matching issue should exist
        wrong_issue = get_issue(db_connection, "change-capture-abc123")
        assert wrong_issue is None

        correct_issue = get_issue(db_connection, "change-capture-infra-xyz789")
        assert correct_issue is not None
        assert correct_issue["title"] == "Issue from change-capture-infra"

    def test_import_skipped_issues_reported_in_stats(self, db_connection, tmp_path):
        """Import stats should include count of skipped issues."""
        from trc_main import import_from_jsonl

        jsonl_path = tmp_path / "issues.jsonl"
        jsonl_path.write_text(
            '{"id":"wrong-project-abc","title":"Wrong 1","status":"open","priority":2,"created_at":"2025-01-15T10:00:00Z","updated_at":"2025-01-15T10:00:00Z","dependencies":[]}\n'
            '{"id":"wrong-project-def","title":"Wrong 2","status":"open","priority":2,"created_at":"2025-01-15T10:00:00Z","updated_at":"2025-01-15T10:00:00Z","dependencies":[]}\n'
            '{"id":"myapp-xyz789","title":"Correct","status":"open","priority":2,"created_at":"2025-01-15T10:00:00Z","updated_at":"2025-01-15T10:00:00Z","dependencies":[]}\n'
        )

        stats = import_from_jsonl(
            db_connection,
            str(jsonl_path),
            project_id="/path/to/myapp",
        )

        assert stats["created"] == 1
        assert stats.get("skipped", 0) == 2


# =============================================================================
# Export Validation Tests (Defense in Depth)
# =============================================================================


class TestExportFiltersToMatchingIds:
    """Test that export only exports issues with matching ID prefixes.

    Defense in depth: Even if contamination somehow gets into the DB,
    export should filter to only matching issues.
    """

    def test_export_only_exports_matching_issue_ids(self, db_connection, tmp_path):
        """Export should only include issues whose ID matches project name.

        Setup: Database has issues with correct project_id but wrong ID prefix
               (simulating existing contamination)
        Action: Export for the project
        Expected: Only issues with matching ID prefix should be exported
        """
        from trc_main import export_to_jsonl

        # Manually insert contaminated data (simulating existing bug)
        project_id = "/path/to/change-capture-infra"

        # Correct issue - ID matches project (6-char hash)
        db_connection.execute(
            """INSERT INTO issues (id, project_id, title, status, priority, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                "change-capture-infra-abc123",
                project_id,
                "Correct issue",
                "open",
                2,
                "2025-01-15T10:00:00Z",
                "2025-01-15T10:00:00Z",
            ),
        )

        # Contaminated issue - ID does NOT match project (but has same project_id)
        db_connection.execute(
            """INSERT INTO issues (id, project_id, title, status, priority, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                "change-capture-xyz789",
                project_id,  # Same project_id (contamination)
                "Contaminated issue",
                "open",
                2,
                "2025-01-15T10:00:00Z",
                "2025-01-15T10:00:00Z",
            ),
        )
        db_connection.commit()

        # Export
        jsonl_path = tmp_path / "issues.jsonl"
        export_to_jsonl(db_connection, project_id, str(jsonl_path))

        # Parse exported content
        lines = jsonl_path.read_text().strip().split("\n")
        exported_issues = [json.loads(line) for line in lines if line]

        # Should only export the matching issue
        assert len(exported_issues) == 1
        assert exported_issues[0]["id"] == "change-capture-infra-abc123"


# =============================================================================
# Prevention Tests (Sync Integration)
# =============================================================================


class TestSyncPreventsContamination:
    """Test that sync operations prevent contamination."""

    def test_sync_project_does_not_import_foreign_issues(
        self, db_connection, two_similar_projects
    ):
        """Sync should not import issues from other projects.

        Setup: change-capture-infra has contaminated JSONL
        Action: Sync change-capture-infra
        Expected: Only matching issues imported
        """
        from trc_main import sync_project, get_issue

        proj = two_similar_projects["proj2"]  # change-capture-infra

        # Write contaminated JSONL
        jsonl_path = proj["trace_dir"] / "issues.jsonl"
        jsonl_path.write_text(
            # Wrong project's issue
            '{"id":"change-capture-foreign","title":"Foreign issue","status":"open","priority":2,"created_at":"2025-01-15T10:00:00Z","updated_at":"2025-01-15T10:00:00Z","dependencies":[]}\n'
            # Correct project's issue
            '{"id":"change-capture-infra-native","title":"Native issue","status":"open","priority":2,"created_at":"2025-01-15T10:00:00Z","updated_at":"2025-01-15T10:00:00Z","dependencies":[]}\n'
        )

        # Sync
        sync_project(db_connection, proj["path"])

        # Foreign issue should NOT be imported
        foreign = get_issue(db_connection, "change-capture-foreign")
        assert foreign is None

        # Native issue should be imported
        native = get_issue(db_connection, "change-capture-infra-native")
        assert native is not None

    def test_contamination_feedback_loop_prevented(
        self, db_connection, two_similar_projects
    ):
        """Import → Export cycle should not propagate contamination.

        Setup: Contaminated JSONL
        Action: Import then export
        Expected: Contamination removed from exported file
        """
        from trc_main import import_from_jsonl, export_to_jsonl

        proj = two_similar_projects["proj2"]  # change-capture-infra
        project_id = proj["project_id"]

        # Initial contaminated JSONL
        jsonl_path = proj["trace_dir"] / "issues.jsonl"
        jsonl_path.write_text(
            '{"id":"change-capture-abc123","title":"Contaminated","status":"open","priority":2,"created_at":"2025-01-15T10:00:00Z","updated_at":"2025-01-15T10:00:00Z","dependencies":[]}\n'
            '{"id":"change-capture-infra-xyz789","title":"Clean","status":"open","priority":2,"created_at":"2025-01-15T10:00:00Z","updated_at":"2025-01-15T10:00:00Z","dependencies":[]}\n'
        )

        # Import (should skip contaminated)
        import_from_jsonl(db_connection, str(jsonl_path), project_id=project_id)

        # Export back
        export_to_jsonl(db_connection, project_id, str(jsonl_path))

        # Read exported content
        lines = jsonl_path.read_text().strip().split("\n")
        exported_issues = [json.loads(line) for line in lines if line]

        # Should only have the clean issue
        assert len(exported_issues) == 1
        assert exported_issues[0]["id"] == "change-capture-infra-xyz789"


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Edge case tests for contamination prevention."""

    def test_import_handles_partial_contamination(self, db_connection, tmp_path):
        """JSONL with mix of valid and invalid issues should work.

        Valid issues should import, invalid ones skipped with warning.
        """
        from trc_main import import_from_jsonl, get_issue

        jsonl_path = tmp_path / "issues.jsonl"
        jsonl_path.write_text(
            '{"id":"myapp-valid1","title":"Valid 1","status":"open","priority":2,"created_at":"2025-01-15T10:00:00Z","updated_at":"2025-01-15T10:00:00Z","dependencies":[]}\n'
            '{"id":"other-invalid","title":"Invalid","status":"open","priority":2,"created_at":"2025-01-15T10:00:00Z","updated_at":"2025-01-15T10:00:00Z","dependencies":[]}\n'
            '{"id":"myapp-valid2","title":"Valid 2","status":"open","priority":2,"created_at":"2025-01-15T10:00:00Z","updated_at":"2025-01-15T10:00:00Z","dependencies":[]}\n'
        )

        stats = import_from_jsonl(
            db_connection,
            str(jsonl_path),
            project_id="/path/to/myapp",
        )

        # Should import valid, skip invalid
        assert stats["created"] == 2
        assert stats.get("skipped", 0) == 1

        # Valid issues exist
        assert get_issue(db_connection, "myapp-valid1") is not None
        assert get_issue(db_connection, "myapp-valid2") is not None

        # Invalid issue not imported
        assert get_issue(db_connection, "other-invalid") is None

    def test_project_name_extracted_from_project_id_url(self, db_connection, tmp_path):
        """Project name should be correctly extracted from URL-style project_id."""
        from trc_main import import_from_jsonl, get_issue

        jsonl_path = tmp_path / "issues.jsonl"
        jsonl_path.write_text(
            '{"id":"my-repo-abc123","title":"Valid","status":"open","priority":2,"created_at":"2025-01-15T10:00:00Z","updated_at":"2025-01-15T10:00:00Z","dependencies":[]}\n'
            '{"id":"other-xyz789","title":"Invalid","status":"open","priority":2,"created_at":"2025-01-15T10:00:00Z","updated_at":"2025-01-15T10:00:00Z","dependencies":[]}\n'
        )

        # URL-style project_id
        stats = import_from_jsonl(
            db_connection,
            str(jsonl_path),
            project_id="github.com/user/my-repo",
        )

        assert stats["created"] == 1
        assert stats.get("skipped", 0) == 1

        assert get_issue(db_connection, "my-repo-abc123") is not None
        assert get_issue(db_connection, "other-xyz789") is None

    def test_import_with_path_style_project_id(self, db_connection, tmp_path):
        """Project name should be correctly extracted from path-style project_id."""
        from trc_main import import_from_jsonl, get_issue

        jsonl_path = tmp_path / "issues.jsonl"
        jsonl_path.write_text(
            '{"id":"myapp-abc123","title":"Valid","status":"open","priority":2,"created_at":"2025-01-15T10:00:00Z","updated_at":"2025-01-15T10:00:00Z","dependencies":[]}\n'
        )

        # Path-style project_id
        stats = import_from_jsonl(
            db_connection,
            str(jsonl_path),
            project_id="/Users/user/repos/myapp",
        )

        assert stats["created"] == 1
        assert get_issue(db_connection, "myapp-abc123") is not None


# =============================================================================
# Update Validation Tests
# =============================================================================


class TestUpdateValidation:
    """Test that updates also validate issue ownership."""

    def test_update_rejects_reassigning_issue_to_wrong_project(
        self, db_connection, tmp_path
    ):
        """Updates should not allow reassigning issues to wrong projects.

        If an issue exists in the correct project, importing it from
        a different project's JSONL should not change its project_id.
        """
        from trc_main import create_issue, import_from_jsonl, get_issue

        # Create issue in correct project
        issue = create_issue(
            db_connection,
            "/path/to/myapp",
            "myapp",
            "Original title",
        )
        assert issue is not None
        issue_id = issue["id"]

        # Try to import same issue from different project's JSONL
        jsonl_path = tmp_path / "issues.jsonl"
        jsonl_path.write_text(
            f'{{"id":"{issue_id}","title":"Modified title","status":"open","priority":2,"created_at":"2025-01-15T10:00:00Z","updated_at":"2025-01-15T10:00:00Z","dependencies":[]}}\n'
        )

        # Import with different project - should skip since ID prefix doesn't match
        stats = import_from_jsonl(
            db_connection,
            str(jsonl_path),
            project_id="/path/to/other-project",
        )

        # Should skip (not update) because ID prefix doesn't match other-project
        assert stats["updated"] == 0
        assert stats.get("skipped", 0) == 1

        # Issue should retain original title
        updated = get_issue(db_connection, issue_id)
        assert updated is not None
        assert updated["title"] == "Original title"
        assert updated["project_id"] == "/path/to/myapp"


# =============================================================================
# Repair Command Tests
# =============================================================================


class TestRepairContaminatedIssues:
    """Test the repair_contaminated_issues function."""

    def test_repair_dry_run_shows_contamination(self, db_connection, tmp_path):
        """Dry run should show what would be repaired without making changes."""
        from trc_main import repair_contaminated_issues, register_project

        # Register two projects
        proj1_path = tmp_path / "myapp"
        proj1_path.mkdir()
        (proj1_path / ".git").mkdir()
        register_project(db_connection, "myapp", str(proj1_path))

        proj2_path = tmp_path / "other"
        proj2_path.mkdir()
        (proj2_path / ".git").mkdir()
        register_project(db_connection, "other", str(proj2_path))

        # Insert contaminated issue (myapp issue assigned to other project)
        db_connection.execute(
            """INSERT INTO issues (id, project_id, title, status, priority, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                "myapp-abc123",
                str(proj2_path),  # Wrong project!
                "Contaminated issue",
                "open",
                2,
                "2025-01-15T10:00:00Z",
                "2025-01-15T10:00:00Z",
            ),
        )
        db_connection.commit()

        # Dry run should detect contamination
        stats = repair_contaminated_issues(db_connection, dry_run=True)

        assert stats["examined"] >= 1
        assert stats["contaminated"] == 1
        assert stats["repaired"] == 1  # Would-be-repaired count

        # Issue should still be in wrong project (dry run doesn't modify DB)
        cursor = db_connection.execute(
            "SELECT project_id FROM issues WHERE id = ?", ("myapp-abc123",)
        )
        row = cursor.fetchone()
        assert row[0] == str(proj2_path)

    def test_repair_fixes_contaminated_issues(self, db_connection, tmp_path):
        """Repair should reassign contaminated issues to correct project."""
        from trc_main import repair_contaminated_issues, register_project

        # Register two projects
        proj1_path = tmp_path / "myapp"
        proj1_path.mkdir()
        (proj1_path / ".git").mkdir()
        register_project(db_connection, "myapp", str(proj1_path))

        proj2_path = tmp_path / "other"
        proj2_path.mkdir()
        (proj2_path / ".git").mkdir()
        register_project(db_connection, "other", str(proj2_path))

        # Insert contaminated issue
        db_connection.execute(
            """INSERT INTO issues (id, project_id, title, status, priority, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                "myapp-abc123",
                str(proj2_path),  # Wrong project!
                "Contaminated issue",
                "open",
                2,
                "2025-01-15T10:00:00Z",
                "2025-01-15T10:00:00Z",
            ),
        )
        db_connection.commit()

        # Repair should fix it
        stats = repair_contaminated_issues(db_connection, dry_run=False)

        assert stats["contaminated"] == 1
        assert stats["repaired"] == 1
        assert stats["orphaned"] == 0

        # Issue should now be in correct project
        cursor = db_connection.execute(
            "SELECT project_id FROM issues WHERE id = ?", ("myapp-abc123",)
        )
        row = cursor.fetchone()
        assert row[0] == str(proj1_path)

    def test_repair_handles_orphaned_issues(self, db_connection, tmp_path):
        """Issues with no matching project should be marked as orphaned."""
        from trc_main import repair_contaminated_issues, register_project

        # Register only one project
        proj_path = tmp_path / "other"
        proj_path.mkdir()
        (proj_path / ".git").mkdir()
        register_project(db_connection, "other", str(proj_path))

        # Insert orphaned issue (no 'myapp' project exists)
        db_connection.execute(
            """INSERT INTO issues (id, project_id, title, status, priority, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                "myapp-abc123",
                str(proj_path),  # Wrong project, and correct one doesn't exist
                "Orphaned issue",
                "open",
                2,
                "2025-01-15T10:00:00Z",
                "2025-01-15T10:00:00Z",
            ),
        )
        db_connection.commit()

        stats = repair_contaminated_issues(db_connection, dry_run=False)

        assert stats["contaminated"] == 1
        assert stats["repaired"] == 0
        assert stats["orphaned"] == 1

        # Issue should still be in wrong project (no fix possible)
        cursor = db_connection.execute(
            "SELECT project_id FROM issues WHERE id = ?", ("myapp-abc123",)
        )
        row = cursor.fetchone()
        assert row[0] == str(proj_path)

    def test_repair_specific_project_only(self, db_connection, tmp_path):
        """Repair with project filter should only examine that project."""
        from trc_main import repair_contaminated_issues, register_project

        # Register three projects
        proj1_path = tmp_path / "myapp"
        proj1_path.mkdir()
        (proj1_path / ".git").mkdir()
        register_project(db_connection, "myapp", str(proj1_path))

        proj2_path = tmp_path / "other"
        proj2_path.mkdir()
        (proj2_path / ".git").mkdir()
        register_project(db_connection, "other", str(proj2_path))

        proj3_path = tmp_path / "third"
        proj3_path.mkdir()
        (proj3_path / ".git").mkdir()
        register_project(db_connection, "third", str(proj3_path))

        # Insert contaminated issues in different projects
        db_connection.execute(
            """INSERT INTO issues (id, project_id, title, status, priority, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                "myapp-abc123",
                str(proj2_path),  # Wrong - should be myapp
                "Contaminated in other",
                "open",
                2,
                "2025-01-15T10:00:00Z",
                "2025-01-15T10:00:00Z",
            ),
        )
        db_connection.execute(
            """INSERT INTO issues (id, project_id, title, status, priority, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                "third-xyz789",
                str(proj2_path),  # Wrong - should be third
                "Contaminated in other (third)",
                "open",
                2,
                "2025-01-15T10:00:00Z",
                "2025-01-15T10:00:00Z",
            ),
        )
        db_connection.commit()

        # Repair only 'other' project
        stats = repair_contaminated_issues(
            db_connection, project_id=str(proj2_path), dry_run=False
        )

        # Should have repaired both issues in 'other' project
        assert stats["examined"] == 2
        assert stats["contaminated"] == 2
        assert stats["repaired"] == 2

    def test_repair_returns_affected_projects(self, db_connection, tmp_path):
        """Repair should return list of affected projects for re-export."""
        from trc_main import repair_contaminated_issues, register_project

        # Register two projects
        proj1_path = tmp_path / "myapp"
        proj1_path.mkdir()
        (proj1_path / ".git").mkdir()
        register_project(db_connection, "myapp", str(proj1_path))

        proj2_path = tmp_path / "other"
        proj2_path.mkdir()
        (proj2_path / ".git").mkdir()
        register_project(db_connection, "other", str(proj2_path))

        # Insert contaminated issue
        db_connection.execute(
            """INSERT INTO issues (id, project_id, title, status, priority, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                "myapp-abc123",
                str(proj2_path),
                "Contaminated",
                "open",
                2,
                "2025-01-15T10:00:00Z",
                "2025-01-15T10:00:00Z",
            ),
        )
        db_connection.commit()

        stats = repair_contaminated_issues(db_connection, dry_run=False)

        # Should include affected projects
        assert "affected_projects" in stats
        # Source (other) and destination (myapp) are affected
        assert str(proj1_path) in stats["affected_projects"]
        assert str(proj2_path) in stats["affected_projects"]

    def test_repair_similar_project_names(
        self, db_connection, two_similar_projects
    ):
        """Repair should correctly handle similar project names."""
        from trc_main import repair_contaminated_issues, register_project

        proj1 = two_similar_projects["proj1"]  # change-capture
        proj2 = two_similar_projects["proj2"]  # change-capture-infra

        # Register both projects
        register_project(db_connection, proj1["name"], proj1["path"])
        register_project(db_connection, proj2["name"], proj2["path"])

        # Insert contaminated issue: change-capture issue in change-capture-infra
        db_connection.execute(
            """INSERT INTO issues (id, project_id, title, status, priority, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                "change-capture-abc123",
                proj2["path"],  # Wrong - should be proj1
                "Wrong project",
                "open",
                2,
                "2025-01-15T10:00:00Z",
                "2025-01-15T10:00:00Z",
            ),
        )
        # Insert correct issue
        db_connection.execute(
            """INSERT INTO issues (id, project_id, title, status, priority, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                "change-capture-infra-xyz789",
                proj2["path"],  # Correct
                "Correct project",
                "open",
                2,
                "2025-01-15T10:00:00Z",
                "2025-01-15T10:00:00Z",
            ),
        )
        db_connection.commit()

        stats = repair_contaminated_issues(db_connection, dry_run=False)

        # Should repair only the contaminated one
        assert stats["contaminated"] == 1
        assert stats["repaired"] == 1

        # Verify assignments
        cursor = db_connection.execute(
            "SELECT project_id FROM issues WHERE id = ?", ("change-capture-abc123",)
        )
        assert cursor.fetchone()[0] == proj1["path"]

        cursor = db_connection.execute(
            "SELECT project_id FROM issues WHERE id = ?",
            ("change-capture-infra-xyz789",),
        )
        assert cursor.fetchone()[0] == proj2["path"]
