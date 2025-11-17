# Minimal Distributed Issue Tracker Design
## A Python Implementation of Beads' Core Patterns

**Version**: 1.0
**Date**: 2025-01-15
**Purpose**: Design document for evaluating a simplified, Python-based implementation of Beads' architectural patterns

---

## Table of Contents

1. [Core Concepts](#core-concepts)
2. [Architecture Overview](#architecture-overview)
3. [Data Model Design](#data-model-design)
4. [Implementation Patterns](#implementation-patterns)
5. [CLI Interface Design](#cli-interface-design)
6. [Project Management Features](#project-management-features)
7. [Implementation Roadmap](#implementation-roadmap)
8. [Evaluation Criteria](#evaluation-criteria)

---

## 1. Core Concepts

### 1.1 The Fundamental Problem

**Challenge**: AI agents need persistent, structured memory for tasks that:
- Span multiple sessions
- Discover new work during execution
- Track dependencies between items
- Sync across machines via git
- Query efficiently for "what's next?"

**Traditional solutions** (markdown todos, GitHub issues, Jira):
- ❌ Break agent flow (context switching)
- ❌ Don't travel with the repository
- ❌ Poor dependency tracking
- ❌ Not optimized for programmatic access

### 1.2 The Core Insight

**Beads' Innovation**: Combine two storage layers for different purposes

```
┌─────────────────────────────────┐
│   SQLite (local, fast)          │  ← Complex queries
│   - Indexes for performance     │  ← Dependency graphs
│   - Recursive CTEs              │  ← "Ready work" detection
│   - Gitignored                  │
└────────────┬────────────────────┘
             │
             │ Auto-sync
             ↓
┌─────────────────────────────────┐
│   JSONL (git-friendly)          │  ← Human-readable
│   - Line-per-record             │  ← Git diffs work
│   - Committed to repo           │  ← Distributed sync
└─────────────────────────────────┘
```

**Why this works**:
- SQLite handles complex queries (DAG traversal, filtering, sorting)
- JSONL provides git-friendly storage (diffs, merge, human inspection)
- Each leverages its strengths, no compromises

### 1.3 Key Design Patterns

#### Pattern 1: Dual Storage with Lazy Sync

**Principle**: Keep both stores in sync, but lazily

```python
# Write path (optimistic)
def create_issue(db, issue):
    db.execute("INSERT INTO issues VALUES (...)")
    mark_dirty(issue.id)
    schedule_export()  # Debounced, runs later

# Read path (defensive)
def list_issues(db):
    if jsonl_is_newer():
        import_from_jsonl(db)  # Sync first
    return db.execute("SELECT * FROM issues")
```

**Benefits**:
- Writes are fast (no immediate JSONL write)
- Reads are correct (always sync before query)
- Batching reduces git commits (debounce window)

#### Pattern 2: Content-Addressable IDs

**Principle**: Hash content for collision-free distributed IDs

```python
# Sequential IDs (traditional)
id = "issue-1", "issue-2", "issue-3"  # Collide on concurrent creation

# Hash IDs (Beads pattern)
id = hash(title + timestamp)  # "bd-a1b2c3"
# Different machines → different timestamps → different hashes
```

**Benefits**:
- No coordination needed for ID generation
- Merge conflicts are rare (different IDs)
- Stable IDs (same content → same hash, for deduplication)

#### Pattern 3: DAG-Based Dependency Tracking

**Principle**: Model work as directed acyclic graph

```
Task A ──blocks──> Task B ──blocks──> Task C
  │
  └──blocks──> Task D

Ready work = nodes with no open blockers
```

**Implementation**: Recursive SQL queries (CTEs)

```sql
WITH RECURSIVE blocked AS (
    SELECT issue_id FROM dependencies
    WHERE blocker_status != 'closed'
    UNION
    SELECT child FROM blocked JOIN children ON parent
)
SELECT * FROM issues WHERE id NOT IN blocked
```

**Benefits**:
- "What can I work on now?" is a query, not manual tracking
- Transitive dependencies handled automatically
- DAG prevents circular dependencies

---

## 2. Architecture Overview

### 2.1 System Components

```
┌─────────────────────────────────────────────────────┐
│                  CLI Interface                      │
│  (Python + Click)                                   │
│  bd create | list | update | close | ready          │
└────────────┬────────────────────────────────────────┘
             │
             ↓
┌─────────────────────────────────────────────────────┐
│              Core Logic Layer                       │
│  - ID generation (hash-based)                       │
│  - Validation (schema, dependencies)                │
│  - Sync coordination (import/export)                │
└────────────┬────────────────────────────────────────┘
             │
        ┌────┴────┐
        ↓         ↓
┌──────────┐  ┌──────────────┐
│ SQLite   │  │ JSONL File   │
│ Database │  │ (git-backed) │
│ (local)  │  │ (shared)     │
└──────────┘  └──────────────┘
```

### 2.2 File Structure

```
your-project/
├── .beads/
│   ├── beads.db           # SQLite (gitignored)
│   ├── issues.jsonl       # JSONL (committed)
│   └── config.yaml        # Settings (committed)
├── .gitignore             # Ignores *.db
├── bd.py                  # Single-file CLI (~500 lines)
└── your-actual-code/
```

**Why single-file**:
- Easy to understand (no package structure)
- Easy to customize (just edit one file)
- Easy to distribute (copy one file)

### 2.3 Data Flow

#### Write Flow
```
User: bd create "Fix bug" -p 1
  ↓
1. Generate hash ID: "bd-a1b2c3"
2. Validate: priority in 0-4, title not empty
3. Insert into SQLite: issues table
4. Mark dirty: dirty_issues table
5. Schedule export: 5s debounce timer
  ↓ (after 5 seconds of no activity)
6. Export to JSONL: atomic write (temp + rename)
7. Commit to git: (optional, manual or via hook)
```

#### Read Flow
```
User: bd list --status open
  ↓
1. Check staleness: hash(JSONL) != last_import_hash?
2. If stale: import from JSONL to SQLite
3. Query SQLite: SELECT * FROM issues WHERE status='open'
4. Return results: JSON or human-readable
```

### 2.4 Concurrency Model

**Simple approach** (no daemon, spawn per command):

```python
# Each CLI invocation
1. Open SQLite connection
2. Check for JSONL updates (import if needed)
3. Execute command
4. Mark dirty (if write)
5. Schedule export (background thread)
6. Exit (export continues in background)
```

**Trade-offs**:
- ✅ Simple (no daemon lifecycle)
- ✅ No stale state (always check JSONL)
- ❌ Slower startup (~50-100ms Python import)
- ❌ No shared cache between invocations

**When to add daemon**: If startup latency becomes annoying (>100ms).

---

## 3. Data Model Design

### 3.1 Core Schema

```sql
-- Issues: The primary work items
CREATE TABLE issues (
    id TEXT PRIMARY KEY,              -- Hash-based: "bd-a1b2c3"
    title TEXT NOT NULL,              -- "Fix authentication bug"
    description TEXT DEFAULT '',      -- Detailed description
    status TEXT DEFAULT 'open',       -- open | in_progress | closed | blocked
    priority INTEGER DEFAULT 2,       -- 0 (critical) to 4 (backlog)
    issue_type TEXT DEFAULT 'task',   -- bug | feature | task | epic | chore
    created_at TEXT NOT NULL,         -- ISO8601: "2025-01-15T10:30:00Z"
    updated_at TEXT NOT NULL,         -- ISO8601: "2025-01-15T11:45:00Z"
    closed_at TEXT,                   -- NULL if open, ISO8601 if closed

    CHECK (priority >= 0 AND priority <= 4),
    CHECK (status IN ('open', 'in_progress', 'closed', 'blocked')),
    CHECK (issue_type IN ('bug', 'feature', 'task', 'epic', 'chore'))
);

-- Dependencies: Relationships between issues
CREATE TABLE dependencies (
    issue_id TEXT NOT NULL,           -- The dependent issue
    depends_on_id TEXT NOT NULL,      -- What it depends on
    type TEXT DEFAULT 'blocks',       -- blocks | related | parent-child | discovered-from
    created_at TEXT NOT NULL,

    PRIMARY KEY (issue_id, depends_on_id),
    FOREIGN KEY (issue_id) REFERENCES issues(id) ON DELETE CASCADE,
    FOREIGN KEY (depends_on_id) REFERENCES issues(id) ON DELETE CASCADE,
    CHECK (type IN ('blocks', 'related', 'parent-child', 'discovered-from'))
);

-- Dirty tracking: Which issues need export
CREATE TABLE dirty_issues (
    issue_id TEXT PRIMARY KEY,
    marked_at TEXT NOT NULL,

    FOREIGN KEY (issue_id) REFERENCES issues(id) ON DELETE CASCADE
);

-- Metadata: System state
CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Initial metadata
INSERT INTO metadata VALUES
    ('last_import_hash', ''),
    ('issue_prefix', 'bd'),
    ('schema_version', '1');
```

### 3.2 Indexes for Performance

```sql
-- Fast filtering by status/priority
CREATE INDEX idx_issues_status ON issues(status);
CREATE INDEX idx_issues_priority ON issues(priority);
CREATE INDEX idx_issues_status_priority ON issues(status, priority);

-- Fast timestamp queries
CREATE INDEX idx_issues_created ON issues(created_at);
CREATE INDEX idx_issues_updated ON issues(updated_at);

-- Fast dependency lookups
CREATE INDEX idx_deps_issue ON dependencies(issue_id);
CREATE INDEX idx_deps_depends ON dependencies(depends_on_id);
CREATE INDEX idx_deps_type ON dependencies(type);
```

### 3.3 Views for Common Queries

```sql
-- Ready work: Issues with no open blockers
CREATE VIEW ready_issues AS
WITH RECURSIVE blocked_issues AS (
    -- Find issues directly blocked
    SELECT DISTINCT d.issue_id
    FROM dependencies d
    JOIN issues blocker ON d.depends_on_id = blocker.id
    WHERE d.type = 'blocks'
      AND blocker.status IN ('open', 'in_progress', 'blocked')

    UNION

    -- Find issues transitively blocked via parent-child
    SELECT d.issue_id
    FROM blocked_issues b
    JOIN dependencies d ON d.depends_on_id = b.issue_id
    WHERE d.type = 'parent-child'
)
SELECT i.*
FROM issues i
WHERE i.status = 'open'
  AND i.id NOT IN (SELECT issue_id FROM blocked_issues);

-- Blocked work: Issues waiting on blockers
CREATE VIEW blocked_issues_view AS
SELECT DISTINCT i.*
FROM issues i
JOIN dependencies d ON i.id = d.issue_id
JOIN issues blocker ON d.depends_on_id = blocker.id
WHERE d.type = 'blocks'
  AND blocker.status IN ('open', 'in_progress', 'blocked')
  AND i.status = 'open';
```

### 3.4 JSONL Format

```jsonl
{"id":"bd-a1b2c3","title":"Fix auth bug","description":"Users can't log in","status":"open","priority":1,"issue_type":"bug","created_at":"2025-01-15T10:30:00Z","updated_at":"2025-01-15T10:30:00Z","closed_at":null,"dependencies":[{"depends_on":"bd-xyz789","type":"blocks"}]}
{"id":"bd-def456","title":"Add dark mode","description":"Support dark theme","status":"in_progress","priority":2,"issue_type":"feature","created_at":"2025-01-14T09:00:00Z","updated_at":"2025-01-15T11:00:00Z","closed_at":null,"dependencies":[]}
{"id":"bd-xyz789","title":"Refactor login","description":"Clean up auth code","status":"closed","priority":1,"issue_type":"task","created_at":"2025-01-13T14:00:00Z","updated_at":"2025-01-15T08:30:00Z","closed_at":"2025-01-15T08:30:00Z","dependencies":[]}
```

**Format notes**:
- One JSON object per line (JSONL = JSON Lines)
- Sorted by ID for consistent git diffs
- Dependencies embedded in each issue
- ISO8601 timestamps (timezone-aware)
- Null for optional fields

---

## 4. Implementation Patterns

### 4.1 Hash ID Generation

```python
import hashlib
import time
import secrets

def generate_hash_id(title: str, prefix: str = "bd") -> str:
    """
    Generate collision-resistant hash ID.

    Uses: title + nanosecond timestamp + random bytes
    Format: prefix-XXXXXX (6 base36 characters)
    Namespace: 36^6 = 2.2 billion possible IDs

    Collision probability with 1000 issues: ~0.02%
    """
    # Combine sources of entropy
    entropy = f"{title}{time.time_ns()}{secrets.token_hex(4)}"
    hash_bytes = hashlib.sha256(entropy.encode()).digest()

    # Convert first 8 bytes to integer
    hash_int = int.from_bytes(hash_bytes[:8], 'big')

    # Encode as base36 (0-9, a-z)
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    result = ""
    for _ in range(6):
        result = chars[hash_int % 36] + result
        hash_int //= 36

    return f"{prefix}-{result}"

# Example usage
>>> generate_hash_id("Fix authentication bug")
'bd-7k2m9x'

>>> generate_hash_id("Fix authentication bug")  # Different each time
'bd-p4n8a2'
```

**Design decisions**:
- Fixed 6 characters (simpler than adaptive)
- Base36 (shorter than hex, more readable than base64)
- Nanosecond timestamp (reduces collisions)
- Random bytes (cryptographic randomness)

### 4.2 Export to JSONL (SQLite → File)

```python
import json
from pathlib import Path
import sqlite3

def export_to_jsonl(db: sqlite3.Connection, jsonl_path: Path) -> int:
    """
    Export all issues to JSONL file (atomic write).

    Returns: Number of issues exported
    """
    # Fetch all issues
    issues = []
    for row in db.execute("SELECT * FROM issues ORDER BY id"):
        issue = dict(row)

        # Fetch dependencies for this issue
        deps = db.execute(
            "SELECT depends_on_id, type FROM dependencies WHERE issue_id = ?",
            (issue['id'],)
        ).fetchall()

        issue['dependencies'] = [
            {"depends_on": d['depends_on_id'], "type": d['type']}
            for d in deps
        ]

        issues.append(issue)

    # Atomic write (temp file + rename)
    temp_path = jsonl_path.with_suffix('.tmp')
    with open(temp_path, 'w') as f:
        for issue in issues:
            f.write(json.dumps(issue, separators=(',', ':')) + '\n')

    # Atomic rename (POSIX guarantees atomicity)
    temp_path.replace(jsonl_path)

    # Update metadata with hash
    jsonl_hash = hash_file(jsonl_path)
    db.execute(
        "UPDATE metadata SET value = ? WHERE key = 'last_import_hash'",
        (jsonl_hash,)
    )

    # Clear dirty tracking
    db.execute("DELETE FROM dirty_issues")
    db.commit()

    return len(issues)

def hash_file(path: Path) -> str:
    """SHA256 hash of file contents (for staleness detection)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()
```

**Key features**:
- Atomic write (temp + rename prevents corruption)
- Sorted output (consistent git diffs)
- Hash tracking (staleness detection)
- Clears dirty flags after export

### 4.3 Import from JSONL (File → SQLite)

```python
def import_from_jsonl(db: sqlite3.Connection, jsonl_path: Path) -> dict:
    """
    Import issues from JSONL file.

    Returns: {"created": N, "updated": N, "unchanged": N}
    """
    if not jsonl_path.exists():
        return {"created": 0, "updated": 0, "unchanged": 0}

    # Check if import needed (hash-based staleness)
    current_hash = hash_file(jsonl_path)
    last_hash = db.execute(
        "SELECT value FROM metadata WHERE key = 'last_import_hash'"
    ).fetchone()[0]

    if current_hash == last_hash:
        return {"created": 0, "updated": 0, "unchanged": 0}

    stats = {"created": 0, "updated": 0, "unchanged": 0}

    with open(jsonl_path) as f:
        for line in f:
            issue = json.loads(line)
            dependencies = issue.pop('dependencies', [])

            # Check if issue exists
            existing = db.execute(
                "SELECT * FROM issues WHERE id = ?", (issue['id'],)
            ).fetchone()

            if existing:
                # Update existing
                columns = ', '.join(f"{k} = ?" for k in issue.keys())
                db.execute(
                    f"UPDATE issues SET {columns} WHERE id = ?",
                    list(issue.values()) + [issue['id']]
                )
                stats['updated'] += 1
            else:
                # Create new
                columns = ', '.join(issue.keys())
                placeholders = ', '.join(['?' for _ in issue])
                db.execute(
                    f"INSERT INTO issues ({columns}) VALUES ({placeholders})",
                    list(issue.values())
                )
                stats['created'] += 1

            # Update dependencies (delete + recreate)
            db.execute("DELETE FROM dependencies WHERE issue_id = ?", (issue['id'],))
            for dep in dependencies:
                db.execute(
                    "INSERT INTO dependencies (issue_id, depends_on_id, type, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (issue['id'], dep['depends_on'], dep['type'], issue['created_at'])
                )

    # Update last import hash
    db.execute(
        "UPDATE metadata SET value = ? WHERE key = 'last_import_hash'",
        (current_hash,)
    )
    db.commit()

    return stats
```

**Key features**:
- Hash-based staleness (skip if unchanged)
- Upsert logic (create or update)
- Dependency sync (delete + recreate)
- Transaction safety (atomic commit)

### 4.4 Sync Orchestration

```python
import threading
import time

class Debouncer:
    """Debounce rapid calls to a function."""

    def __init__(self, delay_seconds: float, callback):
        self.delay = delay_seconds
        self.callback = callback
        self.timer = None
        self.lock = threading.Lock()

    def trigger(self):
        """Call this when event happens. Actual callback fires after delay."""
        with self.lock:
            if self.timer:
                self.timer.cancel()
            self.timer = threading.Timer(self.delay, self.callback)
            self.timer.start()

    def flush(self):
        """Force immediate execution, cancel pending."""
        with self.lock:
            if self.timer:
                self.timer.cancel()
            self.callback()

# Global debouncer (5 second window)
export_debouncer = None

def schedule_export(db: sqlite3.Connection, jsonl_path: Path):
    """Schedule JSONL export (debounced)."""
    global export_debouncer

    if export_debouncer is None:
        export_debouncer = Debouncer(
            delay_seconds=5.0,
            callback=lambda: export_to_jsonl(db, jsonl_path)
        )

    export_debouncer.trigger()

def mark_dirty(db: sqlite3.Connection, issue_id: str):
    """Mark issue as needing export."""
    db.execute(
        "INSERT OR IGNORE INTO dirty_issues (issue_id, marked_at) VALUES (?, ?)",
        (issue_id, datetime.now().isoformat())
    )
    db.commit()
```

**Pattern**:
```
User makes changes → mark_dirty() → schedule_export()
                                          ↓ (after 5s)
                                     export_to_jsonl()
                                          ↓
                                     Write JSONL file
```

**Benefits**:
- Batches multiple changes (reduce git commits)
- Non-blocking (happens in background)
- Immediate flush on exit (export_debouncer.flush())

---

## 5. CLI Interface Design

### 5.1 Command Structure

```bash
# Core commands (CRUD)
bd init                                  # Initialize in current dir
bd create <title> [options]             # Create new issue
bd update <id> [options]                 # Update existing issue
bd close <id>                            # Close issue
bd show <id>                             # Show details
bd list [filters]                        # List issues

# Workflow commands
bd ready                                 # Show ready work
bd blocked                               # Show blocked work

# Dependency commands
bd dep add <issue> <depends-on> [type]   # Add dependency
bd dep remove <issue> <depends-on>       # Remove dependency
bd dep tree <issue>                      # Show dependency tree

# Sync commands
bd sync                                  # Force import/export
bd export                                # Export to JSONL
bd import                                # Import from JSONL
```

### 5.2 Implementation with Click

```python
import click
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path.cwd() / '.beads' / 'beads.db'
JSONL_PATH = Path.cwd() / '.beads' / 'issues.jsonl'

@click.group()
def cli():
    """Minimal issue tracker inspired by Beads."""
    pass

@cli.command()
@click.option('--prefix', default='bd', help='Issue ID prefix')
def init(prefix):
    """Initialize issue tracker in current directory."""
    DB_PATH.parent.mkdir(exist_ok=True)

    db = get_db()
    db.executescript(SCHEMA)
    db.execute(
        "UPDATE metadata SET value = ? WHERE key = 'issue_prefix'",
        (prefix,)
    )
    db.commit()

    click.echo(f"Initialized at {DB_PATH.parent}")
    click.echo(f"Issue prefix: {prefix}")

@cli.command()
@click.argument('title')
@click.option('-p', '--priority', default=2, type=int, help='Priority (0-4)')
@click.option('-t', '--type', 'issue_type', default='task',
              type=click.Choice(['bug', 'feature', 'task', 'epic', 'chore']))
@click.option('-d', '--description', default='', help='Description')
@click.option('--deps', help='Dependencies: discovered-from:bd-123')
@click.option('--json', 'json_output', is_flag=True, help='JSON output')
def create(title, priority, issue_type, description, deps, json_output):
    """Create a new issue."""
    db = get_db()

    # Auto-import before write
    import_from_jsonl(db, JSONL_PATH)

    # Generate ID
    prefix = db.execute(
        "SELECT value FROM metadata WHERE key = 'issue_prefix'"
    ).fetchone()[0]
    issue_id = generate_hash_id(title, prefix)

    # Create issue
    now = datetime.now().isoformat()
    db.execute(
        """INSERT INTO issues
           (id, title, description, status, priority, issue_type, created_at, updated_at)
           VALUES (?, ?, ?, 'open', ?, ?, ?, ?)""",
        (issue_id, title, description, priority, issue_type, now, now)
    )

    # Add dependencies if specified
    if deps:
        dep_type, parent_id = deps.split(':')
        db.execute(
            "INSERT INTO dependencies (issue_id, depends_on_id, type, created_at) "
            "VALUES (?, ?, ?, ?)",
            (issue_id, parent_id, dep_type, now)
        )

    db.commit()
    mark_dirty(db, issue_id)
    schedule_export(db, JSONL_PATH)

    if json_output:
        click.echo(json.dumps({"id": issue_id, "title": title}))
    else:
        click.echo(f"Created {issue_id}: {title}")

@cli.command()
@click.option('--status', type=click.Choice(['open', 'in_progress', 'closed', 'blocked']))
@click.option('--priority', type=int)
@click.option('--type', 'issue_type',
              type=click.Choice(['bug', 'feature', 'task', 'epic', 'chore']))
@click.option('--json', 'json_output', is_flag=True)
def list(status, priority, issue_type, json_output):
    """List issues with optional filters."""
    db = get_db()
    import_from_jsonl(db, JSONL_PATH)

    query = "SELECT * FROM issues WHERE 1=1"
    params = []

    if status:
        query += " AND status = ?"
        params.append(status)
    if priority is not None:
        query += " AND priority = ?"
        params.append(priority)
    if issue_type:
        query += " AND issue_type = ?"
        params.append(issue_type)

    query += " ORDER BY priority, created_at"

    issues = db.execute(query, params).fetchall()

    if json_output:
        click.echo(json.dumps([dict(row) for row in issues], indent=2))
    else:
        for issue in issues:
            status_color = {
                'open': 'white',
                'in_progress': 'yellow',
                'closed': 'green',
                'blocked': 'red'
            }[issue['status']]

            click.secho(
                f"{issue['id']} ",
                fg='cyan', nl=False
            )
            click.secho(
                f"[{issue['status']}] ",
                fg=status_color, nl=False
            )
            click.secho(
                f"[P{issue['priority']}] ",
                fg='magenta', nl=False
            )
            click.echo(issue['title'])

@cli.command()
@click.option('--json', 'json_output', is_flag=True)
def ready(json_output):
    """Show issues ready to work on (no blockers)."""
    db = get_db()
    import_from_jsonl(db, JSONL_PATH)

    issues = db.execute("SELECT * FROM ready_issues ORDER BY priority, created_at").fetchall()

    if json_output:
        click.echo(json.dumps([dict(row) for row in issues], indent=2))
    else:
        if not issues:
            click.echo("No ready work found.")
        else:
            click.echo(f"Found {len(issues)} ready issues:\n")
            for issue in issues:
                click.secho(f"{issue['id']} ", fg='cyan', nl=False)
                click.secho(f"[P{issue['priority']}] ", fg='magenta', nl=False)
                click.echo(issue['title'])

@cli.command()
@click.argument('issue_id')
@click.option('--status', type=click.Choice(['open', 'in_progress', 'closed', 'blocked']))
@click.option('--priority', type=int)
@click.option('--json', 'json_output', is_flag=True)
def update(issue_id, status, priority, json_output):
    """Update an issue."""
    db = get_db()
    import_from_jsonl(db, JSONL_PATH)

    updates = []
    params = []

    if status:
        updates.append("status = ?")
        params.append(status)
        if status == 'closed':
            updates.append("closed_at = ?")
            params.append(datetime.now().isoformat())

    if priority is not None:
        updates.append("priority = ?")
        params.append(priority)

    if not updates:
        click.echo("No updates specified")
        return

    updates.append("updated_at = ?")
    params.append(datetime.now().isoformat())
    params.append(issue_id)

    db.execute(
        f"UPDATE issues SET {', '.join(updates)} WHERE id = ?",
        params
    )
    db.commit()
    mark_dirty(db, issue_id)
    schedule_export(db, JSONL_PATH)

    if json_output:
        click.echo(json.dumps({"id": issue_id, "updated": True}))
    else:
        click.echo(f"Updated {issue_id}")

if __name__ == '__main__':
    cli()
```

### 5.3 JSON Output Format

All commands support `--json` flag for programmatic use:

```bash
# Human-readable
$ bd list --status open
bd-a1b2c3 [open] [P1] Fix authentication bug
bd-def456 [in_progress] [P2] Add dark mode

# JSON (for AI agents)
$ bd list --status open --json
[
  {
    "id": "bd-a1b2c3",
    "title": "Fix authentication bug",
    "description": "Users can't log in with SSO",
    "status": "open",
    "priority": 1,
    "issue_type": "bug",
    "created_at": "2025-01-15T10:30:00Z",
    "updated_at": "2025-01-15T10:30:00Z",
    "closed_at": null
  },
  {
    "id": "bd-def456",
    "title": "Add dark mode",
    "description": "Support dark theme across app",
    "status": "in_progress",
    "priority": 2,
    "issue_type": "feature",
    "created_at": "2025-01-14T09:00:00Z",
    "updated_at": "2025-01-15T11:00:00Z",
    "closed_at": null
  }
]
```

---

## 6. Project Management Features

### 6.1 Dependency Types

#### Blocks (Hard Dependency)
```bash
# Task B cannot start until Task A is closed
bd dep add bd-taskB bd-taskA --type blocks

# Real example
bd create "Deploy to production" -p 0
# → bd-deploy

bd create "Fix security vulnerability" -p 0
# → bd-security

bd dep add bd-deploy bd-security --type blocks
# Deploy is blocked until security fix is closed
```

**Query**: `bd ready` excludes bd-deploy until bd-security is closed

#### Discovered-From (Work Trail)
```bash
# Working on Task A, discovered Task B
bd create "Found auth bug during refactor" -p 1 \
  --deps discovered-from:bd-refactor

# Use case: AI agent discovers work
bd update bd-refactor --status in_progress
# ... agent working ...
bd create "Missing validation in login" -p 0 \
  --deps discovered-from:bd-refactor
```

**Benefit**: Maintains context trail, shows where work came from

#### Parent-Child (Hierarchy)
```bash
# Epic with subtasks
bd create "Redesign homepage" -t epic -p 1
# → bd-epic123

bd create "Update hero section" -p 1
bd dep add bd-hero bd-epic123 --type parent-child

bd create "Add testimonials" -p 1
bd dep add bd-testimonials bd-epic123 --type parent-child
```

**Benefit**: Group related work, track epic progress

#### Related (Soft Link)
```bash
# Similar bugs that might share root cause
bd dep add bd-bug1 bd-bug2 --type related
```

**Benefit**: Cross-reference, doesn't affect ready work

### 6.2 Ready Work Detection

**Algorithm**:
```sql
-- Implemented as a VIEW (ready_issues)
WITH RECURSIVE blocked AS (
    -- Find directly blocked issues
    SELECT d.issue_id
    FROM dependencies d
    JOIN issues blocker ON d.depends_on_id = blocker.id
    WHERE d.type = 'blocks'
      AND blocker.status != 'closed'

    UNION

    -- Find transitively blocked via parent-child
    SELECT d.issue_id
    FROM blocked b
    JOIN dependencies d ON d.depends_on_id = b.issue_id
    WHERE d.type = 'parent-child'
)
SELECT * FROM issues
WHERE status = 'open'
  AND id NOT IN (SELECT issue_id FROM blocked)
ORDER BY priority, created_at;
```

**Example scenario**:
```
A (open) ──blocks──> B (open) ──blocks──> C (open)
                          │
                          └──parent-child──> D (open)

Ready work: [A]  (B blocked by A, C blocked by B, D blocked by B via parent)
After closing A:
Ready work: [B]  (C still blocked by B, D still blocked by B)
After closing B:
Ready work: [C, D]  (both unblocked)
```

### 6.3 Priority System

**Levels**:
```
0 = Critical  (security, data loss, broken builds)
1 = High      (major features, important bugs)
2 = Medium    (nice-to-have features, minor bugs) [DEFAULT]
3 = Low       (polish, optimization)
4 = Backlog   (future ideas, maybe-never)
```

**Sorting**: Ready work sorted by priority first, then age (FIFO within priority)

```bash
# High priority bugs
bd create "SQL injection vulnerability" -p 0 -t bug

# Normal features
bd create "Add export to CSV" -p 2 -t feature

# Future ideas
bd create "Consider GraphQL API" -p 4 -t task
```

### 6.4 Status Workflow

```
open ──────> in_progress ──────> closed
  ↑              │                  ↑
  │              ↓                  │
  └────────── blocked ──────────────┘
```

**Transitions**:
```bash
# Start work
bd update bd-123 --status in_progress

# Block on external dependency
bd update bd-123 --status blocked

# Unblock
bd update bd-123 --status open

# Complete
bd close bd-123
# (Automatically sets status=closed, closed_at=now)
```

### 6.5 Issue Types

```
bug      → Something broken that needs fixing
feature  → New functionality to build
task     → Work item (tests, docs, refactoring)
epic     → Large feature with multiple subtasks
chore    → Maintenance (dependencies, tooling, cleanup)
```

**Usage**:
```bash
bd create "Users can't log in" -t bug -p 0
bd create "Add OAuth support" -t feature -p 1
bd create "Write integration tests" -t task -p 2
bd create "Redesign dashboard" -t epic -p 1
bd create "Update to Python 3.12" -t chore -p 3
```

---

## 7. Implementation Roadmap

### Phase 1: Core (Week 1)

**Goal**: Basic CRUD + JSONL sync

**Deliverables**:
- [ ] Schema creation (SQLite tables)
- [ ] Hash ID generation
- [ ] Commands: init, create, list, show, close
- [ ] Export to JSONL (basic, no debounce)
- [ ] Import from JSONL (basic, no hash check)

**Code estimate**: ~300 lines

**Test**:
```bash
bd init
bd create "Test issue" -p 1
cat .beads/issues.jsonl  # Should contain issue
git add .beads/issues.jsonl
git commit -m "Add test issue"
git push

# On another machine
git pull
bd list  # Should show test issue
```

### Phase 2: Dependencies (Week 2)

**Goal**: Add dependency tracking + ready work

**Deliverables**:
- [ ] Dependency table + queries
- [ ] Commands: dep add, dep remove
- [ ] Ready work view (recursive CTE)
- [ ] Command: ready
- [ ] Dependency types: blocks, discovered-from

**Code estimate**: +150 lines

**Test**:
```bash
bd create "Task A" -p 1
bd create "Task B" -p 1
bd dep add bd-B bd-A --type blocks

bd ready  # Should show only Task A
bd close bd-A
bd ready  # Should show Task B
```

### Phase 3: Polish (Week 3)

**Goal**: Production-ready features

**Deliverables**:
- [ ] Debounced export (5s window)
- [ ] Hash-based staleness detection
- [ ] JSON output flags (--json on all commands)
- [ ] Colored terminal output
- [ ] Error handling (validation, helpful messages)
- [ ] Update command (change priority, status, etc.)

**Code estimate**: +100 lines

**Test**:
```bash
# Rapid changes should batch
bd create "Issue 1"
bd create "Issue 2"
bd create "Issue 3"
# Wait 5s, then check git - should be 1 commit (not 3)

# JSON output for automation
bd ready --json | jq '.[0].id'
```

### Phase 4: Advanced (Optional)

**Deliverables**:
- [ ] Labels/tags system
- [ ] Full-text search
- [ ] Comments on issues
- [ ] Dependency visualization (tree command)
- [ ] Merge conflict resolution helper
- [ ] MCP server integration (FastMCP)

**Code estimate**: +200 lines each

---

## 8. Evaluation Criteria

### 8.1 Does This Solve Your Problem?

**Questions to answer**:

1. **Planning workflow**: Can you quickly create issues during planning?
   - ✅ `bd create "Task title" -p 1` (one command)
   - ✅ Batch create from file (future feature)

2. **Discovery workflow**: Can AI agents file discovered work?
   - ✅ `bd create "Found bug" --deps discovered-from:bd-parent`
   - ✅ JSON output for programmatic use

3. **Context switching**: Does it keep you in flow?
   - ✅ No web UI required
   - ✅ No external service
   - ✅ Lives in repo

4. **Querying**: Can you find "what's next?"
   - ✅ `bd ready` shows unblocked work
   - ✅ Sorted by priority
   - ✅ Fast (SQLite query)

5. **Sync**: Does it work across machines?
   - ✅ Git-based (familiar workflow)
   - ✅ Auto-import before reads
   - ✅ Auto-export after writes

### 8.2 Complexity Assessment

**Lines of code**:
- Core: ~300 lines
- Dependencies: ~150 lines
- Polish: ~100 lines
- **Total: ~550 lines**

**Compare to**:
- Beads (Go): ~40,000 lines
- Ratio: **72x simpler**

**Cognitive load**:
- Single file (no package structure)
- Python (familiar to most)
- SQLite (standard library)
- Click (simple CLI framework)

**Verdict**: ✅ Understandable in 1-2 hours

### 8.3 Performance Assessment

**Expected latency** (on modest hardware):

| Operation | Time | Notes |
|-----------|------|-------|
| bd create | 80ms | Import (20ms) + Insert (5ms) + Export (50ms) |
| bd list | 30ms | Import (20ms) + Query (5ms) + Format (5ms) |
| bd ready | 40ms | Import (20ms) + Recursive query (15ms) + Format (5ms) |
| bd update | 80ms | Same as create |

**Comparison to Beads**:
- Beads (daemon): 10ms
- This (subprocess): 80ms
- **8x slower**, but still feels instant (<100ms threshold)

**At what scale does this break?**
- 1,000 issues: ~200ms (import becomes slow)
- 10,000 issues: ~2s (unacceptable)

**When to optimize**:
- If you have >1,000 issues: Add daemon mode
- If you have >10,000 issues: Use Beads (optimized for scale)

### 8.4 Feature Completeness

**What you get** (compared to Beads):

| Feature | This Design | Beads |
|---------|-------------|-------|
| CRUD operations | ✅ | ✅ |
| Dependencies | ✅ (4 types) | ✅ (4 types) |
| Ready work detection | ✅ | ✅ |
| Git sync | ✅ (manual) | ✅ (auto) |
| JSON output | ✅ | ✅ |
| Priority/status | ✅ | ✅ |
| Hash IDs | ✅ (fixed 6) | ✅ (adaptive 4-6) |
| Labels | ❌ (future) | ✅ |
| Comments | ❌ (future) | ✅ |
| Web UI | ❌ | ✅ |
| Daemon mode | ❌ | ✅ |
| Agent Mail | ❌ | ✅ |
| Multi-platform binaries | ❌ | ✅ |
| MCP integration | ❌ (future) | ✅ |

**Coverage**: ~70% of Beads' features, ~2% of the code

### 8.5 Maintenance Burden

**What you maintain**:
- Single Python file (~550 lines)
- SQLite schema (your choice of changes)
- JSONL format (stable, unlikely to change)

**What you don't maintain**:
- Cross-compilation (Python is cross-platform)
- Daemon lifecycle
- RPC protocol
- Version compatibility
- Distribution channels

**Estimated maintenance**: ~1 hour/month

### 8.6 Extensibility

**Easy to add**:
- New fields (add column, update schema)
- New dependency types (add to CHECK constraint)
- New commands (add @cli.command())
- New views (add SQL view)

**Example - Add labels**:
```sql
-- 1. Add table
CREATE TABLE labels (
    issue_id TEXT,
    label TEXT,
    PRIMARY KEY (issue_id, label),
    FOREIGN KEY (issue_id) REFERENCES issues(id)
);

-- 2. Add to JSONL export
issue['labels'] = db.execute(
    "SELECT label FROM labels WHERE issue_id = ?", (issue['id'],)
).fetchall()

-- 3. Add CLI command
@cli.command()
@click.argument('issue_id')
@click.argument('label')
def label(issue_id, label):
    db.execute("INSERT INTO labels VALUES (?, ?)", (issue_id, label))
```

**Verdict**: ✅ Simple extension model

---

## 9. Decision Framework

### Use This Design If:

- ✅ You want to understand every line of code
- ✅ You value simplicity over features
- ✅ You have <1,000 issues per project
- ✅ You're comfortable with Python
- ✅ You want to customize/extend
- ✅ You enjoy building tools
- ✅ Single agent workflows (not multi-agent coordination)

### Use Beads If:

- ✅ You want a mature, battle-tested tool
- ✅ You need advanced features (labels, comments, web UI)
- ✅ You have >1,000 issues
- ✅ You need multi-agent coordination (Agent Mail)
- ✅ You want community support
- ✅ You prefer maintained tools over building
- ✅ Performance matters (sub-10ms operations)

### Hybrid Approach:

1. **Build this design first** (1-2 weeks)
2. **Use it for real work** (1 month)
3. **Evaluate pain points**:
   - Too slow? → Add daemon mode
   - Missing features? → Add incrementally
   - Works great? → Keep it!
   - Outgrew it? → Migrate to Beads (JSONL is compatible)

---

## 10. Conclusion

This design captures **the essence of Beads** in a minimal, understandable form:

**Core innovation preserved**:
- ✅ Dual storage (SQLite + JSONL)
- ✅ Git-based distribution
- ✅ Hash IDs for collision-free creation
- ✅ DAG-based dependency tracking
- ✅ Ready work detection

**Complexity removed**:
- ❌ No daemon (subprocess is fast enough)
- ❌ No RPC (direct SQLite access)
- ❌ No adaptive hash (fixed 6 chars works)
- ❌ No incremental export (full export is fast for <1K issues)
- ❌ No multi-platform binaries (Python is portable)

**Result**:
- **550 lines** vs **40,000 lines**
- **72x simpler**, **70% of features**
- **1-2 weeks** to build vs **months** to understand Beads

**Recommendation**: Build this, use it, then decide if you need Beads' complexity.

---

**Next Steps**:

1. Save this document
2. Create `bd.py` with Phase 1 features
3. Test basic workflow
4. Evaluate against your actual needs
5. Decide: keep simple, extend incrementally, or adopt Beads

Good luck! 🎯
