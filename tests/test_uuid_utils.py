"""Tests for UUID utility functions."""

import uuid
from pathlib import Path


def test_generate_project_uuid_returns_valid_uuid4():
    """Should generate a valid UUID v4."""
    from trace_core.utils import generate_project_uuid

    result = generate_project_uuid()

    # Should be a valid UUID string
    parsed = uuid.UUID(result)
    assert parsed.version == 4


def test_generate_project_uuid_returns_different_values():
    """Should generate unique UUIDs on each call."""
    from trace_core.utils import generate_project_uuid

    uuids = {generate_project_uuid() for _ in range(100)}

    # All should be unique
    assert len(uuids) == 100


def test_write_project_uuid_creates_id_file(tmp_path):
    """Should write UUID to .trace/id file."""
    from trace_core.utils import write_project_uuid

    trace_dir = tmp_path / ".trace"
    trace_dir.mkdir()
    test_uuid = "550e8400-e29b-41d4-a716-446655440000"

    write_project_uuid(trace_dir, test_uuid)

    id_file = trace_dir / "id"
    assert id_file.exists()
    assert id_file.read_text().strip() == test_uuid


def test_write_project_uuid_overwrites_existing(tmp_path):
    """Should overwrite existing UUID file."""
    from trace_core.utils import write_project_uuid

    trace_dir = tmp_path / ".trace"
    trace_dir.mkdir()
    id_file = trace_dir / "id"
    id_file.write_text("old-uuid")

    new_uuid = "550e8400-e29b-41d4-a716-446655440000"
    write_project_uuid(trace_dir, new_uuid)

    assert id_file.read_text().strip() == new_uuid


def test_get_project_uuid_reads_from_file(tmp_path):
    """Should read UUID from .trace/id file."""
    from trace_core.utils import get_project_uuid

    trace_dir = tmp_path / ".trace"
    trace_dir.mkdir()
    id_file = trace_dir / "id"
    test_uuid = "550e8400-e29b-41d4-a716-446655440000"
    id_file.write_text(test_uuid)

    result = get_project_uuid(trace_dir)

    assert result == test_uuid


def test_get_project_uuid_strips_whitespace(tmp_path):
    """Should strip whitespace from UUID file."""
    from trace_core.utils import get_project_uuid

    trace_dir = tmp_path / ".trace"
    trace_dir.mkdir()
    id_file = trace_dir / "id"
    test_uuid = "550e8400-e29b-41d4-a716-446655440000"
    id_file.write_text(f"  {test_uuid}  \n")

    result = get_project_uuid(trace_dir)

    assert result == test_uuid


def test_get_project_uuid_returns_none_when_file_missing(tmp_path):
    """Should return None when .trace/id file doesn't exist."""
    from trace_core.utils import get_project_uuid

    trace_dir = tmp_path / ".trace"
    trace_dir.mkdir()

    result = get_project_uuid(trace_dir)

    assert result is None


def test_get_project_uuid_returns_none_when_trace_dir_missing(tmp_path):
    """Should return None when .trace directory doesn't exist."""
    from trace_core.utils import get_project_uuid

    trace_dir = tmp_path / ".trace"
    # Don't create the directory

    result = get_project_uuid(trace_dir)

    assert result is None


def test_get_project_uuid_returns_none_for_empty_file(tmp_path):
    """Should return None when .trace/id file is empty."""
    from trace_core.utils import get_project_uuid

    trace_dir = tmp_path / ".trace"
    trace_dir.mkdir()
    id_file = trace_dir / "id"
    id_file.write_text("")

    result = get_project_uuid(trace_dir)

    assert result is None


def test_get_project_uuid_returns_none_for_whitespace_only_file(tmp_path):
    """Should return None when .trace/id file contains only whitespace."""
    from trace_core.utils import get_project_uuid

    trace_dir = tmp_path / ".trace"
    trace_dir.mkdir()
    id_file = trace_dir / "id"
    id_file.write_text("   \n\t  \n")

    result = get_project_uuid(trace_dir)

    assert result is None


def test_roundtrip_write_and_read(tmp_path):
    """Should be able to write and read UUID."""
    from trace_core.utils import generate_project_uuid, get_project_uuid, write_project_uuid

    trace_dir = tmp_path / ".trace"
    trace_dir.mkdir()

    # Generate, write, read
    original = generate_project_uuid()
    write_project_uuid(trace_dir, original)
    result = get_project_uuid(trace_dir)

    assert result == original
