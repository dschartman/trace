"""Tests for query functions (tree, ready work)."""

import pytest


def test_tree_shows_parent_with_children(db_connection):
    """Should display parent-child hierarchy."""
    from trace import create_issue, add_dependency, get_children

    parent = create_issue(db_connection, "/path/to/myapp", "myapp", "Parent Issue")
    child1 = create_issue(db_connection, "/path/to/myapp", "myapp", "Child 1")
    child2 = create_issue(db_connection, "/path/to/myapp", "myapp", "Child 2")

    add_dependency(db_connection, child1["id"], parent["id"], "parent")
    add_dependency(db_connection, child2["id"], parent["id"], "parent")

    children = get_children(db_connection, parent["id"])

    assert len(children) == 2
    child_ids = {c["id"] for c in children}
    assert child1["id"] in child_ids
    assert child2["id"] in child_ids


def test_tree_handles_deep_nesting(db_connection):
    """Should handle multiple levels of parent-child relationships."""
    from trace import create_issue, add_dependency, get_children

    # Create chain: level0 -> level1 -> level2 -> level3
    issues = []
    for i in range(4):
        issue = create_issue(db_connection, "/path/to/myapp", "myapp", f"Level {i}")
        issues.append(issue)

        # Link to parent
        if i > 0:
            add_dependency(db_connection, issue["id"], issues[i - 1]["id"], "parent")

    # Verify chain
    for i in range(3):
        children = get_children(db_connection, issues[i]["id"])
        assert len(children) == 1
        assert children[0]["id"] == issues[i + 1]["id"]

    # Leaf node has no children
    leaf_children = get_children(db_connection, issues[3]["id"])
    assert len(leaf_children) == 0


def test_tree_handles_multiple_children_per_parent(db_connection):
    """Should handle parents with many children."""
    from trace import create_issue, add_dependency, get_children

    parent = create_issue(db_connection, "/path/to/myapp", "myapp", "Parent")

    # Create 5 children
    child_ids = []
    for i in range(5):
        child = create_issue(db_connection, "/path/to/myapp", "myapp", f"Child {i}")
        child_ids.append(child["id"])
        add_dependency(db_connection, child["id"], parent["id"], "parent")

    children = get_children(db_connection, parent["id"])

    assert len(children) == 5
    returned_ids = {c["id"] for c in children}
    assert returned_ids == set(child_ids)


def test_tree_cross_project_parent_child(db_connection):
    """Should support parent-child across different projects."""
    from trace import create_issue, add_dependency, get_children

    lib_parent = create_issue(db_connection, "/path/to/mylib", "mylib", "Lib Feature")
    app_child = create_issue(db_connection, "/path/to/myapp", "myapp", "App Feature")

    add_dependency(db_connection, app_child["id"], lib_parent["id"], "parent")

    children = get_children(db_connection, lib_parent["id"])

    assert len(children) == 1
    assert children[0]["id"] == app_child["id"]
    assert children[0]["project_id"] == "/path/to/myapp"


def test_ready_returns_unblocked_issues(db_connection):
    """Should return issues without blocking dependencies."""
    from trace import create_issue, is_blocked

    ready1 = create_issue(db_connection, "/path/to/myapp", "myapp", "Ready 1")
    ready2 = create_issue(db_connection, "/path/to/myapp", "myapp", "Ready 2")

    assert not is_blocked(db_connection, ready1["id"])
    assert not is_blocked(db_connection, ready2["id"])


def test_ready_excludes_blocked_issues(db_connection):
    """Should exclude issues blocked by open dependencies."""
    from trace import create_issue, add_dependency, is_blocked

    blocker = create_issue(db_connection, "/path/to/myapp", "myapp", "Blocker", status="open")
    blocked = create_issue(db_connection, "/path/to/myapp", "myapp", "Blocked")

    add_dependency(db_connection, blocked["id"], blocker["id"], "blocks")

    assert not is_blocked(db_connection, blocker["id"])  # Blocker itself is not blocked
    assert is_blocked(db_connection, blocked["id"])  # Blocked by open blocker


def test_ready_includes_when_blockers_closed(db_connection):
    """Should include issues whose blocking dependencies are closed."""
    from trace import create_issue, add_dependency, is_blocked, close_issue

    blocker = create_issue(db_connection, "/path/to/myapp", "myapp", "Blocker")
    dependent = create_issue(db_connection, "/path/to/myapp", "myapp", "Dependent")

    add_dependency(db_connection, dependent["id"], blocker["id"], "blocks")

    # Initially blocked
    assert is_blocked(db_connection, dependent["id"])

    # Close blocker
    close_issue(db_connection, blocker["id"])

    # Now not blocked
    assert not is_blocked(db_connection, dependent["id"])


def test_ready_parent_child_does_not_block(db_connection):
    """Parent-child relationships should not block ready work."""
    from trace import create_issue, add_dependency, is_blocked

    parent = create_issue(db_connection, "/path/to/myapp", "myapp", "Parent", status="open")
    child = create_issue(db_connection, "/path/to/myapp", "myapp", "Child")

    add_dependency(db_connection, child["id"], parent["id"], "parent")

    # Parent-child doesn't block - only 'blocks' type does
    assert not is_blocked(db_connection, child["id"])


def test_ready_related_does_not_block(db_connection):
    """Related dependencies should not block ready work."""
    from trace import create_issue, add_dependency, is_blocked

    issue1 = create_issue(db_connection, "/path/to/myapp", "myapp", "Issue 1", status="open")
    issue2 = create_issue(db_connection, "/path/to/myapp", "myapp", "Issue 2")

    add_dependency(db_connection, issue2["id"], issue1["id"], "related")

    # Related doesn't block - only 'blocks' type does
    assert not is_blocked(db_connection, issue2["id"])


def test_ready_multiple_blockers(db_connection):
    """Should be blocked if ANY blocker is open."""
    from trace import create_issue, add_dependency, is_blocked, close_issue

    blocker1 = create_issue(db_connection, "/path/to/myapp", "myapp", "Blocker 1", status="open")
    blocker2 = create_issue(db_connection, "/path/to/myapp", "myapp", "Blocker 2", status="open")
    blocked = create_issue(db_connection, "/path/to/myapp", "myapp", "Blocked")

    add_dependency(db_connection, blocked["id"], blocker1["id"], "blocks")
    add_dependency(db_connection, blocked["id"], blocker2["id"], "blocks")

    # Blocked by both
    assert is_blocked(db_connection, blocked["id"])

    # Close one blocker
    close_issue(db_connection, blocker1["id"])

    # Still blocked by blocker2
    assert is_blocked(db_connection, blocked["id"])

    # Close second blocker
    close_issue(db_connection, blocker2["id"])

    # Now ready
    assert not is_blocked(db_connection, blocked["id"])


def test_ready_cross_project_blocker(db_connection):
    """Should respect blocking dependencies across projects."""
    from trace import create_issue, add_dependency, is_blocked

    lib_blocker = create_issue(db_connection, "/path/to/mylib", "mylib", "Lib Task", status="open")
    app_blocked = create_issue(db_connection, "/path/to/myapp", "myapp", "App Task")

    add_dependency(db_connection, app_blocked["id"], lib_blocker["id"], "blocks")

    assert is_blocked(db_connection, app_blocked["id"])


def test_ready_list_filters_correctly(db_connection):
    """Should correctly filter ready vs blocked issues in a list."""
    from trace import create_issue, add_dependency, list_issues, is_blocked

    ready1 = create_issue(db_connection, "/path/to/myapp", "myapp", "Ready 1", priority=0)
    ready2 = create_issue(db_connection, "/path/to/myapp", "myapp", "Ready 2", priority=1)
    blocker = create_issue(db_connection, "/path/to/myapp", "myapp", "Blocker", status="open")
    blocked = create_issue(db_connection, "/path/to/myapp", "myapp", "Blocked", priority=0)

    add_dependency(db_connection, blocked["id"], blocker["id"], "blocks")

    # Get all open issues
    all_issues = list_issues(db_connection, project_id="/path/to/myapp", status="open")
    assert len(all_issues) == 4

    # Filter to ready
    ready_issues = [i for i in all_issues if not is_blocked(db_connection, i["id"])]

    assert len(ready_issues) == 3
    ready_ids = {i["id"] for i in ready_issues}
    assert ready1["id"] in ready_ids
    assert ready2["id"] in ready_ids
    assert blocker["id"] in ready_ids
    assert blocked["id"] not in ready_ids


def test_ready_respects_priority_order(db_connection):
    """Ready issues should be sortable by priority."""
    from trace import create_issue, list_issues, is_blocked

    p2_issue = create_issue(db_connection, "/path/to/myapp", "myapp", "P2 Issue", priority=2)
    p0_issue = create_issue(db_connection, "/path/to/myapp", "myapp", "P0 Issue", priority=0)
    p1_issue = create_issue(db_connection, "/path/to/myapp", "myapp", "P1 Issue", priority=1)

    # Get issues (already sorted by priority)
    issues = list_issues(db_connection, project_id="/path/to/myapp", status="open")

    # Filter ready (all are ready in this case)
    ready = [i for i in issues if not is_blocked(db_connection, i["id"])]

    # Should be sorted by priority (already done by list_issues)
    assert ready[0]["priority"] == 0
    assert ready[1]["priority"] == 1
    assert ready[2]["priority"] == 2


def test_has_open_children(db_connection):
    """Should detect if parent has open children."""
    from trace import create_issue, add_dependency, has_open_children, close_issue

    parent = create_issue(db_connection, "/path/to/myapp", "myapp", "Parent")
    child1 = create_issue(db_connection, "/path/to/myapp", "myapp", "Child 1", status="open")
    child2 = create_issue(db_connection, "/path/to/myapp", "myapp", "Child 2", status="closed")

    add_dependency(db_connection, child1["id"], parent["id"], "parent")
    add_dependency(db_connection, child2["id"], parent["id"], "parent")

    # Has open children
    assert has_open_children(db_connection, parent["id"])

    # Close the open child
    close_issue(db_connection, child1["id"])

    # No more open children
    assert not has_open_children(db_connection, parent["id"])


def test_tree_with_mixed_statuses(db_connection):
    """Tree should show issues with different statuses."""
    from trace import create_issue, add_dependency, get_children

    parent = create_issue(db_connection, "/path/to/myapp", "myapp", "Parent", status="in_progress")
    child_open = create_issue(db_connection, "/path/to/myapp", "myapp", "Open Child", status="open")
    child_closed = create_issue(
        db_connection, "/path/to/myapp", "myapp", "Closed Child", status="closed"
    )

    add_dependency(db_connection, child_open["id"], parent["id"], "parent")
    add_dependency(db_connection, child_closed["id"], parent["id"], "parent")

    children = get_children(db_connection, parent["id"])

    assert len(children) == 2
    statuses = {c["status"] for c in children}
    assert "open" in statuses
    assert "closed" in statuses
