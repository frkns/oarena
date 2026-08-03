"""`oarena.bots`: discovery and source hashing.

Bot identity is a directory in ``bots_dir`` and nothing else — these tests pin
that, including the paths that must now be *rejected*.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import TRIVIAL_BOT, write_bot
from oarena import bots
from oarena.bots import BotError, BotSource


@pytest.fixture
def dirs(tmp_path: Path) -> Path:
    bots_dir = tmp_path / "bots"
    bots_dir.mkdir(parents=True)
    return bots_dir


# --------------------------------------------------------------------------- #
# discovery
# --------------------------------------------------------------------------- #


def test_discover_finds_directories_with_main_py(dirs: Path) -> None:
    bots_dir = dirs
    write_bot(bots_dir, "alpha")
    write_bot(bots_dir, "beta")

    found = bots.discover(bots_dir)

    assert [s.name for s in found] == ["alpha", "beta"]
    for src in found:
        assert src.entry == src.dir / "main.py"
        assert src.entry.is_file()
        assert src.src_hash


def test_discover_ignores_non_bots(dirs: Path) -> None:
    bots_dir = dirs
    write_bot(bots_dir, "alpha")
    (bots_dir / "loose.py").write_text(TRIVIAL_BOT, encoding="utf-8")  # not a directory
    (bots_dir / "empty").mkdir()  # no main.py
    write_bot(bots_dir, "_scratch")
    write_bot(bots_dir, ".hidden")
    write_bot(bots_dir, "__pycache__")

    assert [s.name for s in bots.discover(bots_dir)] == ["alpha"]


def test_discover_of_a_missing_directory_is_empty(tmp_path: Path) -> None:
    assert bots.discover(tmp_path / "nope") == []


# --------------------------------------------------------------------------- #
# hashing
# --------------------------------------------------------------------------- #


def test_hash_is_stable_across_calls(tmp_path: Path) -> None:
    directory = write_bot(tmp_path, "alpha")
    assert bots.hash_dir(directory) == bots.hash_dir(directory)


def test_hash_changes_when_a_source_file_changes(tmp_path: Path) -> None:
    directory = write_bot(tmp_path, "alpha")
    before = bots.hash_dir(directory)
    (directory / "main.py").write_text(TRIVIAL_BOT + "# tweak\n", encoding="utf-8")
    assert bots.hash_dir(directory) != before


def test_hash_covers_nested_sources(tmp_path: Path) -> None:
    directory = write_bot(tmp_path, "alpha")
    before = bots.hash_dir(directory)
    nested = directory / "lib"
    nested.mkdir()
    (nested / "helper.py").write_text("X = 1\n", encoding="utf-8")
    assert bots.hash_dir(directory) != before


def test_hash_ignores_non_python_and_caches(tmp_path: Path) -> None:
    directory = write_bot(tmp_path, "alpha")
    before = bots.hash_dir(directory)
    (directory / "README.md").write_text("hello", encoding="utf-8")
    cache = directory / "__pycache__"
    cache.mkdir()
    (cache / "main.cpython-312.pyc").write_bytes(b"\x00\x01")
    (cache / "stale.py").write_text("noise\n", encoding="utf-8")
    assert bots.hash_dir(directory) == before


def test_hash_is_independent_of_the_directory_name(tmp_path: Path) -> None:
    one = write_bot(tmp_path / "a", "alpha")
    two = write_bot(tmp_path / "b", "renamed")
    assert bots.hash_dir(one) == bots.hash_dir(two)


def test_hash_of_a_missing_directory_is_the_empty_digest(tmp_path: Path) -> None:
    import hashlib

    assert bots.hash_dir(tmp_path / "nope") == hashlib.sha256().hexdigest()


# --------------------------------------------------------------------------- #
# resolve
# --------------------------------------------------------------------------- #


def test_resolve_by_name(dirs: Path) -> None:
    bots_dir = dirs
    write_bot(bots_dir, "alpha")
    assert bots.resolve(bots_dir, "alpha").name == "alpha"


def test_resolve_refuses_a_directory_outside_bots_dir(dirs: Path) -> None:
    """A path is not a bot spec: bots_dir is the only place a name comes from."""
    bots_dir = dirs
    elsewhere = write_bot(bots_dir.parent / "outside", "wanderer")
    with pytest.raises(BotError, match="unknown bot"):
        bots.resolve(bots_dir, str(elsewhere))


def test_resolve_refuses_a_path_even_to_a_real_bot(dirs: Path) -> None:
    """`bots/alpha` and `bots/alpha/main.py` are paths, not names — both rejected,
    with a message that points at the name that would have worked."""
    bots_dir = dirs
    directory = write_bot(bots_dir, "alpha")
    for spec in (str(directory), str(directory / "main.py"), "bots/alpha"):
        with pytest.raises(BotError) as excinfo:
            bots.resolve(bots_dir, spec)
        assert "alpha" in str(excinfo.value)


def test_discover_returns_exactly_the_directories_in_bots_dir(dirs: Path) -> None:
    bots_dir = dirs
    write_bot(bots_dir, "alpha")
    write_bot(bots_dir.parent / "outside", "wanderer")
    assert [s.name for s in bots.discover(bots_dir)] == ["alpha"]


def test_hash_survives_an_unreadable_source(dirs: Path) -> None:
    """sync() must not die because one file went unreadable."""
    import os

    bots_dir = dirs
    directory = write_bot(bots_dir, "alpha")
    (directory / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    before = bots.hash_dir(directory)
    os.chmod(directory / "helper.py", 0o000)
    try:
        after = bots.hash_dir(directory)
    finally:
        os.chmod(directory / "helper.py", 0o644)
    assert after and after != before


def test_resolve_unknown_name_suggests_alternatives(dirs: Path) -> None:
    bots_dir = dirs
    write_bot(bots_dir, "alpha")
    with pytest.raises(BotError) as excinfo:
        bots.resolve(bots_dir, "alpga")
    assert "alpha" in str(excinfo.value)


def test_resolve_rejects_a_directory_without_main_py(dirs: Path) -> None:
    bots_dir = dirs
    (bots_dir / "hollow").mkdir()
    with pytest.raises(BotError, match="main.py"):
        bots.resolve(bots_dir, str(bots_dir / "hollow"))


def test_resolve_with_no_bots_at_all(dirs: Path) -> None:
    bots_dir = dirs
    with pytest.raises(BotError, match="no bots found"):
        bots.resolve(bots_dir, "alpha")
