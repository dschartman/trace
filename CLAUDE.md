# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Trace** is a minimal distributed issue tracker designed specifically for AI agent workflows. It enables cross-project work tracking, iterative planning, and easy reorganization as understanding evolves.

**Core Philosophy**: Work structure should be fluid, not rigid. Make reorganization trivial so structure becomes a tool for thinking, not a constraint.

## Development Commands

### Dependency Management
```bash
# Add dependencies (NEVER edit pyproject.toml directly)
uv add <package-name>

# Add dev dependencies
uv add --dev <package-name>

# Install all dependencies
uv sync
```

### Testing (Test-First Development)
**IMPORTANT**: Always use `uv run` prefix for Python commands to ensure correct environment.

```bash
# Run all tests
uv run pytest

# Run with coverage report
uv run pytest --cov=trace --cov-report=html

# Run specific test file
uv run pytest tests/test_ids.py

# Run specific test
uv run pytest tests/test_ids.py::test_generate_id_detects_collision

# Run in verbose mode
uv run pytest -v

# Run integration tests only
uv run pytest tests/test_integration.py

# Run Python scripts
uv run python trc_main.py <command>
```

### Code Quality
```bash
# Linting
uv run ruff check .

# Type checking
uv run ty check .

# Format code
uv run ruff format .
```

### Global Tool Installation

**CRITICAL**: `uv tool install` creates a **copy** of the code, not a symlink.

```bash
# Install/update globally (makes `trc` command available)
uv tool install --force .

# Testing during development
uv run python trc_main.py <command>  # Uses source directly
trc <command>                         # Uses installed copy
```

**When making changes to the codebase:**

1. **ALWAYS bump the version in `pyproject.toml`** first
   - `uv` caches builds by version number
   - Without a version bump, `uv` will use the cached old version
   - Example: `0.1.0` → `0.1.1`

2. **Reinstall globally** to test changes:
   ```bash
   uv tool uninstall trc
   uv tool install .
   ```

3. **Verify the new version** is installed:
   ```bash
   uv tool list  # Should show new version number
   ```

**Why this matters:**
- During development, use `uv run python trc_main.py` to test changes immediately
- Before releasing or testing the actual `trc` command, bump version and reinstall
- This ensures the global `trc` command has your latest changes

## Architecture

### Hybrid Storage Model

Trace uses a dual-storage architecture optimized for both performance and git workflows:

```
~/.trace/
├── trace.db              # Central SQLite (all projects, fast queries)
├── default/              # Default project (discovery inbox)
│   └── .trace/issues.jsonl
└── .lock                 # File lock for sync operations

~/Repos/myapp/
└── .trace/
    └── issues.jsonl      # Per-project JSONL (git-friendly)
```

**Key insight**: SQLite for complex queries, JSONL for git mergeability. Sync happens automatically on every operation.

### Project Identification

Projects are uniquely identified by **absolute path** (not name). This supports:
- Same repo cloned to multiple locations
- Multiple repos with the same name
- Cross-project dependencies

Detection logic:
1. Walk up directories to find `.git`
2. Extract name from git remote (or use directory name)
3. Use absolute path as unique `project_id`

### Hash-Based IDs

Issues use 6-character collision-resistant IDs:
- Format: `{project}-{hash}` (e.g., `myapp-7k3m2x`)
- Base36 encoding: `[0-9a-z]`
- Entropy: title + nanosecond timestamp + random bytes
- Collision detection with retry logic (max 10 attempts)

### Dependency Types

Three relationship types:
1. **parent-child**: Hierarchical decomposition (no enforced levels)
2. **blocks**: Blocking dependency (affects ready work)
3. **related**: Informational link

Cross-project dependencies are fully supported.

## Test-Driven Development (CRITICAL)

**ALL code must be test-first**. No exceptions.

### TDD Workflow

1. **Write test first** - Define expected behavior
2. **Run test** (should fail - red)
3. **Implement** minimal code to pass
4. **Run test** (should pass - green)
5. **Refactor** while keeping tests green
6. **Repeat**

### Test Structure

```
tests/
├── conftest.py                        # Shared fixtures
├── test_cli.py                        # CLI commands
├── test_cross_project_contamination.py # Contamination prevention
├── test_db.py                         # Database schema
├── test_dependencies.py               # Dependency tracking
├── test_ids.py                        # ID generation
├── test_issues.py                     # Issue CRUD
├── test_projects.py                   # Project detection
├── test_reorganization.py             # Move/reparent
├── test_sync.py                       # JSONL sync
├── test_queries.py                    # List, ready, tree
├── test_integration.py                # End-to-end workflows
└── [additional edge case tests]       # Locking, isolation, etc.
```

### Coverage Requirements

- **Overall**: 95%+ line coverage
- **Core logic** (IDs, sync, dependencies): 100%
- **CLI**: 90%
- **Integration**: All major workflows

### Test Naming Convention

`test_<feature>_<scenario>_<expected_result>`

Examples:
- `test_generate_id_detects_collision_and_retries`
- `test_create_issue_with_parent_links_correctly`
- `test_sync_imports_when_jsonl_newer`

## Key Design Decisions

1. **No enforced hierarchy**: Use flat parent-child relationships, not epic→feature→story
2. **Path-based project IDs**: Absolute paths ensure uniqueness
3. **Default project**: Discovery inbox at `~/.trace/default/` for pre-project work
4. **Immediate JSONL export**: Prioritize safety over performance
5. **Modular implementation**: Core logic in `trace_core/` package, CLI entry point in `trc_main.py`
6. **No daemon**: Subprocess is fast enough
7. **No size field**: Removed - not useful for AI agents
8. **No auto-close parents**: Parents require explicit close action
9. **Manual merge conflicts**: Treat JSONL like code - user resolves conflicts
10. **JSONL is source of truth**: Central DB is aggregation, can be rebuilt

## Default Behaviors

- **`trc list`**: Shows backlog (open, in_progress, blocked - excludes closed), ordered by priority/created_at
  - Default: excludes closed issues to focus on active work
  - In project: show that project's backlog
  - Outside project: show default project backlog
  - Use `--project any` for cross-project view
  - Use `--status any` to show all statuses (including closed)
  - Use `--status closed` to see only completed work
  - Multiple `--status` flags supported (e.g., `--status open --status closed`)
- **Error handling**: Warn and continue when possible, fail clearly when not
- **Git workflow**: User managed - no auto-commits from trace

## Error Handling Strategy

**Philosophy**: JSONL files are distributed source of truth. Central DB is aggregation.

**Recovery Scenarios**:
1. **Corrupted SQLite**: Rebuild from JSONL files (`trc sync --force-import`)
2. **Malformed JSONL**: Warn, skip bad lines, report errors, user fixes manually
3. **Merge conflicts**: User resolves via git (treat like code)
4. **Project moved**: Requires manual re-registration (`trc init` in new location)
5. **Missing JSONL**: Export from DB if exists, create empty if not

**No automation for**: Merge conflicts, data corruption, project migration

## Reorganization Commands

Critical differentiator - make these trivial:
- `trc reparent <id> --parent <parent-id>` - Change parent (with cycle detection)
- `trc move <id> --to-project <project>` - Move between projects (updates dependencies)
- Cross-project moves preserve all relationships

## Common Pitfalls

1. **Don't edit pyproject.toml directly** - Always use `uv add`
2. **Don't skip tests** - Code without tests will be rejected
3. **Don't create cycles** - Reparent must detect and prevent
4. **Don't break sync atomicity** - Use temp file + rename pattern
5. **Don't forget file locking** - All sync operations must be locked

## File Locations

- Implementation: `trace_core/` package (modular design)
- CLI entry point: `trc_main.py` (re-exports from trace_core)
- Tests: `tests/` directory
- Docs: `docs/` directory
  - `product-vision.md` - Core philosophy
  - `use-cases.md` - Real-world workflows
  - `key-features.md` - Technical details
  - `cli-design.md` - Command reference
  - `quickstart.md` - Getting started guide
  - `design-decisions.md` - Important rationale

## When Working on Features

1. Write tests first (they should fail)
2. Implement minimal code to pass tests
3. Run coverage check
4. Update docs if behavior changes
5. Ensure JSONL export/import handles new fields

## Cross-Project Dependencies

Key capability - ensure:
- Dependencies can link across project boundaries
- `trc ready --project any` shows work ordered by cross-project blocking
- Moving an issue updates all dependencies pointing to it
- JSONL files store dependency IDs (may reference other projects)

## Sync Logic Critical Path

Every command follows:
1. Acquire file lock (`~/.trace/.lock`)
2. Check JSONL mtime vs last sync
3. If JSONL newer: import to DB (e.g., after git pull)
4. Execute command (modify DB)
5. Export DB → JSONL (atomic write: temp + rename)
6. Update last sync timestamp
7. Release lock

## AI Integration Notes

Trace is designed for AI agents (especially Claude Code):
- Commands have `--json` flag for machine-readable output
- Error messages are structured and parseable
- Bulk operations minimize round-trips
- Context-rich output (e.g., `trc show` includes dependencies, children, completion %)

### CRITICAL: Trace vs TodoWrite

**This is an explicit override of TodoWrite's default guidance.**

TodoWrite's general instructions suggest using it for "complex multi-step tasks", but this project uses trace instead for all non-trivial work.

**Use TodoWrite ONLY for:**
- Trivial, single-session work (e.g., "fix typo", "add comment")
- Tasks that will definitely complete in the current session
- Simple coordination within a single conversation

**Use trace for:**
- Anything involving multiple files, tests, or implementation steps
- Any work that could span multiple sessions
- Feature development, bug fixes, refactoring
- Planning or breaking down complex work
- Essentially: anything non-trivial

**When in doubt, use trace.** It's better to track too much than too little.

**Why this matters:** TodoWrite is ephemeral and tied to a single conversation. Trace persists across sessions, commits to git, and provides proper work management. For a tool designed around persistent work tracking, using TodoWrite for complex tasks defeats the purpose.
