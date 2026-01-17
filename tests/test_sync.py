"""Tests for JSONL import/export and file locking."""

import json

import pytest


def test_export_to_jsonl_creates_file(db_connection, tmp_path):
    """Should create JSONL file with issues."""
    from trc_main import create_issue, export_to_jsonl

    create_issue(db_connection, "/path/to/myapp", "myapp", "Issue 1")
    create_issue(db_connection, "/path/to/myapp", "myapp", "Issue 2")

    jsonl_path = tmp_path / "issues.jsonl"
    export_to_jsonl(db_connection, "/path/to/myapp", str(jsonl_path))

    assert jsonl_path.exists()
    lines = jsonl_path.read_text().strip().split("\n")
    assert len(lines) == 2


def test_export_to_jsonl_sorts_by_id(db_connection, tmp_path):
    """Should sort issues by ID for stable diffs."""
    from trc_main import create_issue, export_to_jsonl

    # Create in reverse order
    _issue2 = create_issue(db_connection, "/path/to/myapp", "myapp", "Issue Z")
    _issue1 = create_issue(db_connection, "/path/to/myapp", "myapp", "Issue A")

    jsonl_path = tmp_path / "issues.jsonl"
    export_to_jsonl(db_connection, "/path/to/myapp", str(jsonl_path))

    lines = jsonl_path.read_text().strip().split("\n")
    data1 = json.loads(lines[0])
    data2 = json.loads(lines[1])

    # Should be sorted by ID
    assert data1["id"] < data2["id"]


def test_export_to_jsonl_includes_all_fields(db_connection, tmp_path):
    """Should include all issue fields in export."""
    from trc_main import create_issue, export_to_jsonl

    issue = create_issue(
        db_connection,
        "/path/to/myapp",
        "myapp",
        "Test Issue",
        description="Test description",
        priority=1,
        status="in_progress",
    )
    assert issue is not None

    jsonl_path = tmp_path / "issues.jsonl"
    export_to_jsonl(db_connection, "/path/to/myapp", str(jsonl_path))

    line = jsonl_path.read_text().strip()
    data = json.loads(line)

    assert data["id"] == issue["id"]
    assert data["title"] == "Test Issue"
    assert data["description"] == "Test description"
    assert data["status"] == "in_progress"
    assert data["priority"] == 1
    assert "created_at" in data
    assert "updated_at" in data


def test_export_to_jsonl_includes_dependencies(db_connection, tmp_path):
    """Should include dependencies inline in issue."""
    from trc_main import create_issue, add_dependency, export_to_jsonl

    parent = create_issue(db_connection, "/path/to/myapp", "myapp", "Parent")
    child = create_issue(db_connection, "/path/to/myapp", "myapp", "Child")
    assert parent is not None
    assert child is not None

    add_dependency(db_connection, child["id"], parent["id"], "parent")

    jsonl_path = tmp_path / "issues.jsonl"
    export_to_jsonl(db_connection, "/path/to/myapp", str(jsonl_path))

    lines = jsonl_path.read_text().strip().split("\n")

    # Find child issue
    for line in lines:
        data = json.loads(line)
        if data["id"] == child["id"]:
            assert "dependencies" in data
            assert len(data["dependencies"]) == 1
            assert data["dependencies"][0]["depends_on_id"] == parent["id"]
            assert data["dependencies"][0]["type"] == "parent"
            break
    else:
        pytest.fail("Child issue not found in export")


def test_export_to_jsonl_only_exports_project_issues(db_connection, tmp_path):
    """Should only export issues for specified project."""
    from trc_main import create_issue, export_to_jsonl

    create_issue(db_connection, "/path/to/myapp", "myapp", "App issue")
    create_issue(db_connection, "/path/to/mylib", "mylib", "Lib issue")

    jsonl_path = tmp_path / "issues.jsonl"
    export_to_jsonl(db_connection, "/path/to/myapp", str(jsonl_path))

    lines = jsonl_path.read_text().strip().split("\n")
    issues = [json.loads(line) for line in lines]

    assert len(issues) == 1
    # project_id no longer in JSONL (removed for portability)
    assert "project_id" not in issues[0]
    # Verify it's the right issue by checking title
    assert issues[0]["title"] == "App issue"


def test_export_to_jsonl_handles_empty_project(db_connection, tmp_path):
    """Should create empty file for project with no issues."""
    from trc_main import export_to_jsonl

    jsonl_path = tmp_path / "issues.jsonl"
    export_to_jsonl(db_connection, "/path/to/myapp", str(jsonl_path))

    assert jsonl_path.exists()
    assert jsonl_path.read_text().strip() == ""


def test_export_to_jsonl_overwrites_existing_file(db_connection, tmp_path):
    """Should overwrite existing JSONL file."""
    from trc_main import create_issue, export_to_jsonl

    jsonl_path = tmp_path / "issues.jsonl"
    jsonl_path.write_text("old content\n")

    create_issue(db_connection, "/path/to/myapp", "myapp", "New issue")
    export_to_jsonl(db_connection, "/path/to/myapp", str(jsonl_path))

    lines = jsonl_path.read_text().strip().split("\n")
    assert len(lines) == 1
    assert "old content" not in jsonl_path.read_text()


def test_import_from_jsonl_creates_issues(db_connection, tmp_path):
    """Should import issues from JSONL file."""
    from trc_main import import_from_jsonl, get_issue

    jsonl_path = tmp_path / "issues.jsonl"
    jsonl_path.write_text(
        '{"id":"myapp-abc123","project_id":"/path/to/myapp","title":"Test 1","description":"","status":"open","priority":2,"created_at":"2025-01-15T10:00:00Z","updated_at":"2025-01-15T10:00:00Z","closed_at":null,"dependencies":[]}\n'
        '{"id":"myapp-def456","project_id":"/path/to/myapp","title":"Test 2","description":"Desc","status":"closed","priority":1,"created_at":"2025-01-15T11:00:00Z","updated_at":"2025-01-15T12:00:00Z","closed_at":"2025-01-15T12:00:00Z","dependencies":[]}\n'
    )

    # New signature requires project_id parameter
    stats = import_from_jsonl(db_connection, str(jsonl_path), project_id="/path/to/myapp")

    assert stats["created"] == 2
    assert stats["updated"] == 0

    issue1 = get_issue(db_connection, "myapp-abc123")
    assert issue1 is not None
    assert issue1["title"] == "Test 1"
    assert issue1["status"] == "open"

    issue2 = get_issue(db_connection, "myapp-def456")
    assert issue2 is not None
    assert issue2["title"] == "Test 2"
    assert issue2["status"] == "closed"


def test_import_from_jsonl_updates_existing_issues(db_connection, tmp_path):
    """Should update issues that already exist."""
    from trc_main import create_issue, import_from_jsonl, get_issue

    # Create issue in DB
    create_issue(db_connection, "/path/to/myapp", "myapp", "Old title")

    # Get the ID that was generated
    cursor = db_connection.execute("SELECT id FROM issues WHERE title = 'Old title'")
    issue_id = cursor.fetchone()[0]

    # Import with updated title
    jsonl_path = tmp_path / "issues.jsonl"
    jsonl_path.write_text(
        f'{{"id":"{issue_id}","project_id":"/path/to/myapp","title":"New title","description":"","status":"open","priority":2,"created_at":"2025-01-15T10:00:00Z","updated_at":"2025-01-15T10:00:00Z","closed_at":null,"dependencies":[]}}\n'
    )

    stats = import_from_jsonl(db_connection, str(jsonl_path), project_id="/path/to/myapp")

    assert stats["created"] == 0
    assert stats["updated"] == 1

    updated = get_issue(db_connection, issue_id)
    assert updated is not None
    assert updated["title"] == "New title"


def test_import_from_jsonl_creates_dependencies(db_connection, tmp_path):
    """Should create dependencies from imported data."""
    from trc_main import import_from_jsonl, get_dependencies

    jsonl_path = tmp_path / "issues.jsonl"
    jsonl_path.write_text(
        '{"id":"myapp-abc123","project_id":"/path/to/myapp","title":"Parent","description":"","status":"open","priority":2,"created_at":"2025-01-15T10:00:00Z","updated_at":"2025-01-15T10:00:00Z","closed_at":null,"dependencies":[]}\n'
        '{"id":"myapp-def456","project_id":"/path/to/myapp","title":"Child","description":"","status":"open","priority":2,"created_at":"2025-01-15T10:00:00Z","updated_at":"2025-01-15T10:00:00Z","closed_at":null,"dependencies":[{"depends_on_id":"myapp-abc123","type":"parent"}]}\n'
    )

    import_from_jsonl(db_connection, str(jsonl_path), project_id="/path/to/myapp")

    deps = get_dependencies(db_connection, "myapp-def456")

    assert len(deps) == 1
    assert deps[0]["depends_on_id"] == "myapp-abc123"
    assert deps[0]["type"] == "parent"


def test_import_from_jsonl_skips_invalid_lines(db_connection, tmp_path):
    """Should skip malformed JSON lines and continue."""
    from trc_main import import_from_jsonl, get_issue

    jsonl_path = tmp_path / "issues.jsonl"
    jsonl_path.write_text(
        '{"id":"myapp-abc123","project_id":"/path/to/myapp","title":"Valid 1","status":"open","priority":2,"created_at":"2025-01-15T10:00:00Z","updated_at":"2025-01-15T10:00:00Z","dependencies":[]}\n'
        'invalid json line\n'
        '{"id":"myapp-def456","project_id":"/path/to/myapp","title":"Valid 2","status":"open","priority":2,"created_at":"2025-01-15T10:00:00Z","updated_at":"2025-01-15T10:00:00Z","dependencies":[]}\n'
    )

    stats = import_from_jsonl(db_connection, str(jsonl_path), project_id="/path/to/myapp")

    # Should import 2 valid lines, skip 1 invalid
    assert stats["created"] == 2
    assert stats["errors"] == 1

    assert get_issue(db_connection, "myapp-abc123") is not None
    assert get_issue(db_connection, "myapp-def456") is not None


def test_import_from_jsonl_handles_empty_file(db_connection, tmp_path):
    """Should handle empty JSONL file."""
    from trc_main import import_from_jsonl

    jsonl_path = tmp_path / "issues.jsonl"
    jsonl_path.write_text("")

    stats = import_from_jsonl(db_connection, str(jsonl_path), project_id="/path/to/myapp")

    assert stats["created"] == 0
    assert stats["updated"] == 0


def test_export_import_roundtrip(db_connection, tmp_path):
    """Export and import should preserve all data."""
    from trc_main import create_issue, add_dependency, export_to_jsonl, import_from_jsonl, get_issue

    # Create issues with dependencies
    parent = create_issue(db_connection, "/path/to/myapp", "myapp", "Parent", priority=0)
    child = create_issue(
        db_connection,
        "/path/to/myapp",
        "myapp",
        "Child",
        description="Child desc",
        priority=1,
        status="in_progress",
    )
    assert parent is not None
    assert child is not None
    add_dependency(db_connection, child["id"], parent["id"], "parent")

    # Export
    jsonl_path = tmp_path / "issues.jsonl"
    export_to_jsonl(db_connection, "/path/to/myapp", str(jsonl_path))

    # Clear database
    db_connection.execute("DELETE FROM dependencies")
    db_connection.execute("DELETE FROM issues")
    db_connection.commit()

    # Import
    import_from_jsonl(db_connection, str(jsonl_path), project_id="/path/to/myapp")

    # Verify
    parent_restored = get_issue(db_connection, parent["id"])
    child_restored = get_issue(db_connection, child["id"])
    assert parent_restored is not None
    assert child_restored is not None

    assert parent_restored["title"] == "Parent"
    assert parent_restored["priority"] == 0

    assert child_restored["title"] == "Child"
    assert child_restored["description"] == "Child desc"
    assert child_restored["priority"] == 1
    assert child_restored["status"] == "in_progress"

    from trc_main import get_dependencies

    deps = get_dependencies(db_connection, child["id"])
    assert len(deps) == 1
    assert deps[0]["depends_on_id"] == parent["id"]


def test_get_last_sync_time_returns_none_for_new_project(db_connection):
    """Should return None for project that has never been synced."""
    from trc_main import get_last_sync_time

    result = get_last_sync_time(db_connection, "/path/to/myapp")

    assert result is None


def test_set_last_sync_time_stores_timestamp(db_connection):
    """Should store sync timestamp for project."""
    from trc_main import set_last_sync_time, get_last_sync_time
    import time

    timestamp = time.time()
    set_last_sync_time(db_connection, "/path/to/myapp", timestamp)

    result = get_last_sync_time(db_connection, "/path/to/myapp")

    assert result == timestamp


def test_set_last_sync_time_updates_existing(db_connection):
    """Should update existing sync timestamp."""
    from trc_main import set_last_sync_time, get_last_sync_time

    set_last_sync_time(db_connection, "/path/to/myapp", 100.0)
    set_last_sync_time(db_connection, "/path/to/myapp", 200.0)

    result = get_last_sync_time(db_connection, "/path/to/myapp")

    assert result == 200.0


def test_sync_project_imports_when_jsonl_newer(db_connection, tmp_path):
    """Should import JSONL when file is newer than last sync."""
    from trc_main import sync_project, get_issue, set_last_sync_time, detect_project
    import time

    # Create git repo (required for sync_project)
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    config = git_dir / "config"
    config.write_text("[core]\n\trepositoryformatversion = 0\n")

    # Detect project to get proper project_id
    project = detect_project(cwd=str(tmp_path))
    assert project is not None
    project_id = project["id"]
    project_name = project["name"]

    # Create issue ID that matches project name (6-char hash required)
    issue_id = f"{project_name}-abc123"

    # Create JSONL file
    trace_dir = tmp_path / ".trace"
    trace_dir.mkdir(exist_ok=True)
    jsonl_path = trace_dir / "issues.jsonl"
    jsonl_path.write_text(
        '{"id":"' + issue_id + '","project_id":"' + str(tmp_path) + '","title":"Test Issue","description":"","status":"open","priority":2,"created_at":"2025-01-15T10:00:00Z","updated_at":"2025-01-15T10:00:00Z","closed_at":null,"dependencies":[]}\n'
    )

    # Set old sync time
    set_last_sync_time(db_connection, project_id, time.time() - 100)

    # Sync should import
    sync_project(db_connection, str(tmp_path))

    # Verify import
    issue = get_issue(db_connection, issue_id)
    assert issue is not None
    assert issue["title"] == "Test Issue"


def test_sync_project_skips_when_db_newer(db_connection, tmp_path):
    """Should skip import when DB is already up-to-date."""
    from trc_main import sync_project, create_issue, export_to_jsonl, get_issue, set_last_sync_time
    import time

    # Create issue in DB
    create_issue(db_connection, str(tmp_path), "myapp", "Original")

    # Export to JSONL
    trace_dir = tmp_path / ".trace"
    trace_dir.mkdir(exist_ok=True)
    jsonl_path = trace_dir / "issues.jsonl"
    export_to_jsonl(db_connection, str(tmp_path), str(jsonl_path))

    # Set sync time to future
    future_time = time.time() + 100
    set_last_sync_time(db_connection, str(tmp_path), future_time)

    # Modify JSONL (should be ignored)
    jsonl_path.write_text(
        '{"id":"myapp-xyz999","project_id":"' + str(tmp_path) + '","title":"Should Not Import","description":"","status":"open","priority":2,"created_at":"2025-01-15T10:00:00Z","updated_at":"2025-01-15T10:00:00Z","closed_at":null,"dependencies":[]}\n'
    )

    # Sync should skip import
    sync_project(db_connection, str(tmp_path))

    # Verify no import happened
    issue = get_issue(db_connection, "myapp-xyz999")
    assert issue is None


def test_sync_project_handles_missing_jsonl(db_connection, tmp_path):
    """Should handle missing JSONL gracefully."""
    from trc_main import sync_project

    # Should not error
    sync_project(db_connection, str(tmp_path))


def test_sync_project_updates_last_sync_time(db_connection, tmp_path):
    """Should update last sync timestamp after import."""
    from trc_main import sync_project, get_last_sync_time, detect_project

    # Create git repo (required for sync_project)
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    config = git_dir / "config"
    config.write_text("[core]\n\trepositoryformatversion = 0\n")

    # Detect project to get proper project_id
    project = detect_project(cwd=str(tmp_path))
    assert project is not None
    project_id = project["id"]
    project_name = project["name"]

    # Create issue ID that matches project name (6-char hash required)
    issue_id = f"{project_name}-abc123"

    # Create JSONL file
    trace_dir = tmp_path / ".trace"
    trace_dir.mkdir(exist_ok=True)
    jsonl_path = trace_dir / "issues.jsonl"
    jsonl_path.write_text(
        '{"id":"' + issue_id + '","project_id":"' + str(tmp_path) + '","title":"Test","description":"","status":"open","priority":2,"created_at":"2025-01-15T10:00:00Z","updated_at":"2025-01-15T10:00:00Z","closed_at":null,"dependencies":[]}\n'
    )

    jsonl_mtime = jsonl_path.stat().st_mtime

    # Sync
    sync_project(db_connection, str(tmp_path))

    # Verify last sync time was set
    last_sync = get_last_sync_time(db_connection, project_id)
    assert last_sync == jsonl_mtime


def test_sync_project_auto_generates_uuid_when_missing(db_connection, tmp_path):
    """sync_project should auto-generate UUID if .trace/id doesn't exist."""
    import uuid as uuid_module
    from trc_main import detect_project, sync_project

    # Create git repo
    (tmp_path / ".git").mkdir()

    # Create .trace without id file
    trace_dir = tmp_path / ".trace"
    trace_dir.mkdir(exist_ok=True)
    jsonl_path = trace_dir / "issues.jsonl"
    jsonl_path.write_text("")

    # Make sure no id file exists
    id_file = trace_dir / "id"
    if id_file.exists():
        id_file.unlink()

    # Sync project
    sync_project(db_connection, str(tmp_path))

    # UUID file should be created
    assert id_file.exists()
    uuid_content = id_file.read_text().strip()
    # Should be valid UUID
    parsed = uuid_module.UUID(uuid_content)
    assert parsed.version == 4


def test_sync_project_stores_uuid_in_database(db_connection, tmp_path):
    """sync_project should store auto-generated UUID in projects table."""
    from trc_main import detect_project, sync_project

    # Create git repo
    (tmp_path / ".git").mkdir()

    # Create .trace without id file
    trace_dir = tmp_path / ".trace"
    trace_dir.mkdir(exist_ok=True)
    jsonl_path = trace_dir / "issues.jsonl"
    jsonl_path.write_text("")

    # Make sure no id file exists
    id_file = trace_dir / "id"
    if id_file.exists():
        id_file.unlink()

    # Sync project
    sync_project(db_connection, str(tmp_path))

    # Read UUID from file
    stored_uuid = id_file.read_text().strip()

    # Check database has the UUID
    cursor = db_connection.execute(
        "SELECT uuid FROM projects WHERE current_path = ?",
        (str(tmp_path),)
    )
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == stored_uuid


def test_sync_project_preserves_existing_uuid(db_connection, tmp_path):
    """sync_project should not overwrite existing UUID."""
    from trc_main import sync_project

    # Create git repo
    (tmp_path / ".git").mkdir()

    # Create .trace with existing UUID
    trace_dir = tmp_path / ".trace"
    trace_dir.mkdir(exist_ok=True)
    id_file = trace_dir / "id"
    existing_uuid = "550e8400-e29b-41d4-a716-446655440000"
    id_file.write_text(existing_uuid + "\n")
    jsonl_path = trace_dir / "issues.jsonl"
    jsonl_path.write_text("")

    # Sync project
    sync_project(db_connection, str(tmp_path))

    # UUID should be preserved
    assert id_file.read_text().strip() == existing_uuid


def test_sync_project_registers_project_with_uuid(db_connection, tmp_path):
    """sync_project should register project with UUID in database."""
    from trc_main import sync_project

    # Create git repo
    (tmp_path / ".git").mkdir()

    # Create .trace with existing UUID
    trace_dir = tmp_path / ".trace"
    trace_dir.mkdir(exist_ok=True)
    id_file = trace_dir / "id"
    existing_uuid = "550e8400-e29b-41d4-a716-446655440000"
    id_file.write_text(existing_uuid + "\n")
    jsonl_path = trace_dir / "issues.jsonl"
    jsonl_path.write_text("")

    # Sync project
    sync_project(db_connection, str(tmp_path))

    # Check database has the UUID
    cursor = db_connection.execute(
        "SELECT uuid FROM projects WHERE current_path = ?",
        (str(tmp_path),)
    )
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == existing_uuid
