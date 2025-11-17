# Trace CLI Design

## Design Principles

1. **AI-First**: Optimized for programmatic use by agents like Claude Code
2. **Consistent Patterns**: Predictable argument structure across commands
3. **Human-Friendly**: Also works well for interactive use
4. **Composable**: Easy to chain with standard Unix tools
5. **Informative Errors**: Clear feedback when things go wrong

---

## Command Structure

### Standard Pattern

```bash
trace <command> [<id>] [options] [arguments]
```

**Examples**:
- `trace create "title" --parent abc123`
- `trace update abc123 --priority 1`
- `trace show abc123`
- `trace list --all`

### Output Formats

**Default**: Human-readable text
```bash
$ trace list
myapp-abc123 [P1] Add authentication
myapp-def456 [P0] Fix security bug
```

**JSON**: Machine-readable (for AI/scripts)
```bash
$ trace list --json
[
  {
    "id": "myapp-abc123",
    "project_id": "/Users/don/Repos/myapp",
    "project": "myapp",
    "title": "Add authentication",
    "status": "open",
    "priority": 1,
    ...
  }
]
```

---

## Core Commands

### `trace init`

Initialize a new project in current directory.

```bash
# Basic usage
$ trace init
Initialized project: myapp (/Users/don/Repos/myapp)
Created .trace/issues.jsonl

# Initialize personal/default project
$ trace init --personal ~/Documents/tasks
Initialized personal project at ~/Documents/tasks

# Options
--personal <path>    Create personal project at specified path
--force             Reinitialize even if already exists
```

---

### `trace create`

Create a new issue.

```bash
# Basic
$ trace create "Fix login bug"
Created myapp-abc123: Fix login bug

# With options
$ trace create "Add OAuth" \
    --priority 1 \
    --parent myapp-xyz999 \
    --depends-on mylib-def456 \
    --project myapp \
    --description "Implement OAuth 2.0 flow"

# From stdin (for longer descriptions)
$ trace create "Complex feature" --description "$(cat <<EOF
This is a complex feature that requires:
1. Database changes
2. API updates
3. Frontend work
EOF
)"

# Options
--priority <0-4>           Priority level (default: 2)
--parent <id>              Parent issue ID
--depends-on <id>          Blocking dependency ID
--project <name>           Override auto-detected project
--description <text>       Detailed description
--status <status>          Initial status (default: open)

# Output
<id>: <title>                    # Default
--json                           # JSON object
--quiet                          # Only print ID
```

---

### `trace list`

List issues with filtering.

```bash
# Current project
$ trace list
myapp-abc123 [P1] [open] Add authentication
myapp-def456 [P0] [in_progress] Fix security bug

# All projects
$ trace list --all

# Filter by project
$ trace list --project mylib

# Filter by status
$ trace list --status open
$ trace list --status closed,in_progress

# Filter by priority
$ trace list --priority 0
$ trace list --priority 0,1

# Combine filters
$ trace list --status open --priority 0,1 --project myapp

# Sort options
$ trace list --sort priority        # By priority (default)
$ trace list --sort created         # By creation date
$ trace list --sort updated         # By last update

# Limit results
$ trace list --limit 10

# Options
--all                        Show all projects
--project <name>             Filter by project
--status <status>[,...]      Filter by status
--priority <N>[,...]         Filter by priority
--parent <id>                Show children of parent
--no-children                Exclude issues with parents (top-level only)
--sort <field>               Sort by field
--limit <N>                  Limit results
--json                       JSON output
```

---

### `trace show`

Show detailed information about an issue.

```bash
$ trace show myapp-abc123

ID:          myapp-abc123
Project:     myapp (/Users/don/Repos/myapp)
Title:       Add authentication system
Status:      in_progress
Priority:    1 (high)
Size:        large
Created:     2025-01-15 10:30:00
Updated:     2025-01-16 14:22:00

Description:
  Implement OAuth 2.0 authentication flow with support
  for Google and GitHub providers.

Dependencies:
  Depends on:
    - mylib-def456 [closed] Add OAuth library support

  Blocks:
    - myapp-ghi789 [open] Add user dashboard

  Children:
    - myapp-jkl012 [closed] Research OAuth libraries
    - myapp-mno345 [in_progress] Implement Google OAuth
    - myapp-pqr678 [open] Implement GitHub OAuth

  Parent:
    - myapp-stu901 [open] User management system

# Options
--json                       JSON output
--with-tree                  Include full tree view
```

---

### `trace update`

Update issue fields.

```bash
# Update priority
$ trace update myapp-abc123 --priority 0

# Update status
$ trace update myapp-abc123 --status in_progress

# Update title
$ trace update myapp-abc123 --title "New title"

# Update description
$ trace update myapp-abc123 --description "New description"

# Add dependency
$ trace update myapp-abc123 --depends-on mylib-def456

# Remove dependency
$ trace update myapp-abc123 --remove-dependency mylib-def456

# Multiple updates at once
$ trace update myapp-abc123 \
    --priority 1 \
    --status in_progress \
    --description "Working on this now"

# Options
--priority <0-4>             Update priority
--status <status>            Update status
--title <text>               Update title
--description <text>         Update description
--depends-on <id>            Add dependency
--remove-dependency <id>     Remove dependency
--json                       JSON output
```

---

### `trace close`

Close an issue (shorthand for `update --status closed`).

```bash
# Close issue
$ trace close myapp-abc123
Closed myapp-abc123

# Close with check for children
$ trace close myapp-abc123
Error: Cannot close issue with open children:
  - myapp-def456 [open] Subtask 1
  - myapp-ghi789 [in_progress] Subtask 2

# Force close (close parent even with open children)
$ trace close myapp-abc123 --force
Warning: Closing parent with open children
Closed myapp-abc123

# Options
--force                      Close even with open children
```

---

## Reorganization Commands

### `trace reparent`

Change an issue's parent.

```bash
# Add parent
$ trace reparent myapp-abc123 --parent myapp-xyz999
Reparented myapp-abc123 → myapp-xyz999

# Remove parent (make top-level)
$ trace reparent myapp-abc123 --no-parent
Removed parent from myapp-abc123

# Move multiple issues
$ trace reparent myapp-abc* --parent myapp-xyz999

# Error handling
$ trace reparent myapp-abc123 --parent myapp-def456
Error: Would create cycle (myapp-def456 is a child of myapp-abc123)

# Options
--parent <id>                New parent ID
--no-parent                  Remove parent (make top-level)
--force                      Skip cycle detection (dangerous!)
```

---

### `trace move`

Move issue to different project.

```bash
# Move single issue
$ trace move default-abc123 --to-project myapp
Moved default-abc123 → myapp-abc123

# Move with children
$ trace move myapp-abc123 --to-project mylib --with-children
Moving myapp-abc123 and 3 children to mylib...
  myapp-abc123 → mylib-abc123
  myapp-def456 → mylib-def456
  myapp-ghi789 → mylib-ghi789
  myapp-jkl012 → mylib-jkl012
Moved 4 issues

# Dependencies across projects are preserved
$ trace move myapp-abc123 --to-project mylib
Warning: myapp-def456 depends on this issue (cross-project dependency)
Moved myapp-abc123 → mylib-abc123

# Options
--to-project <name>          Target project
--with-children              Move children too
--force                      Skip dependency warnings
```

---

### `trace relate`

Add related-to relationship between issues.

```bash
# Add related link
$ trace relate myapp-abc123 myapp-def456
Linked myapp-abc123 ↔ myapp-def456 (related)

# Remove related link
$ trace relate myapp-abc123 myapp-def456 --remove
Removed link between myapp-abc123 and myapp-def456

# Show related issues
$ trace show myapp-abc123
...
Related:
  - myapp-def456 [open] Similar bug in other module
```

---

## Query Commands

### `trace ready`

Show issues ready to work on (no blocking dependencies).

```bash
# Current project
$ trace ready
myapp-abc123 [P0] Fix security bug
myapp-def456 [P1] Add OAuth

# All projects
$ trace ready --all

# Grouped by project
$ trace ready --all --by-project
=== myapp (3 ready) ===
myapp-abc123 [P0] Fix security bug
myapp-def456 [P1] Add OAuth
myapp-ghi789 [P2] Update docs

=== mylib (1 ready) ===
mylib-jkl012 [P1] Add new API

# Limit results
$ trace ready --limit 5

# Options
--all                        All projects
--by-project                 Group by project
--limit <N>                  Limit results
--json                       JSON output
```

---

### `trace tree`

Show hierarchical tree view of issue and children.

```bash
$ trace tree myapp-abc123

myapp-abc123 Add authentication [open] (2/4 closed)
├─ myapp-def456 Research OAuth [closed]
├─ myapp-ghi789 Design database [closed]
├─ myapp-jkl012 Implement OAuth [in_progress]
│  ├─ myapp-mno345 Google provider [open]
│  └─ myapp-pqr678 GitHub provider [open]
└─ myapp-stu901 Add tests [open]

# Show with dependencies
$ trace tree myapp-abc123 --with-dependencies
myapp-abc123 Add authentication [blocked]
  depends on: mylib-xyz999 [open]
├─ myapp-def456 Research OAuth [closed]
...

# Show depth limit
$ trace tree myapp-abc123 --depth 2

# Options
--depth <N>                  Limit tree depth
--with-dependencies          Show blocking dependencies
--json                       JSON output
```

---

### `trace search`

Full-text search across issues.

```bash
# Search titles and descriptions
$ trace search "authentication"
myapp-abc123 [P1] Add authentication system
myapp-def456 [P2] Fix authentication bug

# Search in specific project
$ trace search "bug" --project myapp

# Search with filters
$ trace search "oauth" --status open --priority 0,1

# Options
--project <name>             Limit to project
--status <status>            Filter by status
--priority <N>               Filter by priority
--all                        Search all projects (default)
--json                       JSON output
```

---

## Utility Commands

### `trace projects`

List all registered projects.

```bash
$ trace projects
default      ~/.trace/default
myapp        ~/Repos/myapp
mylib        ~/Repos/mylib
trace        ~/Repos/trace

# With statistics
$ trace projects --stats
default      ~/.trace/default                  (3 open, 1 closed)
myapp        ~/Repos/myapp                    (12 open, 8 closed)
mylib        ~/Repos/mylib                     (5 open, 2 closed)
trace        ~/Repos/trace                     (8 open, 0 closed)

# Options
--stats                      Show issue counts
--json                       JSON output
```

---

### `trace sync`

Manually sync a project's JSONL file with central database.

```bash
# Sync current project
$ trace sync
Syncing myapp...
Imported 3 new issues from JSONL
Exported 5 updated issues to JSONL

# Sync specific project
$ trace sync --project mylib

# Sync all projects
$ trace sync --all

# Force reimport (rebuild DB from JSONL)
$ trace sync --force-import

# Force export (rebuild JSONL from DB)
$ trace sync --force-export

# Options
--project <name>             Sync specific project
--all                        Sync all projects
--force-import               Rebuild DB from JSONL
--force-export               Rebuild JSONL from DB
```

---

### `trace config`

View and update configuration.

```bash
# View current config
$ trace config
fallback-project: default
auto-close-parents: false

# Set fallback project
$ trace config set fallback-project personal

# Toggle auto-close
$ trace config set auto-close-parents true

# Unset value
$ trace config unset fallback-project

# Options
set <key> <value>            Set config value
unset <key>                  Remove config value
--json                       JSON output
```

---

## AI Integration Features

### Bulk Creation

For AI agents creating multiple issues:

```bash
# Create from YAML/JSON
$ trace import issues.yaml

# issues.yaml:
issues:
  - title: "Add authentication"
    priority: 1
    children:
      - title: "Research libraries"
      - title: "Implement OAuth"
      - title: "Add tests"
```

### Template Expansion

```bash
# Common patterns
$ trace template feature "Add notifications" --project myapp
Created myapp-abc123: Add notifications
Created myapp-def456: Research notification services
Created myapp-ghi789: Design notification schema
Created myapp-jkl012: Implement notifications
Created myapp-mno345: Add tests
```

### Context-Rich Output

Commands should provide enough context for AI to understand state:

```bash
$ trace show myapp-abc123 --json
{
  "id": "myapp-abc123",
  "project": "myapp",
  "title": "Add authentication",
  "status": "blocked",
  "blocked_by": ["mylib-def456"],
  "children": [
    {"id": "myapp-ghi789", "status": "open"},
    {"id": "myapp-jkl012", "status": "closed"}
  ],
  "ready_to_work": false,
  "completion_percentage": 50
}
```

---

## Error Handling

### Consistent Error Format

```bash
$ trace close myapp-abc123
Error: Cannot close issue with open children
  - myapp-def456 [open] Subtask 1
  - myapp-ghi789 [in_progress] Subtask 2

Suggestion: Close children first, or use --force to override

# Exit code: 1
```

### Warnings vs Errors

**Errors** (exit code 1): Operation cannot proceed
- Cycle detection
- Missing dependencies
- Invalid arguments

**Warnings** (exit code 0): Operation proceeds with note
- Cross-project dependencies
- Closing parent with force flag
- Large bulk operations

---

## Scripting Examples

### Daily Standup

```bash
#!/bin/bash
echo "Ready to work on:"
trace ready --all --limit 5

echo "\nIn progress:"
trace list --status in_progress --all
```

### Weekly Summary

```bash
#!/bin/bash
echo "Closed this week:"
trace list --status closed --all | wc -l

echo "\nTop priorities:"
trace ready --priority 0,1 --all
```

### AI Context Builder

```bash
#!/bin/bash
# Get full context for current project
trace list --current-project --json > /tmp/all-issues.json
trace ready --current-project --json > /tmp/ready-issues.json

echo "AI: Here are all issues and ready work for analysis"
```

---

## Performance Targets

| Command | Target | With 1000 Issues |
|---------|--------|------------------|
| `trace create` | <50ms | <50ms |
| `trace list` | <100ms | <150ms |
| `trace show` | <50ms | <50ms |
| `trace ready` | <200ms | <300ms |
| `trace tree` | <100ms | <150ms |
| `trace sync` | <200ms | <500ms |

---

## Future Enhancements

### Interactive Mode

```bash
$ trace
trace> create "Fix bug"
Created myapp-abc123

trace> show abc123
[shows issue]

trace> exit
```

### Watch Mode

```bash
$ trace watch
Watching .trace/issues.jsonl for changes...
[updates when file changes from git pull]
```

### Autocomplete

```bash
# Bash completion
$ trace sh<TAB>
show

$ trace myapp-<TAB>
myapp-abc123  myapp-def456  myapp-ghi789
```
