"""Static contracts for the FCode match tab and persistent Square viewer."""

from __future__ import annotations

from pathlib import Path


WEB = Path(__file__).resolve().parents[1] / "src" / "oarena" / "web"


def test_platform_tabs_keep_their_shortcuts_when_scrims_is_appended_as_nine() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    app = (WEB / "app.js").read_text(encoding="utf-8")

    assert 'id="nav-fcode" href="#/fcode"' in html
    assert '<span class="rail-key" aria-hidden="true">7</span>' in html
    assert 'id="nav-test-runs" href="#/test-runs"' in html
    assert '<span class="rail-key" aria-hidden="true">8</span>' in html
    assert 'id="nav-scrims" href="#/scrims"' in html
    assert '<span class="rail-key" aria-hidden="true">9</span>' in html
    assert '"#/storage",\n  "#/fcode",\n  "#/test-runs",' in app
    assert '"#/test-runs",\n  "#/scrims",' in app
    assert 'const index = "123456789".indexOf(event.key);' in app


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


def test_match_loader_sits_directly_below_the_game_tabs() -> None:
    views = (WEB / "views.js").read_text(encoding="utf-8")
    section = views[views.index("function mountPlatformView"):views.index('const storage = mount("storage"')]
    layout = section[section.index("const view = viewRoot"):section.index("root.appendChild(view)")]

    assert (
        '    vizSlot,\n'
        '    matchBar,\n'
        '    el("div", { class: "panel fcode-match-loader" }, matchForm, sessionSlot),\n'
    ) in layout


def test_recent_matches_refresh_bypasses_cache_and_ages_update_in_place() -> None:
    views = (WEB / "views.js").read_text(encoding="utf-8")
    section = views[views.index("function mountPlatformView"):views.index('const storage = mount("storage"')]

    assert 'btn("Refresh", {' in section
    assert 'title: officialTests ? "Refresh official test runs" : "Refresh recent FCode matches"' in section
    assert "loadRecent({ reset: true, quiet: true, force: true })" in section
    assert "if (force && !officialTests && !cursor) platformResponseCache.delete(cacheKey);" in section
    assert '"data-platform-relative-time": ""' in views
    assert 'recentSlot.querySelectorAll("time[data-platform-relative-time]")' in section
    assert "ctx.timer(refreshRecentTimestamps, PLATFORM_RELATIVE_TIME_REFRESH_MS);" in section
    assert "const PLATFORM_RELATIVE_TIME_REFRESH_MS = 15_000;" in views


def test_team_scoped_recent_matches_offer_client_side_win_loss_filtering() -> None:
    views = (WEB / "views.js").read_text(encoding="utf-8")
    section = views[views.index("function mountPlatformView"):views.index('const storage = mount("storage"')]
    controls = section[section.index("const outcomeFilter = outcomeTeam"):section.index(
        'const refresh = btn("Refresh"'
    )]

    assert 'platformRecentUi = { mode: "all", teamId: "", teamName: "", outcome: "all" }' in views
    assert 'platformRecentUi.mode === "mine"' in section
    assert 'session?.authenticated ? session.team : null' in section
    assert '["all", "All results"]' in controls
    assert '["win", "Wins"]' in controls
    assert '["loss", "Losses"]' in controls
    assert "platformRecentUi.outcome = value;" in controls
    assert "renderRecent();" in controls
    assert "loadRecent" not in controls
    assert "platformTeamOutcome(match, team.id) === outcome" in section
    assert "const visibleRows = visibleRecentRows();" in section
    assert "No ${outcome} in ${fmt.int(recentRows.length)} loaded matches" in section
    assert 'recentCursor ? "; load more to search older matches"' in section
    assert 'query.set("result"' not in section


def test_test_runs_are_official_and_keep_the_test_route() -> None:
    views = (WEB / "views.js").read_text(encoding="utf-8")
    css = (WEB / "app.css").read_text(encoding="utf-8")
    section = views[views.index("function mountPlatformView"):views.index('const storage = mount("storage"')]

    for expected in (
        'return `/api/platform/test-runs?limit=${PLATFORM_RECENT_LIMIT}`;',
        "response?.test_runs",
        'title: officialTests ? "Test runs" : "FCode"',
        'title: "Official test runs"',
        'title: "Recent matches"',
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


def test_match_game_tabs_show_winner_team_names_not_sides() -> None:
    views = (WEB / "views.js").read_text(encoding="utf-8")
    css = (WEB / "app.css").read_text(encoding="utf-8")
    section = views[views.index("function renderMatchBar"):views.index("function showGame")]

    assert "platformGameWinnerName(game, match)" in section
    assert "text: winnerName" in section
    assert "game?.winner_side" not in section
    assert "max-width: 14ch;" in css
    assert ".fcode-game-result { display: none; }" not in css


def test_fcode_ladder_shows_observed_bot_version_history() -> None:
    views = (WEB / "views.js").read_text(encoding="utf-8")
    css = (WEB / "app.css").read_text(encoding="utf-8")
    section = views[views.index("function platformBotVersionSnapshot"):views.index("function renderMatchBar")]

    for expected in (
        "row?.bot_version",
        "row?.version_first_seen_at",
        "row?.version_transition_known === true",
        "row?.version_history",
        ".slice(0, 3)",
        "`v${snapshot.version} · ≈${age}`",
        "`v${snapshot.version} · seen ${age}`",
        "became the observed active version by",
        "an older version being reactivated",
        'el("td", null, platformBotVersionTime(row))',
        'el("th", { text: "Bot" })',
        'class: "table table-compact fcode-ladder-table"',
        "data?.version_tracking",
        'api("/api/platform/version-tracking")',
        'platformResponseCache.delete("ladder:100")',
        "loadLadder({ trackingPoll: true })",
    ):
        assert expected in section

    assert 'ladderSlot.querySelectorAll("time[data-platform-version-time]")' in section
    assert "refreshPlatformBotVersionTime(node);" in section
    assert ".fcode-ladder-table th:nth-child(3) { width: 17ch; }" in css
    assert ".fcode-bot-version {" in css
    assert "PLATFORM_VERSION_SYNC_POLL_MS = 1_000" in views
    assert "PLATFORM_VERSION_SYNC_MAX_POLLS = 30" in views
    assert "PLATFORM_VERSION_SYNC_SLOW_POLL_MS = 5_000" in views
    assert "PLATFORM_VERSION_SYNC_ERROR_RETRY_MS = 10_000" in views
    assert ".fcode-version-status {" in css


def test_fcode_tab_has_visible_team_bot_version_timeline() -> None:
    views = (WEB / "views.js").read_text(encoding="utf-8")
    css = (WEB / "app.css").read_text(encoding="utf-8")
    section = views[views.index("function mountPlatformView"):views.index('const storage = mount("storage"')]

    for expected in (
        'title: "Bot versions"',
        '"aria-label": "Team bot-version history"',
        '"/api/platform/version-history?limit=100"',
        'const runs = Array.isArray(team.runs) ? team.runs : [];',
        'for (const [index, run] of runs.entries())',
        '"data-current": isCurrent ? "true" : null',
        'text: "latest observed"',
        '"Version change observed"',
        '"Baseline observation"',
        'selectVersionHistoryTeam(team, { explicit: true });',
        'teams.find((candidate) => candidate.team_id === preferredTeamId)',
        'versionHistorySlot.querySelectorAll("time[data-platform-relative-time]")',
        'platformResponseCache.delete("version-history:100")',
        'void loadVersionHistory({ trackingPoll: true });',
        'version-history?team_id=${encodeURIComponent(teamId)}&limit=1',
        'selectedVersionError',
        'platformResponseCache.delete(`version-history-team:${selectedVersionTeamId}`)',
        'const selectedMissingFromFresh = Boolean(',
        'function ensureDefaultVersionTeam()',
        'versionTeamSelectionExplicit || selectedIsSignedIn',
        'Could not refresh this timeline. Showing what was saved earlier.',
        'let ladderRankByTeamId = new Map();',
        'const leftRank = ladderRankByTeamId.get(left.candidate.team_id) ?? Infinity;',
        'Number.isSafeInteger(rank) ? `#${rank} · ` : ""',
    ):
        assert expected in section

    assert section.index('title: "Recent matches"') < section.index('title: "Bot versions"')
    assert section.index('title: "Bot versions"') < section.index('title: "FCode ladder"')
    # The footnote must still say the two things that stop it misleading anyone:
    # the times are sightings, and one version can appear twice.
    assert "a first sighting rather than an upload" in section
    assert "comes back later appears again" in section
    assert ".fcode-side-stack { display: grid;" in css
    assert ".fcode-version-team-select { max-width: 22ch; }" in css
    assert ".fcode-version-timeline .timeline-ts { min-width: 7ch; }" in css


def test_version_runs_expand_to_the_games_played_on_them() -> None:
    views = (WEB / "views.js").read_text(encoding="utf-8")
    css = (WEB / "app.css").read_text(encoding="utf-8")
    section = views[views.index("function mountPlatformView"):views.index('const storage = mount("storage"')]

    assert "/api/platform/version-history/games?" in section
    assert "function loadRunGames(teamId, ordinal)" in section
    assert "function runGamesNode(teamId, ordinal)" in section
    # The stored ordinal addresses the run; the display order is newest-first
    # and must never be mistaken for it.
    assert "Number.isSafeInteger(run?.ordinal) ? run.ordinal : null" in section
    assert "runKey(team.team_id, ordinal)" in section
    # Expansion and fetched games survive the timeline's periodic re-render.
    assert "const expandedRuns = new Set();" in section
    assert "const runGamesCache = new Map();" in section
    assert '"aria-expanded": expanded ? "true" : "false"' in section
    assert 'href: matchId ? platformViewHash(matchId, 1) : null' in section
    assert ".fcode-run-game-list {" in css
    assert '.fcode-run-game[data-result="win"] .fcode-run-result' in css


def test_version_history_states_it_covers_unrated_games_too() -> None:
    views = (WEB / "views.js").read_text(encoding="utf-8")
    section = views[views.index("function mountPlatformView"):views.index('const storage = mount("storage"')]

    assert "the ladder and unrated matches oarena has seen" in section
    assert "Click a version to list its games." in section


def test_open_match_offers_a_quick_switch_between_its_two_teams() -> None:
    views = (WEB / "views.js").read_text(encoding="utf-8")
    css = (WEB / "app.css").read_text(encoding="utf-8")
    section = views[views.index("function mountPlatformView"):views.index('const storage = mount("storage"')]

    assert "function renderVersionQuickSwitch()" in section
    assert 'class: "seg fcode-version-quick"' in section
    # The quick switch sits beside the full dropdown, it does not replace it.
    assert "versionQuickSwitch,\n    versionTeamSelect," in section
    assert 'actions: versionHistoryActions' in section
    assert 'selectVersionHistoryTeam({ id, name }, { explicit: true })' in section
    # Tests have no opponent panel, so the switch stays out of that route.
    assert "if (officialTests || !match) {" in section
    assert ".fcode-version-actions {" in css


def test_the_version_played_in_the_open_match_is_highlighted() -> None:
    views = (WEB / "views.js").read_text(encoding="utf-8")
    css = (WEB / "app.css").read_text(encoding="utf-8")
    section = views[views.index("function mountPlatformView"):views.index('const storage = mount("storage"')]

    assert 'import { playedRunOrdinal as resolvePlayedRunOrdinal } from "./version-runs.js";' in views
    assert "const playingOrdinal = playedRunOrdinal(team);" in section
    assert '"data-playing": isPlaying ? "true" : null,' in section
    assert 'text: "this match"' in section
    # Selecting a different match has to repaint the highlight.
    assert "function syncVersionPanelToMatch()" in section
    assert "syncVersionPanelToMatch();" in section
    # The observation timestamp, not the completion one, decides containment.
    assert "at: match.created_at || match.completed_at," in section
    assert '.timeline-item[data-playing="true"] {' in css


def test_the_played_version_comes_from_local_records_not_the_match_detail() -> None:
    """FCode's match detail carries no team versions; only the list does.

    A match opened by ID would otherwise show no version and highlight nothing,
    so the version each team played is read back from oarena's observations.
    """
    views = (WEB / "views.js").read_text(encoding="utf-8")
    section = views[views.index("function mountPlatformView"):views.index('const storage = mount("storage"')]

    assert "/api/platform/version-history/match?match_id=" in section
    assert "async function loadMatchRuns(matchId)" in section
    assert "void loadMatchRuns(activeDetail?.match?.id);" in section
    # The recorded ordinal wins; the timestamp fallback is only for matches that
    # were never observed.
    assert "if (Number.isSafeInteger(recorded?.ordinal)) return recorded.ordinal;" in section
    assert "const recorded = matchRunFor(id);" in section


def test_the_version_panel_follows_the_open_match_until_you_choose_a_team() -> None:
    """A match between two other teams must still highlight something.

    Defaulting to the signed-in team meant opening any match they were not
    playing in showed an unrelated timeline with nothing marked.
    """
    views = (WEB / "views.js").read_text(encoding="utf-8")
    section = views[views.index("function mountPlatformView"):views.index('const storage = mount("storage"')]

    assert "function preferredVersionTeam()" in section
    assert "function ensureDefaultVersionTeam()" in section
    # Your own team wins whenever it is one of the two playing.
    assert "const own = sides.find(" in section
    # An explicit choice, from the dropdown or the quick switch, stops the follow.
    assert "if (officialTests || versionTeamSelectionExplicit || !versionHistoryData) return false;" in section
    assert "if (!ensureDefaultVersionTeam()) renderVersionHistory();" in section
