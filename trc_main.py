"""Trace - Minimal distributed issue tracker for AI agent workflows.

This is the main entry point for the trc command. All functionality is
implemented in the trace/ package. This file re-exports for backward
compatibility with existing tests.
"""

# Re-export everything from the trace package for backward compatibility
# The trace package's __all__ defines all public symbols
from trace_core import *  # noqa: F401,F403

if __name__ == "__main__":
    main()  # noqa: F405
