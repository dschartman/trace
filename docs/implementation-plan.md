# Trace Implementation Plan (Test-First)

## Overview

This document outlines the test-first implementation plan for trace. Every feature will follow **Test-Driven Development (TDD)**:

1. Write tests that define expected behavior
2. Run tests (they should fail)
3. Implement minimal code to make tests pass
4. Refactor while keeping tests green
5. Repeat

## Testing Strategy

### Testing Framework

- **pytest** - Primary test framework
- **pytest-cov** - Code coverage reporting
- **hypothesis** - Property-based testing for edge cases
- **freezegun** - Time mocking for timestamp testing

### Test Structure

```
trace/
├── trace.py              # Main implementation (~500 lines)
├── tests/
│   ├── __init__.py
│   ├── conftest.py       # Shared fixtures
│   ├── test_ids.py       # ID generation and collision detection
│   ├── test_projects.py  # Project detection and registry
│   ├── test_issues.py    # Issue CRUD operations
│   ├── test_dependencies.py  # Dependency tracking
│   ├── test_sync.py      # JSONL ↔ DB sync logic
│   ├── test_cli.py       # CLI interface
│   ├── test_reorganization.py  # Move/reparent operations
│   ├── test_queries.py   # List, ready, tree queries
│   └── test_integration.py  # End-to-end workflows
└── pyproject.toml
```

### Test Coverage Goals

- **Unit tests**: 100% coverage of core logic
- **Integration tests**: Cover all CLI commands
- **Edge cases**: Collisions, cycles, race conditions
- **Error cases**: All error messages validated

### Test Conventions

1. **Naming**: `test_<feature>_<scenario>_<expected_result>`
   - Example: `test_create_issue_with_parent_links_correctly`

2. **Fixtures**: Use pytest fixtures for common setup
   - `tmp_trace_dir` - Temporary trace directory
   - `db_connection` - Fresh SQLite database
   - `sample_project` - Project with test data

3. **Assertions**: Clear, specific assertions
   - Use `assert x == y` with descriptive failure messages
   - Validate both success and error cases

4. **Isolation**: Each test is independent
   - No shared state between tests
   - Use temporary directories
   - Clean up after each test

## Phase 1: Core Infrastructure (Week 1)

### 1.1: Hash-Based ID Generation

**Tests to write first** (`test_ids.py`):

```python
def test_generate_id_returns_6_char_hash():
    """ID should be exactly 6 characters."""
    id = generate_hash_id("Test issue", "myapp")
    assert len(id) == len("myapp-abc123")
    assert id.startswith("myapp-")
    assert len(id.split("-")[1]) == 6

def test_generate_id_is_deterministic_with_different_timestamps():
    """Same title at different times generates different IDs."""
    id1 = generate_hash_id("Test", "myapp")
    time.sleep(0.001)
    id2 = generate_hash_id("Test", "myapp")
    assert id1 != id2

def test_generate_id_uses_base36_encoding():
    """ID should use [0-9a-z] characters only."""
    id = generate_hash_id("Test", "myapp")
    hash_part = id.split("-")[1]
    assert all(c in "0123456789abcdefghijklmnopqrstuvwxyz" for c in hash_part)

def test_generate_id_detects_collision_and_retries():
    """When collision occurs, should regenerate ID."""
    # Mock: First attempt collides, second succeeds
    existing_ids = {"myapp-abc123"}
    id = generate_hash_id("Test", "myapp", existing_ids=existing_ids)
    assert id != "myapp-abc123"

def test_generate_id_raises_after_max_retries():
    """Should fail after 10 collision retries."""
    # Mock: All IDs collide
    with pytest.raises(RuntimeError, match="Failed to generate unique ID"):
        generate_hash_id("Test", "myapp", max_retries=3, mock_all_collide=True)

@given(st.text(min_size=1, max_size=200))
def test_generate_id_handles_arbitrary_titles(title):
    """Should handle any valid title string."""
    id = generate_hash_id(title, "myapp")
    assert id.startswith("myapp-")
    assert len(id.split("-")[1]) == 6
```

**Implementation**: After tests pass, implement in `trace.py`:
```python
def generate_hash_id(title: str, project: str, db: Connection) -> str:
    """Generate collision-resistant 6-char hash ID."""
    # Implementation here
```

---

### 1.2: Project Detection and Registry

**Tests to write first** (`test_projects.py`):

```python
def test_detect_project_from_git_remote(tmp_path):
    """Should extract project name from git remote."""
    # Setup: Create git repo with remote
    repo = tmp_path / "myapp"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:user/myapp.git"],
        cwd=repo
    )

    # Test
    os.chdir(repo)
    project = detect_project()

    assert project.name == "myapp"
    assert project.path == str(repo)
    assert project.git_remote == "git@github.com:user/myapp.git"

def test_detect_project_from_directory_name_when_no_remote(tmp_path):
    """Should use directory name if no git remote."""
    repo = tmp_path / "myapp"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo)

    os.chdir(repo)
    project = detect_project()

    assert project.name == "myapp"
    assert project.path == str(repo)
    assert project.git_remote is None

def test_detect_project_returns_none_outside_git_repo(tmp_path):
    """Should return None when not in a git repository."""
    os.chdir(tmp_path)
    project = detect_project()
    assert project is None

def test_detect_project_walks_up_to_find_git_root(tmp_path):
    """Should find .git in parent directories."""
    repo = tmp_path / "myapp"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo)

    subdir = repo / "src" / "components"
    subdir.mkdir(parents=True)

    os.chdir(subdir)
    project = detect_project()

    assert project.name == "myapp"
    assert project.path == str(repo)

def test_register_project_creates_database_entry(db_connection):
    """Should add project to projects table."""
    register_project(db_connection, "myapp", "/path/to/myapp", "git@...")

    cursor = db_connection.execute(
        "SELECT name, path, git_remote FROM projects WHERE name = ?",
        ("myapp",)
    )
    row = cursor.fetchone()

    assert row["name"] == "myapp"
    assert row["path"] == "/path/to/myapp"
    assert row["git_remote"] == "git@..."

def test_register_project_updates_existing_entry(db_connection):
    """Should update project if already registered."""
    # First registration
    register_project(db_connection, "myapp", "/old/path", None)

    # Second registration with updated path
    register_project(db_connection, "myapp", "/new/path", "git@...")

    cursor = db_connection.execute("SELECT COUNT(*) FROM projects WHERE name = ?", ("myapp",))
    assert cursor.fetchone()[0] == 1

    cursor = db_connection.execute("SELECT path FROM projects WHERE name = ?", ("myapp",))
    assert cursor.fetchone()["path"] == "/new/path"

def test_get_project_path_returns_registered_path(db_connection):
    """Should retrieve project path from registry."""
    register_project(db_connection, "myapp", "/path/to/myapp")

    path = get_project_path(db_connection, "myapp")
    assert path == Path("/path/to/myapp")

def test_get_project_path_raises_for_unknown_project(db_connection):
    """Should raise error for unregistered project."""
    with pytest.raises(ValueError, match="Unknown project: unknown"):
        get_project_path(db_connection, "unknown")
```

**Implementation**: Project detection and registry functions.

---

### 1.3: Database Schema and Initialization

**Tests to write first** (`test_db.py`):

```python
def test_init_db_creates_schema(tmp_trace_dir):
    """Should create all tables with correct schema."""
    db = init_database(tmp_trace_dir / "trace.db")

    # Check tables exist
    cursor = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row["name"] for row in cursor.fetchall()]

    assert "issues" in tables
    assert "projects" in tables
    assert "dependencies" in tables
    assert "metadata" in tables

def test_init_db_creates_issues_table_with_correct_columns(tmp_trace_dir):
    """Issues table should have all required columns."""
    db = init_database(tmp_trace_dir / "trace.db")

    cursor = db.execute("PRAGMA table_info(issues)")
    columns = {row["name"]: row["type"] for row in cursor.fetchall()}

    assert columns["id"] == "TEXT"
    assert columns["project_id"] == "TEXT"
    assert columns["title"] == "TEXT"
    assert columns["description"] == "TEXT"
    assert columns["status"] == "TEXT"
    assert columns["priority"] == "INTEGER"
    assert columns["created_at"] == "TEXT"
    assert columns["updated_at"] == "TEXT"
    assert columns["closed_at"] == "TEXT"

def test_init_db_creates_indexes(tmp_trace_dir):
    """Should create indexes for common queries."""
    db = init_database(tmp_trace_dir / "trace.db")

    cursor = db.execute(
        "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
    )
    indexes = [row["name"] for row in cursor.fetchall()]

    assert "idx_issues_project" in indexes
    assert "idx_issues_status" in indexes
    assert "idx_issues_priority" in indexes

def test_init_db_sets_schema_version(tmp_trace_dir):
    """Should record schema version in metadata."""
    db = init_database(tmp_trace_dir / "trace.db")

    cursor = db.execute(
        "SELECT value FROM metadata WHERE key = 'schema_version'"
    )
    version = cursor.fetchone()["value"]

    assert version == "1"

def test_init_db_is_idempotent(tmp_trace_dir):
    """Calling init_db twice should not error."""
    db_path = tmp_trace_dir / "trace.db"
    init_database(db_path)
    init_database(db_path)  # Should not raise

def test_init_db_enforces_status_constraint(tmp_trace_dir):
    """Should only allow valid status values."""
    db = init_database(tmp_trace_dir / "trace.db")

    # Valid status - should work
    db.execute(
        "INSERT INTO issues (id, project_id, title, status, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("test-abc123", "myapp", "Test", "open", "2025-01-15T10:00:00Z")
    )

    # Invalid status - should fail
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO issues (id, project_id, title, status, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("test-def456", "myapp", "Test", "invalid", "2025-01-15T10:00:00Z")
        )

def test_init_db_enforces_priority_range(tmp_trace_dir):
    """Priority should default to 2 and accept 0-4."""
    db = init_database(tmp_trace_dir / "trace.db")

    # Insert without priority - should default to 2
    db.execute(
        "INSERT INTO issues (id, project_id, title, created_at) "
        "VALUES (?, ?, ?, ?)",
        ("test-abc123", "myapp", "Test", "2025-01-15T10:00:00Z")
    )

    cursor = db.execute("SELECT priority FROM issues WHERE id = ?", ("test-abc123",))
    assert cursor.fetchone()["priority"] == 2
```

**Implementation**: Database initialization and schema.

---

### 1.4: File Locking for Sync Safety

**Tests to write first** (`test_sync.py`):

```python
def test_file_lock_prevents_concurrent_access(tmp_trace_dir):
    """Two processes should not acquire lock simultaneously."""
    lock_path = tmp_trace_dir / ".lock"

    # Process 1 acquires lock
    with file_lock(lock_path) as lock1:
        # Process 2 attempts to acquire (should block/fail)
        with pytest.raises(BlockingIOError):
            with file_lock(lock_path, blocking=False):
                pass

def test_file_lock_releases_on_exit(tmp_trace_dir):
    """Lock should release when context exits."""
    lock_path = tmp_trace_dir / ".lock"

    with file_lock(lock_path):
        pass

    # Should be able to acquire again
    with file_lock(lock_path):
        pass

def test_file_lock_releases_on_exception(tmp_trace_dir):
    """Lock should release even if exception occurs."""
    lock_path = tmp_trace_dir / ".lock"

    try:
        with file_lock(lock_path):
            raise ValueError("Test error")
    except ValueError:
        pass

    # Should be able to acquire after exception
    with file_lock(lock_path):
        pass

def test_file_lock_creates_lock_file_if_missing(tmp_trace_dir):
    """Should create lock file if it doesn't exist."""
    lock_path = tmp_trace_dir / ".lock"
    assert not lock_path.exists()

    with file_lock(lock_path):
        assert lock_path.exists()
```

**Implementation**: File locking context manager.

---

## Phase 2: Issue CRUD Operations (Week 2)

### 2.1: Create Issue

**Tests to write first** (`test_issues.py`):

```python
def test_create_issue_with_minimal_fields(db_connection):
    """Should create issue with only required fields."""
    issue = create_issue(
        db=db_connection,
        project_id="myapp",
        title="Fix bug"
    )

    assert issue.id.startswith("myapp-")
    assert issue.title == "Fix bug"
    assert issue.status == "open"
    assert issue.priority == 2
    assert issue.created_at is not None

def test_create_issue_with_all_fields(db_connection):
    """Should create issue with all optional fields."""
    issue = create_issue(
        db=db_connection,
        project_id="myapp",
        title="Add feature",
        description="Detailed description",
        priority=1,
        status="in_progress"
    )

    assert issue.title == "Add feature"
    assert issue.description == "Detailed description"
    assert issue.priority == 1
    assert issue.status == "in_progress"

def test_create_issue_sets_timezone_aware_timestamp(db_connection):
    """Timestamps should be UTC with timezone info."""
    issue = create_issue(db_connection, "myapp", "Test")

    created = datetime.fromisoformat(issue.created_at)
    assert created.tzinfo is not None
    assert created.tzinfo == timezone.utc

def test_create_issue_with_parent_creates_dependency(db_connection):
    """Should create parent-child dependency."""
    parent = create_issue(db_connection, "myapp", "Parent")
    child = create_issue(
        db_connection,
        "myapp",
        "Child",
        parent_id=parent.id
    )

    cursor = db_connection.execute(
        "SELECT * FROM dependencies WHERE issue_id = ? AND depends_on_id = ?",
        (child.id, parent.id)
    )
    dep = cursor.fetchone()

    assert dep is not None
    assert dep["type"] == "parent"

def test_create_issue_with_depends_on_creates_blocks_dependency(db_connection):
    """Should create blocks dependency."""
    blocker = create_issue(db_connection, "myapp", "Blocker")
    blocked = create_issue(
        db_connection,
        "myapp",
        "Blocked",
        depends_on_id=blocker.id
    )

    cursor = db_connection.execute(
        "SELECT * FROM dependencies WHERE issue_id = ? AND depends_on_id = ?",
        (blocked.id, blocker.id)
    )
    dep = cursor.fetchone()

    assert dep is not None
    assert dep["type"] == "blocks"

def test_create_issue_validates_status(db_connection):
    """Should reject invalid status values."""
    with pytest.raises(ValueError, match="Invalid status"):
        create_issue(db_connection, "myapp", "Test", status="invalid")

def test_create_issue_validates_priority_range(db_connection):
    """Should reject priority outside 0-4 range."""
    with pytest.raises(ValueError, match="Priority must be 0-4"):
        create_issue(db_connection, "myapp", "Test", priority=5)

def test_create_issue_cross_project_dependency(db_connection):
    """Should allow dependencies across projects."""
    lib_issue = create_issue(db_connection, "mylib", "Add API")
    app_issue = create_issue(
        db_connection,
        "myapp",
        "Use API",
        depends_on_id=lib_issue.id
    )

    # Should have cross-project dependency
    cursor = db_connection.execute(
        "SELECT i1.project_id, i2.project_id FROM dependencies d "
        "JOIN issues i1 ON d.issue_id = i1.id "
        "JOIN issues i2 ON d.depends_on_id = i2.id "
        "WHERE d.issue_id = ?",
        (app_issue.id,)
    )
    row = cursor.fetchone()
    assert row[0] != row[1]  # Different projects
```

**Implementation**: `create_issue()` function with validation.

---

### 2.2: Read/Query Issues

**Tests to write first** (`test_issues.py`):

```python
def test_get_issue_by_id(db_connection):
    """Should retrieve issue by ID."""
    created = create_issue(db_connection, "myapp", "Test")

    issue = get_issue(db_connection, created.id)

    assert issue.id == created.id
    assert issue.title == "Test"

def test_get_issue_returns_none_for_nonexistent_id(db_connection):
    """Should return None if issue doesn't exist."""
    issue = get_issue(db_connection, "myapp-nonexistent")
    assert issue is None

def test_list_issues_returns_all_for_project(db_connection):
    """Should list all issues for a project."""
    create_issue(db_connection, "myapp", "Issue 1")
    create_issue(db_connection, "myapp", "Issue 2")
    create_issue(db_connection, "other", "Issue 3")

    issues = list_issues(db_connection, project_id="myapp")

    assert len(issues) == 2
    assert all(i.project_id == "myapp" for i in issues)

def test_list_issues_filters_by_status(db_connection):
    """Should filter issues by status."""
    create_issue(db_connection, "myapp", "Open", status="open")
    create_issue(db_connection, "myapp", "Closed", status="closed")

    open_issues = list_issues(db_connection, project_id="myapp", status="open")

    assert len(open_issues) == 1
    assert open_issues[0].title == "Open"

def test_list_issues_filters_by_priority(db_connection):
    """Should filter issues by priority."""
    create_issue(db_connection, "myapp", "P0", priority=0)
    create_issue(db_connection, "myapp", "P1", priority=1)
    create_issue(db_connection, "myapp", "P2", priority=2)

    high_priority = list_issues(db_connection, project_id="myapp", priority=0)

    assert len(high_priority) == 1
    assert high_priority[0].priority == 0

def test_list_issues_sorts_by_priority_then_created_at(db_connection):
    """Should sort by priority (asc), then created_at (asc)."""
    with freeze_time("2025-01-15 10:00:00"):
        issue1 = create_issue(db_connection, "myapp", "P2 Old", priority=2)

    with freeze_time("2025-01-15 11:00:00"):
        issue2 = create_issue(db_connection, "myapp", "P0", priority=0)

    with freeze_time("2025-01-15 12:00:00"):
        issue3 = create_issue(db_connection, "myapp", "P2 New", priority=2)

    issues = list_issues(db_connection, project_id="myapp")

    assert issues[0].id == issue2.id  # P0 first
    assert issues[1].id == issue1.id  # P2 older
    assert issues[2].id == issue3.id  # P2 newer
```

**Implementation**: `get_issue()` and `list_issues()` functions.

---

### 2.3: Update Issue

**Tests to write first** (`test_issues.py`):

```python
def test_update_issue_title(db_connection):
    """Should update issue title."""
    issue = create_issue(db_connection, "myapp", "Old title")

    update_issue(db_connection, issue.id, title="New title")

    updated = get_issue(db_connection, issue.id)
    assert updated.title == "New title"

def test_update_issue_status(db_connection):
    """Should update issue status."""
    issue = create_issue(db_connection, "myapp", "Test")

    update_issue(db_connection, issue.id, status="in_progress")

    updated = get_issue(db_connection, issue.id)
    assert updated.status == "in_progress"

def test_update_issue_sets_updated_at(db_connection):
    """Should update updated_at timestamp."""
    with freeze_time("2025-01-15 10:00:00"):
        issue = create_issue(db_connection, "myapp", "Test")

    with freeze_time("2025-01-15 11:00:00"):
        update_issue(db_connection, issue.id, title="Updated")

    updated = get_issue(db_connection, issue.id)
    assert updated.updated_at > issue.created_at

def test_update_issue_sets_closed_at_when_closing(db_connection):
    """Should set closed_at when status changes to closed."""
    issue = create_issue(db_connection, "myapp", "Test")
    assert issue.closed_at is None

    update_issue(db_connection, issue.id, status="closed")

    updated = get_issue(db_connection, issue.id)
    assert updated.closed_at is not None

def test_update_issue_clears_closed_at_when_reopening(db_connection):
    """Should clear closed_at when reopening."""
    issue = create_issue(db_connection, "myapp", "Test", status="closed")

    update_issue(db_connection, issue.id, status="open")

    updated = get_issue(db_connection, issue.id)
    assert updated.closed_at is None

def test_update_issue_validates_fields(db_connection):
    """Should validate updated field values."""
    issue = create_issue(db_connection, "myapp", "Test")

    with pytest.raises(ValueError, match="Invalid status"):
        update_issue(db_connection, issue.id, status="invalid")

    with pytest.raises(ValueError, match="Priority must be 0-4"):
        update_issue(db_connection, issue.id, priority=10)

def test_update_issue_raises_for_nonexistent_issue(db_connection):
    """Should raise error for nonexistent issue."""
    with pytest.raises(ValueError, match="Issue not found"):
        update_issue(db_connection, "myapp-nonexistent", title="Test")
```

**Implementation**: `update_issue()` function.

---

### 2.4: Close Issue (with Parent-Child Validation)

**Tests to write first** (`test_issues.py`):

```python
def test_close_issue_without_children(db_connection):
    """Should close issue without children."""
    issue = create_issue(db_connection, "myapp", "Test")

    close_issue(db_connection, issue.id)

    updated = get_issue(db_connection, issue.id)
    assert updated.status == "closed"
    assert updated.closed_at is not None

def test_close_issue_with_all_children_closed(db_connection):
    """Should close parent if all children are closed."""
    parent = create_issue(db_connection, "myapp", "Parent")
    child1 = create_issue(db_connection, "myapp", "Child 1", parent_id=parent.id, status="closed")
    child2 = create_issue(db_connection, "myapp", "Child 2", parent_id=parent.id, status="closed")

    close_issue(db_connection, parent.id)

    updated = get_issue(db_connection, parent.id)
    assert updated.status == "closed"

def test_close_issue_with_open_children_raises_error(db_connection):
    """Should prevent closing parent with open children."""
    parent = create_issue(db_connection, "myapp", "Parent")
    child1 = create_issue(db_connection, "myapp", "Child 1", parent_id=parent.id, status="closed")
    child2 = create_issue(db_connection, "myapp", "Child 2", parent_id=parent.id, status="open")

    with pytest.raises(ValueError, match="Cannot close issue with open children"):
        close_issue(db_connection, parent.id)

def test_close_issue_with_open_children_force(db_connection):
    """Should close parent with --force flag."""
    parent = create_issue(db_connection, "myapp", "Parent")
    child = create_issue(db_connection, "myapp", "Child", parent_id=parent.id)

    close_issue(db_connection, parent.id, force=True)

    updated = get_issue(db_connection, parent.id)
    assert updated.status == "closed"
```

**Implementation**: `close_issue()` function with child validation.

---

## Phase 3: JSONL Sync (Week 3)

### 3.1: Export to JSONL

**Tests to write first** (`test_sync.py`):

```python
def test_export_to_jsonl_creates_file(db_connection, tmp_path):
    """Should create JSONL file with issues."""
    create_issue(db_connection, "myapp", "Issue 1")
    create_issue(db_connection, "myapp", "Issue 2")

    jsonl_path = tmp_path / "issues.jsonl"
    export_to_jsonl(db_connection, "myapp", jsonl_path)

    assert jsonl_path.exists()
    lines = jsonl_path.read_text().strip().split("\n")
    assert len(lines) == 2

def test_export_to_jsonl_sorts_by_id(db_connection, tmp_path):
    """Should sort issues by ID for stable diffs."""
    create_issue(db_connection, "myapp", "Issue Z", id="myapp-zzz999")
    create_issue(db_connection, "myapp", "Issue A", id="myapp-aaa111")

    jsonl_path = tmp_path / "issues.jsonl"
    export_to_jsonl(db_connection, "myapp", jsonl_path)

    lines = jsonl_path.read_text().strip().split("\n")
    issue1 = json.loads(lines[0])
    issue2 = json.loads(lines[1])

    assert issue1["id"] < issue2["id"]

def test_export_to_jsonl_includes_dependencies(db_connection, tmp_path):
    """Should include dependencies inline in issue."""
    parent = create_issue(db_connection, "myapp", "Parent")
    child = create_issue(db_connection, "myapp", "Child", parent_id=parent.id)

    jsonl_path = tmp_path / "issues.jsonl"
    export_to_jsonl(db_connection, "myapp", jsonl_path)

    lines = jsonl_path.read_text().strip().split("\n")
    child_data = json.loads(lines[0])  # Assuming sorted

    assert "dependencies" in child_data
    assert any(d["depends_on_id"] == parent.id for d in child_data["dependencies"])

def test_export_to_jsonl_atomic_write(db_connection, tmp_path):
    """Should use atomic write (temp file + rename)."""
    create_issue(db_connection, "myapp", "Test")

    jsonl_path = tmp_path / "issues.jsonl"

    # Mock file write failure
    with patch("pathlib.Path.rename", side_effect=OSError("Disk full")):
        with pytest.raises(OSError):
            export_to_jsonl(db_connection, "myapp", jsonl_path)

    # Original file should not exist (atomic write failed completely)
    assert not jsonl_path.exists()

def test_export_to_jsonl_only_exports_project_issues(db_connection, tmp_path):
    """Should only export issues for specified project."""
    create_issue(db_connection, "myapp", "App issue")
    create_issue(db_connection, "mylib", "Lib issue")

    jsonl_path = tmp_path / "issues.jsonl"
    export_to_jsonl(db_connection, "myapp", jsonl_path)

    lines = jsonl_path.read_text().strip().split("\n")
    issues = [json.loads(line) for line in lines]

    assert len(issues) == 1
    assert all(i["project_id"] == "myapp" for i in issues)

def test_export_to_jsonl_handles_empty_project(db_connection, tmp_path):
    """Should create empty file for project with no issues."""
    jsonl_path = tmp_path / "issues.jsonl"
    export_to_jsonl(db_connection, "myapp", jsonl_path)

    assert jsonl_path.exists()
    assert jsonl_path.read_text().strip() == ""
```

**Implementation**: `export_to_jsonl()` function with atomic write.

---

### 3.2: Import from JSONL

**Tests to write first** (`test_sync.py`):

```python
def test_import_from_jsonl_creates_issues(db_connection, tmp_path):
    """Should import issues from JSONL file."""
    jsonl_path = tmp_path / "issues.jsonl"
    jsonl_path.write_text(
        '{"id":"myapp-abc123","project_id":"myapp","title":"Test 1","status":"open","priority":2,"created_at":"2025-01-15T10:00:00Z"}\n'
        '{"id":"myapp-def456","project_id":"myapp","title":"Test 2","status":"closed","priority":1,"created_at":"2025-01-15T11:00:00Z","closed_at":"2025-01-15T12:00:00Z"}\n'
    )

    stats = import_from_jsonl(db_connection, jsonl_path)

    assert stats["created"] == 2
    assert stats["updated"] == 0

    issue1 = get_issue(db_connection, "myapp-abc123")
    assert issue1.title == "Test 1"

def test_import_from_jsonl_updates_existing_issues(db_connection, tmp_path):
    """Should update issues that already exist."""
    # Create issue in DB
    create_issue(db_connection, "myapp", "Old title", id="myapp-abc123")

    # Import with updated title
    jsonl_path = tmp_path / "issues.jsonl"
    jsonl_path.write_text(
        '{"id":"myapp-abc123","project_id":"myapp","title":"New title","status":"open","priority":2,"created_at":"2025-01-15T10:00:00Z"}\n'
    )

    stats = import_from_jsonl(db_connection, jsonl_path)

    assert stats["created"] == 0
    assert stats["updated"] == 1

    issue = get_issue(db_connection, "myapp-abc123")
    assert issue.title == "New title"

def test_import_from_jsonl_preserves_dependencies(db_connection, tmp_path):
    """Should restore dependency relationships."""
    jsonl_path = tmp_path / "issues.jsonl"
    jsonl_path.write_text(
        '{"id":"myapp-abc123","project_id":"myapp","title":"Parent","status":"open","priority":2,"created_at":"2025-01-15T10:00:00Z","dependencies":[]}\n'
        '{"id":"myapp-def456","project_id":"myapp","title":"Child","status":"open","priority":2,"created_at":"2025-01-15T11:00:00Z","dependencies":[{"depends_on_id":"myapp-abc123","type":"parent"}]}\n'
    )

    import_from_jsonl(db_connection, jsonl_path)

    cursor = db_connection.execute(
        "SELECT * FROM dependencies WHERE issue_id = ? AND depends_on_id = ?",
        ("myapp-def456", "myapp-abc123")
    )
    assert cursor.fetchone() is not None

def test_import_from_jsonl_handles_malformed_json(db_connection, tmp_path):
    """Should skip malformed lines and report errors."""
    jsonl_path = tmp_path / "issues.jsonl"
    jsonl_path.write_text(
        '{"id":"myapp-abc123","title":"Valid"}\n'
        '{invalid json}\n'
        '{"id":"myapp-def456","title":"Also valid"}\n'
    )

    stats = import_from_jsonl(db_connection, jsonl_path)

    assert stats["created"] == 2
    assert len(stats["errors"]) == 1
    assert "Line 2" in stats["errors"][0]

def test_import_from_jsonl_cross_project_dependencies(db_connection, tmp_path):
    """Should handle cross-project dependencies."""
    # First import library issue
    lib_jsonl = tmp_path / "mylib-issues.jsonl"
    lib_jsonl.write_text(
        '{"id":"mylib-abc123","project_id":"mylib","title":"Lib issue","status":"open","priority":2,"created_at":"2025-01-15T10:00:00Z"}\n'
    )
    import_from_jsonl(db_connection, lib_jsonl)

    # Then import app issue that depends on lib issue
    app_jsonl = tmp_path / "myapp-issues.jsonl"
    app_jsonl.write_text(
        '{"id":"myapp-def456","project_id":"myapp","title":"App issue","status":"open","priority":2,"created_at":"2025-01-15T11:00:00Z","dependencies":[{"depends_on_id":"mylib-abc123","type":"blocks"}]}\n'
    )
    import_from_jsonl(db_connection, app_jsonl)

    # Verify cross-project dependency exists
    cursor = db_connection.execute(
        "SELECT i1.project_id, i2.project_id FROM dependencies d "
        "JOIN issues i1 ON d.issue_id = i1.id "
        "JOIN issues i2 ON d.depends_on_id = i2.id "
        "WHERE d.issue_id = ?",
        ("myapp-def456",)
    )
    row = cursor.fetchone()
    assert row[0] != row[1]
```

**Implementation**: `import_from_jsonl()` function with error handling.

---

### 3.3: Bidirectional Sync Logic

**Tests to write first** (`test_sync.py`):

```python
def test_sync_imports_when_jsonl_newer(db_connection, tmp_path):
    """Should import from JSONL when it's newer than DB."""
    # Create JSONL file
    jsonl_path = tmp_path / "issues.jsonl"
    jsonl_path.write_text(
        '{"id":"myapp-abc123","project_id":"myapp","title":"From JSONL","status":"open","priority":2,"created_at":"2025-01-15T10:00:00Z"}\n'
    )

    # Sync (should import)
    sync_project(db_connection, "myapp", jsonl_path)

    issue = get_issue(db_connection, "myapp-abc123")
    assert issue is not None
    assert issue.title == "From JSONL"

def test_sync_exports_when_db_newer(db_connection, tmp_path):
    """Should export to JSONL when DB is newer."""
    jsonl_path = tmp_path / "issues.jsonl"

    # Create issue in DB
    create_issue(db_connection, "myapp", "From DB", id="myapp-abc123")

    # Sync (should export)
    sync_project(db_connection, "myapp", jsonl_path)

    # Verify JSONL was created
    assert jsonl_path.exists()
    lines = jsonl_path.read_text().strip().split("\n")
    issue_data = json.loads(lines[0])
    assert issue_data["title"] == "From DB"

def test_sync_roundtrip_preserves_data(db_connection, tmp_path):
    """Export then import should preserve all data."""
    jsonl_path = tmp_path / "issues.jsonl"

    # Create complex issue with dependencies
    parent = create_issue(db_connection, "myapp", "Parent", priority=1)
    child = create_issue(
        db_connection,
        "myapp",
        "Child",
        parent_id=parent.id,
        description="Detailed description"
    )

    # Export
    export_to_jsonl(db_connection, "myapp", jsonl_path)

    # Clear DB
    db_connection.execute("DELETE FROM dependencies")
    db_connection.execute("DELETE FROM issues")

    # Import
    import_from_jsonl(db_connection, jsonl_path)

    # Verify everything is preserved
    parent_restored = get_issue(db_connection, parent.id)
    assert parent_restored.title == "Parent"
    assert parent_restored.priority == 1

    child_restored = get_issue(db_connection, child.id)
    assert child_restored.description == "Detailed description"

    cursor = db_connection.execute(
        "SELECT * FROM dependencies WHERE issue_id = ?",
        (child.id,)
    )
    assert cursor.fetchone() is not None

def test_sync_with_file_lock(db_connection, tmp_path):
    """Sync should acquire file lock."""
    jsonl_path = tmp_path / "issues.jsonl"
    lock_path = tmp_path / ".lock"

    # Acquire lock manually
    lock_file = open(lock_path, 'w')
    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    # Attempt sync (should fail to acquire lock)
    with pytest.raises(BlockingIOError):
        with file_lock(lock_path, blocking=False):
            sync_project(db_connection, "myapp", jsonl_path)

    # Release lock
    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    lock_file.close()
```

**Implementation**: `sync_project()` function with timestamp checking.

---

## Phase 4: CLI Implementation (Week 4)

### 4.1: CLI Framework Setup

**Tests to write first** (`test_cli.py`):

```python
def test_cli_init_creates_trace_directory(tmp_path):
    """trace init should create .trace directory."""
    os.chdir(tmp_path)
    subprocess.run(["git", "init"], check=True)

    result = subprocess.run(
        ["trace", "init"],
        capture_output=True,
        text=True
    )

    assert result.returncode == 0
    assert (tmp_path / ".trace").exists()
    assert (tmp_path / ".trace" / "issues.jsonl").exists()

def test_cli_create_outputs_issue_id(tmp_path):
    """trace create should output created issue ID."""
    os.chdir(tmp_path)
    subprocess.run(["git", "init"], check=True)
    subprocess.run(["trace", "init"], check=True)

    result = subprocess.run(
        ["trace", "create", "Test issue"],
        capture_output=True,
        text=True
    )

    assert result.returncode == 0
    assert "Created" in result.stdout
    assert re.search(r"[a-z0-9]{6}", result.stdout)  # Has 6-char ID

def test_cli_create_with_priority_flag(tmp_path):
    """trace create --priority should set priority."""
    os.chdir(tmp_path)
    subprocess.run(["git", "init"], check=True)
    subprocess.run(["trace", "init"], check=True)

    result = subprocess.run(
        ["trace", "create", "High priority", "--priority", "0"],
        capture_output=True,
        text=True
    )

    assert result.returncode == 0

    # Verify in list output
    result = subprocess.run(
        ["trace", "list"],
        capture_output=True,
        text=True
    )
    assert "[P0]" in result.stdout

def test_cli_list_shows_issues(tmp_path):
    """trace list should display issues."""
    os.chdir(tmp_path)
    subprocess.run(["git", "init"], check=True)
    subprocess.run(["trace", "init"], check=True)
    subprocess.run(["trace", "create", "Issue 1"], check=True)
    subprocess.run(["trace", "create", "Issue 2"], check=True)

    result = subprocess.run(
        ["trace", "list"],
        capture_output=True,
        text=True
    )

    assert result.returncode == 0
    assert "Issue 1" in result.stdout
    assert "Issue 2" in result.stdout

def test_cli_show_displays_issue_details(tmp_path):
    """trace show should display full issue details."""
    os.chdir(tmp_path)
    subprocess.run(["git", "init"], check=True)
    subprocess.run(["trace", "init"], check=True)

    create_result = subprocess.run(
        ["trace", "create", "Test issue", "--description", "Detailed description"],
        capture_output=True,
        text=True
    )
    issue_id = re.search(r"Created (\S+):", create_result.stdout).group(1)

    result = subprocess.run(
        ["trace", "show", issue_id],
        capture_output=True,
        text=True
    )

    assert result.returncode == 0
    assert "Test issue" in result.stdout
    assert "Detailed description" in result.stdout

def test_cli_json_output_is_valid(tmp_path):
    """--json flag should output valid JSON."""
    os.chdir(tmp_path)
    subprocess.run(["git", "init"], check=True)
    subprocess.run(["trace", "init"], check=True)
    subprocess.run(["trace", "create", "Test"], check=True)

    result = subprocess.run(
        ["trace", "list", "--json"],
        capture_output=True,
        text=True
    )

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["title"] == "Test"

def test_cli_error_messages_are_clear(tmp_path):
    """Error messages should be helpful."""
    os.chdir(tmp_path)
    subprocess.run(["git", "init"], check=True)
    subprocess.run(["trace", "init"], check=True)

    result = subprocess.run(
        ["trace", "show", "nonexistent-id"],
        capture_output=True,
        text=True
    )

    assert result.returncode != 0
    assert "not found" in result.stderr.lower() or "not found" in result.stdout.lower()
```

**Implementation**: Click-based CLI with all basic commands.

---

## Phase 5: Reorganization Commands (Week 5)

### 5.1: Reparent Command

**Tests to write first** (`test_reorganization.py`):

```python
def test_reparent_adds_parent(db_connection):
    """Should add parent relationship."""
    parent = create_issue(db_connection, "myapp", "Parent")
    child = create_issue(db_connection, "myapp", "Child")

    reparent(db_connection, child.id, parent.id)

    cursor = db_connection.execute(
        "SELECT * FROM dependencies WHERE issue_id = ? AND type = 'parent'",
        (child.id,)
    )
    dep = cursor.fetchone()
    assert dep["depends_on_id"] == parent.id

def test_reparent_changes_existing_parent(db_connection):
    """Should change parent from one to another."""
    old_parent = create_issue(db_connection, "myapp", "Old parent")
    new_parent = create_issue(db_connection, "myapp", "New parent")
    child = create_issue(db_connection, "myapp", "Child", parent_id=old_parent.id)

    reparent(db_connection, child.id, new_parent.id)

    cursor = db_connection.execute(
        "SELECT * FROM dependencies WHERE issue_id = ? AND type = 'parent'",
        (child.id,)
    )
    dep = cursor.fetchone()
    assert dep["depends_on_id"] == new_parent.id

def test_reparent_removes_parent_with_none(db_connection):
    """Should remove parent relationship."""
    parent = create_issue(db_connection, "myapp", "Parent")
    child = create_issue(db_connection, "myapp", "Child", parent_id=parent.id)

    reparent(db_connection, child.id, None)

    cursor = db_connection.execute(
        "SELECT COUNT(*) FROM dependencies WHERE issue_id = ? AND type = 'parent'",
        (child.id,)
    )
    assert cursor.fetchone()[0] == 0

def test_reparent_detects_cycle(db_connection):
    """Should prevent creating cycles."""
    issue1 = create_issue(db_connection, "myapp", "Issue 1")
    issue2 = create_issue(db_connection, "myapp", "Issue 2", parent_id=issue1.id)
    issue3 = create_issue(db_connection, "myapp", "Issue 3", parent_id=issue2.id)

    # Try to make issue1 a child of issue3 (would create cycle)
    with pytest.raises(ValueError, match="Would create cycle"):
        reparent(db_connection, issue1.id, issue3.id)

def test_reparent_prevents_self_parent(db_connection):
    """Should prevent issue from being its own parent."""
    issue = create_issue(db_connection, "myapp", "Issue")

    with pytest.raises(ValueError, match="cannot be its own parent"):
        reparent(db_connection, issue.id, issue.id)

def test_reparent_allows_cross_project(db_connection):
    """Should allow parent-child across projects."""
    parent = create_issue(db_connection, "mylib", "Library feature")
    child = create_issue(db_connection, "myapp", "App feature")

    reparent(db_connection, child.id, parent.id)

    cursor = db_connection.execute(
        "SELECT i1.project_id, i2.project_id FROM dependencies d "
        "JOIN issues i1 ON d.issue_id = i1.id "
        "JOIN issues i2 ON d.depends_on_id = i2.id "
        "WHERE d.issue_id = ?",
        (child.id,)
    )
    row = cursor.fetchone()
    assert row[0] != row[1]
```

**Implementation**: `reparent()` function with cycle detection.

---

### 5.2: Move Command

**Tests to write first** (`test_reorganization.py`):

```python
def test_move_changes_project_id(db_connection):
    """Should change issue's project_id."""
    issue = create_issue(db_connection, "default", "Issue")

    new_id = move_issue(db_connection, issue.id, "myapp")

    moved = get_issue(db_connection, new_id)
    assert moved.project_id == "myapp"
    assert moved.title == "Issue"

def test_move_generates_new_id_for_target_project(db_connection):
    """Should generate new ID with target project prefix."""
    issue = create_issue(db_connection, "default", "Issue", id="default-abc123")

    new_id = move_issue(db_connection, "default-abc123", "myapp")

    assert new_id.startswith("myapp-")
    assert new_id != "default-abc123"

def test_move_removes_old_issue(db_connection):
    """Should remove issue from old project."""
    issue = create_issue(db_connection, "default", "Issue")
    old_id = issue.id

    new_id = move_issue(db_connection, old_id, "myapp")

    old_issue = get_issue(db_connection, old_id)
    assert old_issue is None

def test_move_updates_dependencies(db_connection):
    """Should update dependencies to point to new ID."""
    issue1 = create_issue(db_connection, "default", "Issue 1")
    issue2 = create_issue(db_connection, "default", "Issue 2", depends_on_id=issue1.id)

    new_id = move_issue(db_connection, issue1.id, "myapp")

    cursor = db_connection.execute(
        "SELECT depends_on_id FROM dependencies WHERE issue_id = ?",
        (issue2.id,)
    )
    assert cursor.fetchone()["depends_on_id"] == new_id

def test_move_with_children_moves_all(db_connection):
    """Should move parent and all children."""
    parent = create_issue(db_connection, "default", "Parent")
    child1 = create_issue(db_connection, "default", "Child 1", parent_id=parent.id)
    child2 = create_issue(db_connection, "default", "Child 2", parent_id=parent.id)

    new_ids = move_issue(db_connection, parent.id, "myapp", with_children=True)

    assert len(new_ids) == 3
    assert all(id.startswith("myapp-") for id in new_ids)

    # Verify parent-child relationships preserved
    new_parent_id = [id for id in new_ids if get_issue(db_connection, id).title == "Parent"][0]
    cursor = db_connection.execute(
        "SELECT COUNT(*) FROM dependencies "
        "WHERE depends_on_id = ? AND type = 'parent'",
        (new_parent_id,)
    )
    assert cursor.fetchone()[0] == 2

def test_move_warns_about_cross_project_dependencies(db_connection):
    """Should warn when moving issue that other projects depend on."""
    lib_issue = create_issue(db_connection, "mylib", "Lib feature")
    app_issue = create_issue(db_connection, "myapp", "App feature", depends_on_id=lib_issue.id)

    # Move lib issue to different project
    warnings = []
    new_id = move_issue(db_connection, lib_issue.id, "other", warnings=warnings)

    assert len(warnings) > 0
    assert "myapp" in warnings[0]  # Warning mentions dependent project
```

**Implementation**: `move_issue()` function with dependency updates.

---

## Phase 6: Query Commands (Week 6)

### 6.1: Tree View

**Tests to write first** (`test_queries.py`):

```python
def test_tree_returns_hierarchical_structure(db_connection):
    """Should return tree structure with children."""
    parent = create_issue(db_connection, "myapp", "Parent")
    child1 = create_issue(db_connection, "myapp", "Child 1", parent_id=parent.id)
    child2 = create_issue(db_connection, "myapp", "Child 2", parent_id=parent.id)
    grandchild = create_issue(db_connection, "myapp", "Grandchild", parent_id=child1.id)

    tree = get_tree(db_connection, parent.id)

    assert tree.issue.id == parent.id
    assert len(tree.children) == 2
    assert tree.children[0].issue.title == "Child 1"
    assert len(tree.children[0].children) == 1

def test_tree_calculates_completion_percentage(db_connection):
    """Should calculate percentage of closed children."""
    parent = create_issue(db_connection, "myapp", "Parent")
    create_issue(db_connection, "myapp", "Child 1", parent_id=parent.id, status="closed")
    create_issue(db_connection, "myapp", "Child 2", parent_id=parent.id, status="closed")
    create_issue(db_connection, "myapp", "Child 3", parent_id=parent.id, status="open")
    create_issue(db_connection, "myapp", "Child 4", parent_id=parent.id, status="open")

    tree = get_tree(db_connection, parent.id)

    assert tree.completion_percentage == 50

def test_tree_handles_deep_nesting(db_connection):
    """Should handle arbitrarily deep trees."""
    issues = []
    parent = create_issue(db_connection, "myapp", "Level 0")
    issues.append(parent)

    for i in range(1, 10):
        child = create_issue(db_connection, "myapp", f"Level {i}", parent_id=issues[-1].id)
        issues.append(child)

    tree = get_tree(db_connection, parent.id)

    # Walk down to depth 9
    current = tree
    depth = 0
    while current.children:
        depth += 1
        current = current.children[0]

    assert depth == 9
```

**Implementation**: `get_tree()` recursive query function.

---

### 6.2: Ready Work Query

**Tests to write first** (`test_queries.py`):

```python
def test_ready_returns_issues_without_blockers(db_connection):
    """Should return only issues with no open dependencies."""
    ready_issue = create_issue(db_connection, "myapp", "Ready")
    blocker = create_issue(db_connection, "myapp", "Blocker", status="open")
    blocked = create_issue(db_connection, "myapp", "Blocked", depends_on_id=blocker.id)

    ready = get_ready_work(db_connection, "myapp")

    ready_ids = [i.id for i in ready]
    assert ready_issue.id in ready_ids
    assert blocker.id in ready_ids  # Blocker itself is ready
    assert blocked.id not in ready_ids

def test_ready_excludes_issues_blocked_by_open_parent(db_connection):
    """Should not return children of open parent issues."""
    parent = create_issue(db_connection, "myapp", "Parent", status="open")
    child = create_issue(db_connection, "myapp", "Child", parent_id=parent.id)

    ready = get_ready_work(db_connection, "myapp")

    # Parent is ready (leaf node), child is not (has open parent)
    ready_ids = [i.id for i in ready]
    assert parent.id in ready_ids
    # Actually, both should be ready since parent-child doesn't block
    # Let's clarify: only "blocks" type dependencies should block ready work

def test_ready_includes_issues_with_closed_dependencies(db_connection):
    """Should include issues whose dependencies are closed."""
    closed_dep = create_issue(db_connection, "myapp", "Dependency", status="closed")
    ready_issue = create_issue(db_connection, "myapp", "Ready", depends_on_id=closed_dep.id)

    ready = get_ready_work(db_connection, "myapp")

    ready_ids = [i.id for i in ready]
    assert ready_issue.id in ready_ids

def test_ready_sorts_by_priority(db_connection):
    """Should sort ready work by priority."""
    issue_p2 = create_issue(db_connection, "myapp", "P2", priority=2)
    issue_p0 = create_issue(db_connection, "myapp", "P0", priority=0)
    issue_p1 = create_issue(db_connection, "myapp", "P1", priority=1)

    ready = get_ready_work(db_connection, "myapp")

    assert ready[0].priority == 0
    assert ready[1].priority == 1
    assert ready[2].priority == 2

def test_ready_cross_project(db_connection):
    """Should return ready work across all projects."""
    create_issue(db_connection, "myapp", "App issue", priority=1)
    create_issue(db_connection, "mylib", "Lib issue", priority=0)

    ready = get_ready_work(db_connection, project_id=None)  # All projects

    assert len(ready) == 2
    assert ready[0].project_id == "mylib"  # P0 first
    assert ready[1].project_id == "myapp"  # P1 second
```

**Implementation**: `get_ready_work()` function with dependency checking.

---

## Phase 7: Integration Testing (Week 7)

### 7.1: End-to-End Workflows

**Tests to write first** (`test_integration.py`):

```python
def test_full_feature_planning_workflow(tmp_path):
    """Test complete feature planning workflow."""
    # Setup project
    project = tmp_path / "myapp"
    project.mkdir()
    subprocess.run(["git", "init"], cwd=project, check=True)
    os.chdir(project)

    # Initialize trace
    subprocess.run(["trace", "init"], check=True)

    # Create parent feature
    result = subprocess.run(
        ["trace", "create", "Add authentication", "--priority", "1"],
        capture_output=True,
        text=True,
        check=True
    )
    parent_id = re.search(r"Created (\S+):", result.stdout).group(1)

    # Break down into children
    subprocess.run(
        ["trace", "create", "Research OAuth libs", "--parent", parent_id],
        check=True
    )
    subprocess.run(
        ["trace", "create", "Implement Google auth", "--parent", parent_id],
        check=True
    )
    subprocess.run(
        ["trace", "create", "Add tests", "--parent", parent_id],
        check=True
    )

    # View tree
    result = subprocess.run(
        ["trace", "tree", parent_id],
        capture_output=True,
        text=True,
        check=True
    )
    assert "Add authentication" in result.stdout
    assert "Research OAuth libs" in result.stdout

    # Check ready work
    result = subprocess.run(
        ["trace", "ready"],
        capture_output=True,
        text=True,
        check=True
    )
    assert "Research OAuth libs" in result.stdout

    # Verify JSONL was created
    assert (project / ".trace" / "issues.jsonl").exists()

def test_cross_project_dependency_workflow(tmp_path):
    """Test cross-project dependencies."""
    # Create two projects
    lib_project = tmp_path / "mylib"
    app_project = tmp_path / "myapp"

    for proj in [lib_project, app_project]:
        proj.mkdir()
        subprocess.run(["git", "init"], cwd=proj, check=True)
        os.chdir(proj)
        subprocess.run(["trace", "init"], check=True)

    # Create library issue
    os.chdir(lib_project)
    result = subprocess.run(
        ["trace", "create", "Add WebSocket support"],
        capture_output=True,
        text=True,
        check=True
    )
    lib_issue_id = re.search(r"Created (\S+):", result.stdout).group(1)

    # Create app issue that depends on library
    os.chdir(app_project)
    subprocess.run(
        ["trace", "create", "Add real-time notifications",
         "--depends-on", lib_issue_id],
        check=True
    )

    # Check ready work across projects
    result = subprocess.run(
        ["trace", "ready", "--all"],
        capture_output=True,
        text=True,
        check=True
    )

    # Library issue should be ready, app issue should be blocked
    assert "Add WebSocket support" in result.stdout
    # App issue might not show in ready (it's blocked)

def test_git_merge_workflow(tmp_path):
    """Test JSONL merges cleanly in git."""
    # Create project and trace
    project = tmp_path / "myapp"
    project.mkdir()
    subprocess.run(["git", "init"], cwd=project, check=True)
    os.chdir(project)
    subprocess.run(["trace", "init"], check=True)

    # Create issue and commit
    subprocess.run(["trace", "create", "Issue 1"], check=True)
    subprocess.run(["git", "add", ".trace/issues.jsonl"], cwd=project, check=True)
    subprocess.run(["git", "commit", "-m", "Add issue 1"], cwd=project, check=True)

    # Create branch
    subprocess.run(["git", "checkout", "-b", "feature"], cwd=project, check=True)
    subprocess.run(["trace", "create", "Issue 2"], check=True)
    subprocess.run(["git", "add", ".trace/issues.jsonl"], cwd=project, check=True)
    subprocess.run(["git", "commit", "-m", "Add issue 2"], cwd=project, check=True)

    # Go back to main and create different issue
    subprocess.run(["git", "checkout", "master"], cwd=project, check=True)
    subprocess.run(["trace", "create", "Issue 3"], check=True)
    subprocess.run(["git", "add", ".trace/issues.jsonl"], cwd=project, check=True)
    subprocess.run(["git", "commit", "-m", "Add issue 3"], cwd=project, check=True)

    # Merge (should succeed without conflicts)
    result = subprocess.run(
        ["git", "merge", "feature"],
        cwd=project,
        capture_output=True,
        text=True
    )

    # Should merge cleanly (JSONL appends lines)
    assert result.returncode == 0

    # List should show all 3 issues
    result = subprocess.run(
        ["trace", "list"],
        capture_output=True,
        text=True,
        check=True
    )
    assert "Issue 1" in result.stdout
    assert "Issue 2" in result.stdout
    assert "Issue 3" in result.stdout

def test_reorganization_workflow(tmp_path):
    """Test reorganizing work structure."""
    project = tmp_path / "myapp"
    project.mkdir()
    subprocess.run(["git", "init"], cwd=project, check=True)
    os.chdir(project)
    subprocess.run(["trace", "init"], check=True)

    # Create initial structure
    result = subprocess.run(
        ["trace", "create", "Old parent"],
        capture_output=True,
        text=True,
        check=True
    )
    old_parent_id = re.search(r"Created (\S+):", result.stdout).group(1)

    result = subprocess.run(
        ["trace", "create", "Child", "--parent", old_parent_id],
        capture_output=True,
        text=True,
        check=True
    )
    child_id = re.search(r"Created (\S+):", result.stdout).group(1)

    # Create new parent
    result = subprocess.run(
        ["trace", "create", "New parent"],
        capture_output=True,
        text=True,
        check=True
    )
    new_parent_id = re.search(r"Created (\S+):", result.stdout).group(1)

    # Reparent child
    subprocess.run(
        ["trace", "reparent", child_id, "--parent", new_parent_id],
        check=True
    )

    # Verify tree
    result = subprocess.run(
        ["trace", "tree", new_parent_id],
        capture_output=True,
        text=True,
        check=True
    )
    assert "Child" in result.stdout
```

**Implementation**: Ensure all integration scenarios work end-to-end.

---

## Testing Infrastructure

### Fixtures (conftest.py)

```python
import pytest
import tempfile
import shutil
from pathlib import Path

@pytest.fixture
def tmp_trace_dir(tmp_path):
    """Create temporary trace directory."""
    trace_dir = tmp_path / ".trace"
    trace_dir.mkdir()
    return trace_dir

@pytest.fixture
def db_connection(tmp_trace_dir):
    """Create fresh database connection."""
    db_path = tmp_trace_dir / "trace.db"
    db = init_database(db_path)
    yield db
    db.close()

@pytest.fixture
def sample_project(db_connection, tmp_path):
    """Create sample project with test data."""
    project_path = tmp_path / "sample"
    project_path.mkdir()
    subprocess.run(["git", "init"], cwd=project_path, check=True)

    register_project(db_connection, "sample", str(project_path))

    # Create sample issues
    parent = create_issue(db_connection, "sample", "Parent task")
    create_issue(db_connection, "sample", "Child 1", parent_id=parent.id)
    create_issue(db_connection, "sample", "Child 2", parent_id=parent.id)

    return project_path
```

---

## Coverage and Quality Gates

### Minimum Coverage Requirements

- **Overall**: 95% line coverage
- **Core logic** (IDs, sync, dependencies): 100%
- **CLI**: 90% (some error paths hard to test)
- **Integration**: All major workflows covered

### Running Tests

```bash
# Run all tests
pytest

# With coverage
pytest --cov=trace --cov-report=html

# Run specific test file
pytest tests/test_ids.py

# Run specific test
pytest tests/test_ids.py::test_generate_id_detects_collision

# Run with verbose output
pytest -v

# Run integration tests only
pytest tests/test_integration.py
```

### Continuous Integration

On every commit:
1. Run full test suite
2. Check coverage thresholds
3. Run linting (ruff, mypy)
4. Verify documentation builds

---

## Implementation Workflow

For each feature:

1. **Write tests first**
   - Start with simplest test
   - Add edge cases
   - Add error cases

2. **Run tests** (they should fail)
   ```bash
   pytest tests/test_feature.py::test_new_feature -v
   ```

3. **Implement minimal code** to pass tests
   - Focus on making tests pass
   - Don't over-engineer

4. **Run tests** (should pass)
   ```bash
   pytest tests/test_feature.py::test_new_feature -v
   ```

5. **Refactor** while keeping tests green
   - Clean up code
   - Extract functions
   - Improve names

6. **Add more tests** for edge cases discovered

7. **Repeat** until feature complete

---

## Success Criteria

Trace is ready for use when:

- ✅ All Phase 1-6 tests pass
- ✅ 95%+ code coverage
- ✅ Integration tests demonstrate all use cases
- ✅ CLI is fully functional
- ✅ JSONL syncs correctly
- ✅ Reorganization works without issues
- ✅ Documentation is complete

---

## Next Steps

Ready to start implementation? The suggested order:

1. **Week 1**: Phase 1 (Infrastructure)
   - Set up project structure
   - Implement ID generation (with tests!)
   - Project detection
   - Database schema
   - File locking

2. **Week 2**: Phase 2 (Issue CRUD)
   - Create, read, update, close
   - Parent-child relationships
   - Cross-project dependencies

3. **Week 3**: Phase 3 (Sync)
   - JSONL export
   - JSONL import
   - Bidirectional sync

4. **Week 4**: Phase 4 (CLI)
   - Click framework
   - All basic commands
   - JSON output

5. **Week 5**: Phase 5 (Reorganization)
   - Reparent command
   - Move command
   - Cycle detection

6. **Week 6**: Phase 6 (Queries)
   - Tree view
   - Ready work
   - Search

7. **Week 7**: Phase 7 (Integration)
   - End-to-end tests
   - Polish
   - Documentation

This test-first approach ensures we build exactly what we need, with confidence that it works correctly.
