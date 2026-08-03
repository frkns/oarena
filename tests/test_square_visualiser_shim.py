from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


SQUARE_VIEWER = (
    Path(__file__).resolve().parents[1] / "src" / "oarena" / "square_visualiser"
)
SHIM = SQUARE_VIEWER / "square-only.js"
SQUARE_APP = SQUARE_VIEWER / "assets" / "main-square.js"


def test_square_shim_parses_and_loads_before_the_upstream_module() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")

    result = subprocess.run(
        [node, "--check", str(SHIM)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout

    index = (SQUARE_VIEWER / "index.html").read_text(encoding="utf-8")
    assert index.index('src="./square-only.js"') < index.index(
        'src="./assets/main-square.js"'
    )


def test_square_shim_integration_contract() -> None:
    source = SHIM.read_text(encoding="utf-8")

    assert 'pageUrl.searchParams.set("render", "square")' not in source
    assert "executingScript = document.currentScript" in source
    assert "executingScript?.src || pageUrl" in source
    assert "executingScript?.dataset.oarenaSpriteBase" in source
    assert "configuredSpriteBaseUrl?.href ||" in source
    assert 'pageUrl.searchParams.get("assetBaseUrl")' in source
    assert 'pageUrl.searchParams.get("teamA")' in source
    assert 'pageUrl.searchParams.get("teamB")' in source

    assert "window.__OARENA_FCODE_METADATA_READY__" in source
    assert "window.__OARENA_FCODE_METADATA__ = recorded" in source
    assert "window.__OARENA_LIVE_FCODE_METADATA__ = metadata" in source
    assert "window.__OARENA_LIVE_FCODE_METADATA_READY__ = livePromise" in source

    # The embedded application owns its DOM. Controls and chrome are pruned in
    # the React source instead of being hidden or renamed after every render.
    for mutation_hook in (
        "MutationObserver",
        "reconcile(",
        "replaceTeamCardNames",
        "leafElements",
        "data-oarena-compatibility-warning",
    ):
        assert mutation_hook not in source

    # The shim retains bot names for both the browser title and the replay
    # payload consumed by the native viewer.
    assert "teamA = normaliseName(game.a)" in source
    assert "teamB = normaliseName(game.b)" in source
    assert "updateTitle();" in source


def test_square_shim_bridge_is_same_origin_and_validates_messages() -> None:
    source = SHIM.read_text(encoding="utf-8")

    assert "event.origin !== window.location.origin" in source
    assert "event.source !== window.parent" in source
    assert 'message.type === "oarena:square:hello"' in source
    assert 'message.type === "oarena:square:theme"' in source
    assert 'message.type === "oarena:square:visibility"' in source
    assert 'message.type !== "oarena:square:load"' in source
    assert "message.replay instanceof ArrayBuffer" in source
    assert "sameOriginUrl(message.replayUrl)" in source
    assert 'cache: "force-cache"' in source
    assert "validRequestId(message.requestId)" in source
    assert "typeof message.key === \"string\"" in source

    for status in (
        "oarena:square:ready",
        "oarena:square:loading",
        "oarena:square:loaded",
        "oarena:square:error",
    ):
        assert status in source


def test_square_shim_fetches_replay_and_switches_metadata() -> None:
    source = SHIM.read_text(encoding="utf-8")

    assert "replayBytes(message, signal)" in source
    assert "metadataForGame(game)" in source
    assert "await loadHandler({ requestId, replay, game, theme, key })" in source
    assert "window.__OARENA_FCODE_METADATA__ = metadata" in source
    assert "new AbortController()" in source
    assert "bridgeState.loadController?.abort()" in source
    assert "signal," in source
    assert "bridgeState.applyChain.then(apply, apply)" in source
    assert 'error?.name !== "AbortError"' in source
    assert "prepareHandler" not in source
    assert "oarena:square:prepared" not in source


def test_square_viewer_extracts_profiler_records_from_bot_stdout() -> None:
    shim = SHIM.read_text(encoding="utf-8")
    app = SQUARE_APP.read_text(encoding="utf-8")

    assert 'const modernPrefix = "[OARENA:ProfilerReport]"' in shim
    assert 'const legacyPrefix = "OARENA_TELEMETRY "' in shim
    assert "extractProfilerReports," in shim
    assert "profilerRecords:" in shim
    assert "extractOarenaProfilerRecords(Ee)" in app
    assert "output.stdout = captured.text" in app
    assert "replayRef.current?.profilerRecords" in app


def test_legacy_replay_warning_lives_in_the_oarena_game_report() -> None:
    views = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "oarena"
        / "web"
        / "views.js"
    ).read_text(encoding="utf-8")

    assert "data.has_replay && !data.has_fcode_metadata" in views
    assert "This legacy replay has no recorded engine metadata" in views
    assert 'role: "note"' in views
