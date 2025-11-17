# AI Agent Integration Guide

This guide helps AI agents like Claude Code effectively use Trace for work tracking and planning.

## Core Philosophy

Trace is designed specifically for **AI agent workflows** where:
- Work structure evolves as understanding grows
- Planning happens iteratively across sessions
- Cross-project dependencies are common
- Reorganization should be trivial, not painful

**Key insight**: Structure is a tool for thinking, not a constraint. Start natural, reorganize freely.

## When to Use Trace vs TodoWrite

### Use Trace for:
- ✅ Work spanning multiple sessions (persists beyond conversation)
- ✅ Breaking down complex features iteratively
- ✅ Bugs/improvements discovered during exploration
- ✅ Cross-project coordination
- ✅ Planning that will evolve and need reorganization
- ✅ Anything non-trivial that you'd put in TodoWrite

### Use TodoWrite for:
- ✅ Immediate, single-session task lists
- ✅ Simple execution tracking (3-5 steps)
- ✅ Showing user your current progress in real-time
- ✅ Trivial checklists that won't need persistence

### Rule of thumb:
**If it might matter next session or needs reorganization later → use Trace**
**If it's just for tracking immediate work → use TodoWrite**

## Granularity: No Wrong Answer

Trace has **no enforced hierarchy**. There are no epics, features, stories, or tasks. Just issues with optional parent-child relationships.

### Examples of Valid Granularity:

**Fine-grained:**
```bash
trc create "Add authentication"
trc create "Install oauth2 library" --parent auth-abc123
trc create "Create /login endpoint" --parent auth-abc123
trc create "Add password hashing" --parent auth-abc123
trc create "Write tests for auth flow" --parent auth-abc123
```

**Coarse-grained:**
```bash
trc create "Add authentication system"
trc create "Add API endpoints for data export"
```

**Mixed (most common):**
```bash
trc create "Refactor data layer"
trc create "Extract database logic to service" --parent refactor-abc
trc create "Add caching" --parent refactor-abc
trc create "Update documentation"  # No parent - standalone
```

### Start Natural, Adjust Later

Don't overthink granularity. Start with what feels right:
- Planning a feature? Create a parent, add obvious children
- Found a bug? Create an issue
- Need to break something down more? Create children
- Too granular? Use `trc reparent` or `trc close` to consolidate

**The key**: Reorganization is trivial, so structure can evolve naturally.

## Proactive Usage

### Use Trace Early and Often

Don't wait for users to ask. Use trace when:

1. **User requests feature work**: Immediately break it down in trace
2. **You discover bugs while exploring**: Create issues as you find them
3. **Planning multi-step work**: Put the plan in trace, not just TodoWrite
4. **Cross-project dependencies emerge**: Link them in trace

### Example Session:

```
User: "Add user notifications to the app"

Agent: Let me break this down in trace...
[Creates parent issue]
trc create "Add user notifications"

[Explores codebase, discovers approach]
trc create "Add notification schema to database" --parent app-abc123
trc create "Create notification service" --parent app-abc123
trc create "Add UI for notification center" --parent app-abc123

[While exploring, notices bug]
trc create "Bug: notification timestamps not timezone-aware"

[Starts work, uses TodoWrite for immediate tracking]
TodoWrite: [Implementing notification schema...]
```

## Cross-Project Workflows

Trace shines for work spanning multiple repositories:

```bash
# In your app repo
trc create "Add real-time updates" --depends-on mylib-websocket-xyz

# Work on library first
cd ~/Repos/mylib
trc ready --all  # Shows library work blocks app work

# After completing library
trc close mylib-websocket-xyz

# Back in app
trc ready  # Now shows app work is unblocked
```

## Common Workflows

### 1. Feature Planning

```bash
# High-level parent
trc create "Add multi-tenant support"

# Break down as you learn more
trc create "Design tenant isolation model" --parent tenant-abc
trc create "Add tenant_id to all tables" --parent tenant-abc
trc create "Update queries for tenant filtering" --parent tenant-abc

# View the plan
trc tree tenant-abc

# See what's ready to start
trc ready
```

### 2. Bug Discovery

```bash
# While exploring codebase
trc create "Security: API keys in logs"
trc create "Bug: Race condition in cache update"
trc create "Tech debt: Using deprecated XML parser"

# Link related work
trc create "Upgrade to new XML library" --depends-on app-cache-bug
```

### 3. Iterative Refinement

```bash
# Initial plan
trc create "Optimize database queries"
trc create "Add indexes" --parent opt-abc

# After investigation, refine
trc create "Analyze slow queries first" --parent opt-abc
trc reparent opt-indexes opt-abc  # Make indexes a child too

# Discover it's bigger than expected
trc create "Migrate to connection pooling" --parent opt-abc
```

### 4. Cross-Session Continuity

Trace persists across sessions, so work can continue seamlessly:

```
Session 1 (Agent):
  trc create "Refactor auth system"
  trc create "Extract validation logic" --parent auth-abc
  trc create "Add unit tests" --parent auth-abc
  [Completes first subtask]
  trc close auth-extract-xyz

Session 2 (Days later, different agent):
  trc ready  # Shows "Add unit tests" is ready
  [Continues work naturally]
```

## Best Practices

### 1. Create Parents Early
If work has obvious sub-tasks, create the parent immediately:
```bash
trc create "Add payment processing"
# Don't wait - create children as you plan
trc create "Integrate Stripe API" --parent payment-abc
trc create "Add webhook handling" --parent payment-abc
```

### 2. Use Descriptive Titles
Good: "Add OAuth2 authentication with Google"
Better than: "Auth stuff"

### 3. Mark Work Complete
Always close issues when done:
```bash
trc close myapp-abc123
```

### 4. Check Ready Work
Before asking "what should I work on?":
```bash
trc ready  # Current project
trc ready --all  # All projects
```

### 5. Link Dependencies Explicitly
```bash
trc create "Update frontend to use new API" --depends-on backend-api-xyz
```

## Integration with TodoWrite

Use both! They serve different purposes:

**TodoWrite**: Real-time progress for current session
```
[1. in_progress] Implementing OAuth login
[2. pending] Write tests
[3. pending] Update documentation
```

**Trace**: Persistent work tracking
```bash
myapp-abc123 [open] Add OAuth authentication
  myapp-def456 [in_progress] Implement OAuth login
  myapp-ghi789 [open] Write integration tests
  myapp-jkl012 [open] Update auth documentation
```

**Workflow**: Use Trace for planning, TodoWrite for execution tracking within a session.

## Commands Reference

### Essential Commands
```bash
trc create "title"                    # Create issue
trc create "title" --parent <id>      # Create child issue
trc ready                             # Show ready work
trc list                              # List all issues
trc show <id>                         # Show details
trc close <id>                        # Mark complete
trc tree <id>                         # View hierarchy
```

### Reorganization
```bash
trc reparent <id> <new-parent>        # Change parent
trc reparent <id> none                # Remove parent
trc move <id> <project>               # Move to different project
```

### Advanced
```bash
trc create "title" --depends-on <id>  # Add blocker
trc ready --all                       # Cross-project ready work
trc list --all                        # All projects
```

## Output for CLAUDE.md

Run `trc guide` to get a ready-to-paste template for your project's CLAUDE.md file.

## Tuning the Guide

This guide (`docs/ai-agent-guide.md`) is the comprehensive reference. Use it to:
- Understand the full philosophy
- See extended examples
- Refine the `trc guide` template over time

The `trc guide` output should stay concise (fits in one screen), while this doc can be comprehensive.

## Questions?

- See `docs/product-vision.md` for design philosophy
- See `docs/use-cases.md` for real-world workflows
- See `docs/cli-design.md` for complete command reference
