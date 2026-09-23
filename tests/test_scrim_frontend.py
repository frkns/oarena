"""Static contracts for the official FCode Scrims tab."""

from __future__ import annotations

from pathlib import Path


WEB = Path(__file__).resolve().parents[1] / "src" / "oarena" / "web"


def test_scrims_has_a_dedicated_route_and_reuses_the_fcode_viewer_link() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    app = (WEB / "app.js").read_text(encoding="utf-8")
    views = (WEB / "views.js").read_text(encoding="utf-8")

    assert 'id="nav-scrims" href="#/scrims" data-view="scrims"' in html
    assert 'scrims: { nav: "nav-scrims", label: "Scrims" }' in app
    assert 'case "scrims":\n      return tail === undefined ? route("scrims") : null;' in app
    assert 'const scrims = mount("scrims"' in views
    assert 'href: platformViewHash(matchId, 1)' in views
    section = views[views.index('const scrims = mount("scrims"'):views.index('const storage = mount("storage"')]
    assert "showReplay(" not in section
    assert "/square-viz" not in section


def test_scrims_exposes_manual_autoscrim_stats_and_persistent_errors() -> None:
    views = (WEB / "views.js").read_text(encoding="utf-8")
    section = views[views.index('const scrims = mount("scrims"'):views.index('const storage = mount("storage"')]

    for expected in (
        'card({ title: "Request scrim" }',
        'card({ title: "Autoscrim" }',
        'title: "Results by opponent"',
        'card({ title: "Recent requests"',
        'addTopScrimTargets',
        'autoscrimTopKButton',
        'autoscrimTopKInput',
        'buildScrimRequest({',
        'buildAutoscrimConfig({',
        'sourceMatchId: sourceMatchInput.value',
        'request.error || request.last_error',
        'class: "scrim-history-error", text: error, title: error',
        'opponentVersions.map((version) => `v${version}`)',
    ):
        assert expected in section

    assert "innerHTML" not in section


def test_scrim_polling_is_local_and_one_initial_refresh_imports_remote_matches() -> None:
    app = (WEB / "app.js").read_text(encoding="utf-8")
    views = (WEB / "views.js").read_text(encoding="utf-8")
    section = views[views.index('const scrims = mount("scrims"'):views.index('const storage = mount("storage"')]

    assert '"platform_scrim"' in app
    assert 'ctx.on("platform_scrim", () => void loadDashboard({ quiet: true }));' in section
    assert 'ctx.timer(() => void loadDashboard({ quiet: true }), SCRIM_POLL_MS);' in section
    assert 'const SCRIM_POLL_MS = 8_000;' in views
    assert 'await loadDashboard({ quiet: false });' in section
    assert 'if (ctx.alive() && !scrimInitialRefreshIssued)' in section
    assert 'scrimInitialRefreshIssued = await refreshOfficial();' in section
    assert 'api("/api/platform/scrims/refresh", { method: "POST", body: {} })' in section
    assert 'api(`/api/platform/scrims?${query.toString()}`)' in section


def test_scrim_controls_surface_backoff_without_guessing_the_platform_limit() -> None:
    views = (WEB / "views.js").read_text(encoding="utf-8")
    section = views[views.index('const scrims = mount("scrims"'):views.index('const storage = mount("storage"')]

    assert "auto.backoff_until" in section
    assert "auto.next_attempt_at" in section
    assert "auto.blocked_reason" in section
    assert "auto.can_request === false" in section
    assert 'manualSubmit.disabled = manualPending || Boolean(reason);' in section
    assert 'data-scrim-deadline' in section
    assert "setInterval" not in section


def test_scrim_map_endpoint_accepts_strings_or_named_objects_and_caps_choices() -> None:
    views = (WEB / "views.js").read_text(encoding="utf-8")
    helper = (WEB / "scrim-form.js").read_text(encoding="utf-8")
    section = views[views.index('async function loadOfficialMaps'):views.index('async function refreshOfficial')]

    assert 'api("/api/platform/maps")' in section
    assert 'api("/api/maps")' in section
    assert "Promise.allSettled" in section
    assert 'String(row?.name || row || "").trim()' in section
    assert "SCRIM_MAP_MAX = 5" in helper
    assert "normalizeScrimMaps(mapNames, { strict: true })" in helper


def test_scrim_map_picker_reuses_the_shared_map_preview() -> None:
    views = (WEB / "views.js").read_text(encoding="utf-8")
    preview = (WEB / "map-preview.js").read_text(encoding="utf-8")
    section = views[views.index('const scrims = mount("scrims"'):views.index('const storage = mount("storage"')]

    assert 'import { createMapPreview } from "./map-preview.js";' in views
    assert "const mapPreview = createMapPreview(root);" in section
    assert "mapPreview.bind(chip, map);" in section
    assert "Random from all ${available.length} maps" in section
    assert 'mapThumb(map, { size, grid: false })' in preview


def test_scrims_banner_names_the_state_and_can_restart_a_paused_session() -> None:
    """A paused autoscrim must be visible and fixable from the tab itself.

    The rate-limit regression was invisible here: the tab kept rendering a
    generic badge while nothing was being scrimmed, and nothing on the page
    restarted it.
    """
    views = (WEB / "views.js").read_text(encoding="utf-8")
    css = (WEB / "app.css").read_text(encoding="utf-8")
    section = views[views.index('const scrims = mount("scrims"'):views.index('const storage = mount("storage"')]

    assert "function autoscrimStatus()" in section
    assert "function renderBanner()" in section
    assert "renderBanner();" in section
    assert 'btn("Resume autoscrim"' in section
    assert "auto.rate_limited" in section
    assert 'label: "Waiting for the shared FCode quota"' in section
    for tone in ("good", "wait", "warn", "bad"):
        assert f'.scrim-banner[data-tone="{tone}"]' in css


def test_scrims_report_the_live_shared_quota_rather_than_a_frozen_number() -> None:
    views = (WEB / "views.js").read_text(encoding="utf-8")
    section = views[views.index('const scrims = mount("scrims"'):views.index('const storage = mount("storage"')]

    assert 'statTile(\n        "FCode quota"' in section
    assert "dashboard?.quota || {}" in section
    assert "function quotaWindowText(quota)" in views
    # The old copy hard-coded "5 per 10 minutes"; the quota is now reported.
    assert "5-per-10-minute" not in views
    assert "Five games, unrated" in section


def test_scrim_autoscrim_form_has_no_duplicate_or_dead_fields() -> None:
    views = (WEB / "views.js").read_text(encoding="utf-8")
    start = views.index("const autoscrimForm = el(")
    form = views[start:views.index("const view = viewRoot(", start)]

    assert form.count('text: "Top teams"') == 0
    assert form.count('text: "Opponents"') == 1
    assert form.count('text: "Ladder leaders"') == 1
    # The coverage control was removed upstream; its orphan label went with it.
    assert "Coverage" not in form
    assert "runs continuously until disabled" not in form
