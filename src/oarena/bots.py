"""Bot discovery and source hashing.

A *bot* is a directory below the project's ``bots_dir`` containing ``main.py``;
that file is the path handed to the fcode engine, and the directory's basename is
the bot's name. Catalog directories may be nested, and a direct child symlink may
mount an external catalog. Discovery stops at bot roots and rejects duplicate
names or physical aliases, so the name remains an unambiguous identity.

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
import stat
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


def _skip_catalog_dir(name: str) -> bool:
    return name.startswith((".", "_")) or name in SKIP_DIRS


def _directory_key(path: Path) -> tuple[int, int] | None:
    """Return the followed physical identity of a directory, if readable."""

    try:
        info = path.stat()
    except (OSError, RuntimeError):
        return None
    if not stat.S_ISDIR(info.st_mode):
        return None
    return info.st_dev, info.st_ino


def _contains(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def _direct_mount_target(root: Path, entry: Path) -> Path | None:
    """Resolve one direct catalog link, rejecting dangling and ancestor links."""

    if not entry.is_symlink():
        return None
    try:
        target = entry.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if not target.is_dir() or _contains(target, root):
        # A link to the catalog itself or one of its ancestors is a cycle and
        # could otherwise turn a typo such as ``bots/all -> /`` into a scan of
        # an arbitrary filesystem tree.
        return None
    return target


def mounted_catalog_roots(base: Path) -> tuple[Path, ...]:
    """External roots mounted by direct directory symlinks below ``base``.

    The reload supervisor watches these resolved roots in addition to the
    lexical catalog, because its generic scanner deliberately does not follow
    directory symlinks.
    """

    root = _abs(base)
    try:
        resolved_root = root.resolve(strict=True)
        entries = sorted(root.iterdir())
    except (OSError, RuntimeError):
        return ()

    found: set[Path] = set()
    for entry in entries:
        if _skip_catalog_dir(entry.name):
            continue
        target = _direct_mount_target(resolved_root, entry)
        if target is not None and not _contains(resolved_root, target):
            found.add(target)
    return tuple(sorted(found, key=os.fspath))


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
    """Recursively find bot roots in ``base`` and direct mounted catalogs.

    Ordinary directories recurse freely. Only symlinks that are immediate
    children of ``base`` are followed; nested links inside a mounted repository
    remain ordinary bot source and cannot escape into another tree. Physical
    directory identities make cycles and aliases deterministic.
    """

    root = _abs(base)
    root_key = _directory_key(root)
    if root_key is None:
        return []
    try:
        resolved_root = root.resolve(strict=True)
        entries = sorted(root.iterdir(), reverse=True)
    except (OSError, RuntimeError):
        return []

    seen: dict[tuple[int, int], Path] = {root_key: root}
    pending: list[Path] = []
    for entry in entries:
        if _skip_catalog_dir(entry.name):
            continue
        if entry.is_symlink() and _direct_mount_target(resolved_root, entry) is None:
            continue
        if _directory_key(entry) is not None:
            pending.append(entry)

    found: list[Path] = []
    while pending:
        directory = pending.pop()
        key = _directory_key(directory)
        if key is None:
            continue
        previous = seen.get(key)
        if previous is not None:
            raise BotError(
                "bot catalog directory is reachable through multiple aliases: "
                f"{previous} and {directory}"
            )
        seen[key] = directory

        if (directory / ENTRY_NAME).is_file():
            found.append(directory)
            continue

        try:
            children = sorted(directory.iterdir(), reverse=True)
        except OSError:
            continue
        for child in children:
            if (
                _skip_catalog_dir(child.name)
                or child.is_symlink()
                or _directory_key(child) is None
            ):
                continue
            pending.append(child)

    by_name: dict[str, Path] = {}
    for directory in found:
        previous = by_name.get(directory.name)
        if previous is not None:
            raise BotError(
                f"duplicate bot name {directory.name!r}: {previous} and {directory}"
            )
        by_name[directory.name] = directory
    return [by_name[name] for name in sorted(by_name)]


def discover(bots_dir: Path) -> list[BotSource]:
    """Every bot below ``bots_dir``, sorted by its unique basename.

    A bare ``bots_dir/foo.py`` is not a bot — fcode needs a directory. Catalog
    directories beginning with ``.`` or ``_`` are ignored, as are cache/local
    directories. Direct child symlinks may mount external bot collections.
    """
    return [_source(d) for d in _bot_dirs(bots_dir)]


def discover_names(bots_dir: Path) -> list[str]:
    """Bot names in the current catalog without hashing their source trees."""
    return [directory.name for directory in _bot_dirs(bots_dir)]


def resolve(bots_dir: Path, spec: str) -> BotSource:
    """Turn a user-supplied bot spec into a :class:`BotSource`.

    ``spec`` is a discovered bot's basename and nothing else. Filesystem paths
    are deliberately *not* accepted: external collections must be mounted by a
    direct catalog symlink, and duplicate basenames are rejected during discovery.
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
