# Trace Quickstart Guide

Get started with Trace in 5 minutes.

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/trace.git
cd trace

# Install with uv
uv sync

# Verify installation
uv run python trace.py
```

## Your First Project

### 1. Initialize Trace

Navigate to your git repository and initialize trace:

```bash
cd ~/repos/myproject
trace init
```

This creates:
- `~/.trace/trace.db` - Central database (first time only)
- `.trace/issues.jsonl` - Project-specific JSONL file
- Registers the project

### 2. Create Your First Issue

```bash
trace create "Add user authentication"
```

Output:
```
Created myproject-a7k3m2: Add user authentication
```

The ID format is `{project}-{6-char-hash}`.

### 3. Break It Down

Create child tasks with `--parent`:

```bash
trace create "Research OAuth libraries" --parent myproject-a7k3m2
trace create "Design login flow" --parent myproject-a7k3m2
trace create "Implement Google login" --parent myproject-a7k3m2
trace create "Add logout functionality" --parent myproject-a7k3m2
trace create "Write integration tests" --parent myproject-a7k3m2
```

### 4. View the Hierarchy

```bash
trace tree myproject-a7k3m2
```

Output:
```
○ myproject-a7k3m2 - Add user authentication [open]
   ├─ ○ myproject-b8n4x3 - Research OAuth libraries [open]
   ├─ ○ myproject-c9p5y4 - Design login flow [open]
   ├─ ○ myproject-d0q6z5 - Implement Google login [open]
   ├─ ○ myproject-e1r7a6 - Add logout functionality [open]
   └─ ○ myproject-f2s8b7 - Write integration tests [open]
```

### 5. Check Ready Work

See what's unblocked and ready to work on:

```bash
trace ready
```

Output:
```
Ready work (not blocked):

○ myproject-b8n4x3 [P2] Research OAuth libraries
   └─ child of: myproject-a7k3m2 - Add user authentication
○ myproject-c9p5y4 [P2] Design login flow
   └─ child of: myproject-a7k3m2 - Add user authentication
○ myproject-d0q6z5 [P2] Implement Google login
   └─ child of: myproject-a7k3m2 - Add user authentication
...
```

### 6. Work on an Issue

View details:

```bash
trace show myproject-b8n4x3
```

Update status:

```bash
trace update myproject-b8n4x3 --status in_progress
```

### 7. Complete Work

Close the issue when done:

```bash
trace close myproject-b8n4x3
```

## Core Commands

### Creating Issues

```bash
# Basic
trace create "Issue title"

# With description
trace create "Issue title" --description "Detailed description"

# With priority (0=critical, 4=backlog, default=2)
trace create "Critical bug" --priority 0

# With parent
trace create "Subtask" --parent myproject-abc123

# With blocking dependency
trace create "Feature" --depends-on mylib-def456

# All together
trace create "Complex task" \
    --description "Full details here" \
    --priority 1 \
    --parent myproject-abc123 \
    --depends-on mylib-def456 \
    --status in_progress
```

### Viewing Work

```bash
# List issues in current project
trace list

# List all issues across projects
trace list --all

# Show issue details
trace show myproject-abc123

# View hierarchy
trace tree myproject-abc123

# See ready work
trace ready

# See ready work across all projects
trace ready --all
```

### Updating Issues

```bash
# Change status
trace update myproject-abc123 --status in_progress

# Change priority
trace update myproject-abc123 --priority 0

# Change title
trace update myproject-abc123 --title "New title"

# Multiple changes
trace update myproject-abc123 --priority 1 --status closed
```

### Reorganizing

```bash
# Change parent
trace reparent myproject-child123 myproject-newparent456

# Remove parent
trace reparent myproject-child123 none

# Move to different project
trace move myproject-abc123 targetproject
```

### Closing Work

```bash
# Close an issue
trace close myproject-abc123

# Note: Cannot close issues with open children
```

## Common Workflows

### Workflow 1: Feature Development

```bash
# 1. Create parent feature
trace create "Add notifications"
# Output: Created myapp-a1b2c3

# 2. Break down into tasks
trace create "Design notification schema" --parent myapp-a1b2c3
trace create "Implement email notifications" --parent myapp-a1b2c3
trace create "Implement push notifications" --parent myapp-a1b2c3
trace create "Add notification settings UI" --parent myapp-a1b2c3

# 3. Check ready work
trace ready

# 4. Work on tasks (in progress)
trace update myapp-d4e5f6 --status in_progress

# 5. Complete tasks
trace close myapp-d4e5f6

# 6. View progress
trace tree myapp-a1b2c3

# 7. Close parent when all children done
trace close myapp-a1b2c3
```

### Workflow 2: Cross-Project Dependencies

```bash
# In library project
cd ~/repos/mylib
trace create "Add WebSocket support"
# Output: Created mylib-x7y8z9

# In app project
cd ~/repos/myapp
trace create "Use WebSocket in UI" --depends-on mylib-x7y8z9
# Output: Created myapp-a1b2c3
# Output:   Depends-on: mylib-x7y8z9

# Check ready work (app issue will be blocked)
trace ready
# Shows only mylib-x7y8z9

# Complete library work first
cd ~/repos/mylib
trace close mylib-x7y8z9

# Now app work is unblocked
cd ~/repos/myapp
trace ready
# Shows myapp-a1b2c3
```

### Workflow 3: Git Integration

```bash
# Create issues
trace create "Fix bug in auth flow"
trace create "Update documentation"

# Changes are automatically in .trace/issues.jsonl
git status
# Shows: .trace/issues.jsonl modified

# Commit and push
git add .trace/issues.jsonl
git commit -m "Add new issues for auth bug and docs"
git push

# On another machine
git pull

# Trace automatically syncs
trace list  # Shows the new issues
```

### Workflow 4: Exploring Ideas

```bash
# Start exploring an idea
trace create "Investigate caching strategies"
trace create "Research Redis vs Memcached" --parent ...
trace create "Benchmark different approaches" --parent ...

# As you learn more, reorganize
trace reparent myapp-abc123 myapp-newparent

# Create blockers as needed
trace create "Set up Redis cluster" --depends-on myinfra-def456
```

## Tips & Tricks

### Priorities

Use priorities to indicate urgency:
- `0` - Critical (drop everything)
- `1` - High (next sprint)
- `2` - Normal (default, backlog)
- `3` - Low (nice to have)
- `4` - Backlog (someday/maybe)

### Status Values

Available statuses:
- `open` - Not started (default)
- `in_progress` - Currently working on it
- `blocked` - Waiting on dependencies
- `closed` - Complete

### Organizing Work

- **Use parent-child for decomposition**: Break large features into smaller tasks
- **Use blocks for dependencies**: When one issue must complete before another
- **Use related for context**: Link related issues without blocking

### Git Workflow

- Always commit `.trace/issues.jsonl` with your code
- The JSONL format merges cleanly in git
- Trace automatically syncs when you run commands after `git pull`

## Next Steps

- Read [CLI Design](cli-design.md) for complete command reference
- See [Use Cases](use-cases.md) for real-world examples
- Explore [Key Features](key-features.md) for technical details
- Review [Product Vision](product-vision.md) for philosophy

## Troubleshooting

### "Not in a git repository"

Trace requires a git repository. Run `git init` first.

### "Issue not found"

Make sure you're in the correct project directory, or use `trace list --all` to see all issues.

### Lock timeout errors

If you get lock timeout errors, another trace command is running. Wait for it to complete, or check for stuck processes.

### JSONL conflicts after git pull

If you get merge conflicts in `.trace/issues.jsonl`:
1. Resolve the conflict manually (it's just JSON lines)
2. Ensure valid JSON format
3. Run `trace list` to verify the sync works

## Getting Help

- Check `trace` for command list
- Use `trace <command> --help` for command-specific help
- Review documentation in `docs/` directory
- Open an issue on GitHub

