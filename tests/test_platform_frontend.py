"""Static contracts for the FCode match tab and persistent Square viewer."""

from __future__ import annotations

from pathlib import Path


WEB = Path(__file__).resolve().parents[1] / "src" / "oarena" / "web"


def test_fcode_stays_shortcut_seven_when_test_runs_is_appended_as_eight() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    app = (WEB / "app.js").read_text(encoding="utf-8")

    assert 'id="nav-fcode" href="#/fcode"' in html
    assert '<span class="rail-key" aria-hidden="true">7</span>' in html
    assert 'id="nav-test-runs" href="#/test-runs"' in html
    assert '<span class="rail-key" aria-hidden="true">8</span>' in html
    assert '"#/storage",\n  "#/fcode",\n  "#/test-runs",' in app
    assert 'const index = "12345678".indexOf(event.key);' in app


def test_remote_matches_reuse_the_only_square_iframe() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    app = (WEB / "app.js").read_text(encoding="utf-8")
    views = (WEB / "views.js").read_text(encoding="utf-8")

    assert html.count('id="square-viewer-frame"') == 1
    assert "function showReplay(slot, replaySource, theme)" in app
    assert "showReplay," in app
    assert "key: `fcode:${matchId}:${number}`" in views
    assert "localGameId: null" in views
    assert "/api/platform/matches/${encodeURIComponent(matchId)}/games/${number}/replay" in views
    section = views[views.index("function mountPlatformView"):views.index('const storage = mount("storage"')]
    assert "/viz/" not in section
    assert 'mountPlatformView(root, params, ctx, { officialTests: true })' in section


def test_fcode_tab_exposes_match_browser_controls() -> None:
    views = (WEB / "views.js").read_text(encoding="utf-8")
    section = views[views.index("function mountPlatformView"):views.index('const storage = mount("storage"')]

    for expected in (
        'text: "Open official"',
        'text: "Replay file"',
        'btn("Fullscreen"',
        '["all", "All"]',
        '["ladder", "Ladder"]',
        '["unrated", "Unrated"]',
        '["mine", "Mine"]',
        '["tests", "Tests"]',
        '"Recent matches"',
        'title: "FCode ladder"',
        "remote replays do not include a recorded engine-metadata snapshot",
    ):
        assert expected in section

    assert "innerHTML" not in section


def test_test_runs_are_official_and_keep_the_test_route() -> None:
    views = (WEB / "views.js").read_text(encoding="utf-8")
    css = (WEB / "app.css").read_text(encoding="utf-8")
    section = views[views.index("function mountPlatformView"):views.index('const storage = mount("storage"')]

    for expected in (
        'return `/api/platform/test-runs?limit=${PLATFORM_RECENT_LIMIT}`;',
        "response?.test_runs",
        'title: officialTests ? "Test runs" : "FCode"',
        'officialTests ? "Official test runs" : "Recent matches"',
        'platformViewHash(matchId, game, routeBase)',
        'routeBase = officialTests ? "#/test-runs" : "#/fcode"',
        'fcode-browse-grid${officialTests ? " is-single" : ""}',
        'class: `fcode-test-error ${match.error ? "err" : "mute"}`',
        '["queued", "running"]',
        "}, 5_000);",
        'if (!officialTests) void loadLadder();',
    ):
        assert expected in section

    assert 'api(`/api/test-runs?' not in views
    assert 'globalThis.oarena?.openRunDialog?.("match")' not in section
    assert ".fcode-browse-grid.is-single { grid-template-columns: minmax(0, 1fr); }" in css
    assert ".fcode-test-error { max-width: 36ch;" in css


def test_running_platform_match_refreshes_partial_games_without_hiding_replay() -> None:
    views = (WEB / "views.js").read_text(encoding="utf-8")
    section = views[
        views.index("function scheduleMatchPoll"):
        views.index("matchForm.addEventListener", views.index("function scheduleMatchPoll"))
    ]

    assert "const nextGame = normalizePlatformGame(activeGame?.number, fallbackGame);" in section
    assert "{ refresh: true, quiet: true }," in section
    assert "if (!background) {" in section
    assert "normalizePlatformGame(activeGame?.number, wantedGame)" in section
    assert "Number(item.number) === selectedGame" in section
    assert "const keepRenderedReplay = Boolean(" in section
    assert "activeGame = game;\n        renderMatchBar();" in section
    assert section.count("scheduleMatchPoll(matchId, wantedGame);") >= 2


def test_fcode_game_number_field_stays_compact_without_overflowing_its_grid() -> None:
    css = (WEB / "app.css").read_text(encoding="utf-8")

    assert "grid-template-columns: minmax(22rem, 1fr) 6ch auto;" in css
    assert ".fcode-game-number { width: 6ch; }" in css
