"""`oarena.maps`: the hand-written ``.map26`` decoder, discovery and selection."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from conftest import STOCK_MAPS, copy_maps, requires_maps
from oarena import maps
from oarena.maps import MapError


# --------------------------------------------------------------------------- #
# parsing the real thing
# --------------------------------------------------------------------------- #


@requires_maps
def test_every_stock_map_parses() -> None:
    assert STOCK_MAPS is not None
    found = maps.discover(STOCK_MAPS)

    assert found, "the stock map directory is empty"
    for game_map in found:
        assert game_map.ok, game_map.name
        assert game_map.width > 0 and game_map.height > 0
        assert len(game_map.tiles) == game_map.area
        assert len(game_map.spawns) == 2, game_map.name
        assert set(game_map.tiles) <= {maps.FLOOR, maps.WALL, maps.ORE}
        for x, y in game_map.spawns:
            assert 0 <= x < game_map.width
            assert 0 <= y < game_map.height


@requires_maps
def test_known_map_geometry() -> None:
    assert STOCK_MAPS is not None
    sprint = maps.parse(STOCK_MAPS / "sprint.map26")
    duel = maps.parse(STOCK_MAPS / "duel.map26")

    assert (sprint.name, sprint.width, sprint.height) == ("sprint", 10, 10)
    assert sprint.area == 100
    assert sprint.ore == 6
    assert (duel.width, duel.height) == (12, 12)
    assert duel.walls == 2


@requires_maps
def test_discover_is_sorted_by_area_then_name() -> None:
    assert STOCK_MAPS is not None
    found = maps.discover(STOCK_MAPS)
    assert [(m.area, m.name) for m in found] == sorted(
        (m.area, m.name) for m in found
    )


@requires_maps
def test_tile_lookup_matches_the_flat_buffer() -> None:
    assert STOCK_MAPS is not None
    game_map = maps.parse(STOCK_MAPS / "pinch.map26")
    for y in range(game_map.height):
        for x in range(game_map.width):
            assert game_map.tile(x, y) == game_map.tiles[y * game_map.width + x]
    assert game_map.tile(-1, 0) == maps.FLOOR
    assert game_map.tile(game_map.width, 0) == maps.FLOOR


@requires_maps
def test_to_json_carries_base64_tiles() -> None:
    assert STOCK_MAPS is not None
    game_map = maps.parse(STOCK_MAPS / "sprint.map26")
    payload = game_map.to_json()

    assert set(payload) == {
        "name", "source", "width", "height", "area", "walls", "ore", "spawns", "tiles", "analysis"
    }
    assert payload["source"] == "official"
    assert base64.b64decode(payload["tiles"]) == game_map.tiles
    assert payload["spawns"] == [list(s) for s in game_map.spawns]
    assert payload["analysis"]["spawn_count"] == 2
    assert payload["analysis"]["passable"] + payload["walls"] == payload["area"]


# --------------------------------------------------------------------------- #
# degraded input
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "payload",
    [b"", b"\xff\xff\xff\xff", b"garbage that is not protobuf at all", b"\x08"],
)
def test_parse_never_raises(tmp_path: Path, payload: bytes) -> None:
    path = tmp_path / "broken.map26"
    path.write_bytes(payload)
    game_map = maps.parse(path)

    assert game_map.name == "broken"
    assert game_map.width == 0 and game_map.height == 0
    assert game_map.tiles == b""
    assert game_map.ok is False


def test_parse_of_a_missing_file_degrades(tmp_path: Path) -> None:
    game_map = maps.parse(tmp_path / "absent.map26")
    assert game_map.width == 0 and game_map.tiles == b""


def test_declared_size_mismatch_drops_the_grid(tmp_path: Path) -> None:
    # width=4 height=4 but only one 2-byte row.
    path = tmp_path / "ragged.map26"
    path.write_bytes(b"\x08\x04\x10\x04\x1a\x04\x0a\x02\x00\x01")
    game_map = maps.parse(path)

    assert (game_map.width, game_map.height) == (4, 4)
    assert game_map.tiles == b""
    assert game_map.ok is False


def test_discover_of_a_missing_directory_is_empty(tmp_path: Path) -> None:
    assert maps.discover(tmp_path / "nope") == []


def test_discover_combines_and_labels_official_and_extra_maps(tmp_path: Path) -> None:
    official = tmp_path / "maps"
    extra = tmp_path / "more_maps"
    if not copy_maps(official, ("sprint",)) or not copy_maps(extra, ("duel",)):
        pytest.skip("no stock .map26 files available")

    found = maps.discover(official, extra)

    assert {game_map.name: game_map.source for game_map in found} == {
        "sprint": "official",
        "duel": "extra",
    }


def test_official_map_wins_an_extra_name_collision(tmp_path: Path) -> None:
    official = tmp_path / "maps"
    extra = tmp_path / "more_maps"
    if not copy_maps(official, ("sprint",)) or not copy_maps(extra, ("sprint",)):
        pytest.skip("no stock .map26 files available")

    found = maps.discover(official, extra)

    assert [(game_map.name, game_map.source) for game_map in found] == [
        ("sprint", "official")
    ]


# --------------------------------------------------------------------------- #
# resolve
# --------------------------------------------------------------------------- #


@pytest.fixture
def maps_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "maps"
    if not copy_maps(directory, ("sprint", "duel")):
        pytest.skip("no stock .map26 files available")
    return directory


def test_resolve_accepts_bare_name(maps_dir: Path) -> None:
    assert maps.resolve(maps_dir, "sprint").name == "sprint"


def test_resolve_accepts_filename(maps_dir: Path) -> None:
    assert maps.resolve(maps_dir, "sprint.map26").name == "sprint"


def test_resolve_accepts_an_absolute_path(maps_dir: Path) -> None:
    assert maps.resolve(maps_dir, str(maps_dir / "duel.map26")).name == "duel"


def test_resolve_accepts_a_path_without_the_suffix(maps_dir: Path) -> None:
    assert maps.resolve(maps_dir, str(maps_dir / "duel")).name == "duel"


def test_resolve_lists_alternatives_on_a_miss(maps_dir: Path) -> None:
    with pytest.raises(MapError) as excinfo:
        maps.resolve(maps_dir, "atlantis")
    assert "atlantis" in str(excinfo.value)
    assert "sprint" in str(excinfo.value)


def test_resolve_rejects_an_empty_name(maps_dir: Path) -> None:
    with pytest.raises(MapError):
        maps.resolve(maps_dir, "   ")


def test_resolve_finds_an_extra_map(maps_dir: Path, tmp_path: Path) -> None:
    extra = tmp_path / "more_maps"
    if not copy_maps(extra, ("pinch",)):
        pytest.skip("no stock .map26 files available")

    game_map = maps.resolve(maps_dir, "pinch", extra)

    assert game_map.name == "pinch"
    assert game_map.source == "extra"


# --------------------------------------------------------------------------- #
# select
# --------------------------------------------------------------------------- #


def test_select_prefers_the_request(maps_dir: Path) -> None:
    chosen = maps.select(maps_dir, ["duel"], ["sprint"])
    assert [m.name for m in chosen] == ["duel"]


def test_select_falls_back_to_the_configured_default(maps_dir: Path) -> None:
    chosen = maps.select(maps_dir, None, ["sprint"])
    assert [m.name for m in chosen] == ["sprint"]


def test_select_with_neither_returns_every_map(maps_dir: Path) -> None:
    chosen = maps.select(maps_dir, None, [])
    assert {m.name for m in chosen} == {"sprint", "duel"}


def test_select_with_neither_includes_extra_maps(maps_dir: Path, tmp_path: Path) -> None:
    extra = tmp_path / "more_maps"
    if not copy_maps(extra, ("pinch",)):
        pytest.skip("no stock .map26 files available")

    chosen = maps.select(maps_dir, None, [], extra)

    assert {m.name for m in chosen} == {"sprint", "duel", "pinch"}
    assert next(m for m in chosen if m.name == "pinch").source == "extra"


def test_select_collapses_duplicates_keeping_order(maps_dir: Path) -> None:
    chosen = maps.select(maps_dir, ["duel", "sprint", "duel.map26"], [])
    assert [m.name for m in chosen] == ["duel", "sprint"]


def test_select_raises_when_nothing_is_available(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(MapError, match="no maps to play"):
        maps.select(empty, None, [])


def test_select_propagates_an_unknown_name(maps_dir: Path) -> None:
    with pytest.raises(MapError):
        maps.select(maps_dir, ["atlantis"], [])
