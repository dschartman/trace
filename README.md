# Trace

> A minimal distributed issue tracker for AI agent workflows

Trace is a cross-project issue tracker designed for iterative planning and reorganization with AI assistants like Claude Code. It combines the brilliant ideas from [Beads](https://github.com/steveyegge/beads) with cross-project support and reorganization-first design.

## Why Trace?

**Problem**: AI agents need to break down work, track progress across sessions, and reorganize plans as understanding evolves - but traditional issue trackers are rigid and heavyweight.

**Solution**: Trace provides:
- **Cross-project tracking** - One view of work across all your projects
- **Flexible hierarchies** - Natural parent-child trees, no enforced levels
- **Easy reorganization** - Move, reparent, restructure as plans evolve
- **Git-friendly** - JSONL files that merge cleanly
- **AI-native** - Simple CLI optimized for programmatic use

## Installation

Trace requires Python 3.12+ and uses [uv](https://github.com/astral-sh/uv) for dependency management.

### Install as a Global Tool

For regular use across all your projects:

```bash
# Clone the repository
git clone https://github.com/dschartman/trace.git
cd trace

# Install globally using uv
uv tool install .
```

This makes the `trc` command available system-wide.

### Install for Development

If you want to contribute or modify trace while having it available globally:

```bash
# Clone the repository
git clone https://github.com/dschartman/trace.git
cd trace

# Install in editable mode
uv tool install --editable .
```

With editable mode, changes you make to the code are immediately reflected in the `trc` command without reinstalling.

### Verify Installation

```bash
trc --help
```

## Quick Start

```bash
# Initialize trace in a project
$ cd ~/Repos/myapp
$ trc init
Initialized project: myapp

# Create an issue (description required for context)
$ trc create "Add authentication system" --description "OAuth2 + Google SSO"
Created myapp-abc123: Add authentication system

# Break it down
$ trc create "Research OAuth libraries" --description "Compare passport vs oauth2orize" --parent myapp-abc123
$ trc create "Implement Google login" --description "Handle token exchange and validation" --parent myapp-abc123
$ trc create "Add tests" --description "Cover login, logout, token refresh flows" --parent myapp-abc123

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

## For AI Agents

Trace is designed specifically for AI workflows. Run `trc guide` to get integration instructions for your CLAUDE.md file.

**Key principles for agents:**
- Use trace proactively - don't wait for users to ask
- Prefer trace over TodoWrite for non-trivial work
- Start with natural granularity, reorganize as understanding evolves
- Think of trace as your external memory across sessions

See [AI Agent Integration Guide](docs/ai-agent-guide.md) for comprehensive guidance.

## Key Features

### Cross-Project Dependencies

```bash
# Working in your app
$ cd ~/Repos/myapp
$ trc create "Use new API endpoint" --description "Migrate from v1 to v2 API" --depends-on mylib-xyz999
Created myapp-abc123 (blocked by mylib-xyz999)

# View ready work across all projects
$ trc ready --project any
mylib-xyz999 [P1] Add new API endpoint
   └─ blocks: myapp-abc123
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
$ trc create "Explore distributed caching" --description "Research Redis vs Memcached for session storage"
Created default-abc123 in default project

# Later, promote to real project
$ trc move default-abc123 --to-project distcache
```

### Auto-Detection

```bash
# Automatically detects project from git repo
$ cd ~/Repos/myapp
$ trc create "Fix bug" --description "Button click not registering on mobile"  # Auto-tagged as project: myapp

# Override when needed
$ trc create "Task" --description "Context" --project other-project
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
| **Language** | Go | Python |
| **Structure** | Epic/Feature/Task | Flat parent-child |
| **Focus** | AI memory per-project | Cross-project + reorganization |
| **Default project** | No | Yes (discovery inbox) |

Beads is excellent for single-project tracking. Trace optimizes for multi-project workflows and fluid reorganization.

## Status

Core implementation is complete with 156 passing tests and ~95% code coverage. All major features are functional including cross-project dependencies, reorganization, and automatic JSONL sync.

**Future enhancements**: MCP server for Claude Code integration, advanced queries, time tracking, bulk operations.

## Documentation

- **[AI Agent Integration Guide](docs/ai-agent-guide.md)** - Comprehensive guide for AI integration
- **[Use Cases](docs/use-cases.md)** - Real-world workflows and examples
- **[Key Features](docs/key-features.md)** - Technical features and implementation
- **[CLI Design](docs/cli-design.md)** - Complete command reference
- **[Product Vision](docs/product-vision.md)** - Goals, principles, and philosophy

## License

MIT

## Contributing

This is primarily a personal project, but ideas and feedback are welcome via issues.

## Acknowledgments

- [Beads](https://github.com/beadproject/bead) - The brilliant foundation this builds upon
- Claude Code - The AI workflow this optimizes for
