# Trace

> A minimal distributed issue tracker for AI agent workflows

Trace is a cross-project issue tracker designed for iterative planning and reorganization with AI assistants like Claude Code. It combines the brilliant ideas from [Beads](https://github.com/steveyegge/beads) with cross-project support and reorganization-first design.

**Command**: `trc` (the command-line tool is called `trc` for brevity)

## Why Trace?

**Problem**: AI agents need to break down work, track progress across sessions, and reorganize plans as understanding evolves - but traditional issue trackers are repo-specific, rigid, and heavyweight.

**Solution**: Trace provides:
- **Cross-project tracking** - One view of work across all your projects
- **Flexible hierarchies** - Natural parent-child trees, no enforced levels
- **Easy reorganization** - Move, reparent, restructure as plans evolve
- **Git-friendly** - JSONL files that merge cleanly
- **AI-native** - Simple CLI optimized for programmatic use

## Quick Start

```bash
# Initialize trace in a project
$ cd ~/Repos/myapp
$ trc init
Initialized project: myapp

# Create an issue
$ trc create "Add authentication system"
Created myapp-abc123: Add authentication system

# Break it down
$ trc create "Research OAuth libraries" --parent myapp-abc123
$ trc create "Implement Google login" --parent myapp-abc123
$ trc create "Add tests" --parent myapp-abc123

# View the tree
$ trc tree myapp-abc123
myapp-abc123 Add authentication system [open]
 myapp-def456 Research OAuth libraries [open]
 myapp-ghi789 Implement Google login [open]
 myapp-jkl012 Add tests [open]

# See what's ready to work on
$ trc ready
myapp-def456 [P2] Research OAuth libraries
```

## Key Features

### Cross-Project Dependencies

```bash
# Working in your app
$ cd ~/Repos/myapp
$ trc create "Use new API endpoint" --depends-on mylib-xyz999
Created myapp-abc123 (blocked by mylib-xyz999)

# View ready work across all projects
$ trc ready --all --by-project
=== mylib (1 ready) ===
mylib-xyz999 [P1] Add new API endpoint

=== myapp (0 ready) ===
(myapp-abc123 blocked by mylib-xyz999)
```

### Flexible Reorganization

```bash
# New information changes your approach
$ trc reparent myapp-abc123 --parent myapp-xyz999

# Move work between projects
$ trc move default-abc123 --to-project myapp

# Add/remove dependencies
$ trc update myapp-abc123 --depends-on mylib-def456
```

### Default Project (Discovery Inbox)

```bash
# Before creating a project
$ trc create "Explore distributed caching"
Created default-abc123 in default project

# Later, promote to real project
$ trc move default-abc123 --to-project distcache
```

### Auto-Detection

```bash
# Automatically detects project from git repo
$ cd ~/Repos/myapp
$ trc create "Fix bug"  # Auto-tagged as project: myapp

# Override when needed
$ trc create "Task" --project other-project
```

## Architecture

Trace uses a hybrid storage model:

```
~/.trace/
├── trace.db              # Central SQLite database (all projects)
├── default/              # Default project (discovery inbox)
│   └── .trace/issues.jsonl
└── .lock                 # File lock for sync

~/Repos/myapp/
└── .trace/
    └── issues.jsonl      # Project-specific JSONL (git-friendly)
```

**Benefits**:
- Central DB for fast cross-project queries
- Per-project JSONL for git-friendly storage
- Automatic sync between them
- JSONL files merge cleanly in git

## Documentation

- **[Product Vision](docs/product-vision.md)** - Goals, principles, and philosophy
- **[Use Cases](docs/use-cases.md)** - Real-world workflows and examples
- **[Key Features](docs/key-features.md)** - Technical features and implementation
- **[CLI Design](docs/cli-design.md)** - Complete command reference
- **[Technical Design](MINIMAL_BEADS_DESIGN.md)** - Original design proposal

## Use Cases

### 1. Feature Planning with AI

AI breaks down features iteratively, creating parent-child structures that evolve as implementation progresses.

```bash
You: "Add user authentication"
Claude: Creates parent + initial children
        Refines breakdown as it learns more
        Reorganizes when assumptions change
```

### 2. Exploring Ideas

Use trace to structure thinking before committing to a project.

```bash
# Explore concept in default project
$ trc create "Distributed cache system"
$ trc create "Research consistency models" --parent ...

# When ready, promote to real project
$ trc move default-* --to-project distcache
```

### 3. Discovering Work

AI explores a codebase and creates issues for problems found.

```bash
# While reading code
Claude: trc create "Security: plaintext passwords"
Claude: trc create "Bug: session timeout not enforced"
Claude: trc create "Tech debt: deprecated library"
```

### 4. Cross-Project Coordination

Track dependencies across your entire project ecosystem.

```bash
# App depends on library changes
$ trc create "Add notifications" --project myapp \
    --depends-on mylib-websockets

$ trc ready --all  # Shows library work must come first
```

## Design Principles

1. **Simple over flexible** - Sensible defaults, minimal configuration
2. **Fast over perfect** - <100ms for most operations
3. **Git-native** - Work with git, not against it
4. **AI-first** - Optimize for programmatic use
5. **Reorganization-friendly** - Structure is fluid, not rigid
6. **Cross-project aware** - Projects are connected, not isolated

## Comparison to Beads

Trace is heavily inspired by [Beads](https://github.com/beadproject/bead) but differs in:

| Feature | Beads | Trace |
|---------|-------|-------|
| **Scope** | Per-repository | Cross-project |
| **Language** | Go | Python (~500 lines) |
| **Structure** | Epic/Feature/Task | Flat parent-child |
| **Focus** | AI memory per-project | Cross-project + reorganization |
| **Default project** | No | Yes (discovery inbox) |

Beads is excellent for single-project tracking. Trace optimizes for multi-project workflows and fluid reorganization.

## Status

**Current**: Core implementation complete ✅

**What Works**:
- ✅ All core functionality (156 tests passing)
- ✅ Hash-based ID generation with collision detection
- ✅ Project detection from git repositories
- ✅ Full CRUD operations (create, read, update, delete, close)
- ✅ Dependency management (parent-child, blocks, related)
- ✅ JSONL export/import with automatic sync
- ✅ File locking for concurrent access safety
- ✅ Reorganization commands (reparent, move)
- ✅ Query commands (list, ready, tree, show)
- ✅ Complete CLI with all flags

**Test Coverage**:
- 156 tests passing
- ~95% code coverage for core functionality
- 4 end-to-end integration tests
- All major workflows validated

**Future Enhancements**:
- MCP server for Claude Code integration
- Advanced queries and filters
- Time tracking
- Bulk operations
- Web UI (optional)

## Philosophy

Trace treats work structure as **fluid, not rigid**. Plans change as understanding evolves. New information emerges. Assumptions break down. Trace makes reorganization trivial so your work structure can adapt naturally.

Traditional issue trackers enforce rigid hierarchies (epic → feature → story → task). Trace provides flexible parent-child relationships that match how work actually decomposes - sometimes 2 levels, sometimes 5, whatever makes sense.

The key insight: **Make reorganization so easy that structure becomes a tool for thinking, not a constraint**.

## License

MIT

## Contributing

This is primarily a personal project, but ideas and feedback are welcome via issues.

## Acknowledgments

- [Beads](https://github.com/beadproject/bead) - The brilliant foundation this builds upon
- Claude Code - The AI workflow this optimizes for
