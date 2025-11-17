# Trace Use Cases

## Overview

This document describes the primary workflows and use cases that trace is designed to support, with a focus on AI-agent-assisted development.

---

## Use Case 1: Feature Planning with AI Agent

### Scenario

You want to add a new feature to a personal project and use an AI agent (Claude Code) to help plan and implement it.

### Traditional Workflow (Markdown Planning)

```
You: "I want to add user authentication to my web app"

Claude: "Let me create a plan..."
[Creates plan.md with breakdown]

Problem: Plan becomes stale, doesn't track completion,
no cross-session memory
```

### Trace Workflow

```bash
# 1. Start conversation in project
$ cd ~/Repos/myapp

# 2. You describe the feature
You: "I want to add user authentication"

# 3. Claude creates parent trace
Claude: trace create "Add user authentication system" --size large
→ myapp-abc123

# 4. Claude breaks it down iteratively
Claude: trace create "Research auth libraries" --parent myapp-abc123
→ myapp-def456

Claude: trace create "Design user database schema" --parent myapp-abc123
→ myapp-ghi789

Claude: trace create "Implement OAuth flow" --parent myapp-abc123
→ myapp-jkl012

# 5. View the breakdown
$ trc tree myapp-abc123
myapp-abc123 Add user authentication system [open]
├─ myapp-def456 Research auth libraries [open]
├─ myapp-ghi789 Design user database schema [open]
└─ myapp-jkl012 Implement OAuth flow [open]

# 6. Work on first item
$ trc show myapp-def456 --ready
# Claude researches, then closes it
$ trc close myapp-def456

# 7. New information emerges
You: "Actually, we need to support both OAuth and magic links"

# Claude reorganizes
Claude: trace create "Implement magic link auth" --parent myapp-abc123
→ myapp-mno345

Claude: trace update myapp-jkl012 --priority 1
Claude: trace update myapp-mno345 --priority 2

# 8. Further breakdown as work progresses
Claude: trace create "Add email service integration" --parent myapp-mno345
Claude: trace create "Create magic link tokens" --parent myapp-mno345
```

### Key Benefits

- **Persistent context** - Work structure survives across sessions
- **Iterative refinement** - Easy to add/modify/reorganize
- **Clear status** - See what's done, what's next
- **Cross-session** - Pick up where you left off days later

---

## Use Case 2: Exploring Ideas Conceptually

### Scenario

You have a vague idea for a new project and want to use trace to flesh out the concept and structure your thinking.

### Workflow

```bash
# 1. Not in any project yet
$ cd ~

# 2. Start exploring the idea
You: "I'm thinking about building a distributed cache system"

# Claude creates in default project
Claude: trace create "Distributed cache system concept" --project default
→ default-abc123

# 3. Break down to understand scope
Claude: trace create "Core architecture decisions" --parent default-abc123
→ default-def456

Claude: trace create "Consistency model (AP vs CP)" --parent default-def456
Claude: trace create "Storage backend options" --parent default-def456
Claude: trace create "Network protocol design" --parent default-def456

# 4. Explore each area
$ trc tree default-abc123
default-abc123 Distributed cache system concept
└─ default-def456 Core architecture decisions
   ├─ default-ghi789 Consistency model (AP vs CP)
   ├─ default-jkl012 Storage backend options
   └─ default-mno345 Network protocol design

# 5. Research and document findings
Claude updates descriptions as you explore each topic

# 6. Decide it's viable - create real project
$ mkdir ~/Repos/distcache && cd ~/Repos/distcache
$ trc init
Initialized project: distcache

# 7. Move relevant work from default to project
$ trc move default-abc123 --to-project distcache
Moved default-abc123 → distcache-abc123
  (and all 4 children)

# 8. Now continue work in the real project
```

### Key Benefits

- **Think through structure** - Use traces to organize thoughts
- **No premature commitment** - Explore before creating repo
- **Easy transition** - Move from concept to implementation
- **Discovery trail** - Keep track of research and decisions

---

## Use Case 3: Researching Existing Project

### Scenario

You're exploring an existing codebase (maybe someone else's, or your own from months ago) and need to identify work that should be done.

### Workflow

```bash
# 1. Clone and explore
$ git clone https://github.com/example/some-lib
$ cd some-lib
$ trc init

# 2. Start reading code with Claude
You: "Help me understand how authentication works"

# 3. Claude discovers issues while exploring
Claude: "I found several issues while reading the code..."

Claude: trace create "Security: Passwords stored in plaintext" --priority 0
→ some-lib-abc123

Claude: trace create "Bug: Session timeout not enforced" --priority 1
→ some-lib-def456

Claude: trace create "Tech debt: Deprecated auth library" --priority 2
→ some-lib-ghi789

# 4. Group related work
Claude: trace create "Authentication system improvements"
→ some-lib-parent123

Claude: trace reparent some-lib-abc123 --parent some-lib-parent123
Claude: trace reparent some-lib-def456 --parent some-lib-parent123

# 5. Continue exploring other areas
You: "Now check the database layer"

Claude: trace create "Database improvements"
Claude: trace create "Missing indexes on user queries" --parent ...
Claude: trace create "N+1 query in dashboard" --parent ...

# 6. Review all discovered work
$ trc list --all
some-lib-abc123 [P0] Security: Passwords stored in plaintext
some-lib-def456 [P1] Bug: Session timeout not enforced
some-lib-ghi789 [P2] Tech debt: Deprecated auth library
...

# 7. Prioritize cross-cutting concerns
$ trc ready --by-priority
```

### Key Benefits

- **Systematic discovery** - Track issues as you find them
- **Context preservation** - Link related issues together
- **Prioritization** - See critical vs. nice-to-have work
- **Incremental** - Add traces as you explore, no upfront planning needed

---

## Use Case 4: Reorganizing Work Structure

### Scenario

You're midway through implementation when new information changes your approach, requiring work reorganization.

### Workflow

```bash
# Initial plan
$ trc tree myapp-auth123
myapp-auth123 Add authentication
├─ myapp-oauth111 Implement OAuth
│  ├─ myapp-google222 Google OAuth
│  └─ myapp-github333 GitHub OAuth
└─ myapp-session444 Session management

# New information: Need to support enterprise SAML
You: "We need to support SAML for enterprise customers"

# Problem: OAuth and SAML have different architectures
# Need to refactor the structure

# Claude reorganizes:
Claude: trace create "Authentication providers" --parent myapp-auth123
→ myapp-providers555

# Move OAuth under providers
Claude: trace reparent myapp-oauth111 --parent myapp-providers555

# Add SAML as sibling to OAuth
Claude: trace create "Implement SAML SSO" --parent myapp-providers555
→ myapp-saml666

# Session management is now blocked by provider choice
Claude: trace update myapp-session444 --depends-on myapp-providers555

# New structure
$ trc tree myapp-auth123
myapp-auth123 Add authentication
├─ myapp-providers555 Authentication providers
│  ├─ myapp-oauth111 Implement OAuth
│  │  ├─ myapp-google222 Google OAuth
│  │  └─ myapp-github333 GitHub OAuth
│  └─ myapp-saml666 Implement SAML SSO
└─ myapp-session444 Session management [blocked by myapp-providers555]

# Reprioritize
Claude: trace update myapp-providers555 --priority 0
Claude: trace update myapp-session444 --priority 1
```

### Key Benefits

- **Fluid structure** - Easy to reorganize without recreating everything
- **Preserve history** - Issues keep their IDs and context
- **Dependency tracking** - Blocked relationships update automatically
- **No waste** - Reuse existing work, just restructure

---

## Use Case 5: Cross-Project Work

### Scenario

You need to implement a feature in one project that depends on changes in another project.

### Workflow

```bash
# Working on app that uses a library you maintain
$ cd ~/Repos/myapp

You: "I need to add real-time notifications"

Claude: trace create "Add real-time notifications" --project myapp
→ myapp-notif123

Claude: "This requires WebSocket support in mylib"

# Create issue in the library project
Claude: trace create "Add WebSocket server support" --project mylib
→ mylib-ws456

# Link the dependency across projects
Claude: trace update myapp-notif123 --depends-on mylib-ws456

# View cross-project dependencies
$ trc show myapp-notif123
ID: myapp-notif123
Project: myapp
Title: Add real-time notifications
Status: blocked
Depends on:
  - mylib-ws456 [open] Add WebSocket server support (project: mylib)

# Work on library first
$ cd ~/Repos/mylib
$ trc list --current-project
mylib-ws456 [P1] Add WebSocket server support

# After completing library work
$ trc close mylib-ws456

# App work automatically unblocked
$ cd ~/Repos/myapp
$ trc ready
myapp-notif123 [P1] Add real-time notifications ✓ now ready
```

### Key Benefits

- **Cross-project visibility** - See dependencies across all projects
- **Automatic blocking** - Can't start app work until library ready
- **Unified planning** - Plan work across your entire ecosystem
- **Priority clarity** - Know which project to work on first

---

## Use Case 6: Weekly Planning Across Projects

### Scenario

Monday morning - you want to see top priorities across all your projects.

### Workflow

```bash
# Global ready work view
$ trc ready --all --by-project --limit 10

=== myapp (3 ready) ===
myapp-abc123 [P0] Fix login security vulnerability
myapp-def456 [P1] Add user dashboard
myapp-ghi789 [P2] Update dependencies

=== mylib (2 ready) ===
mylib-jkl012 [P0] Memory leak in cache
mylib-mno345 [P1] Add new API endpoint

=== trace (1 ready) ===
trace-pqr678 [P1] Implement tree visualization

# Focus on P0 items first
$ trc list --priority 0 --all
myapp-abc123 [P0] Fix login security vulnerability
mylib-jkl012 [P0] Memory leak in cache

# Work on security fix first
$ cd ~/Repos/myapp
$ trc show myapp-abc123
# Start work...
```

### Key Benefits

- **Unified view** - All projects in one place
- **Priority-driven** - See what matters most
- **Context switching** - Easy to move between projects
- **Weekly rhythm** - Quick overview of the week ahead

---

## AI Agent Requirements

Based on these use cases, trace must support:

### Easy Creation
```bash
trc create "title" [--parent ID] [--priority N] [--project name]
```

### Easy Updates
```bash
trc update ID [--priority N] [--status STATUS] [--description TEXT]
trc close ID
```

### Easy Reorganization
```bash
trc reparent ID --parent PARENT_ID
trc move ID --to-project PROJECT
trc update ID --depends-on DEPENDENCY_ID
```

### Easy Querying
```bash
trc list [--project NAME | --all] [--priority N] [--status STATUS]
trc ready [--all] [--by-project] [--limit N]
trc tree ID
trc show ID
```

### AI-Friendly Output
- Parseable formats (JSON flag?)
- Concise IDs (6 chars)
- Clear status indicators
- Relationship visualization

---

## Summary

Trace optimizes for:
1. **Iterative planning** - Create and refine as you go
2. **Conceptual exploration** - Use traces to think through ideas
3. **Discovery** - Find and track work while exploring code
4. **Reorganization** - Adapt structure as understanding evolves
5. **Cross-project** - Manage dependencies across your ecosystem
6. **AI-native** - Designed for programmatic use by agents

The key insight: **Work structure should be fluid, not rigid**. Trace makes reorganization trivial so plans can evolve naturally.
