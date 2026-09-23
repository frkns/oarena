"""Discovery and parsing of fcode ``.map26`` maps.

``.map26`` is a small protobuf message.  Rather than take a protobuf dependency
for four fields, this module hand-decodes the wire format:

===== ==================== ==========================================
field wire type            meaning
===== ==================== ==========================================
1     varint               width
2     varint               height
3     length-delimited     one row, repeated ``height`` times; the
                           payload is itself ``0x0a <len> <width bytes>``
4     length-delimited     a spawn: ``{1: team, 3: {1: x, 2: y}}``
===== ==================== ==========================================

Tile bytes are ``0`` floor, ``1`` wall, ``2`` ore.  Row *r* is ``y = r`` and
byte *c* within it is ``x = c``, so the flattened grid is indexed
``y * width + x``.

:func:`parse` never raises: a corrupt or truncated file degrades to a zero-sized
map so a bad file in ``maps/`` can be listed and reported rather than crashing
the arena.
"""

from __future__ import annotations

import base64
import os
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import Any

MAP_SUFFIX = ".map26"

FLOOR = 0
WALL = 1
ORE = 2


class MapError(RuntimeError):
    """Raised when a requested map cannot be resolved."""


# --------------------------------------------------------------------------- #
# protobuf wire decoding
# --------------------------------------------------------------------------- #


def _read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    """Decode a base-128 varint at *pos*; returns ``(value, next_pos)``."""
    result = 0
    shift = 0
    while True:
        if pos >= len(buf):
            raise ValueError("truncated varint")
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7
        if shift > 63:
            raise ValueError("varint too long")


def _fields(buf: bytes) -> Iterator[tuple[int, int, Any]]:
    """Yield ``(field_number, wire_type, value)`` for every field in *buf*.

    ``value`` is an ``int`` for varints and fixed-width fields, and ``bytes``
    for length-delimited ones.
    """
    pos = 0
    end = len(buf)
    while pos < end:
        key, pos = _read_varint(buf, pos)
        field_no, wire = key >> 3, key & 0x07
        if wire == 0:
            value, pos = _read_varint(buf, pos)
        elif wire == 1:
            if pos + 8 > end:
                raise ValueError("truncated fixed64")
            value = int.from_bytes(buf[pos : pos + 8], "little")
            pos += 8
        elif wire == 2:
            length, pos = _read_varint(buf, pos)
            if length < 0 or pos + length > end:
                raise ValueError("truncated length-delimited field")
            value = buf[pos : pos + length]
            pos += length
        elif wire == 5:
            if pos + 4 > end:
                raise ValueError("truncated fixed32")
            value = int.from_bytes(buf[pos : pos + 4], "little")
            pos += 4
        else:
            raise ValueError(f"unsupported wire type {wire}")
        yield field_no, wire, value


def _row_tiles(payload: bytes) -> bytes:
    """Unwrap a row message (``{1: bytes}``) into its raw tile bytes."""
    for field_no, wire, value in _fields(payload):
        if field_no == 1 and wire == 2:
            return bytes(value)
    return b""


def _spawn_point(payload: bytes) -> tuple[int, int] | None:
    """Unwrap a spawn message (``{1: team, 3: {1: x, 2: y}}``) into ``(x, y)``."""
    for field_no, wire, value in _fields(payload):
        if field_no == 3 and wire == 2:
            x = y = 0
            for sub_no, sub_wire, sub_value in _fields(value):
                if sub_wire != 0:
                    continue
                if sub_no == 1:
                    x = int(sub_value)
                elif sub_no == 2:
                    y = int(sub_value)
            return x, y
    return None


# --------------------------------------------------------------------------- #
# the map
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class GameMap:
    """One ``.map26`` file. ``width == 0`` means the file could not be parsed."""

    name: str
    path: Path
    width: int
    height: int
    tiles: bytes
    spawns: tuple[tuple[int, int], ...]
    source: str = "official"

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def walls(self) -> int:
        return self.tiles.count(WALL)

    @property
    def ore(self) -> int:
        return self.tiles.count(ORE)

    @property
    def ok(self) -> bool:
        """True when the grid parsed cleanly and matches the declared size."""
        return self.width > 0 and self.height > 0 and len(self.tiles) == self.area

    def tile(self, x: int, y: int) -> int:
        """The tile at ``(x, y)``, or ``FLOOR`` when out of range."""
        if not (0 <= x < self.width and 0 <= y < self.height):
            return FLOOR
        index = y * self.width + x
        return self.tiles[index] if index < len(self.tiles) else FLOOR

    def analysis(self) -> dict[str, int | float | str]:
        """Compact terrain facts for the map dashboard.

        Ore is treated as passable terrain here: a harvester occupies it later,
        but a builder can reach it. The component count therefore answers the
        useful map-design question, "can the two starts reach the same board?"
        """
        if not self.ok:
            return {
                "floor": 0,
                "passable": 0,
                "wall_pct": 0.0,
                "ore_pct": 0.0,
                "spawn_count": len(self.spawns),
                "components": 0,
                "largest_component": 0,
                "symmetry": "unreadable",
            }

        walls = self.walls
        ore = self.ore
        floor = self.area - walls - ore
        seen: set[tuple[int, int]] = set()
        components = largest = 0
        for y in range(self.height):
            for x in range(self.width):
                if (x, y) in seen or self.tile(x, y) == WALL:
                    continue
                components += 1
                stack = [(x, y)]
                seen.add((x, y))
                size = 0
                while stack:
                    cx, cy = stack.pop()
                    size += 1
                    for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                        if (
                            0 <= nx < self.width
                            and 0 <= ny < self.height
                            and (nx, ny) not in seen
                            and self.tile(nx, ny) != WALL
                        ):
                            seen.add((nx, ny))
                            stack.append((nx, ny))
                largest = max(largest, size)

        same = lambda transform: all(
            self.tile(x, y) == self.tile(*transform(x, y))
            for y in range(self.height)
            for x in range(self.width)
        )
        rotational = same(lambda x, y: (self.width - 1 - x, self.height - 1 - y))
        horizontal = same(lambda x, y: (self.width - 1 - x, y))
        vertical = same(lambda x, y: (x, self.height - 1 - y))
        symmetry = "rotational" if rotational else "horizontal" if horizontal else "vertical" if vertical else "asymmetric"
        return {
            "floor": floor,
            "passable": floor + ore,
            "wall_pct": walls / self.area,
            "ore_pct": ore / self.area,
            "spawn_count": len(self.spawns),
            "components": components,
            "largest_component": largest,
            "symmetry": symmetry,
        }

    def to_json(self) -> dict[str, Any]:
        """Serialise for the web UI's thumbnail renderer (tiles are base64).

        Cached against the file's identity. Both halves of this -- base64 of the
        tiles and `analysis()`, which floods the whole board -- depend only on
        the file, and the dashboard asks for all of them on every `/api/state`:
        239 maps cost 0.2s per request to recompute unchanged answers.
        """
        key = _file_identity(self.path)
        if key is not None:
            cached = _JSON_CACHE.get(key)
            if cached is not None:
                return cached
        payload = self._build_json()
        if key is not None:
            if len(_JSON_CACHE) >= _JSON_CACHE_MAX:
                _JSON_CACHE.clear()
            _JSON_CACHE[key] = payload
        return payload

    def _build_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source": self.source,
            "width": self.width,
            "height": self.height,
            "area": self.area,
            "walls": self.walls,
            "ore": self.ore,
            "spawns": [[x, y] for x, y in self.spawns],
            "tiles": base64.b64encode(self.tiles).decode("ascii"),
            "analysis": self.analysis(),
        }


# Keyed by (path, mtime, size), so editing or replacing a map file is picked up
# on the next read without any explicit invalidation.
_JSON_CACHE: dict[tuple[str, int, int], dict[str, Any]] = {}
_JSON_CACHE_MAX = 4096


def _file_identity(path: Path) -> tuple[str, int, int] | None:
    try:
        info = os.stat(path)
    except OSError:
        return None
    return (str(path), info.st_mtime_ns, info.st_size)


def _empty(path: Path, source: str = "official") -> GameMap:
    return GameMap(
        name=path.stem,
        path=path,
        width=0,
        height=0,
        tiles=b"",
        spawns=(),
        source=source,
    )


def parse(path: Path, *, source: str = "official") -> GameMap:
    """Decode a ``.map26``. Never raises; unparsable files come back zero-sized."""
    path = Path(path)
    try:
        path = path.resolve()
    except OSError:
        return _empty(path, source)
    try:
        raw = path.read_bytes()
    except OSError:
        return _empty(path, source)

    width = height = 0
    rows: list[bytes] = []
    spawns: list[tuple[int, int]] = []
    try:
        for field_no, wire, value in _fields(raw):
            if field_no == 1 and wire == 0:
                width = int(value)
            elif field_no == 2 and wire == 0:
                height = int(value)
            elif field_no == 3 and wire == 2:
                rows.append(_row_tiles(value))
            elif field_no == 4 and wire == 2:
                point = _spawn_point(value)
                if point is not None:
                    spawns.append(point)
    except (ValueError, IndexError):
        return _empty(path, source)

    if width <= 0 or height <= 0:
        return _empty(path, source)

    tiles = b"".join(rows)
    if len(tiles) != width * height:
        # Declared dimensions and payload disagree: keep the header, drop the
        # grid so nothing downstream indexes into a ragged buffer.
        tiles = b""

    return GameMap(
        name=path.stem,
        path=path,
        width=width,
        height=height,
        tiles=tiles,
        spawns=tuple(spawns),
        source=source,
    )


# --------------------------------------------------------------------------- #
# discovery / selection
# --------------------------------------------------------------------------- #


def _discover_one(directory: Path, source: str) -> list[GameMap]:
    if not directory.is_dir():
        return []
    return [
        parse(path, source=source)
        for path in sorted(directory.rglob(f"*{MAP_SUFFIX}"))
        if path.is_file()
    ]


def discover(maps_dir: Path, extra_maps_dir: Path | None = None) -> list[GameMap]:
    """Discover official and optional extra maps, smallest first.

    Map names are the persistent identity used by the game database. If an
    extra map collides with an official name, the official map wins so an
    accidental generated file cannot silently change historical meaning.
    """
    found = _discover_one(Path(maps_dir), "official")
    known = {game_map.name for game_map in found}
    if extra_maps_dir is not None:
        for game_map in _discover_one(Path(extra_maps_dir), "extra"):
            if game_map.name not in known:
                known.add(game_map.name)
                found.append(game_map)
    found.sort(key=lambda m: (m.area, m.name))
    return found


def resolve(
    maps_dir: Path,
    spec: str,
    extra_maps_dir: Path | None = None,
) -> GameMap:
    """Resolve a map by bare name, filename or path. Raises :class:`MapError`."""
    text = str(spec).strip()
    if not text:
        raise MapError("empty map name")
    directory = Path(maps_dir)

    candidates: list[tuple[Path, str]] = [
        (directory / text, "official"),
        (directory / f"{text}{MAP_SUFFIX}", "official"),
    ]
    if extra_maps_dir is not None:
        extra = Path(extra_maps_dir)
        candidates.extend(
            ((extra / text, "extra"), (extra / f"{text}{MAP_SUFFIX}", "extra"))
        )
    for candidate, source in candidates:
        if candidate.is_file():
            return parse(candidate, source=source)

    # Bare names also resolve inside provenance/batch subdirectories.
    if Path(text).name == text:
        filename = text if text.endswith(MAP_SUFFIX) else f"{text}{MAP_SUFFIX}"
        roots = [(directory, "official")]
        if extra_maps_dir is not None:
            roots.append((Path(extra_maps_dir), "extra"))
        for root, source in roots:
            matches = sorted(path for path in root.rglob(filename) if path.is_file())
            if len(matches) > 1:
                paths = ", ".join(str(path) for path in matches)
                raise MapError(f"ambiguous map {text!r}: {paths}")
            if matches:
                return parse(matches[0], source=source)

    for candidate in (
        Path(text).expanduser(),
        Path(f"{text}{MAP_SUFFIX}").expanduser(),
    ):
        if candidate.is_file():
            return parse(candidate, source="custom")

    known = ", ".join(m.name for m in discover(directory, extra_maps_dir))
    searched = f"{directory} and {extra_maps_dir}" if extra_maps_dir is not None else str(directory)
    hint = f" — available: {known}" if known else f" — no {MAP_SUFFIX} files in {searched}"
    raise MapError(f"unknown map {text!r}{hint}")


def select(
    maps_dir: Path,
    requested: Sequence[str] | None,
    default: Sequence[str],
    extra_maps_dir: Path | None = None,
) -> list[GameMap]:
    """Pick the maps for a run: *requested* wins, else *default*, else all.

    Duplicates are collapsed while preserving the caller's order. Raises
    :class:`MapError` when the selection ends up empty.
    """
    names = list(requested) if requested else list(default or ())
    if names:
        chosen: list[GameMap] = []
        seen: set[str] = set()
        for name in names:
            game_map = resolve(maps_dir, name, extra_maps_dir)
            key = str(game_map.path)
            if key not in seen:
                seen.add(key)
                chosen.append(game_map)
    else:
        chosen = discover(maps_dir, extra_maps_dir)

    if not chosen:
        raise MapError(
            f"no maps to play — {maps_dir}"
            f"{f' and {extra_maps_dir}' if extra_maps_dir is not None else ''} "
            f"contain no {MAP_SUFFIX} files"
        )
    return chosen
