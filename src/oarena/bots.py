"""Bot discovery and source hashing.

A *bot* is a directory in the project's ``bots_dir`` containing ``main.py``; that
file is the path handed to the fcode engine, and the directory's name is the bot's
name. That is the whole of bot identity — there is no registry, no second location
and no way to mint a name from anywhere else, so what you see in ``bots_dir`` is
exactly what the ladder can contain.

To freeze a version for A/B testing, copy the directory::

    cp -r bots/greedy bots/greedy_v3

The copy is an ordinary bot from the next command onwards.

Hashing is deliberately narrow and reproducible: sha256 over every ``*.py`` file
below the bot directory, in sorted relative-path order. It must agree across runs
and machines, so nothing about the filesystem (mtimes, inode order, absolute
paths) is allowed to leak into it.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from difflib import get_close_matches
from pathlib import Path

ENTRY_NAME = "main.py"
"""The file fcode executes; a directory without it is not a bot."""

SKIP_DIRS = frozenset({"__pycache__", "local", "node_modules"})
"""Directory names never descended into. Dot-directories are skipped too."""


class BotError(RuntimeError):
    """A bot could not be found or read."""


@dataclass(frozen=True)
class BotSource:
    """A bot as it exists on disk right now."""

    name: str
    dir: Path
    entry: Path
    src_hash: str


# --------------------------------------------------------------------------
# paths
# --------------------------------------------------------------------------


def _abs(p: Path) -> Path:
    """Absolute, normalised, but *not* symlink-resolved."""
    return Path(os.path.abspath(str(p)))


def _skip_dir(name: str) -> bool:
    return name.startswith(".") or name in SKIP_DIRS


def _iter_py(d: Path) -> list[tuple[str, Path]]:
    """Every ``*.py`` below ``d`` as ``(relative posix path, absolute path)``.

    Sorted by relative path so the hash is order-stable.
    """
    root = _abs(d)
    out: list[tuple[str, Path]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [n for n in dirnames if not _skip_dir(n)]
        here = Path(dirpath)
        for fn in filenames:
            if fn.endswith(".py"):
                path = here / fn
                out.append((path.relative_to(root).as_posix(), path))
    out.sort(key=lambda item: item[0])
    return out


# --------------------------------------------------------------------------
# hashing
# --------------------------------------------------------------------------


def hash_dir(d: Path) -> str:
    """sha256 fingerprint of every ``*.py`` under ``d``.

    Each file contributes ``b"<relpath>\\0" + contents + b"\\0"`` in sorted
    relative-path order, so the digest is identical on any machine that holds the
    same sources. A missing or source-free directory hashes to sha256 of nothing.

    A file that cannot be read (a dangling symlink, a permissions problem, a file
    deleted mid-walk) contributes its path and a marker instead of its bytes. A
    bot with an unreadable source is a real state that ``sync`` has to survive:
    raising here would take down every oarena command until the file was fixed.
    """
    h = hashlib.sha256()
    for rel, path in _iter_py(d):
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        try:
            h.update(path.read_bytes())
        except OSError:
            h.update(b"<unreadable>")
        h.update(b"\0")
    return h.hexdigest()


def _source(d: Path) -> BotSource:
    d = _abs(d)
    return BotSource(name=d.name, dir=d, entry=d / ENTRY_NAME, src_hash=hash_dir(d))


# --------------------------------------------------------------------------
# discovery
# --------------------------------------------------------------------------


def _bot_dirs(base: Path) -> list[Path]:
    """Immediate sub-directories of ``base`` that hold a ``main.py``."""
    try:
        entries = sorted(_abs(base).iterdir())
    except OSError:
        return []
    return [
        d
        for d in entries
        if not d.name.startswith(("_", "."))
        and d.name not in SKIP_DIRS
        and d.is_dir()
        and (d / ENTRY_NAME).is_file()
    ]


def discover(bots_dir: Path) -> list[BotSource]:
    """Every bot in ``bots_dir``, sorted by name.

    A bare ``bots_dir/foo.py`` is not a bot — fcode needs a directory. Names
    beginning with ``.`` or ``_`` are ignored, as is ``__pycache__``.
    """
    return [_source(d) for d in _bot_dirs(bots_dir)]


def resolve(bots_dir: Path, spec: str) -> BotSource:
    """Turn a user-supplied bot spec into a :class:`BotSource`.

    ``spec`` is a directory name in ``bots_dir`` and nothing else. Filesystem
    paths are deliberately *not* accepted: allowing them would let a bot be
    registered from outside the project and let two directories claim one name,
    which is exactly the ambiguity ``bots_dir`` is meant to remove.
    """
    sources = discover(bots_dir)
    for src in sources:
        if src.name == spec:
            return src
    raise BotError(_unknown_message(spec, sources, bots_dir))


def _unknown_message(spec: str, sources: list[BotSource], bots_dir: Path) -> str:
    names = [s.name for s in sources]
    if not names:
        return (
            f"unknown bot {spec!r}: no bots found in {_abs(bots_dir)} — "
            f"a bot is a directory containing {ENTRY_NAME}"
        )

    near: list[str] = get_close_matches(spec, names, n=3, cutoff=0.5)
    lowered = spec.lower()
    for name in names:
        if len(near) >= 5:
            break
        if lowered and lowered in name.lower() and name not in near:
            near.append(name)

    # A path is the most likely wrong guess now that only names are accepted.
    hint = ""
    if any(sep in spec for sep in ("/", os.sep)) or spec.endswith(".py"):
        stem = Path(spec).name
        if stem == ENTRY_NAME:
            stem = Path(spec).parent.name
        hint = f" — bots are named by their directory in {_abs(bots_dir)}, so try {stem!r}"
        return f"unknown bot {spec!r}{hint}"

    if near:
        return f"unknown bot {spec!r} — did you mean: {', '.join(near)}?"

    listed = ", ".join(names[:12])
    if len(names) > 12:
        listed += f", … (+{len(names) - 12} more)"
    return f"unknown bot {spec!r} — known bots: {listed}"
