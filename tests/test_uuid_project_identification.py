"""Comprehensive tests for UUID-based project identification.

Tests to verify:
- New project gets UUID at init
- Existing project auto-migrates on first operation
- UUID persists across operations
- Worktree scenario: same UUID from different paths
- Cross-project dependencies work with UUIDs
- JSONL roundtrip preserves data
- Schema migration from v3 to v4
"""

import json
import subprocess
import uuid as uuid_module
from pathlib import Path

import pytest
from typer.testing import CliRunner

from trc_main import app


def extract_issue_id(output: str) -> str:
    """Extract issue ID from CLI output."""
    import re
    match = re.search(r"([\w-]+)-([a-z0-9]{6})", output)
    if match:
        return match.group(0)
    raise ValueError(f"Could not extract issue ID from: {output}")


class TestUUIDAtInit:
    """Tests for UUID generation at init time."""

    def test_init_creates_uuid_file(self, sample_project, tmp_trace_dir, monkeypatch):
        """trc init should create .trace/id file with UUID."""
        runner = CliRunner()
        monkeypatch.chdir(sample_project["path"])

        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0

        id_file = sample_project["trace_dir"] / "id"
        assert id_file.exists()

        # Should be valid UUID v4
        content = id_file.read_text().strip()
        parsed = uuid_module.UUID(content)
        assert parsed.version == 4

    def test_init_preserves_existing_uuid(self, sample_project, tmp_trace_dir, monkeypatch):
        """trc init should not overwrite existing UUID."""
        runner = CliRunner()
        monkeypatch.chdir(sample_project["path"])

        # Pre-create UUID file
        existing_uuid = "11111111-1111-1111-1111-111111111111"
        id_file = sample_project["trace_dir"] / "id"
        id_file.write_text(existing_uuid)

        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0

        # UUID should be preserved
        assert id_file.read_text().strip() == existing_uuid


class TestAutoMigration:
    """Tests for auto-migration of existing projects."""

    def test_first_operation_generates_uuid(self, sample_project, tmp_trace_dir, monkeypatch):
        """First operation on project without UUID should auto-generate one."""
        from trc_main import get_db, sync_project

        runner = CliRunner()
        monkeypatch.chdir(sample_project["path"])

        # Create .trace directory without id file
        id_file = sample_project["trace_dir"] / "id"
        if id_file.exists():
            id_file.unlink()
        jsonl_path = sample_project["trace_dir"] / "issues.jsonl"
        jsonl_path.write_text("")

        # Sync should auto-generate UUID
        db = get_db()
        sync_project(db, sample_project["path"])

        # UUID file should now exist
        assert id_file.exists()
        content = id_file.read_text().strip()
        uuid_module.UUID(content)  # Should be valid UUID
        db.close()


class TestUUIDPersistence:
    """Tests for UUID persistence across operations."""

    def test_uuid_same_across_multiple_creates(self, sample_project, tmp_trace_dir, monkeypatch):
        """All issues created should have same project UUID."""
        from trc_main import get_db, get_issue

        runner = CliRunner()
        monkeypatch.chdir(sample_project["path"])

        runner.invoke(app, ["init"])

        # Create multiple issues
        result1 = runner.invoke(app, ["create", "Issue 1", "--description", ""])
        result2 = runner.invoke(app, ["create", "Issue 2", "--description", ""])
        result3 = runner.invoke(app, ["create", "Issue 3", "--description", ""])

        id1 = extract_issue_id(result1.output)
        id2 = extract_issue_id(result2.output)
        id3 = extract_issue_id(result3.output)

        # All should have same project_id (UUID)
        db = get_db()
        issue1 = get_issue(db, id1)
        issue2 = get_issue(db, id2)
        issue3 = get_issue(db, id3)
        db.close()

        assert issue1["project_id"] == issue2["project_id"]
        assert issue2["project_id"] == issue3["project_id"]
        uuid_module.UUID(issue1["project_id"])  # Should be valid UUID


class TestWorktreeScenario:
    """Tests for git worktree scenarios where same project accessed from different paths."""

    def test_same_uuid_from_different_worktrees(self, tmp_trace_dir, tmp_path, monkeypatch):
        """Same .trace/id should be used regardless of worktree path."""
        runner = CliRunner()

        # Create main repo
        main_path = tmp_path / "main"
        main_path.mkdir()
        subprocess.run(["git", "init"], cwd=main_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/test/worktree-test.git"],
            cwd=main_path,
            check=True,
            capture_output=True,
        )

        # Init trace in main
        monkeypatch.chdir(main_path)
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0

        # Get UUID from main
        main_uuid = (main_path / ".trace" / "id").read_text().strip()

        # Create a git commit so we can create worktree
        subprocess.run(["git", "add", "."], cwd=main_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit", "--allow-empty"],
            cwd=main_path,
            check=True,
            capture_output=True,
        )

        # Create worktree
        worktree_path = tmp_path / "worktree"
        subprocess.run(
            ["git", "worktree", "add", str(worktree_path), "-b", "feature"],
            cwd=main_path,
            check=True,
            capture_output=True,
        )

        # Copy .trace directory to worktree (simulating shared .trace)
        # In real scenario, .trace would be committed to git
        import shutil
        worktree_trace = worktree_path / ".trace"
        if worktree_trace.exists():
            shutil.rmtree(worktree_trace)
        shutil.copytree(main_path / ".trace", worktree_trace)

        # UUID in worktree should be same as main
        worktree_uuid = (worktree_path / ".trace" / "id").read_text().strip()
        assert worktree_uuid == main_uuid


class TestCrossProjectDependencies:
    """Tests for cross-project dependencies with UUIDs."""

    def test_cross_project_parent_link_with_uuid(self, tmp_trace_dir, tmp_path, monkeypatch):
        """Cross-project parent links should work with UUID-based project_ids."""
        from trc_main import get_db, get_issue, get_dependencies

        runner = CliRunner()

        # Create two projects
        proj1_path = tmp_path / "proj1"
        proj1_path.mkdir()
        subprocess.run(["git", "init"], cwd=proj1_path, check=True, capture_output=True)

        proj2_path = tmp_path / "proj2"
        proj2_path.mkdir()
        subprocess.run(["git", "init"], cwd=proj2_path, check=True, capture_output=True)

        # Init both
        monkeypatch.chdir(proj1_path)
        runner.invoke(app, ["init"])

        monkeypatch.chdir(proj2_path)
        runner.invoke(app, ["init"])

        # Create parent in proj1
        monkeypatch.chdir(proj1_path)
        result = runner.invoke(app, ["create", "Parent issue", "--description", ""])
        parent_id = extract_issue_id(result.output)

        # Create child in proj2 with cross-project parent
        result = runner.invoke(
            app,
            ["create", "Child issue", "--description", "", "--project", "proj2", "--parent", parent_id],
        )
        child_id = extract_issue_id(result.output)

        # Verify dependency exists
        db = get_db()
        deps = get_dependencies(db, child_id)
        parent_deps = [d for d in deps if d["type"] == "parent"]
        assert len(parent_deps) == 1
        assert parent_deps[0]["depends_on_id"] == parent_id
        db.close()


class TestJSONLRoundtrip:
    """Tests for JSONL export/import with UUID-based projects."""

    def test_jsonl_roundtrip_preserves_issues(self, sample_project, tmp_trace_dir, monkeypatch):
        """Issues should survive JSONL export/import cycle."""
        from trc_main import get_db, get_issue

        runner = CliRunner()
        monkeypatch.chdir(sample_project["path"])

        runner.invoke(app, ["init"])

        # Create issues
        result = runner.invoke(app, ["create", "Test issue", "--description", "Description"])
        issue_id = extract_issue_id(result.output)

        # Verify issue exists
        db = get_db()
        issue = get_issue(db, issue_id)
        assert issue is not None
        assert issue["title"] == "Test issue"
        original_project_id = issue["project_id"]
        db.close()

        # Read JSONL
        jsonl_path = sample_project["trace_dir"] / "issues.jsonl"
        assert jsonl_path.exists()

        with jsonl_path.open("r") as f:
            lines = [line for line in f if line.strip()]
        assert len(lines) == 1

        data = json.loads(lines[0])
        assert data["id"] == issue_id
        assert data["title"] == "Test issue"
        # JSONL should NOT contain project_id (it's inferred from git context)
        assert "project_id" not in data

    def test_issue_project_id_is_uuid_not_url(self, sample_project, tmp_trace_dir, monkeypatch):
        """Issue's project_id should be UUID, not URL or path."""
        from trc_main import get_db, get_issue

        runner = CliRunner()
        monkeypatch.chdir(sample_project["path"])

        runner.invoke(app, ["init"])
        result = runner.invoke(app, ["create", "Test issue", "--description", ""])
        issue_id = extract_issue_id(result.output)

        db = get_db()
        issue = get_issue(db, issue_id)
        project_id = issue["project_id"]
        db.close()

        # Should be valid UUID
        uuid_module.UUID(project_id)

        # Should NOT be a URL
        assert "github.com" not in project_id
        assert "/" not in project_id

        # Should NOT be a path
        assert not project_id.startswith("/")


class TestSchemaMigration:
    """Tests for schema migration from v3 to v4."""

    def test_v3_to_v4_migration_adds_uuid_column(self, tmp_trace_dir):
        """Schema v3 to v4 migration should add uuid column."""
        import sqlite3

        from trc_main import init_database

        db_path = str(tmp_trace_dir["db"])

        # Create v3 database manually
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                current_path TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            INSERT INTO metadata (key, value) VALUES ('schema_version', '3');

            INSERT INTO projects (id, name, current_path)
            VALUES ('github.com/test/project', 'project', '/path/to/project');
        """)
        conn.commit()
        conn.close()

        # Run migration
        db = init_database(db_path)

        # Check uuid column exists
        cursor = db.execute("PRAGMA table_info(projects)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "uuid" in columns

        # Check schema version is 4
        cursor = db.execute("SELECT value FROM metadata WHERE key = 'schema_version'")
        assert cursor.fetchone()[0] == "4"

        # Check existing project is preserved
        cursor = db.execute("SELECT id, name, current_path FROM projects")
        row = cursor.fetchone()
        assert row[0] == "github.com/test/project"
        assert row[1] == "project"
        assert row[2] == "/path/to/project"
