"""Tests for reorganization commands (reparent, move)."""

import pytest


def test_reparent_changes_parent(db_connection):
    """Should change parent of an issue."""
    from trace import create_issue, add_dependency, reparent_issue, get_dependencies

    old_parent = create_issue(db_connection, "/path/to/myapp", "myapp", "Old Parent")
    new_parent = create_issue(db_connection, "/path/to/myapp", "myapp", "New Parent")
    child = create_issue(db_connection, "/path/to/myapp", "myapp", "Child")

    # Set initial parent
    add_dependency(db_connection, child["id"], old_parent["id"], "parent")

    # Reparent
    reparent_issue(db_connection, child["id"], new_parent["id"])

    # Check dependencies
    deps = get_dependencies(db_connection, child["id"])
    parent_deps = [d for d in deps if d["type"] == "parent"]

    assert len(parent_deps) == 1
    assert parent_deps[0]["depends_on_id"] == new_parent["id"]


def test_reparent_removes_old_parent(db_connection):
    """Should remove old parent dependency."""
    from trace import create_issue, add_dependency, reparent_issue, get_dependencies

    old_parent = create_issue(db_connection, "/path/to/myapp", "myapp", "Old Parent")
    new_parent = create_issue(db_connection, "/path/to/myapp", "myapp", "New Parent")
    child = create_issue(db_connection, "/path/to/myapp", "myapp", "Child")

    add_dependency(db_connection, child["id"], old_parent["id"], "parent")
    reparent_issue(db_connection, child["id"], new_parent["id"])

    deps = get_dependencies(db_connection, child["id"])
    old_parent_deps = [d for d in deps if d["depends_on_id"] == old_parent["id"]]

    assert len(old_parent_deps) == 0


def test_reparent_detects_direct_cycle(db_connection):
    """Should prevent creating direct cycle (child -> parent -> child)."""
    from trace import create_issue, add_dependency, reparent_issue

    parent = create_issue(db_connection, "/path/to/myapp", "myapp", "Parent")
    child = create_issue(db_connection, "/path/to/myapp", "myapp", "Child")

    add_dependency(db_connection, child["id"], parent["id"], "parent")

    # Try to make parent a child of child (cycle)
    with pytest.raises(ValueError, match="[Cc]ycle"):
        reparent_issue(db_connection, parent["id"], child["id"])


def test_reparent_detects_indirect_cycle(db_connection):
    """Should prevent creating indirect cycle (A -> B -> C -> A)."""
    from trace import create_issue, add_dependency, reparent_issue

    issue_a = create_issue(db_connection, "/path/to/myapp", "myapp", "Issue A")
    issue_b = create_issue(db_connection, "/path/to/myapp", "myapp", "Issue B")
    issue_c = create_issue(db_connection, "/path/to/myapp", "myapp", "Issue C")

    # Create chain: C -> B -> A
    add_dependency(db_connection, issue_b["id"], issue_a["id"], "parent")
    add_dependency(db_connection, issue_c["id"], issue_b["id"], "parent")

    # Try to make A a child of C (would create cycle)
    with pytest.raises(ValueError, match="[Cc]ycle"):
        reparent_issue(db_connection, issue_a["id"], issue_c["id"])


def test_reparent_allows_moving_to_sibling(db_connection):
    """Should allow reparenting to sibling (no cycle)."""
    from trace import create_issue, add_dependency, reparent_issue, get_dependencies

    grandparent = create_issue(db_connection, "/path/to/myapp", "myapp", "Grandparent")
    parent = create_issue(db_connection, "/path/to/myapp", "myapp", "Parent")
    sibling = create_issue(db_connection, "/path/to/myapp", "myapp", "Sibling")
    child = create_issue(db_connection, "/path/to/myapp", "myapp", "Child")

    # Structure: grandparent -> parent -> child
    #            grandparent -> sibling
    add_dependency(db_connection, parent["id"], grandparent["id"], "parent")
    add_dependency(db_connection, sibling["id"], grandparent["id"], "parent")
    add_dependency(db_connection, child["id"], parent["id"], "parent")

    # Reparent child to sibling (should work)
    reparent_issue(db_connection, child["id"], sibling["id"])

    deps = get_dependencies(db_connection, child["id"])
    parent_deps = [d for d in deps if d["type"] == "parent"]

    assert parent_deps[0]["depends_on_id"] == sibling["id"]


def test_reparent_with_none_removes_parent(db_connection):
    """Should remove parent when reparenting to None."""
    from trace import create_issue, add_dependency, reparent_issue, get_dependencies

    parent = create_issue(db_connection, "/path/to/myapp", "myapp", "Parent")
    child = create_issue(db_connection, "/path/to/myapp", "myapp", "Child")

    add_dependency(db_connection, child["id"], parent["id"], "parent")

    # Remove parent
    reparent_issue(db_connection, child["id"], None)

    deps = get_dependencies(db_connection, child["id"])
    parent_deps = [d for d in deps if d["type"] == "parent"]

    assert len(parent_deps) == 0


def test_reparent_preserves_other_dependencies(db_connection):
    """Should preserve blocks and related dependencies."""
    from trace import create_issue, add_dependency, reparent_issue, get_dependencies

    old_parent = create_issue(db_connection, "/path/to/myapp", "myapp", "Old Parent")
    new_parent = create_issue(db_connection, "/path/to/myapp", "myapp", "New Parent")
    blocker = create_issue(db_connection, "/path/to/myapp", "myapp", "Blocker")
    child = create_issue(db_connection, "/path/to/myapp", "myapp", "Child")

    add_dependency(db_connection, child["id"], old_parent["id"], "parent")
    add_dependency(db_connection, child["id"], blocker["id"], "blocks")

    reparent_issue(db_connection, child["id"], new_parent["id"])

    deps = get_dependencies(db_connection, child["id"])

    # Should have new parent and blocker
    assert len(deps) == 2
    assert any(d["depends_on_id"] == new_parent["id"] and d["type"] == "parent" for d in deps)
    assert any(d["depends_on_id"] == blocker["id"] and d["type"] == "blocks" for d in deps)


def test_move_issue_to_different_project(db_connection):
    """Should move issue to different project."""
    from trace import create_issue, move_issue, get_issue

    issue = create_issue(db_connection, "/path/to/myapp", "myapp", "Issue to move")

    # Move to different project
    new_id = move_issue(db_connection, issue["id"], "/path/to/mylib", "mylib")

    moved = get_issue(db_connection, new_id)

    # ID should change to new project prefix
    assert moved["id"].startswith("mylib-")
    assert moved["project_id"] == "/path/to/mylib"


def test_move_updates_dependencies(db_connection):
    """Should update dependencies when moving issue."""
    from trace import create_issue, add_dependency, move_issue, get_dependencies, get_issue

    parent = create_issue(db_connection, "/path/to/myapp", "myapp", "Parent")
    child = create_issue(db_connection, "/path/to/myapp", "myapp", "Child")

    add_dependency(db_connection, child["id"], parent["id"], "parent")

    # Move child to different project
    new_id = move_issue(db_connection, child["id"], "/path/to/mylib", "mylib")

    # Get dependencies of moved issue
    deps = get_dependencies(db_connection, new_id)

    # Should still depend on parent (cross-project)
    assert len(deps) == 1
    assert deps[0]["depends_on_id"] == parent["id"]


def test_move_updates_children_dependencies(db_connection):
    """When moving parent, children's dependencies should be updated."""
    from trace import create_issue, add_dependency, move_issue, get_dependencies

    parent = create_issue(db_connection, "/path/to/myapp", "myapp", "Parent")
    child = create_issue(db_connection, "/path/to/myapp", "myapp", "Child")

    add_dependency(db_connection, child["id"], parent["id"], "parent")

    # Move parent to different project
    new_parent_id = move_issue(db_connection, parent["id"], "/path/to/mylib", "mylib")

    # Child's dependency should point to new parent ID
    deps = get_dependencies(db_connection, child["id"])

    assert len(deps) == 1
    assert deps[0]["depends_on_id"] == new_parent_id


def test_move_preserves_issue_data(db_connection):
    """Should preserve title, description, status, priority when moving."""
    from trace import create_issue, move_issue, get_issue

    issue = create_issue(
        db_connection,
        "/path/to/myapp",
        "myapp",
        "Original Title",
        description="Original description",
        priority=1,
        status="in_progress",
    )

    new_id = move_issue(db_connection, issue["id"], "/path/to/mylib", "mylib")

    moved = get_issue(db_connection, new_id)

    assert moved["title"] == "Original Title"
    assert moved["description"] == "Original description"
    assert moved["priority"] == 1
    assert moved["status"] == "in_progress"


def test_move_deletes_old_issue(db_connection):
    """Should delete old issue after moving."""
    from trace import create_issue, move_issue, get_issue

    issue = create_issue(db_connection, "/path/to/myapp", "myapp", "Issue")
    old_id = issue["id"]

    move_issue(db_connection, old_id, "/path/to/mylib", "mylib")

    # Old issue should not exist
    assert get_issue(db_connection, old_id) is None


def test_move_handles_cross_project_dependencies(db_connection):
    """Should handle existing cross-project dependencies."""
    from trace import create_issue, add_dependency, move_issue, get_dependencies

    lib_issue = create_issue(db_connection, "/path/to/mylib", "mylib", "Lib Issue")
    app_issue = create_issue(db_connection, "/path/to/myapp", "myapp", "App Issue")

    add_dependency(db_connection, app_issue["id"], lib_issue["id"], "blocks")

    # Move app issue to another project
    new_id = move_issue(db_connection, app_issue["id"], "/path/to/other", "other")

    # Should still depend on lib issue
    deps = get_dependencies(db_connection, new_id)
    assert len(deps) == 1
    assert deps[0]["depends_on_id"] == lib_issue["id"]


def test_reparent_cross_project_parent(db_connection):
    """Should allow reparenting to issue in different project."""
    from trace import create_issue, add_dependency, reparent_issue, get_dependencies

    lib_parent = create_issue(db_connection, "/path/to/mylib", "mylib", "Lib Parent")
    app_child = create_issue(db_connection, "/path/to/myapp", "myapp", "App Child")

    # Reparent to cross-project parent
    reparent_issue(db_connection, app_child["id"], lib_parent["id"])

    deps = get_dependencies(db_connection, app_child["id"])
    parent_deps = [d for d in deps if d["type"] == "parent"]

    assert len(parent_deps) == 1
    assert parent_deps[0]["depends_on_id"] == lib_parent["id"]
