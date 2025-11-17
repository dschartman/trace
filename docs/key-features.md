# Trace Key Features

## Core Features (Phase 1)

### 1. Cross-Project Tracking

**Problem**: Most issue trackers are repo-specific and can't track work across multiple projects.

**Solution**: Trace maintains a central database of all issues across all your projects while keeping per-project JSONL files for git-friendly storage.

```bash
# View all work across all projects
$ trace list --all

# View ready work by project
$ trace ready --all --by-project

# Create cross-project dependencies
$ trace create "Use new API" --project myapp --depends-on mylib-abc123
```

**Implementation**:
- Central SQLite database at `~/.trace/trace.db`
- Per-project JSONL files at `<project>/.trace/issues.jsonl`
- Project registry maps project names to paths
- Automatic sync between central DB and project JSONL files

---

### 2. Flexible Parent-Child Hierarchies

**Problem**: Rigid type systems (epic/feature/story/task) don't match how work naturally decomposes.

**Solution**: Flat structure with parent-child relationships. No enforced levels - structure emerges naturally.

```bash
# Create parent
$ trace create "Add authentication"
→ myapp-abc123

# Add children
$ trace create "Research libraries" --parent myapp-abc123
$ trace create "Implement OAuth" --parent myapp-abc123

# Children can have children (arbitrary depth)
$ trace create "Google OAuth" --parent myapp-def456

# View tree structure
$ trace tree myapp-abc123
myapp-abc123 Add authentication
├─ myapp-def456 Research libraries
└─ myapp-ghi789 Implement OAuth
   └─ myapp-jkl012 Google OAuth
```

**Implementation**:
- `dependencies` table with `type='parent'`
- Recursive queries for tree traversal
- No type field - structure is implicit

---

### 3. Project Auto-Detection

**Problem**: Manually specifying project for every command is tedious.

**Solution**: Trace auto-detects project from current directory's git repository.

```bash
# In a project directory
$ cd ~/Repos/myapp
$ trace create "Fix bug"
# → Automatically tagged as project: myapp

# Outside a project
$ cd ~
$ trace create "Personal task"
# → Goes to 'default' project (discovery inbox)

# Override detection
$ trace create "Something else" --project other-project
```

**Implementation**:
- Walk up directory tree to find `.git`
- Extract project name from git remote or directory name
- Use absolute path as unique project ID
- Cache project detection for performance
- `projects` table stores name → path mapping

---

### 4. Default Project (Discovery Inbox)

**Problem**: AI agents discover work before formal projects exist.

**Solution**: Special "default" project serves as staging area for pre-project work.

```bash
# First use (anywhere)
$ trace create "Explore distributed caching"
? Initialize trace? (Y/n) y
Created default-abc123 in default project

# Later, create real project
$ mkdir ~/Repos/distcache && cd ~/Repos/distcache
$ trace init
Initialized project: distcache

# Move work from default to real project
$ trace move default-abc123 --to-project distcache
Moved default-abc123 → distcache-abc123
```

**Implementation**:
- Default project lives at `~/.trace/default/`
- Auto-created on first use outside a git repo
- Standard project (has JSONL file, can be queried)
- `trace move` command promotes issues to real projects

---

### 5. Git-Friendly JSONL Storage

**Problem**: Binary or complex formats don't merge cleanly in git.

**Solution**: One JSON object per line, sorted by ID. Git diffs show actual changes.

```jsonl
{"id":"myapp-abc123","project_id":"/Users/don/Repos/myapp","title":"Add auth",...}
{"id":"myapp-def456","project_id":"/Users/don/Repos/myapp","title":"Fix bug",...}
```

**Git diff**:
```diff
+ {"id":"myapp-ghi789","project_id":"/Users/don/Repos/myapp","title":"New feature",...}
- {"id":"myapp-def456","project_id":"/Users/don/Repos/myapp","title":"Fix bug","status":"open",...}
+ {"id":"myapp-def456","project_id":"/Users/don/Repos/myapp","title":"Fix bug","status":"closed",...}
```

**Implementation**:
- Export to `.trace/issues.jsonl` after every change
- Atomic write (temp file + rename)
- Sorted by ID for stable diffs
- Import on startup if JSONL is newer than DB
- Dependencies stored inline in issue object

---

### 6. Hash-Based Collision-Resistant IDs

**Problem**: Sequential IDs cause merge conflicts. UUIDs are too long.

**Solution**: 6-character hash IDs with collision detection.

```bash
$ trace create "Add tests"
→ myapp-7k3m2x  # Short, readable, unique
```

**Implementation**:
```python
def generate_id(title: str, project: str) -> str:
    # High-entropy sources
    data = f"{title}:{time.time_ns()}:{random.random()}"
    hash_digest = hashlib.shake_256(data.encode()).hexdigest(3)
    id = base_convert(hash_digest, 36)[:6]

    # Collision detection (retry if exists)
    while db.execute("SELECT 1 FROM issues WHERE id = ?",
                     (f"{project}-{id}",)).fetchone():
        # Regenerate

    return f"{project}-{id}"
```

- 36^6 = 2.1 billion possible IDs
- Collision probability ~1% at 5000 issues per project
- Retry logic ensures uniqueness
- Short enough to type/remember

---

### 7. Dependency Tracking

**Problem**: Work often depends on other work, including across projects.

**Solution**: Three dependency types: blocks, parent-child, related.

```bash
# Blocking dependencies
$ trace create "Deploy to prod" --depends-on myapp-abc123
→ Blocked until myapp-abc123 is closed

# Parent-child (hierarchical)
$ trace create "Subtask" --parent myapp-abc123

# Related (informational)
$ trace relate myapp-abc123 myapp-def456
```

**Ready work** = no open blocking dependencies:
```bash
$ trace ready
myapp-abc123 [P1] Fix auth bug        ✓ ready
myapp-def456 [P0] Deploy to prod      ⏸ blocked by myapp-abc123
```

**Implementation**:
- `dependencies` table with type field
- Recursive queries for transitive dependencies
- Cross-project dependencies supported
- Parent issues can't be closed until children closed

---

### 8. Status Propagation

**Problem**: Parent issues should reflect child status.

**Solution**: Parent issues automatically track child completion.

```bash
$ trace tree myapp-abc123
myapp-abc123 Add authentication [open] (2/4 complete)
├─ myapp-def456 Research libraries [closed]
├─ myapp-ghi789 Design schema [closed]
├─ myapp-jkl012 Implement OAuth [in_progress]
└─ myapp-mno345 Add tests [open]

# Can't close parent until children done
$ trace close myapp-abc123
Error: Cannot close issue with open children:
  - myapp-jkl012 [in_progress]
  - myapp-mno345 [open]
```

**Implementation**:
- Query child status before allowing parent close
- Optional: Auto-close parent when last child closes
- `trace tree` shows completion percentage

---

### 9. Easy Reorganization

**Problem**: Work structure changes as understanding evolves.

**Solution**: First-class commands for reorganizing work.

```bash
# Move issue to different project
$ trace move default-abc123 --to-project myapp

# Change parent
$ trace reparent myapp-abc123 --parent myapp-xyz999

# Add/remove dependencies
$ trace update myapp-abc123 --depends-on mylib-def456
$ trace update myapp-abc123 --remove-dependency mylib-def456

# Bulk operations
$ trace reparent myapp-* --parent myapp-parent123
```

**Implementation**:
- Update foreign keys in dependencies table
- Maintain referential integrity
- Cycle detection (can't make child a parent of its ancestor)
- Move command updates project_id and triggers re-export

---

### 10. Priority-Based Ordering

**Problem**: Need to know what to work on next.

**Solution**: Simple 0-4 priority system with ready work querying.

```bash
# Create with priority
$ trace create "Critical bug" --priority 0

# Update priority
$ trace update myapp-abc123 --priority 1

# View by priority
$ trace list --priority 0

# Ready work (sorted by priority)
$ trace ready
myapp-abc123 [P0] Critical security fix
myapp-def456 [P1] New feature
myapp-ghi789 [P2] Code cleanup
```

**Priority levels**:
- 0: Critical/Blocking
- 1: High priority
- 2: Normal (default)
- 3: Low priority
- 4: Someday/Maybe

**Implementation**:
- Integer field, default 2
- ORDER BY priority, created_at in queries
- No enforcement (priorities are hints)

---

## Additional Features

### 11. Rich Descriptions

Issues support multi-line descriptions for context:

```bash
$ trace create "Add caching" --description "$(cat <<EOF
Need to add Redis caching to improve API response times.

Requirements:
- Cache GET requests for 5 minutes
- Invalidate on POST/PUT/DELETE
- Add cache headers

See: https://docs.redis.io/caching
EOF
)"
```

---

## Phase 2 Features (Future)

### 12. MCP Server Integration

Expose trace as MCP server for Claude Code:

```javascript
// Claude Desktop config
{
  "mcpServers": {
    "trace": {
      "command": "trace",
      "args": ["mcp"]
    }
  }
}
```

**Tools exposed**:
- `trace_create`
- `trace_list`
- `trace_update`
- `trace_tree`

### 13. Bulk Operations

```bash
# Create multiple issues from file
$ trace import issues.md

# Bulk updates
$ trace update "myapp-*" --label "refactoring"

# Template-based creation
$ trace template feature "Add notifications"
→ Creates parent + standard children
```

### 14. Time Tracking

```bash
$ trace start myapp-abc123  # Start timer
$ trace stop               # Stop and log time
$ trace time myapp-abc123  # Show time spent
```

### 15. Advanced Queries

```bash
# Complex filters
$ trace list --status open --priority 0,1 --assigned-to me

# Date ranges
$ trace list --created-after 2025-01-01

# Full-text search
$ trace search "authentication bug"

# JSON output for scripting
$ trace list --json | jq '.[] | select(.priority == 0)'
```

---

## Technical Implementation

### Dual Storage Architecture

```
SQLite (Fast queries)          JSONL (Git-friendly)
        ↓                              ↓
  ~/.trace/trace.db          .trace/issues.jsonl
        ↓                              ↓
   [Lazy sync on every operation]
        ↓                              ↓
  Source of truth           Transportable via git
```

### Sync Strategy

1. **On every command**:
   - Lock central DB
   - Check if project JSONL is newer than last sync
   - If newer: import JSONL → DB (e.g., after git pull)
   - Run command (modify DB)
   - Export DB → JSONL (atomic write)
   - Unlock

2. **Conflict resolution**: Git handles JSONL merges. If conflicts occur, DB is rebuilt from merged JSONL.

### File Locking

```python
import fcntl

with open("~/.trace/.lock", 'w') as f:
    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
    # Atomic operation
    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
```

### Error Handling and Recovery

**Philosophy**: JSONL files are the distributed source of truth. Central DB is an aggregation.

**Error Scenarios**:

1. **Corrupted SQLite Database**
   - Rebuild from available JSONL files
   - Accept loss of cross-project metadata (new users rebuild anyway)
   - User runs `trace sync --force-import` per project

2. **Malformed JSONL Lines**
   - Skip bad lines with warnings
   - Report line numbers and errors to user
   - User investigates and manually fixes or removes bad entries
   - Continue processing valid lines

3. **Missing JSONL File**
   - If DB has data: export creates JSONL
   - If DB empty: create empty JSONL on init

4. **Project Directory Moved/Renamed**
   - Requires manual re-registration
   - Only "default" project is auto-registered
   - User must run `trace init` in new location or manually update project registry

5. **Merge Conflicts in JSONL**
   - Treat like code conflicts
   - User resolves manually via git
   - No automation - quality issues are user responsibility

**No Automation For**:
- Git merge conflicts
- Corrupted/inconsistent data resolution
- Project migration between paths

---

## Design Constraints

1. **Single file implementation**: ~500-600 lines of Python
2. **No external services**: SQLite + filesystem only
3. **No configuration**: Sensible defaults, minimal options
4. **No plugins**: Core features only, keep it simple
5. **No web UI**: CLI-first, others can build on top

---

## AI Integration Requirements

For Claude Code and other AI agents:

1. **Predictable CLI**: Consistent argument patterns
2. **Machine-readable output**: JSON format available
3. **Idempotent operations**: Safe to retry
4. **Helpful errors**: Clear messages when operations fail
5. **Bulk-friendly**: Easy to create/update many issues
6. **Context-rich**: Show related issues, dependencies in output

---

## Non-Features (Explicitly Out of Scope)

1. ❌ User accounts / permissions
2. ❌ Comments / discussion threads
3. ❌ Attachments / file uploads
4. ❌ Email notifications
5. ❌ Web interface
6. ❌ Team collaboration features
7. ❌ Integration with external services (GitHub, Jira, etc.)
8. ❌ Custom fields / schemas
9. ❌ Workflows / state machines
10. ❌ Reporting / analytics

These may be added later, but are not part of the minimal vision.
