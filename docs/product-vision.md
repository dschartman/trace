# Trace Product Vision

## Overview

Trace is a **minimal distributed issue tracker** designed for AI agent workflows, specifically optimized for iterative planning, exploration, and reorganization with Claude Code and other AI assistants.

## The Problem

AI agents need to:
- Break down complex work across multiple sessions and context windows
- Discover and track work across multiple projects
- Iteratively refine plans as new information emerges
- Reorganize work structures when assumptions change
- Maintain context across conversations and git operations

Traditional issue trackers fail because they:
- Are repo-specific (can't track cross-project dependencies)
- Require rigid categorization (epic/feature/story) that doesn't match natural decomposition
- Have complex UIs optimized for humans, not programmatic access
- Don't integrate naturally with git workflows
- Make reorganization difficult and heavyweight

## The Solution

Trace provides:

1. **Cross-project tracking** - One central view of work across all your projects
2. **Flexible hierarchies** - Natural parent-child relationships without enforced levels
3. **Git-friendly storage** - JSONL files per project that merge cleanly
4. **AI-native interface** - Simple CLI optimized for programmatic use
5. **Easy reorganization** - Move, reparent, and restructure work as understanding evolves

## Core Identity

**Trace is a project and work tracker**, not a universal task manager. Its primary focus is:

- Software projects and technical work
- AI-assisted planning and decomposition
- Cross-project coordination
- Iterative refinement of work breakdown

It *can* function as a task tracker, but that's not the primary goal.

## Key Differentiators from Beads

While heavily inspired by Beads' brilliant design, trace differs in:

1. **Cross-project by default** - Central database with per-project JSONL files
2. **Python-based** - Simpler to modify and extend for personal needs
3. **Reorganization-first** - Optimized for fluid work structures, not static plans
4. **Default project** - Discovery inbox for pre-project work
5. **Minimal** - Even simpler than Beads, ~500 lines of Python

## Success Criteria

Trace succeeds when:

1. **AI agents naturally use it** - Claude Code creates and updates traces without prompting
2. **Plans stay synchronized** - Work tracked in trace matches actual project state
3. **Reorganization is trivial** - Changing work structure takes seconds, not minutes
4. **Cross-project clarity** - Can instantly see "what's most important this week" across all projects
5. **Git workflow integrates** - JSONL files merge cleanly, no manual conflict resolution needed

## Non-Goals

Trace explicitly does NOT aim to:

- Replace project management tools (Jira, Linear, etc.) for teams
- Provide a web UI or rich visualizations
- Support complex workflows (approval chains, SLA tracking, etc.)
- Be a general-purpose database or knowledge base
- Handle binary attachments or rich media

## Target Users

**Primary**: Individual developers working with AI assistants on multiple personal projects

**Secondary**: Small teams who value simplicity and git-native workflows over enterprise features

## Design Principles

1. **Simple over flexible** - Fixed 6-char IDs, no configuration knobs
2. **Fast over perfect** - Subprocess calls are fine if <100ms
3. **Git-native** - Work with git, not against it
4. **AI-first** - Optimize for programmatic use, humans benefit too
5. **Reorganization-friendly** - Structure should be fluid, not rigid
6. **Cross-project aware** - Projects are connected, not isolated

## Implementation Philosophy

- Single file implementation (~500-600 lines)
- SQLite + JSONL dual storage
- No daemon (initially)
- Lazy sync on every operation
- Hash-based collision-resistant IDs
- Flat parent-child trees (no enforced levels)

## Timeline & Phases

**Phase 1** (Current): Core functionality
- Project detection and registry
- Issue CRUD operations
- Parent-child relationships
- Basic reorganization (move, reparent)
- Cross-project queries

**Phase 2**: AI Integration
- MCP server for Claude Code
- Rich context for AI agents
- Bulk operations

**Phase 3**: Advanced Features
- Cycle detection
- Advanced queries and filters
- Performance optimization for 1000+ issues

**Phase 4** (Maybe): Enhancements
- Time tracking
- Git hook integration
- Export formats
