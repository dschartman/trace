"""Tests for dependency management (parent-child, blocks, related)."""

import pytest


def test_add_parent_dependency(db_connection):
    """Should create parent-child dependency."""
    from trace import create_issue, add_dependency, get_dependencies

    parent = create_issue(db_connection, "/path/to/myapp", "myapp", "Parent")
    child = create_issue(db_connection, "/path/to/myapp", "myapp", "Child")

    add_dependency(db_connection, child["id"], parent["id"], "parent")

    deps = get_dependencies(db_connection, child["id"])

    assert len(deps) == 1
    assert deps[0]["depends_on_id"] == parent["id"]
    assert deps[0]["type"] == "parent"


def test_add_blocks_dependency(db_connection):
    """Should create blocks dependency."""
    from trace import create_issue, add_dependency, get_dependencies

    blocker = create_issue(db_connection, "/path/to/myapp", "myapp", "Blocker")
    blocked = create_issue(db_connection, "/path/to/myapp", "myapp", "Blocked")

    add_dependency(db_connection, blocked["id"], blocker["id"], "blocks")

    deps = get_dependencies(db_connection, blocked["id"])

    assert len(deps) == 1
    assert deps[0]["depends_on_id"] == blocker["id"]
    assert deps[0]["type"] == "blocks"


def test_add_related_dependency(db_connection):
    """Should create related dependency."""
    from trace import create_issue, add_dependency, get_dependencies

    issue1 = create_issue(db_connection, "/path/to/myapp", "myapp", "Issue 1")
    issue2 = create_issue(db_connection, "/path/to/myapp", "myapp", "Issue 2")

    add_dependency(db_connection, issue1["id"], issue2["id"], "related")

    deps = get_dependencies(db_connection, issue1["id"])

    assert len(deps) == 1
    assert deps[0]["type"] == "related"


def test_add_cross_project_dependency(db_connection):
    """Should allow dependencies across projects."""
    from trace import create_issue, add_dependency, get_dependencies

    lib_issue = create_issue(db_connection, "/path/to/mylib", "mylib", "Add API")
    app_issue = create_issue(db_connection, "/path/to/myapp", "myapp", "Use API")

    add_dependency(db_connection, app_issue["id"], lib_issue["id"], "blocks")

    deps = get_dependencies(db_connection, app_issue["id"])

    assert len(deps) == 1
    assert deps[0]["depends_on_id"] == lib_issue["id"]


def test_add_multiple_dependencies(db_connection):
    """Should support multiple dependencies for one issue."""
    from trace import create_issue, add_dependency, get_dependencies

    parent = create_issue(db_connection, "/path/to/myapp", "myapp", "Parent")
    blocker = create_issue(db_connection, "/path/to/myapp", "myapp", "Blocker")
    child = create_issue(db_connection, "/path/to/myapp", "myapp", "Child")

    add_dependency(db_connection, child["id"], parent["id"], "parent")
    add_dependency(db_connection, child["id"], blocker["id"], "blocks")

    deps = get_dependencies(db_connection, child["id"])

    assert len(deps) == 2
    dep_types = {d["type"] for d in deps}
    assert "parent" in dep_types
    assert "blocks" in dep_types


def test_add_dependency_validates_type(db_connection):
    """Should reject invalid dependency types."""
    from trace import create_issue, add_dependency

    issue1 = create_issue(db_connection, "/path/to/myapp", "myapp", "Issue 1")
    issue2 = create_issue(db_connection, "/path/to/myapp", "myapp", "Issue 2")

    with pytest.raises(ValueError, match="Invalid dependency type"):
        add_dependency(db_connection, issue1["id"], issue2["id"], "invalid")


def test_add_dependency_prevents_duplicates(db_connection):
    """Should not create duplicate dependencies."""
    from trace import create_issue, add_dependency, get_dependencies

    parent = create_issue(db_connection, "/path/to/myapp", "myapp", "Parent")
    child = create_issue(db_connection, "/path/to/myapp", "myapp", "Child")

    # Add same dependency twice
    add_dependency(db_connection, child["id"], parent["id"], "parent")
    add_dependency(db_connection, child["id"], parent["id"], "parent")

    deps = get_dependencies(db_connection, child["id"])

    # Should only have one dependency
    assert len(deps) == 1


def test_remove_dependency(db_connection):
    """Should remove dependency."""
    from trace import create_issue, add_dependency, remove_dependency, get_dependencies

    parent = create_issue(db_connection, "/path/to/myapp", "myapp", "Parent")
    child = create_issue(db_connection, "/path/to/myapp", "myapp", "Child")

    add_dependency(db_connection, child["id"], parent["id"], "parent")
    remove_dependency(db_connection, child["id"], parent["id"])

    deps = get_dependencies(db_connection, child["id"])

    assert len(deps) == 0


def test_get_dependencies_returns_empty_for_no_deps(db_connection):
    """Should return empty list if issue has no dependencies."""
    from trace import create_issue, get_dependencies

    issue = create_issue(db_connection, "/path/to/myapp", "myapp", "Test")
    deps = get_dependencies(db_connection, issue["id"])

    assert deps == []


def test_get_children(db_connection):
    """Should get all children of a parent issue."""
    from trace import create_issue, add_dependency, get_children

    parent = create_issue(db_connection, "/path/to/myapp", "myapp", "Parent")
    child1 = create_issue(db_connection, "/path/to/myapp", "myapp", "Child 1")
    child2 = create_issue(db_connection, "/path/to/myapp", "myapp", "Child 2")

    add_dependency(db_connection, child1["id"], parent["id"], "parent")
    add_dependency(db_connection, child2["id"], parent["id"], "parent")

    children = get_children(db_connection, parent["id"])

    assert len(children) == 2
    child_ids = {c["id"] for c in children}
    assert child1["id"] in child_ids
    assert child2["id"] in child_ids


def test_get_children_returns_empty_for_no_children(db_connection):
    """Should return empty list if issue has no children."""
    from trace import create_issue, get_children

    issue = create_issue(db_connection, "/path/to/myapp", "myapp", "Test")
    children = get_children(db_connection, issue["id"])

    assert children == []


def test_get_blockers(db_connection):
    """Should get all issues that block this issue."""
    from trace import create_issue, add_dependency, get_blockers

    blocker1 = create_issue(db_connection, "/path/to/myapp", "myapp", "Blocker 1")
    blocker2 = create_issue(db_connection, "/path/to/myapp", "myapp", "Blocker 2")
    blocked = create_issue(db_connection, "/path/to/myapp", "myapp", "Blocked")

    add_dependency(db_connection, blocked["id"], blocker1["id"], "blocks")
    add_dependency(db_connection, blocked["id"], blocker2["id"], "blocks")

    blockers = get_blockers(db_connection, blocked["id"])

    assert len(blockers) == 2
    blocker_ids = {b["id"] for b in blockers}
    assert blocker1["id"] in blocker_ids
    assert blocker2["id"] in blocker_ids


def test_is_blocked_by_open_issues(db_connection):
    """Should detect if issue is blocked by open issues."""
    from trace import create_issue, add_dependency, is_blocked

    blocker = create_issue(db_connection, "/path/to/myapp", "myapp", "Blocker", status="open")
    blocked = create_issue(db_connection, "/path/to/myapp", "myapp", "Blocked")

    add_dependency(db_connection, blocked["id"], blocker["id"], "blocks")

    assert is_blocked(db_connection, blocked["id"]) is True


def test_is_not_blocked_when_blockers_closed(db_connection):
    """Should not be blocked if all blockers are closed."""
    from trace import create_issue, add_dependency, close_issue, is_blocked

    blocker = create_issue(db_connection, "/path/to/myapp", "myapp", "Blocker")
    blocked = create_issue(db_connection, "/path/to/myapp", "myapp", "Blocked")

    add_dependency(db_connection, blocked["id"], blocker["id"], "blocks")
    close_issue(db_connection, blocker["id"])

    assert is_blocked(db_connection, blocked["id"]) is False


def test_has_open_children(db_connection):
    """Should detect if issue has open children."""
    from trace import create_issue, add_dependency, has_open_children

    parent = create_issue(db_connection, "/path/to/myapp", "myapp", "Parent")
    child1 = create_issue(db_connection, "/path/to/myapp", "myapp", "Child 1", status="closed")
    child2 = create_issue(db_connection, "/path/to/myapp", "myapp", "Child 2", status="open")

    add_dependency(db_connection, child1["id"], parent["id"], "parent")
    add_dependency(db_connection, child2["id"], parent["id"], "parent")

    assert has_open_children(db_connection, parent["id"]) is True


def test_no_open_children_when_all_closed(db_connection):
    """Should return False if all children are closed."""
    from trace import create_issue, add_dependency, close_issue, has_open_children

    parent = create_issue(db_connection, "/path/to/myapp", "myapp", "Parent")
    child1 = create_issue(db_connection, "/path/to/myapp", "myapp", "Child 1")
    child2 = create_issue(db_connection, "/path/to/myapp", "myapp", "Child 2")

    add_dependency(db_connection, child1["id"], parent["id"], "parent")
    add_dependency(db_connection, child2["id"], parent["id"], "parent")

    close_issue(db_connection, child1["id"])
    close_issue(db_connection, child2["id"])

    assert has_open_children(db_connection, parent["id"]) is False
