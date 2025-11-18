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
uv run python trc_main.py
```

## Your First Project

### 1. Initialize Trace

Navigate to your git repository and initialize trace:

```bash
cd ~/repos/myproject
trc init
```

This creates:
- `~/.trace/trace.db` - Central database (first time only)
- `.trace/issues.jsonl` - Project-specific JSONL file
- Registers the project

### 2. Create Your First Issue

**Note**: `--description` is required to preserve context across sessions:

```bash
trc create "Add user authentication" --description "OAuth2 + Google SSO for web and mobile"
```

Output:
```
Created myproject-a7k3m2: Add user authentication
```

The ID format is `{project}-{6-char-hash}`.

### 3. Break It Down

Create child tasks with `--parent`:

```bash
trc create "Research OAuth libraries" --description "Compare passport vs oauth2orize" --parent myproject-a7k3m2
trc create "Design login flow" --description "UX mockups and token refresh strategy" --parent myproject-a7k3m2
trc create "Implement Google login" --description "OAuth2 callback handling" --parent myproject-a7k3m2
trc create "Add logout functionality" --description "Clear sessions and tokens" --parent myproject-a7k3m2
trc create "Write integration tests" --description "Test login, logout, token refresh" --parent myproject-a7k3m2
```

### 4. View the Hierarchy

```bash
trc tree myproject-a7k3m2
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
trc ready
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
trc show myproject-b8n4x3
```

Update status:

```bash
trc update myproject-b8n4x3 --status in_progress
```

### 7. Complete Work

Close the issue when done:

```bash
trc close myproject-b8n4x3
```

## Core Commands

### Creating Issues

**Note**: `--description` is **required** for all issues to preserve context.

```bash
# Basic (description required)
trc create "Issue title" --description "Context for this work"

# Empty description opt-out (rare)
trc create "Quick fix" --description ""

# With priority (0=critical, 4=backlog, default=2)
trc create "Critical bug" --description "Production down, fix ASAP" --priority 0

# With parent
trc create "Subtask" --description "See parent for context" --parent myproject-abc123

# With blocking dependency
trc create "Feature" --description "Waiting for library update" --depends-on mylib-def456

# All together
trc create "Complex task" \
    --description "Full implementation details here" \
    --priority 1 \
    --parent myproject-abc123 \
    --depends-on mylib-def456 \
    --status in_progress
```

### Viewing Work

```bash
# List issues in current project
trc list

# List all issues across projects
trc list --all

# Show issue details
trc show myproject-abc123

# View hierarchy
trc tree myproject-abc123

# See ready work
trc ready

# See ready work across all projects
trc ready --all
```

### Updating Issues

```bash
# Change status
trc update myproject-abc123 --status in_progress

# Change priority
trc update myproject-abc123 --priority 0

# Change title
trc update myproject-abc123 --title "New title"

# Multiple changes
trc update myproject-abc123 --priority 1 --status closed
```

### Reorganizing

```bash
# Change parent
trc reparent myproject-child123 myproject-newparent456

# Remove parent
trc reparent myproject-child123 none

# Add dependency to existing issue
trc add-dependency myproject-abc123 myproject-def456  # blocks by default
trc add-dependency myproject-abc123 myproject-def456 --type parent
trc add-dependency myproject-abc123 myproject-def456 --type related

# Move to different project
trc move myproject-abc123 targetproject
```

### Closing Work

```bash
# Close an issue
trc close myproject-abc123

# Note: Cannot close issues with open children
```

## Common Workflows

### Workflow 1: Feature Development

```bash
# 1. Create parent feature
trc create "Add notifications" --description "In-app + email, see PRD in docs/"
# Output: Created myapp-a1b2c3

# 2. Break down into tasks
trc create "Design notification schema" --description "User preferences, read/unread state" --parent myapp-a1b2c3
trc create "Implement email notifications" --description "Use SendGrid API" --parent myapp-a1b2c3
trc create "Implement push notifications" --description "FCM for mobile, SSE for web" --parent myapp-a1b2c3
trc create "Add notification settings UI" --description "Toggle switches for each type" --parent myapp-a1b2c3

# 3. Check ready work
trc ready

# 4. Work on tasks (in progress)
trc update myapp-d4e5f6 --status in_progress

# 5. Complete tasks
trc close myapp-d4e5f6

# 6. View progress
trc tree myapp-a1b2c3

# 7. Close parent when all children done
trc close myapp-a1b2c3
```

### Workflow 2: Cross-Project Dependencies

```bash
# In library project
cd ~/repos/mylib
trc create "Add WebSocket support" --description "Real-time event streaming API"
# Output: Created mylib-x7y8z9

# In app project (or use --project to create from anywhere)
cd ~/repos/myapp
trc create "Use WebSocket in UI" --description "Live updates for dashboard" --depends-on mylib-x7y8z9
# Output: Created myapp-a1b2c3
# Output:   Depends-on: mylib-x7y8z9

# Alternative: Create in different project without cd
trc create "Add caching layer" --description "Use Redis" --project mylib
# Output: Created mylib-abc456

# Check ready work (app issue will be blocked)
trc ready
# Shows only mylib-x7y8z9

# Complete library work first
cd ~/repos/mylib
trc close mylib-x7y8z9

# Now app work is unblocked
cd ~/repos/myapp
trc ready
# Shows myapp-a1b2c3
```

### Workflow 3: Git Integration

```bash
# Create issues
trc create "Fix bug in auth flow" --description "Token refresh failing after 5min"
trc create "Update documentation" --description "Add new API endpoints to README"

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
trc list  # Shows the new issues
```

### Workflow 4: Exploring Ideas

```bash
# Start exploring an idea
trc create "Investigate caching strategies" --description "Target <100ms response times"
trc create "Research Redis vs Memcached" --description "Compare features and performance" --parent ...
trc create "Benchmark different approaches" --description "Load test with production traffic" --parent ...

# As you learn more, reorganize
trc reparent myapp-abc123 myapp-newparent

# Create blockers as needed
trc create "Set up Redis cluster" --description "3-node cluster for HA" --depends-on myinfra-def456
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
- **Add dependencies later**: Use `trc add-dependency` to add relationships after creating issues

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

Make sure you're in the correct project directory, or use `trc list --all` to see all issues.

### Lock timeout errors

If you get lock timeout errors, another trace command is running. Wait for it to complete, or check for stuck processes.

### JSONL conflicts after git pull

If you get merge conflicts in `.trace/issues.jsonl`:
1. Resolve the conflict manually (it's just JSON lines)
2. Ensure valid JSON format
3. Run `trc list` to verify the sync works

## Getting Help

- Check `trace` for command list
- Use `trc <command> --help` for command-specific help
- Review documentation in `docs/` directory
- Open an issue on GitHub

