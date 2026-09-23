from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest


BUNDLE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "oarena"
    / "square_visualiser"
    / "assets"
    / "main-square.js"
)


@pytest.fixture(scope="module")
def bundle() -> str:
    return BUNDLE.read_text(encoding="utf-8")


def test_square_bundle_is_valid_javascript() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    subprocess.run([node, "--check", str(BUNDLE)], check=True)


def test_square_bundle_decodes_and_reduces_current_replays(bundle: str) -> None:
    assert 'ammo: { type: "int32", id: 7 }' in bundle
    assert 'coreConvertAmmo: { type: "CoreConvertAmmo", id: 14 }' in bundle
    assert 'builderHeal: { type: "BuilderHeal", id: 15 }' in bundle
    assert 'builderBuild: { type: "BuilderBuild", id: 16 }' in bundle
    assert 'target: { type: "Pos", id: 2 }' in bundle
    assert '(e.players[0].ammo = s.a.ammo ?? 0)' in bundle
    assert 'br(e, o.id, "heal", o.position.x, o.position.y, i)' in bundle
    assert 'br(e, o.id, "build", o.position.x, o.position.y, i)' in bundle
    assert "delta > 0" not in bundle
    assert "const target = s.targetPos ?? s.pos" in bundle
    assert 'Object.prototype.hasOwnProperty.call(s, "tled")' in bundle
    assert "i > 5e4" in bundle


def test_square_bundle_uses_current_stats_and_ranges(bundle: str) -> None:
    roster = re.search(r"const Wo = \{(?P<body>.*?)\n\};", bundle, re.DOTALL)
    assert roster is not None
    assert set(re.findall(r"\[y\.(\w+)\]", roster.group("body"))) == {
        "BuilderBot",
        "Conveyor",
        "Splitter",
        "Harvester",
        "Barrier",
        "Gunner",
        "Sentinel",
        "Launcher",
    }
    assert 'title: "Ammunition"' in bundle
    assert "Math.abs(w) + Math.abs(R) === 1" in bundle
    assert 'gameConstant("SENTINEL_VISION_RADIUS_SQ", 32)' in bundle
    assert "for (let h = -1; h <= 1; h++)" not in re.search(
        r"function Sl\(.*?\n\}", bundle, re.DOTALL
    ).group(0)


def test_square_sidebar_graphs_have_a_real_drawing_height(bundle: str) -> None:
    graph_section = re.search(
        r'children: "Graphs",(?P<body>.*?)P &&\n\s+c\.jsx\(Cl',
        bundle,
        re.DOTALL,
    )
    assert graph_section is not None
    body = graph_section.group("body")
    assert body.count("c.jsx(en, {") == 5
    assert body.count("height: 96,") == 5


def test_square_bundle_waits_for_recorded_and_live_metadata(bundle: str) -> None:
    assert re.search(
        r"function gameConstant\(\s*e,\s*t,\s*n = .*?game_constants,\s*\)",
        bundle,
        re.DOTALL,
    )
    assert "function snapshotGameConstants(" in bundle
    assert "__OARENA_FCODE_METADATA_READY__" in bundle
    assert "__OARENA_LIVE_FCODE_METADATA_READY__" in bundle
    assert "__OARENA_LIVE_FCODE_METADATA__" in bundle
    for name in (
        "STARTING_TITANIUM",
        "CORE_MAX_HP",
        "STACK_SIZE",
        "GUNNER_AMMO_COST",
        "SENTINEL_AMMO_COST",
        "BUILDER_BOT_VISION_RADIUS_SQ",
        "CORE_VISION_RADIUS_SQ",
        "CORE_ACTION_RADIUS_SQ",
        "GUNNER_VISION_RADIUS_SQ",
        "SENTINEL_VISION_RADIUS_SQ",
        "LAUNCHER_VISION_RADIUS_SQ",
    ):
        assert re.search(rf'gameConstant\(\s*"{name}"', bundle)


def test_square_bundle_pins_constants_to_each_replay(bundle: str) -> None:
    assert "replayGameConstants = snapshotGameConstants(metadata)" in bundle
    assert "gameConstants: replayGameConstants" in bundle
    assert "gameConstants: e.gameConstants" in bundle
    assert "ol(d, h, e.gameConstants)" in bundle
    assert "il(o, e.gameConstants)" in bundle


def test_square_bundle_keeps_a_bounded_prepared_replay_cache(bundle: str) -> None:
    assert "const OARENA_PREPARED_REPLAY_LIMIT = 4" in bundle
    assert "const OARENA_PREPARED_REPLAY_BYTE_BUDGET = 64 * 1024 * 1024" in bundle
    assert "preparedReplays = m.useRef(new Map())" in bundle
    assert "preparedReplayBytes = m.useRef(0)" in bundle
    assert "takePreparedReplay(replayKey)" in bundle
    assert "handleBridgeHasPrepared = m.useCallback" in bundle
    assert "preparedReplays.current.has(key)" in bundle
    assert "storePreparedReplay(" in bundle
    assert 'new Error("Replay bytes are required")' in bundle
    assert "Ee = fl(_, !0, options.metadata)" in bundle
    assert "const decoded = fl(_, !1, metadata)" in bundle
    assert "if (warmTimeSeries) decoded.computeTimeSeries(Ko)" in bundle
    assert "ut.dispose()" in bundle
    assert "fr.loadReplay(Ee)" in bundle


def test_square_bridge_reports_ready_only_after_phaser_create(bundle: str) -> None:
    bridge_effect = re.search(
        r"const _ = globalThis\.__OARENA_SQUARE_BRIDGE__;(?P<body>.*?)\n  \}, \[",
        bundle,
        re.DOTALL,
    )
    assert bridge_effect is not None
    body = bridge_effect.group("body")
    assert "h.current.whenReady(() =>" in body
    assert "ke = _.connect(" in body
    assert body.index("h.current.whenReady(() =>") < body.index("ke = _.connect(")


def test_square_bundle_cancels_precompute_and_resets_scene_on_switch(bundle: str) -> None:
    assert "pauseBackgroundPrecompute()" in bundle
    assert "this.timeSeriesCache.clear()" in bundle
    assert "replayRef.current?.pauseBackgroundPrecompute()" in bundle

    load_replay = re.search(
        r"loadReplay\(t\) \{(?P<body>.*?)\n  \}\n  setTurn\(",
        bundle,
        re.DOTALL,
    )
    assert load_replay is not None
    body = load_replay.group("body")
    for reset in (
        "this.tweens.killAll()",
        "(this.currentTurn = 0)",
        "(this.currentSubStep = 0)",
        "(this.botStepMode = !1)",
        "this.subStepCache.clear()",
        "this.prevPositions.clear()",
        "(this.hoveredTile = null)",
        "(this.selectedTile = null)",
        "(this.selectedEntityId = null)",
        "this.rangeGraphics?.clear()",
        "this.onSelectChange?.(null)",
        "this.onSubStepChange?.(0, 0)",
    ):
        assert reset in body


def test_square_bundle_does_not_preload_obsolete_assets(bundle: str) -> None:
    assert (
        "/^(?:axionite|armoured_conveyor|bridge|foundry|road|breach)/" in bundle
    )
    assert "obsoleteAsset.test(n.key) || this.load.image(n.key, n.file)" in bundle


def test_square_bundle_draws_indicators_above_entities(bundle: str) -> None:
    create = re.search(
        r"create\(\) \{(?P<body>.*?)this\.input\.on\(\"pointerdown\"",
        bundle,
        re.DOTALL,
    )
    assert create is not None
    body = create.group("body")
    layers = (
        "this.mapLayer = this.add.container",
        "this.gridGraphics = this.add.graphics",
        "this.entityLayer = this.add.container",
        "this.indicatorGraphics = this.add.graphics",
        "this.turretFireGraphics = this.add.graphics",
        "this.builderActionGraphics = this.add.graphics",
        "this.tileOutlineGraphics = this.add.graphics",
        "this.rangeGraphics = this.add.graphics",
        "this.highlightGraphics = this.add.graphics",
        "this.uiLayer = this.add.container",
    )
    assert [body.index(layer) for layer in layers] == sorted(
        body.index(layer) for layer in layers
    )


def test_square_bundle_uses_native_cambridge_grid_without_fcode_controls(
    bundle: str,
) -> None:
    assert "this.gridGraphics.lineStyle(2, 3813416, 0.5)" in bundle
    assert "if (!this.replay) return;" in re.search(
        r"renderGrid\(t\) \{(?P<body>.*?)\n  \}", bundle, re.DOTALL
    ).group("body")

    for removed in (
        "showGrid",
        "setShowGrid",
        "onToggleShowGrid",
        'children: "Visibility"',
        'label: "Show grid"',
        'label: "Grid"',
        'label: "Dither"',
        "Improve performance (dither bridges)",
    ):
        assert removed not in bundle

    entry = bundle[bundle.index("Za.createRoot(document.getElementById") :]
    assert "showHeader" not in entry


def test_square_bundle_has_no_unreachable_iso_rendering_plumbing(bundle: str) -> None:
    for removed in (
        '"iso"',
        "renderMode",
        "setRenderMode",
        "renderIsoEnvOverlays",
        "placeIsoUnitSprite",
        "ditherBridges",
        "bridge_dither_",
    ):
        assert removed not in bundle

    assert 'projection = Os("square")' in bundle
    assert 'ground = js("square")' in bundle
    assert "bridge_grad_" in bundle
    assert "createLinearGradient" in bundle


def test_square_bundle_prunes_non_cambridge_share_ui(bundle: str) -> None:
    for removed in (
        "Share match",
        "Generating image…",
        "navigator.share",
        "navigator.clipboard",
        "function Rp(",
    ):
        assert removed not in bundle


def test_square_bundle_shares_one_time_series_cache_key(bundle: str) -> None:
    assert "computeTimeSeries(da)" not in bundle
    assert "const da =" not in bundle
    assert bundle.count("computeTimeSeries(Ko)") >= 2
    assert "cached.replay.computeTimeSeries(Ko)" in bundle


def test_square_bundle_mounts_only_the_active_responsive_sidebar(bundle: str) -> None:
    assert "className: ya" not in bundle
    assert "className: Sa" not in bundle
    assert "className: wa" not in bundle
    assert re.search(r'!q &&\s+c\.jsx\("div".*?c\.jsx\(Fl,', bundle, re.DOTALL)
    assert re.search(r'q &&\s+c\.jsx\("div".*?c\.jsx\(Vo,', bundle, re.DOTALL)
    assert re.search(r'q &&\s+c\.jsx\("div".*?c\.jsx\(Ll,', bundle, re.DOTALL)


def test_square_bundle_shows_bot_names_beside_team_colours(bundle: str) -> None:
    assert "function teamDisplayLabel(" in bundle
    assert '`${e} (${n})`' in bundle
    assert 'teamAName:' in bundle
    assert 'typeof V?.a === "string" && V.a.trim() ? V.a.trim() : "Team A"' in bundle
    assert 'typeof V?.b === "string" && V.b.trim() ? V.b.trim() : "Team B"' in bundle
    assert 'teamDisplayLabel(W === re.A ? "Gold" : "Silver", ne)' in bundle
