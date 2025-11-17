# Development History - Trace Implementation

> **Note**: This document is historical. It tracked implementation progress during development.
> **All work described here is now complete** (156 tests passing, all features implemented).

**Last Updated:** 2025-11-17
**Final Status:** ✅ Core implementation complete - All 156 tests passing

---

## Table of Contents

1. [Current Status Summary](#current-status-summary)
2. [Completed Work](#completed-work)
3. [Remaining Work Items](#remaining-work-items)
4. [File Reference](#file-reference)
5. [How to Continue](#how-to-continue)

---

## Current Status Summary

### Metrics
- **Total Tests:** 140 (all passing ✅)
- **Code Size:** 1,670 lines in `trace.py`
- **Test Coverage:** ~95% for core functionality
- **Phases Complete:** 1-5 of 7 (from `docs/implementation-plan.md`)

### What Works
- ✅ Hash-based ID generation with collision detection
- ✅ Project detection from git repositories
- ✅ SQLite database with full schema
- ✅ Issue CRUD operations (create, read, update, delete, close)
- ✅ Dependency management (parent-child, blocks, related)
- ✅ JSONL export (git-friendly storage)
- ✅ JSONL import (from file to database)
- ✅ File locking for concurrent access safety
- ✅ Reorganization commands (reparent, move)
- ✅ Query commands (list, ready, tree, show)
- ✅ CLI for all core operations

### What's Missing
- ⚠️ **Automatic JSONL sync** - Only partial implementation
- ❌ **Complete CLI argument parsing** - Missing flags for `trace create`
- ❌ **Integration tests** - End-to-end workflow tests
- ❌ **Documentation** - README, quickstart guide

---

## Completed Work

### Phase 1: Core Infrastructure ✅
**Location:** `trace.py` lines 28-326
**Tests:** `tests/test_ids.py`, `tests/test_projects.py`, `tests/test_db.py`, `tests/test_locking.py`

- Hash-based ID generation (6-char base36)
- Collision detection with retry logic
- Project detection from git remotes
- SQLite schema with constraints and indexes
- File locking with fcntl (timeout-based)

### Phase 2: Issue CRUD ✅
**Location:** `trace.py` lines 392-589
**Tests:** `tests/test_issues.py` (22 tests)

- `create_issue()` - Create with validation
- `get_issue()` - Fetch by ID
- `list_issues()` - Filter by project/status, sorted by priority
- `update_issue()` - Modify fields with timestamp tracking
- `close_issue()` - Close with timestamp

### Phase 3: Dependencies ✅
**Location:** `trace.py` lines 591-751
**Tests:** `tests/test_dependencies.py` (16 tests)

- Three dependency types: parent, blocks, related
- Cross-project dependencies supported
- `is_blocked()` - Check if issue has open blockers
- `has_open_children()` - Check if parent has open children
- `get_children()` - Recursive parent-child queries

### Phase 4: JSONL Sync ✅
**Location:** `trace.py` lines 914-1089
**Tests:** `tests/test_sync.py` (13 tests)

- `export_to_jsonl()` - Atomic write (temp + rename)
- `import_from_jsonl()` - Create/update from JSONL
- Sorted by ID for stable diffs
- Malformed JSON handling (skip and continue)

### Phase 5: Reorganization ✅
**Location:** `trace.py` lines 757-908
**Tests:** `tests/test_reorganization.py` (14 tests)

- `reparent_issue()` - Change parent with cycle detection
- `move_issue()` - Move between projects (updates all dependencies)
- `detect_cycle()` - Prevent circular parent-child relationships

### Phase 6: Query Commands ✅
**Location:** `trace.py` lines 1170-1410
**Tests:** `tests/test_queries.py` (15 tests), `tests/test_cli.py` (17 tests)

- `cli_list()` - List issues with filters
- `cli_ready()` - Show unblocked work
- `cli_tree()` - Display parent-child hierarchy
- `cli_show()` - Detailed issue view

### CLI Commands ✅
**Location:** `trace.py` lines 1098-1661

All commands implemented:
- `trace init` - Initialize project
- `trace create <title>` - Create issue (basic)
- `trace list [--all]` - List issues
- `trace show <id>` - Show details
- `trace close <id>` - Close issue
- `trace update <id> [options]` - Update fields
- `trace ready [--all]` - Show ready work
- `trace tree <id>` - Show hierarchy
- `trace reparent <id> <parent>` - Change parent
- `trace move <id> <project>` - Move to different project

---

## Remaining Work Items

### 1. Automatic JSONL Sync ⚠️ CRITICAL

**Priority:** HIGH
**Effort:** ~2-3 hours
**Status:** Partially implemented

#### Problem
Currently, JSONL import only happens in 2 commands (`cli_list`, `cli_ready`). All other commands don't check if the JSONL file is newer than the database.

**Why this matters:** After `git pull`, the JSONL file will be updated, but the database won't reflect changes until you run `trace list`.

#### What CLAUDE.md Specifies

From `CLAUDE.md` lines 277-284:

```
Every command follows:
1. Acquire file lock (`~/.trace/.lock`)
2. Check JSONL mtime vs last sync
3. If JSONL newer: import to DB (e.g., after git pull)
4. Execute command (modify DB)
5. Export DB → JSONL (atomic write: temp + rename)
6. Update last sync timestamp
7. Release lock
```

#### Current Implementation Gaps

1. **No mtime checking** - We don't track when DB was last synced
2. **Inconsistent import** - Only `cli_list` and `cli_ready` import before execution
3. **No file locking around sync** - Lock exists but not used in sync operations
4. **No last sync timestamp** - No mechanism to compare JSONL mtime

#### Current Sync Locations

```python
# trace.py:1189 - cli_list imports before listing
if jsonl_path.exists():
    import_from_jsonl(db, str(jsonl_path))

# trace.py:1316 - cli_ready imports before showing ready work
if jsonl_path.exists():
    import_from_jsonl(db, str(jsonl_path))
```

#### What Needs to Be Done

**Step 1: Add metadata tracking**

```python
# Add to metadata table
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT
);

# Track per-project last sync
def get_last_sync_time(db: Connection, project_id: str) -> Optional[float]:
    """Get timestamp of last JSONL sync for project."""
    cursor = db.execute(
        "SELECT value FROM metadata WHERE key = ?",
        (f"last_sync:{project_id}",)
    )
    row = cursor.fetchone()
    return float(row[0]) if row else None

def set_last_sync_time(db: Connection, project_id: str, timestamp: float):
    """Record timestamp of JSONL sync."""
    db.execute(
        "INSERT OR REPLACE INTO metadata (key, value, updated_at) VALUES (?, ?, ?)",
        (f"last_sync:{project_id}", str(timestamp),
         datetime.now(timezone.utc).isoformat())
    )
```

**Step 2: Create sync wrapper**

```python
def sync_project(db: Connection, project_path: str) -> None:
    """Sync project: import from JSONL if newer than last sync."""
    trace_dir = Path(project_path) / ".trace"
    jsonl_path = trace_dir / "issues.jsonl"

    if not jsonl_path.exists():
        return

    # Check if JSONL is newer than last sync
    jsonl_mtime = jsonl_path.stat().st_mtime
    last_sync = get_last_sync_time(db, project_path)

    if last_sync is None or jsonl_mtime > last_sync:
        # JSONL is newer, import it
        import_from_jsonl(db, str(jsonl_path))
        set_last_sync_time(db, project_path, jsonl_mtime)
```

**Step 3: Apply to all CLI commands**

Add `sync_project()` call at the start of every command that reads project data:
- `cli_create()`
- `cli_show()`
- `cli_update()`
- `cli_close()`
- `cli_reparent()`
- `cli_move()`
- `cli_tree()`

**Example:**
```python
def cli_show(issue_id: str):
    """Show issue details."""
    db = get_db()

    # Get project and sync BEFORE querying
    issue = get_issue(db, issue_id)
    if issue:
        sync_project(db, issue["project_id"])  # ← ADD THIS
        issue = get_issue(db, issue_id)  # Re-fetch after sync

    # ... rest of function
```

**Step 4: Add file locking**

Wrap sync operations in file lock:
```python
from trace import file_lock, get_lock_path

def cli_create(title: str, ...):
    lock_path = get_lock_path()

    with file_lock(lock_path):
        db = get_db()
        project = detect_project()

        # Sync before operation
        sync_project(db, project["path"])

        # Execute command
        issue = create_issue(db, ...)

        # Export after operation
        export_to_jsonl(db, ...)
        set_last_sync_time(db, project["path"], time.time())
```

#### Testing Strategy

Add tests to `tests/test_sync.py`:

```python
def test_sync_imports_when_jsonl_newer(tmp_path, db_connection):
    """Should import JSONL when file is newer than last sync."""
    # Create issue in JSONL
    # Set old last_sync timestamp
    # Call sync_project()
    # Verify issue imported

def test_sync_skips_when_db_newer(tmp_path, db_connection):
    """Should skip import when DB is already up-to-date."""
    # Create issue in DB and export
    # Touch JSONL to older time
    # Call sync_project()
    # Verify no re-import (check via log or timestamp)

def test_sync_handles_missing_jsonl(db_connection):
    """Should handle missing JSONL gracefully."""
    # Call sync_project() with non-existent path
    # Should not error
```

#### Files to Modify

- `trace.py` (add sync logic)
- `tests/test_sync.py` (add sync tests)

---

### 2. Complete CLI Argument Parsing ❌ HIGH PRIORITY

**Priority:** HIGH
**Effort:** ~1-2 hours
**Status:** Not started

#### Problem

The `trace create` command only accepts a title. It doesn't support the flags documented in `docs/cli-design.md`.

#### What docs/cli-design.md Specifies

From `docs/cli-design.md` lines 87-109:

```bash
trace create "Add OAuth" \
    --priority 1 \
    --parent myapp-xyz999 \
    --depends-on mylib-def456 \
    --project myapp \
    --description "Implement OAuth 2.0 flow"

# Options
--priority <0-4>           Priority level (default: 2)
--parent <id>              Parent issue ID
--depends-on <id>          Blocking dependency ID
--project <name>           Override auto-detected project
--description <text>       Detailed description
--status <status>          Initial status (default: open)
```

#### Current Implementation

From `trace.py` lines 1568-1574:

```python
elif command == "create":
    if len(sys.argv) < 3:
        print("Error: Title required")
        print("Usage: trace create <title>")
        sys.exit(1)
    title = " ".join(sys.argv[2:])
    sys.exit(cli_create(title))  # ← Only passes title!
```

The `cli_create()` function ALREADY accepts these parameters:

```python
def cli_create(title: str, description: str = "", priority: int = 2,
               parent: Optional[str] = None):
```

We just need to parse the arguments and pass them!

#### What Needs to Be Done

**Step 1: Parse arguments**

Replace the create command handler in `trace.py` (around line 1568):

```python
elif command == "create":
    if len(sys.argv) < 3:
        print("Error: Title required")
        print("Usage: trace create <title> [options]")
        sys.exit(1)

    # Parse title (everything before first flag)
    title_parts = []
    i = 2
    while i < len(sys.argv) and not sys.argv[i].startswith("--"):
        title_parts.append(sys.argv[i])
        i += 1

    if not title_parts:
        print("Error: Title required")
        sys.exit(1)

    title = " ".join(title_parts)

    # Parse flags
    description = ""
    priority = 2
    status = "open"
    parent = None
    depends_on = None

    while i < len(sys.argv):
        if sys.argv[i] == "--description" and i + 1 < len(sys.argv):
            description = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--priority" and i + 1 < len(sys.argv):
            try:
                priority = int(sys.argv[i + 1])
            except ValueError:
                print("Error: Priority must be a number 0-4")
                sys.exit(1)
            i += 2
        elif sys.argv[i] == "--status" and i + 1 < len(sys.argv):
            status = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--parent" and i + 1 < len(sys.argv):
            parent = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--depends-on" and i + 1 < len(sys.argv):
            depends_on = sys.argv[i + 1]
            i += 2
        else:
            print(f"Unknown option: {sys.argv[i]}")
            sys.exit(1)

    # Pass to cli_create
    sys.exit(cli_create(title, description=description, priority=priority,
                        parent=parent))
```

**Step 2: Update cli_create to handle --depends-on**

Currently `cli_create()` only handles `--parent`. Need to add support for `--depends-on`:

```python
def cli_create(title: str, description: str = "", priority: int = 2,
               parent: Optional[str] = None, depends_on: Optional[str] = None,
               status: str = "open"):
    """Create a new issue."""
    project = detect_project()

    if project is None:
        print("Error: Not in a git repository")
        print("Run 'trace init' first")
        return 1

    db = get_db()

    # Create issue
    issue = create_issue(
        db,
        project["path"],
        project["name"],
        title,
        description=description,
        priority=priority,
        status=status,  # ← Add status parameter
    )

    # Add parent dependency if specified
    if parent:
        add_dependency(db, issue["id"], parent, "parent")

    # Add blocking dependency if specified
    if depends_on:
        add_dependency(db, issue["id"], depends_on, "blocks")

    # Export to JSONL
    trace_dir = Path(project["path"]) / ".trace"
    jsonl_path = trace_dir / "issues.jsonl"
    export_to_jsonl(db, project["path"], str(jsonl_path))

    print(f"Created {issue['id']}: {title}")
    if parent:
        print(f"  Parent: {parent}")
    if depends_on:
        print(f"  Blocks: {depends_on}")

    db.close()
    return 0
```

**Step 3: Update help text**

Update the help message (around line 1547):

```python
print("  trace create <title> [options]  Create issue")
print("    --description <text>          Detailed description")
print("    --priority <0-4>              Priority level (default: 2)")
print("    --parent <id>                 Parent issue ID")
print("    --depends-on <id>             Blocking dependency ID")
print("    --status <status>             Initial status (default: open)")
```

#### Testing Strategy

Add tests to `tests/test_cli.py`:

```python
def test_cli_create_with_description(sample_project, tmp_trace_dir, monkeypatch, capsys):
    """cli_create should accept --description flag."""
    from trace import cli_init, get_db, get_issue
    import sys

    monkeypatch.chdir(sample_project["path"])
    cli_init()

    # Mock sys.argv
    monkeypatch.setattr(sys, "argv", [
        "trace", "create", "Test issue",
        "--description", "This is a test",
        "--priority", "1"
    ])

    # Run main CLI
    # ... verify issue created with description and priority

def test_cli_create_with_depends_on(sample_project, tmp_trace_dir, monkeypatch, capsys):
    """cli_create should accept --depends-on flag."""
    # Similar test for --depends-on
```

#### Files to Modify

- `trace.py` (CLI argument parsing)
- `tests/test_cli.py` (add flag tests)

---

### 3. Integration Tests ❌ MEDIUM PRIORITY

**Priority:** MEDIUM
**Effort:** ~3-4 hours
**Status:** Not started

#### Problem

No end-to-end workflow tests exist. All current tests are unit tests.

#### What docs/implementation-plan.md Specifies

From `docs/implementation-plan.md` lines 1437-1529:

Three main integration test scenarios:

1. **Feature Planning Workflow**
   - Initialize trace in a project
   - Create parent feature
   - Break down into children
   - View tree
   - Check ready work
   - Verify JSONL created

2. **Cross-Project Dependency Workflow**
   - Create two projects
   - Create issue in lib project
   - Create issue in app project that depends on lib
   - Check ready work across projects
   - Verify cross-project blocking

3. **Git Workflow** (stretch goal)
   - Create issue
   - Commit JSONL
   - Create another issue
   - Simulate git pull
   - Verify sync

#### What Needs to Be Done

Create `tests/test_integration.py`:

```python
"""Integration tests for end-to-end workflows."""

import subprocess
import os
from pathlib import Path
import re

import pytest


def test_feature_planning_workflow(tmp_path, tmp_trace_dir, monkeypatch):
    """Test complete feature planning workflow."""
    from trace import cli_init, cli_create, cli_tree, cli_ready

    # Setup project
    project = tmp_path / "myapp"
    project.mkdir()
    subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True)

    monkeypatch.chdir(project)

    # Initialize trace
    result = cli_init()
    assert result == 0
    assert (project / ".trace" / "issues.jsonl").exists()

    # Create parent feature
    import sys
    from io import StringIO
    captured_output = StringIO()

    result = cli_create("Add authentication", priority=1)
    assert result == 0

    # Extract parent ID from output
    # ... continue with workflow

    # Create child tasks
    # View tree
    # Check ready work
    # Verify JSONL contents


def test_cross_project_dependencies(tmp_path, tmp_trace_dir, monkeypatch):
    """Test cross-project dependency workflow."""
    from trace import cli_init, cli_create, cli_ready, get_db, add_dependency

    # Create lib project
    lib_project = tmp_path / "mylib"
    lib_project.mkdir()
    subprocess.run(["git", "init"], cwd=lib_project, check=True, capture_output=True)

    # Create app project
    app_project = tmp_path / "myapp"
    app_project.mkdir()
    subprocess.run(["git", "init"], cwd=app_project, check=True, capture_output=True)

    # Initialize both
    monkeypatch.chdir(lib_project)
    cli_init()

    monkeypatch.chdir(app_project)
    cli_init()

    # Create lib issue
    monkeypatch.chdir(lib_project)
    cli_create("Add WebSocket support")

    # Create app issue that depends on lib
    # ... continue workflow


def test_jsonl_roundtrip(tmp_path, tmp_trace_dir, monkeypatch):
    """Test JSONL export/import roundtrip."""
    from trace import cli_init, cli_create, get_db, get_issue

    # Create project
    # Create issues
    # Export to JSONL
    # Wipe database
    # Import from JSONL
    # Verify all issues restored


def test_git_pull_simulation(tmp_path, tmp_trace_dir, monkeypatch):
    """Test sync after simulated git pull."""
    from trace import cli_init, cli_create, cli_list, export_to_jsonl
    import shutil

    # Create project and issue
    # Save JSONL
    # Modify JSONL externally (simulate git pull)
    # Run any command
    # Verify sync detected and imported changes
```

#### Files to Create

- `tests/test_integration.py` (new file)

---

### 4. Documentation ❌ LOW PRIORITY

**Priority:** LOW
**Effort:** ~2 hours
**Status:** Not started

#### What's Needed

1. **README.md**
   - Project overview
   - Installation instructions
   - Quick start guide
   - Basic usage examples

2. **Quickstart Guide**
   - First project setup
   - Creating issues
   - Viewing work
   - Reorganizing

3. **Update CLAUDE.md**
   - Mark Phase 1-5 as complete
   - Update current status
   - Add notes about remaining work

#### Files to Create/Update

- `README.md` (new)
- `docs/quickstart.md` (new)
- `CLAUDE.md` (update status section)

---

## File Reference

### Core Implementation
- **trace.py** (1,670 lines) - Main implementation
  - Lines 28-105: ID generation
  - Lines 111-157: File locking
  - Lines 195-238: Project detection
  - Lines 301-326: Database schema
  - Lines 392-589: Issue CRUD
  - Lines 591-751: Dependencies
  - Lines 757-908: Reorganization
  - Lines 914-1089: JSONL sync
  - Lines 1098-1661: CLI commands

### Tests (140 tests total)
- **tests/conftest.py** - Shared fixtures
- **tests/test_ids.py** (11 tests) - ID generation
- **tests/test_projects.py** (11 tests) - Project detection
- **tests/test_db.py** (13 tests) - Database schema
- **tests/test_issues.py** (22 tests) - Issue CRUD
- **tests/test_dependencies.py** (16 tests) - Dependencies
- **tests/test_sync.py** (13 tests) - JSONL sync
- **tests/test_locking.py** (8 tests) - File locking
- **tests/test_reorganization.py** (14 tests) - Reparent/move
- **tests/test_queries.py** (15 tests) - Tree/ready queries
- **tests/test_cli.py** (17 tests) - CLI commands

### Documentation
- **CLAUDE.md** - Project instructions for AI
- **docs/product-vision.md** - Core philosophy
- **docs/use-cases.md** - Real-world workflows
- **docs/key-features.md** - Technical details
- **docs/cli-design.md** - Command reference
- **docs/implementation-plan.md** - Phase-by-phase specs
- **docs/design-decisions.md** - Architecture decisions
- **docs/remaining-work.md** - This document

### Configuration
- **pyproject.toml** - Project metadata and dependencies
- **uv.lock** - Locked dependency versions

---

## How to Continue

### Quick Start (Resume Work)

1. **Verify environment:**
   ```bash
   cd /Users/don/Repos/trace
   uv sync  # Install dependencies
   pytest   # Verify all 140 tests pass
   ```

2. **Choose a work item:**
   - Start with #1 (Automatic JSONL Sync) - most critical
   - Or #2 (CLI Argument Parsing) - quick win
   - Or #3 (Integration Tests) - comprehensive validation

3. **Follow TDD:**
   - Write tests first
   - Run tests (should fail)
   - Implement minimal code to pass
   - Refactor while keeping tests green

### Running Tests

```bash
# All tests
pytest

# Specific test file
pytest tests/test_sync.py

# Specific test
pytest tests/test_sync.py::test_export_import_roundtrip

# With coverage
pytest --cov=trace --cov-report=html

# Verbose
pytest -v

# Stop on first failure
pytest -x
```

### Code Style

```bash
# Format code
ruff format .

# Lint
ruff check .
```

### Git Workflow

```bash
# Current branch
git status

# Run tests before committing
pytest

# Commit changes
git add .
git commit -m "Add automatic JSONL sync logic

Implements mtime checking and sync before all commands.
Adds file locking around sync operations.

✅ All 140 tests passing"
```

---

## Key Principles (Reminders)

From `CLAUDE.md`:

1. **Test-First Development** - No code without tests
2. **Single-file implementation** - Keep everything in `trace.py`
3. **Action-driven sync** - No daemons, sync on command execution
4. **JSONL is source of truth** - DB is aggregation, can be rebuilt
5. **Cross-project support** - Issues can depend across projects
6. **Reorganization is trivial** - Make structure fluid, not rigid

---

## Questions? Issues?

- **CLAUDE.md** - Full project context and guidelines
- **docs/implementation-plan.md** - Detailed test specifications
- **docs/cli-design.md** - Complete CLI API reference
- **GitHub Issues** - Track bugs/features (when ready)

**Current test count:** 140 passing ✅
**Next milestone:** 160+ tests (after adding sync, CLI flags, integration tests)

---

**End of Document**
