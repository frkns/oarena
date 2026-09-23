"""Static contracts for the tagged local-match game selector."""

from __future__ import annotations

from pathlib import Path


WEB = Path(__file__).resolve().parents[1] / "src" / "oarena" / "web"


def test_tagged_game_detail_loads_one_bounded_summary_page() -> None:
    views = (WEB / "views.js").read_text(encoding="utf-8")
    section = views[views.index('const game = mount("game"'):views.index('const bots = mount("bots"')]
    cache = views[views.index("function requestMatchBatch"):views.index("// Keep the warmed page current")]

    for expected in (
        'limit: "500"',
        'api(`/api/batch?${query.toString()}`)',
        "MATCH_GAMES_CACHE_MAX_AGE_MS",
        "cached?.inflight",
    ):
        assert expected in cache

    for expected in (
        "requestMatchBatch(batchTag)",
        "entry?.tag === batchTag && Number.isInteger(entry?.batch_ordinal)",
        "left.batch_ordinal - right.batch_ordinal || Number(left.id) - Number(right.id)",
        "selectedRow.batch_ordinal !== selected.batch_ordinal",
        'data.tag === batchTag',
        'Number.isInteger(data.batch_ordinal)',
        "batchReplayRows = games",
        'if (viewerChoice === "2d") squareViewer?.prepareGames(games, id)',
    ):
        assert expected in section

    assert "squareViewer?.prepareGames(batchReplayRows, id)" in section


def test_batch_links_preserve_tag_and_do_not_duplicate_the_viewer() -> None:
    views = (WEB / "views.js").read_text(encoding="utf-8")
    section = views[views.index('const game = mount("game"'):views.index('const bots = mount("bots"')]

    assert '`#/games/${encodeURIComponent(gameId)}?tag=${encodeURIComponent(batchTag)}`' in section
    assert '`#/games?tag=${encodeURIComponent(batchTag)}`' in section
    assert 'href: taggedGameHref(entry.id)' in section
    assert 'href: taggedGamesHref' in section
    assert '"aria-current": active ? "page" : null' in section
    assert 'page?.more' in section
    assert 'location.hash = taggedGamesHref' in section
    assert "scrollIntoView" in section
    assert section.count('const vizSlot = el("div", { class: "viz-frame" })') == 1


def test_tagged_games_route_is_an_exact_match_result_set() -> None:
    views = (WEB / "views.js").read_text(encoding="utf-8")
    section = views[views.index('const games = mount("games"'):views.index("/* 4. Game detail")]

    assert 'gameFilter = { ...EMPTY_GAME_FILTER, tag: routedTag }' in section
    assert 'pendingGameFilter = null' in section
    assert '`${gameHref(game.id)}?tag=${encodeURIComponent(gameFilter.tag)}`' in section
    assert 'location.hash = detailHref' in section
    assert 'Object.hasOwn(patch, "tag") && !patch.tag' in section
    assert 'location.hash = "#/games"' in section
    assert 'isWebMatchTag(gameFilter.tag)' in section


def test_games_highlight_only_rows_from_the_latest_finite_match() -> None:
    views = (WEB / "views.js").read_text(encoding="utf-8")
    css = (WEB / "app.css").read_text(encoding="utf-8")
    section = views[views.index('const games = mount("games"'):views.index("/* 4. Game detail")]

    assert 'isLatestMatchGame(game, latestMatchTag)' in section
    assert '"data-latest-match": latestMatch ? "true" : null' in section
    assert 'latest match highlighted' in section
    assert 'page?.latest_match_tag' in section
    assert 'ctx.on("run_started"' in section
    assert "latestMatchRunRevision" in views
    assert "requestRevision !== latestMatchRunRevision" in section
    assert "const tag = startedMatchTag(payload);" in views
    assert ".game-row.is-latest-match" in css
    assert "background: var(--accent-soft);" in css


def test_batch_selector_is_compact_horizontal_and_does_not_resize_viewer() -> None:
    css = (WEB / "app.css").read_text(encoding="utf-8")
    selector = css[css.index(".game-batch-selector-slot"):css.index(".viz-frame {")]

    assert ".game-batch-links" in selector
    assert "overflow-x: auto;" in selector
    assert "flex: 0 0 auto;" in selector
    assert "height: 28px;" in selector
    assert "block-size" not in selector
    assert "max-height" not in selector


def test_batch_selector_names_the_winning_bot_after_side_swaps() -> None:
    views = (WEB / "views.js").read_text(encoding="utf-8")
    css = (WEB / "app.css").read_text(encoding="utf-8")
    section = views[views.index("async function loadBatchSelector"):views.index("function mountViz")]
    selector = css[css.index(".game-batch-selector-slot"):css.index(".viz-frame {")]

    assert 'entry.winner === "a" || entry.winner === "b"' in section
    assert "fmt.winner(entry)" in section
    assert "String(entry.winner).toUpperCase()" not in section
    assert "text: result" in section
    assert "title: resultTitle" in section
    assert "max-width: 18ch;" in selector
    assert "text-overflow: ellipsis;" in selector


def test_finite_web_match_is_armed_before_post_and_accepted_after_confirmation() -> None:
    app = (WEB / "app.js").read_text(encoding="utf-8")
    start = app[app.index("  async function start() {"):app.index(
        '  tabMatch.addEventListener("click"', app.index("  async function start() {")
    )]
    finite = start[start.index("        const maps = selectedMaps();"):]

    arm = finite.index("webMatchCompletions.arm(batchTag)")
    post = finite.index('await api("/api/match"')
    confirm = finite.index("result?.tag !== batchTag")
    accept = finite.index("webMatchCompletions.accept(batchTag)")
    assert arm < post < confirm < accept
    assert "tag: batchTag" in finite
    assert "webMatchCompletions.reject(batchTag)" in finite

    # Arena and Match's "everyone" shortcut remain untagged indefinite runs.
    indefinite = start[:start.index("        const maps = selectedMaps();")]
    assert 'await api("/api/arena"' in indefinite
    assert "newWebMatchBatchTag" not in indefinite
    assert "batchTag" not in indefinite


def test_completed_web_match_events_navigate_to_the_exact_tagged_game() -> None:
    app = (WEB / "app.js").read_text(encoding="utf-8")
    dispatch = app[app.index("function dispatch("):app.index("function handleFrame(")]
    handoff = app[app.index("function fetchWebMatchBatch("):app.index(
        "function setConnection("
    )]

    assert "webMatchCompletions.captureGame(game)" in dispatch
    assert "webMatchCompletions.captureRunFinished(data)" in dispatch
    assert 'dom.modalHost?.querySelector("#run-dialog")' in handoff
    assert "navigate(hash)" in handoff
    assert handoff.count("dom.view.scrollTop = 0") >= 2
    assert "completion.firstGame?.batch_ordinal === 0" in handoff
    assert 'limit: "500"' in handoff
    assert 'api(`/api/batch?${query}`)' in handoff
    assert "webMatchCompletions.acceptedTags()" in handoff
    assert 'batch.status === "running"' in handoff
    assert "completedRunHash(completion.tag, batch?.games)" in handoff
    assert app.count("reconcileCompletedWebMatches();") >= 2


def test_completed_web_match_has_an_online_fallback_and_truthful_optimistic_status() -> None:
    app = (WEB / "app.js").read_text(encoding="utf-8")
    start = app[app.index("  async function start() {"):app.index(
        '  tabMatch.addEventListener("click"', app.index("  async function start() {")
    )]
    handoff = app[app.index("const webMatchCompletions"):app.index(
        "function setConnection("
    )]

    assert "if (!completion) scheduleWebMatchReconciliation(batchTag);" in start
    assert "!state.online" not in start
    assert "WEB_MATCH_RECONCILE_MIN_MS" in handoff
    assert "WEB_MATCH_RECONCILE_MAX_MS" in handoff
    assert 'if (batch.status === "running") {' in handoff
    assert "retry = true;" in handoff
    assert "stopWebMatchReconciliation(completion.tag);" in handoff
    assert "state.status = optimisticRunStatus(state.status, optimisticRun);" in start
    assert "state.status = { ...(state.status || {}), running: true" not in start
