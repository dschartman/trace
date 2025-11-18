# AI Agent Integration Guide

This guide helps AI agents like Claude Code effectively use Trace for work tracking and planning.

## Core Philosophy

Trace is designed specifically for **AI agent workflows** where:
- Work structure evolves as understanding grows
- Planning happens iteratively across sessions
- Cross-project dependencies are common
- Reorganization should be trivial, not painful

**Key insight**: Structure is a tool for thinking, not a constraint. Start natural, reorganize freely.

## Mandatory Descriptions: Context Across Sessions

**All `trc create` commands require `--description`** to preserve context for future sessions.

### Why Mandatory?

AI agents work across multiple sessions. When you or another agent returns to a work item days later, the description provides critical context that the title alone cannot convey.

### Good Descriptions
Even brief descriptions are valuable:
```bash
# Good: Provides context
trc create "Fix login timeout" --description "Users getting logged out after 5min, should be 30min"

# Good: Links to investigation
trc create "Optimize slow queries" --description "See analysis in #database channel. Focus on user_activity table."

# Good: Even minimal context helps
trc create "Update docs" --description "Reflect new --description requirement"

# Good: Reference to parent
trc create "Add tests" --description "See parent for scope" --parent feature-abc
```

### Empty String Opt-Out
If truly no context is needed (rare), explicitly opt-out:
```bash
trc create "Quick fix" --description ""
```

### Bad: Skipping Description
```bash
# ❌ This will error - description is required
trc create "Fix bug"
```

### Why This Matters

Without descriptions:
- ❌ Future agents can't understand work context
- ❌ Priority and scope are unclear
- ❌ Dependencies and reasoning are lost
- ❌ Work items become stale and forgotten

With descriptions:
- ✅ Work is self-documenting
- ✅ Context persists across sessions and agents
- ✅ Decision-making is faster
- ✅ Reorganization is easier with full context

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
trc create "Add authentication" --description "OAuth2 + Google, see security requirements doc"
trc create "Install oauth2 library" --description "Research passport vs oauth2orize" --parent auth-abc123
trc create "Create /login endpoint" --description "Handle callback and token exchange" --parent auth-abc123
trc create "Add password hashing" --description "Use bcrypt with salt rounds=10" --parent auth-abc123
trc create "Write tests for auth flow" --description "Cover login, logout, token refresh" --parent auth-abc123
```

**Coarse-grained:**
```bash
trc create "Add authentication system" --description "Full OAuth2 implementation with Google SSO"
trc create "Add API endpoints for data export" --description "CSV and JSON formats, paginated"
```

**Mixed (most common):**
```bash
trc create "Refactor data layer" --description "Extract ORM logic, prepare for multi-tenancy"
trc create "Extract database logic to service" --description "Create DataService class" --parent refactor-abc
trc create "Add caching" --description "Redis for query results" --parent refactor-abc
trc create "Update documentation" --description "API docs for v2 endpoints"  # No parent - standalone
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
trc create "Add user notifications" --description "In-app + email, see PRD in docs/notifications.md"

[Explores codebase, discovers approach]
trc create "Add notification schema to database" --description "New notifications table with user_id, type, read_at" --parent app-abc123
trc create "Create notification service" --description "Handle creation, marking as read, email dispatch" --parent app-abc123
trc create "Add UI for notification center" --description "Bell icon + dropdown, real-time updates via SSE" --parent app-abc123

[While exploring, notices bug]
trc create "Bug: notification timestamps not timezone-aware" --description "All timestamps stored as UTC but displayed without conversion"

[Starts work, uses TodoWrite for immediate tracking]
TodoWrite: [Implementing notification schema...]
```

## Cross-Project Workflows

Trace shines for work spanning multiple repositories:

```bash
# In your app repo
trc create "Add real-time updates" --description "Use WebSocket from mylib once ready" --depends-on mylib-websocket-xyz

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
trc create "Add multi-tenant support" --description "Isolate data per customer, see architecture doc"

# Break down as you learn more
trc create "Design tenant isolation model" --description "Research row-level security vs separate schemas" --parent tenant-abc
trc create "Add tenant_id to all tables" --description "Migration script needed, estimate ~20 tables" --parent tenant-abc
trc create "Update queries for tenant filtering" --description "Add WHERE tenant_id clauses throughout codebase" --parent tenant-abc

# View the plan
trc tree tenant-abc

# See what's ready to start
trc ready
```

### 2. Bug Discovery

```bash
# While exploring codebase
trc create "Security: API keys in logs" --description "Found in auth.log line 342, remove before prod deploy"
trc create "Bug: Race condition in cache update" --description "Multiple workers writing simultaneously, use distributed lock"
trc create "Tech debt: Using deprecated XML parser" --description "lxml is deprecated, migrate to defusedxml"

# Link related work
trc create "Upgrade to new XML library" --description "Blocked on cache fix testing" --depends-on app-cache-bug
```

### 3. Iterative Refinement

```bash
# Initial plan
trc create "Optimize database queries" --description "Page load times >3s, target <500ms"
trc create "Add indexes" --description "Start with user_activity table" --parent opt-abc

# After investigation, refine
trc create "Analyze slow queries first" --description "Use EXPLAIN ANALYZE on top 10 slowest" --parent opt-abc
trc reparent opt-indexes opt-abc  # Make indexes a child too

# Discover it's bigger than expected
trc create "Migrate to connection pooling" --description "Hitting max connections at peak load" --parent opt-abc
```

### 4. Cross-Session Continuity

Trace persists across sessions, so work can continue seamlessly:

```
Session 1 (Agent):
  trc create "Refactor auth system" --description "Extract validation, add OAuth support"
  trc create "Extract validation logic" --description "Move to validators.py module" --parent auth-abc
  trc create "Add unit tests" --description "Cover all validation edge cases" --parent auth-abc
  [Completes first subtask]
  trc close auth-extract-xyz

Session 2 (Days later, different agent):
  trc ready  # Shows "Add unit tests" is ready
  trc show auth-tests-xyz  # Reads description to understand context
  [Continues work naturally]
```

## Best Practices

### 1. Always Add Descriptions
Descriptions are mandatory and preserve context:
```bash
# ✅ Good - provides context
trc create "Add payment processing" --description "Stripe integration, webhook for subscription events"

# ✅ Acceptable - minimal but useful
trc create "Fix typo" --description "In auth error message"

# ❌ Bad - will error
trc create "Add payment processing"
```

### 2. Create Parents Early
If work has obvious sub-tasks, create the parent immediately:
```bash
trc create "Add payment processing" --description "Stripe integration, webhook for subscription events"
# Don't wait - create children as you plan
trc create "Integrate Stripe API" --description "Setup API keys, test mode first" --parent payment-abc
trc create "Add webhook handling" --description "Handle payment.succeeded event" --parent payment-abc
```

### 3. Use Descriptive Titles
Good: "Add OAuth2 authentication with Google"
Better than: "Auth stuff"

### 4. Mark Work Complete
Always close issues when done:
```bash
trc close myapp-abc123
```

### 5. Check Ready Work
Before asking "what should I work on?":
```bash
trc ready  # Current project
trc ready --all  # All projects
```

### 6. Link Dependencies Explicitly
```bash
trc create "Update frontend to use new API" --description "Waiting for /v2/users endpoint" --depends-on backend-api-xyz
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
trc create "title" --description "context"           # Create issue (description required)
trc create "title" --description "context" --parent <id>  # Create child issue
trc create "title" --description ""                  # Opt-out of description (rare)
trc ready                                            # Show ready work
trc list                                             # List backlog (excludes closed)
trc list --status any                                # List all issues including closed
trc list --status closed                             # List only completed work
trc show <id>                                        # Show details
trc close <id>                                       # Mark complete
trc tree <id>                                        # View hierarchy
```

### Reorganization
```bash
trc reparent <id> <new-parent>        # Change parent
trc reparent <id> none                # Remove parent
trc move <id> <project>               # Move to different project
```

### Advanced
```bash
trc create "title" --description "context" --project <name>   # Create in different project
trc create "title" --description "context" --depends-on <id>  # Add blocker
trc ready --project any                                       # Cross-project ready work
trc list --project any                                        # All projects backlog
trc list --project any --status any                           # All projects all statuses
trc list --status open --status closed                        # Multiple status filters
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
