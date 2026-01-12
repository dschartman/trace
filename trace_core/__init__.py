"""Trace - Minimal distributed issue tracker for AI agent workflows.

This package provides the core functionality for the trace issue tracker.
Import from here for the public API.
"""

from trace_core.exceptions import IDCollisionError, LockError
from trace_core.constants import (
    VALID_STATUSES,
    VALID_DEPENDENCY_TYPES,
    PRIORITY_RANGE,
    MAX_ID_RETRIES,
    LOCK_TIMEOUT,
    HASH_LENGTH,
    BASE36_CHARS,
)
from trace_core.utils import (
    get_iso_timestamp,
    file_lock,
    sanitize_project_name,
)
from trace_core.ids import generate_id, _to_base36
from trace_core.db import (
    init_database,
    get_trace_home,
    get_db_path,
    get_db,
    get_lock_path,
)
from trace_core.projects import (
    detect_project,
    is_project_initialized,
    register_project,
    resolve_project,
    get_project_path,
)
from trace_core.issues import (
    create_issue,
    get_issue,
    list_issues,
    update_issue,
    close_issue,
)
from trace_core.dependencies import (
    add_dependency,
    remove_dependency,
    get_dependencies,
    get_children,
    get_blockers,
    is_blocked,
    has_open_children,
)
from trace_core.sync import (
    get_last_sync_time,
    set_last_sync_time,
    sync_project,
    export_to_jsonl,
    import_from_jsonl,
)
from trace_core.reorganization import (
    detect_cycle,
    reparent_issue,
    move_issue,
)
from trace_core.comments import (
    add_comment,
    get_comments,
)
from trace_core.contamination import (
    validate_issue_belongs_to_project,
    extract_project_name_from_id,
    extract_project_name_from_issue_id,
    find_project_by_name,
    repair_contaminated_issues,
)
from trace_core.cli import app, main

__all__ = [
    # Exceptions
    "IDCollisionError",
    "LockError",
    # Constants
    "VALID_STATUSES",
    "VALID_DEPENDENCY_TYPES",
    "PRIORITY_RANGE",
    "MAX_ID_RETRIES",
    "LOCK_TIMEOUT",
    "HASH_LENGTH",
    "BASE36_CHARS",
    # Utils
    "get_iso_timestamp",
    "file_lock",
    "sanitize_project_name",
    # IDs
    "generate_id",
    "_to_base36",
    # Database
    "init_database",
    "get_trace_home",
    "get_db_path",
    "get_db",
    "get_lock_path",
    # Projects
    "detect_project",
    "is_project_initialized",
    "register_project",
    "resolve_project",
    "get_project_path",
    # Issues
    "create_issue",
    "get_issue",
    "list_issues",
    "update_issue",
    "close_issue",
    # Dependencies
    "add_dependency",
    "remove_dependency",
    "get_dependencies",
    "get_children",
    "get_blockers",
    "is_blocked",
    "has_open_children",
    # Sync
    "get_last_sync_time",
    "set_last_sync_time",
    "sync_project",
    "export_to_jsonl",
    "import_from_jsonl",
    # Reorganization
    "detect_cycle",
    "reparent_issue",
    "move_issue",
    # Comments
    "add_comment",
    "get_comments",
    # Contamination
    "validate_issue_belongs_to_project",
    "extract_project_name_from_id",
    "extract_project_name_from_issue_id",
    "find_project_by_name",
    "repair_contaminated_issues",
    # CLI
    "app",
    "main",
]
