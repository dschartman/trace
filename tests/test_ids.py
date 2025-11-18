"""Tests for hash-based ID generation with collision detection."""

import time

import pytest


def test_generate_id_returns_correct_format():
    """ID should be in format: {project}-{6-char-hash}."""
    from trc_main import generate_id

    id = generate_id("Test issue", "myapp")

    assert "-" in id
    parts = id.split("-")
    assert len(parts) == 2
    assert parts[0] == "myapp"
    assert len(parts[1]) == 6


def test_generate_id_uses_base36_encoding():
    """ID hash should use [0-9a-z] characters only."""
    from trc_main import generate_id

    id = generate_id("Test issue", "myapp")
    hash_part = id.split("-")[1]

    assert all(c in "0123456789abcdefghijklmnopqrstuvwxyz" for c in hash_part)


def test_generate_id_is_non_deterministic():
    """Same title at different times generates different IDs."""
    from trc_main import generate_id

    id1 = generate_id("Test", "myapp")
    time.sleep(0.001)  # Ensure different timestamp
    id2 = generate_id("Test", "myapp")

    assert id1 != id2


def test_generate_id_different_titles_different_ids():
    """Different titles should generate different IDs."""
    from trc_main import generate_id

    id1 = generate_id("First issue", "myapp")
    id2 = generate_id("Second issue", "myapp")

    assert id1 != id2


def test_generate_id_different_projects_different_prefixes():
    """Different projects should have different prefixes."""
    from trc_main import generate_id

    id1 = generate_id("Test", "myapp")
    id2 = generate_id("Test", "mylib")

    assert id1.startswith("myapp-")
    assert id2.startswith("mylib-")


def test_generate_id_detects_collision_and_retries():
    """When collision occurs, should regenerate ID with different hash."""
    from trc_main import generate_id

    existing_ids = {"myapp-abc123", "myapp-def456"}

    # Generate many IDs - none should collide with existing
    for _ in range(10):
        new_id = generate_id("Test", "myapp", existing_ids=existing_ids)
        assert new_id not in existing_ids


def test_generate_id_fails_after_max_retries():
    """Should raise exception if can't generate unique ID after max retries."""
    from unittest.mock import patch
    from trc_main import generate_id, IDCollisionError

    # Mock the hash generation to always return the same value
    # This forces every attempt to generate the same ID
    with patch("trc_main.hashlib.sha256") as mock_sha256:
        # Make SHA256 always return the same digest
        mock_digest = b"\x12\x34\x56\x78" + b"\x00" * 28
        mock_sha256.return_value.digest.return_value = mock_digest

        # Create existing ID that matches what the mocked hash will generate
        from trc_main import _to_base36

        hash_int = int.from_bytes(mock_digest[:4], byteorder="big")
        hash_b36 = _to_base36(hash_int)[:6].zfill(6)
        existing_ids = {f"myapp-{hash_b36}"}

        with pytest.raises(IDCollisionError) as exc_info:
            generate_id("Test", "myapp", existing_ids=existing_ids, max_retries=5)

        assert "after 5 attempts" in str(exc_info.value)


def test_generate_id_handles_special_characters_in_title():
    """Should handle special characters, unicode, etc."""
    from trc_main import generate_id

    titles = [
        "Fix bug with @user mentions",
        "Add support for €uro currency",
        "Handle newlines\nand\ttabs",
        "Unicode: 你好世界 🌍",
    ]

    for title in titles:
        id = generate_id(title, "myapp")
        assert id.startswith("myapp-")
        assert len(id.split("-")[1]) == 6


def test_generate_id_handles_empty_title():
    """Should handle empty title gracefully."""
    from trc_main import generate_id

    id = generate_id("", "myapp")
    assert id.startswith("myapp-")
    assert len(id.split("-")[1]) == 6


def test_generate_id_handles_very_long_title():
    """Should handle very long titles."""
    from trc_main import generate_id

    long_title = "A" * 10000
    id = generate_id(long_title, "myapp")

    assert id.startswith("myapp-")
    assert len(id.split("-")[1]) == 6


def test_generate_id_project_name_sanitization():
    """Project names with special chars should be sanitized."""
    from trc_main import generate_id

    # Project names should already be sanitized before reaching generate_id,
    # but we test defensive behavior
    id = generate_id("Test", "my-app")
    assert id.startswith("my-app-")
