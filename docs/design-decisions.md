# Design Decisions

This document captures key design decisions made during trace's development, including the rationale behind each choice.

## Table of Contents

1. [Storage Architecture](#storage-architecture)
2. [Project Model](#project-model)
3. [Work Hierarchy](#work-hierarchy)
4. [Features Removed](#features-removed)
5. [Error Handling](#error-handling)
6. [Git Workflow](#git-workflow)
7. [Default Behaviors](#default-behaviors)

---

## Storage Architecture

### Decision: Hybrid Storage (Central DB + Per-Project JSONL)

**Choice**: Use both SQLite central database AND per-project JSONL files.

**Rationale**:
- **SQLite**: Fast cross-project queries, complex joins, dependency traversal
- **JSONL**: Git-friendly, mergeable, human-readable, travels with repos
- Each storage type plays to its strengths

**Alternatives Considered**:
- ❌ **JSONL only**: Too slow for cross-project queries
- ❌ **SQLite only**: Doesn't work with git, not distributed
- ❌ **Separate per-project DBs**: Can't query across projects

### Decision: JSONL as Source of Truth

**Choice**: JSONL files are the distributed source of truth. Central DB is aggregation.

**Rationale**:
- JSONL lives in git - survives repo cloning, sharing, backup
- Multiple users can have different central DBs but share JSONL
- Central DB can be rebuilt from JSONL files
- Matches git workflow: distributed with central aggregation

**Implications**:
- Corrupted central DB? Rebuild from JSONL
- New user clones repo? JSONL comes with it, DB auto-builds
- Cross-project metadata (dependencies) may be lost if central DB corrupted, but can be rebuilt

---

## Project Model

### Decision: Path-Based Project Identification

**Choice**: Projects are uniquely identified by absolute filesystem path (not name).

**Rationale**:
- Supports same repo cloned to multiple locations (different branches/experiments)
- Supports multiple repos with identical names
- Enables cross-project dependencies without naming conflicts

**Example**:
```
/Users/don/Repos/myapp        → project ID
/Users/don/Experiments/myapp  → different project ID
/tmp/myapp-test               → different project ID
```

**Trade-off**: Moving a directory breaks the link (requires re-registration).

**Accepted because**: Project moves are rare, manual re-registration is acceptable.

### Decision: "Default" Project (Not "Personal")

**Choice**: Auto-created "default" project at `~/.trace/default/` instead of "personal".

**Rationale**:
- **default** = temporary staging area for pre-project work
- **personal** = permanent task list (implies different use case)
- Trace is a **project tracker**, not a universal task manager
- Default project naturally flows: discover → default → promote to real project
- Name "default" appears in `trc list` output when not in a project (clear context)

**Workflow**:
```bash
# Exploring an idea
$ trc create "Research distributed caching"  # → default project

# Later, create real project
$ mkdir ~/Repos/distcache && cd ~/Repos/distcache
$ trc init

# Promote work
$ trc move default-abc123 --to-project distcache
```

### Decision: Auto-Detection with Explicit Override

**Choice**: Auto-detect project from git repo, allow `--project` override.

**Implementation**:
1. Walk up directories to find `.git`
2. Extract name from git remote (or use directory name)
3. Use absolute path as unique ID
4. Register in central DB

**Benefits**:
- Zero friction: `trc create "Fix bug"` just works in a repo
- Explicit when needed: `--project` flag for cross-project operations
- Clear errors: "No project detected" when outside a repo

---

## Work Hierarchy

### Decision: Flat Parent-Child (No Enforced Levels)

**Choice**: Simple parent-child relationships with no enforced hierarchy.

**Rationale**:
- Traditional epic→feature→story→task is **rigid**
- AI decomposition is **fluid**: sometimes 2 levels, sometimes 5
- Real work doesn't fit neat categories
- Reorganization needs to be trivial

**Rejected**: Type-based hierarchy (epic/feature/story/task) with enforcement.

**Why rejected**: Forces premature categorization, makes reorganization complex, doesn't match how AI agents naturally break down work.

### Decision: No Auto-Close Parents

**Choice**: Parents require explicit `trc close` action.

**Rationale**:
- Parent issues represent different things:
  - Containers for related work
  - Blocked work waiting on children
  - Meta-issues that need review after children done
- Auto-closing assumes parent = container only
- Explicit close gives user control

**Implementation**: `trc close <parent-id>` validates all children are closed, but doesn't auto-close when last child closes.

---

## Features Removed

### Decision: Remove `--size` Field

**Choice**: No size field (small/medium/large/epic) in Phase 1.

**Rationale**:
- Not useful for AI agents (doesn't inform decisions)
- Adds complexity (validation, filtering, docs)
- YAGNI: Add later if proven necessary

**What was removed**:
- `--size` flag in `trc create`
- `--size` flag in `trc update`
- `--size` filter in `trc list`
- Size validation logic
- Size field in database schema

**Can be added later if**: Users demonstrate clear value for planning/estimation.

### Decision: No Performance Validation

**Choice**: No upfront performance benchmarking or validation tests.

**Rationale**:
- Premature optimization
- Don't know real-world usage patterns yet
- Cross that bridge when it becomes an issue
- Keeps implementation simple

**What was removed**:
- Performance testing framework
- Benchmark suite
- Performance targets (previously: <50ms create, <100ms list)

**Still maintained**: Fast implementation (subprocess <100ms is acceptable, no heavy operations).

---

## Error Handling

### Decision: Manual Merge Conflict Resolution

**Choice**: Treat JSONL merge conflicts exactly like code conflicts - user resolves manually.

**Rationale**:
- Merge conflicts are rare (low collision probability with hash IDs)
- When they occur, they represent genuine coordination issues
- Automation can't determine correct resolution
- Users already know how to resolve git conflicts

**Example scenario**:
```jsonl
<<<<<<< HEAD
{"id":"myapp-abc123","status":"closed",...}
=======
{"id":"myapp-abc123","status":"in_progress",...}
>>>>>>> feature-branch
```

**User action**: Resolve like code, commit merged version.

**No `trc resolve` command**: Would add complexity for rare case, wouldn't know correct resolution anyway.

### Decision: Warn and Continue for Malformed Data

**Choice**: Skip malformed JSONL lines with warnings, don't crash.

**Rationale**:
- Partial recovery better than total failure
- User can investigate and fix specific issues
- Preserves valid data even when some is corrupted

**Implementation**:
```python
stats = {"created": 0, "errors": []}
for line_num, line in enumerate(jsonl_file):
    try:
        issue = json.loads(line)
        # ... process
    except JSONDecodeError as e:
        stats["errors"].append(f"Line {line_num}: {e}")
        continue  # Keep going
```

### Decision: Rebuild DB from JSONL for Corruption

**Choice**: If central DB corrupted, rebuild from available JSONL files.

**Rationale**:
- JSONL is source of truth
- New users rebuild anyway (clone repo → JSONL present → DB auto-builds)
- Cross-project metadata may be lost, but that's acceptable
- Simple recovery: `trc sync --force-import` per project

**What's lost**: Cross-project dependencies not in any single JSONL file.

**Accepted because**: Rare scenario, partial recovery better than none.

---

## Git Workflow

### Decision: User-Managed Commits (No Auto-Commit)

**Choice**: Trace never auto-commits JSONL files. Users commit manually or via their own hooks.

**Rationale**:
- Don't make git decisions for users
- Users have different commit philosophies (granular vs. bundled)
- Hooks/automation varies by team
- Simple: trace writes JSONL, user commits when ready

**Rejected**: `trc commit` command or auto-commit on operations.

**Why rejected**: Too opinionated, makes assumptions about user's git workflow.

**Recommended workflow**:
```bash
# After work session
$ trc list  # Verify state
$ git add .trace/issues.jsonl
$ git commit -m "Update issue tracking"
```

---

## Default Behaviors

### Decision: `trc list` Shows Flat, Ordered List

**Choice**: Default list view is flat (no hierarchy), ordered by priority/status/created_at.

**Rationale**:
- **YAGNI**: Start simple, add hierarchy views only if needed
- Flat list is easy to scan
- Order matters more than nesting for "what to work on next"
- `trc tree <id>` exists for hierarchical views

**Ordering**:
1. Priority (0-4, ascending - P0 first)
2. Status (open, in_progress, blocked, closed)
3. Created date (oldest first)

**Context-aware**:
- In project: show that project's issues
- Outside project: show default project issues
- `--all` flag for cross-project view

### Decision: Configuration in `~/.trace/`

**Choice**: Configuration lives in `~/.trace/config.yaml` (or similar).

**Contents**:
- Project registry (name → path mapping)
- Last sync timestamps per project
- Minimal - no feature flags or complex settings

**Rationale**:
- Central location makes sense for cross-project tool
- User-level config (not system-level)
- Keep it minimal - avoid configuration complexity

---

## Summary of Key Trade-offs

| Decision | Trade-off Accepted | Why Acceptable |
|----------|-------------------|----------------|
| Path-based project IDs | Moving directory breaks link | Rare operation, manual fix OK |
| JSONL as source of truth | Cross-project metadata may be lost if DB corrupted | Can rebuild, rare scenario |
| Manual merge conflicts | User must resolve conflicts | Rare, user knows context |
| No auto-close parents | Extra manual step | Gives user control, parents mean different things |
| No size field | Can't estimate/plan by size | YAGNI, can add later |
| No performance validation | May have performance issues | Cross that bridge when necessary |
| User-managed git | User must remember to commit | Respects user's workflow |

---

## Decision-Making Principles Applied

1. **Simple over flexible**: Fixed decisions rather than configuration options
2. **YAGNI** (You Aren't Gonna Need It): Defer features until proven necessary
3. **Respect user's workflow**: Don't make assumptions (git, categorization)
4. **Fail clearly**: Better to error with clear message than corrupt data
5. **Optimize for reorganization**: Structure should be fluid, not rigid

---

## Open Questions (Future Decisions)

These were discussed but deferred:

1. **Auto-close parent when last child closes?**
   - Decided: No (explicit close only)
   - Could revisit: Add `--auto-close-children` config flag

2. **Schema migrations?**
   - Not needed for Phase 1
   - Will need strategy for Phase 2+

3. **Team collaboration features?**
   - Out of scope for personal project focus
   - Could be Phase 4+

4. **MCP server priority vs. other Phase 2 features?**
   - TBD based on Phase 1 usage

---

## Document Changelog

- **2025-01-16**: Initial decisions documented from design conversations
  - Storage architecture
  - Project model (default vs. personal)
  - Size field removal
  - Performance validation removal
  - Error handling strategy
  - Git workflow approach
