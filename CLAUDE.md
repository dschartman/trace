# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Trace** is a minimal distributed issue tracker designed specifically for AI agent workflows. It enables cross-project work tracking, iterative planning, and easy reorganization as understanding evolves.

**Current Status**: Core implementation complete. All 156 tests passing. Phases 1-6 complete (core functionality, CRUD, dependencies, JSONL sync, reorganization, queries). Automatic JSONL sync implemented. Full CLI with all flags.

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
├── conftest.py              # Shared fixtures (tmp_trace_dir, db_connection, etc.)
├── test_ids.py              # ID generation & collision detection
├── test_projects.py         # Project detection & registry
├── test_issues.py           # Issue CRUD operations
├── test_dependencies.py     # Dependency tracking
├── test_sync.py             # JSONL ↔ DB sync
├── test_cli.py              # CLI commands
├── test_reorganization.py   # Move/reparent operations
├── test_queries.py          # List, ready, tree queries
└── test_integration.py      # End-to-end workflows
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

## Implementation Phases

### Phase 1: Core Infrastructure (Current)
- Hash ID generation with collision detection
- Project detection and registry
- Database schema with constraints
- File locking for sync safety
- Issue CRUD operations
- JSONL import/export

### Phase 2-7
See `docs/implementation-plan.md` for complete breakdown.

## Key Design Decisions

1. **No enforced hierarchy**: Use flat parent-child relationships, not epic→feature→story
2. **Path-based project IDs**: Absolute paths ensure uniqueness
3. **Default project**: Discovery inbox at `~/.trace/default/` for pre-project work
4. **Immediate JSONL export**: Prioritize safety over performance
5. **Single-file implementation**: Target ~500 lines in `trc_main.py`
6. **No daemon (Phase 1)**: Subprocess is fast enough
7. **No size field**: Removed - not useful for AI agents
8. **No auto-close parents**: Parents require explicit close action
9. **Manual merge conflicts**: Treat JSONL like code - user resolves conflicts
10. **JSONL is source of truth**: Central DB is aggregation, can be rebuilt

## Default Behaviors

- **`trc list`**: Shows flat list, ordered by priority/status/created_at (YAGNI approach)
  - In project: show that project's issues
  - Outside project: show default project issues
  - Use `--all` for cross-project view
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

- Implementation: `trc_main.py` (single file, ~500 lines target)
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
- `trc ready --all` shows work ordered by cross-project blocking
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

Future: MCP server will expose trace as native Claude Code tool.
