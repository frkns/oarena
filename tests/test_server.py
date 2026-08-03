"""`oarena.server`: every route's status code, JSON shape and SSE behaviour.

A real :class:`~oarena.server.Server` is bound on an ephemeral port and driven
over HTTP, so the routing, header and streaming code all run for real.  Games
are still played by the in-process fake runner.
"""

from __future__ import annotations

import gzip
import json
import shutil
import subprocess
import threading
import time
from dataclasses import replace
from http.client import HTTPConnection, HTTPResponse
from pathlib import Path
from typing import Any, Iterator

import pytest

from conftest import Project
from fake_worker import FAKE_FCODE_METADATA, FAKE_FCODE_VERSION
from oarena import server as servermod
from oarena.league import Job
from oarena.runner import GameOutcome
from oarena.server import App, Server, make_server
from oarena.store import Game


class Client:
    """A tiny HTTP client bound to one running server."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port

    def raw(self, method: str, path: str, body: Any = None) -> HTTPResponse:
        conn = HTTPConnection(self.host, self.port, timeout=10)
        payload = None if body is None else json.dumps(body).encode()
        headers = {"Content-Type": "application/json"} if payload else {}
        conn.request(method, path, body=payload, headers=headers)
        response = conn.getresponse()
        response.read()  # drain so the connection can be closed cleanly
        conn.close()
        return response

    def get(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, bytes, HTTPResponse]:
        conn = HTTPConnection(self.host, self.port, timeout=10)
        conn.request("GET", path, headers=headers or {})
        response = conn.getresponse()
        data = response.read()
        conn.close()
        return response.status, data, response

    def json(self, path: str) -> Any:
        status, data, response = self.get(path)
        assert status == 200, (path, status, data[:200])
        assert response.getheader("Cache-Control") == "no-store"
        return json.loads(data)

    def send(self, method: str, path: str, body: Any = None) -> tuple[int, Any]:
        conn = HTTPConnection(self.host, self.port, timeout=10)
        payload = None if body is None else json.dumps(body).encode()
        headers = {"Content-Type": "application/json"} if payload else {}
        conn.request(method, path, body=payload, headers=headers)
        response = conn.getresponse()
        raw = response.read()
        conn.close()
        try:
            return response.status, json.loads(raw)
        except ValueError:
            return response.status, raw


@pytest.fixture
def app(project: Project) -> App:
    project.league.sync()
    return App(
        project.cfg, project.store, project.bus, project.league, project.rater
    )


@pytest.fixture
def live(app: App) -> Iterator[tuple[App, Client]]:
    httpd: Server = make_server(app, "127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.05},
                              daemon=True)
    thread.start()
    try:
        yield app, Client(*httpd.server_address[:2])
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


@pytest.fixture
def client(live: tuple[App, Client]) -> Client:
    return live[1]


@pytest.fixture
def seeded(live: tuple[App, Client]) -> tuple[App, Client]:
    """A server whose store already holds a couple of finished games."""
    app, client = live
    replay = app.cfg.tmp_dir / "seed.replay26"
    log = app.cfg.tmp_dir / "seed.log"
    replay.write_bytes(b"REPLAY" * 20)
    log.write_text("Traceback (most recent call last):\nValueError: nope\n", encoding="utf-8")
    app.league.finish(
        Job("alpha", "beta", "sprint", 1),
        GameOutcome(status="ok", winner="a", win_condition="core_destroyed", turns=500,
                    replay_path=replay, log_path=log,
                    fcode_version=FAKE_FCODE_VERSION,
                    fcode_metadata=FAKE_FCODE_METADATA),
    )
    app.league.finish(
        Job("beta", "gamma", "duel", 2),
        GameOutcome(status="timeout", winner=None, error="exceeded 300s wall clock"),
    )
    return app, client


# --------------------------------------------------------------------------- #
# static files
# --------------------------------------------------------------------------- #


def test_index_is_served(client: Client) -> None:
    status, body, response = client.get("/")
    assert status == 200
    assert response.getheader("Content-Type", "").startswith("text/html")
    assert b"<" in body
    assert b'data-theme="dark"' in body
    assert response.getheader("Cache-Control") == "no-store"


def test_static_files_are_served(client: Client) -> None:
    status, body, response = client.get("/static/app.css")
    assert status == 200
    assert response.getheader("Content-Type", "").startswith("text/css")
    assert body


@pytest.mark.parametrize(
    ("path", "content_type"),
    [
        ("/square-viz/", "text/html"),
        ("/square-viz/index.html", "text/html"),
        ("/square-viz/square-only.js", "text/javascript"),
        ("/square-viz/assets/main-square.js", "text/javascript"),
        ("/square-viz/assets/app-ngkJrQ_K.js", "text/javascript"),
        ("/square-viz/assets/app-mehzAGkK.css", "text/css"),
        ("/square-viz/fonts/HKGrotesk-Regular.otf", "font/otf"),
        ("/square-viz/base_gold.png", "image/png"),
        ("/square-viz/natural_wall.jpg", "image/jpeg"),
    ],
)
def test_packaged_square_visualiser_assets_are_served(
    client: Client, path: str, content_type: str
) -> None:
    status, body, response = client.get(path)
    assert status == 200
    assert response.getheader("Content-Type", "").startswith(content_type)
    assert response.getheader("Cache-Control") == "no-store"
    assert body


def test_square_visualiser_index_uses_independent_asset_revisions(
    client: Client, app: App
) -> None:
    status, body, response = client.get(
        "/square-viz/?replayUrl=%2Fapi%2Fgames%2F1%2Freplay"
    )
    assert status == 200
    assert response.getheader("Cache-Control") == "no-store"
    code_prefix = f"./_code/{app.square_visualiser_code_revision}/".encode()
    sprite_prefix = f"./_sprites/{app.square_visualiser_sprite_revision}/".encode()
    assert b'src="' + code_prefix + b'square-only.js"' in body
    assert b'data-oarena-sprite-base="' + sprite_prefix + b'"' in body
    assert b'src="' + code_prefix + b'assets/main-square.js"' in body
    assert b'href="' + code_prefix + b'assets/app-mehzAGkK.css"' in body
    assert b'"/assets/' not in body
    assert b"/_assets/" not in body


@pytest.mark.parametrize(
    ("namespace", "relative", "content_type"),
    [
        ("code", "square-only.js", "text/javascript"),
        ("code", "assets/main-square.js", "text/javascript"),
        ("code", "assets/app-ngkJrQ_K.js", "text/javascript"),
        ("code", "assets/app-mehzAGkK.css", "text/css"),
        ("code", "fonts/HKGrotesk-Regular.otf", "font/otf"),
        ("sprites", "base_gold.png", "image/png"),
        ("sprites", "natural_wall.jpg", "image/jpeg"),
    ],
)
def test_split_versioned_square_assets_are_immutable(
    client: Client,
    app: App,
    namespace: str,
    relative: str,
    content_type: str,
) -> None:
    revision = getattr(app, f"square_visualiser_{namespace.rstrip('s')}_revision")
    path = f"/square-viz/_{namespace}/{revision}/{relative}"
    status, body, response = client.get(path)
    assert status == 200
    assert body
    assert response.getheader("Content-Type", "").startswith(content_type)
    assert response.getheader("Cache-Control") == servermod._IMMUTABLE


@pytest.mark.parametrize(
    "path",
    [
        "/square-viz/_code/0000000000000000/square-only.js",
        "/square-viz/_sprites/0000000000000000/base_gold.png",
        "/square-viz/_assets/0000000000000000/base_gold.png",
    ],
)
def test_stale_square_asset_revision_is_rejected(client: Client, path: str) -> None:
    status, _body, response = client.get(path)
    assert status == 404
    assert response.getheader("Cache-Control") == "no-store"


def test_legacy_combined_square_asset_route_remains_immutable(
    client: Client, app: App
) -> None:
    path = (
        f"/square-viz/_assets/{app.square_visualiser_revision}/base_gold.png"
    )
    status, body, response = client.get(path)
    assert status == 200
    assert body
    assert response.getheader("Cache-Control") == servermod._IMMUTABLE


@pytest.mark.parametrize(
    ("namespace", "relative"),
    [
        ("code", "base_gold.png"),
        ("sprites", "square-only.js"),
        ("sprites", "assets/main-square.js"),
    ],
)
def test_split_square_asset_routes_reject_the_wrong_kind(
    client: Client, app: App, namespace: str, relative: str
) -> None:
    revision = getattr(app, f"square_visualiser_{namespace.rstrip('s')}_revision")
    status, _body, response = client.get(
        f"/square-viz/_{namespace}/{revision}/{relative}"
    )
    assert status == 404
    assert response.getheader("Cache-Control") == "no-store"


def test_square_asset_revisions_change_independently(tmp_path: Path) -> None:
    source = tmp_path / "viewer.js"
    sprite = tmp_path / "base_gold.png"
    font = tmp_path / "fonts" / "viewer.otf"
    font.parent.mkdir()
    source.write_text("one", encoding="utf-8")
    sprite.write_bytes(b"sprite one")
    font.write_bytes(b"font one")

    first = servermod._square_visualiser_revisions(tmp_path)
    servermod._square_visualiser_revisions.cache_clear()
    source.write_text("two", encoding="utf-8")
    code_changed = servermod._square_visualiser_revisions(tmp_path)
    assert code_changed.code != first.code
    assert code_changed.legacy != first.legacy
    assert code_changed.sprites == first.sprites

    servermod._square_visualiser_revisions.cache_clear()
    (tmp_path / "index.html").write_text("entry changed", encoding="utf-8")
    entry_changed = servermod._square_visualiser_revisions(tmp_path)
    assert entry_changed.code == code_changed.code
    assert entry_changed.legacy != code_changed.legacy
    assert entry_changed.sprites == code_changed.sprites

    servermod._square_visualiser_revisions.cache_clear()
    sprite.write_bytes(b"sprite two")
    sprite_changed = servermod._square_visualiser_revisions(tmp_path)
    assert sprite_changed.code == entry_changed.code
    assert sprite_changed.legacy != entry_changed.legacy
    assert sprite_changed.sprites != entry_changed.sprites
    servermod._square_visualiser_revisions.cache_clear()


@pytest.mark.parametrize(
    "relative",
    [
        "square-only.js",
        "assets/app-ngkJrQ_K.js",
        "assets/app-mehzAGkK.css",
    ],
)
def test_square_text_assets_negotiate_gzip(
    client: Client, app: App, relative: str
) -> None:
    path = (
        f"/square-viz/_code/{app.square_visualiser_code_revision}/{relative}"
    )
    source = (app.square_visualiser_dir / relative).read_bytes()

    status, compressed, response = client.get(
        path, headers={"Accept-Encoding": "br, gzip;q=0.8"}
    )
    assert status == 200
    assert response.getheader("Content-Encoding") == "gzip"
    assert response.getheader("Vary") == "Accept-Encoding"
    assert int(response.getheader("Content-Length", "-1")) == len(compressed)
    assert gzip.decompress(compressed) == source

    status, identity, response = client.get(
        path, headers={"Accept-Encoding": "gzip;q=0, identity"}
    )
    assert status == 200
    assert response.getheader("Content-Encoding") is None
    assert response.getheader("Vary") == "Accept-Encoding"
    assert int(response.getheader("Content-Length", "-1")) == len(source)
    assert identity == source


def test_square_entry_document_negotiates_gzip(client: Client) -> None:
    status, compressed, response = client.get(
        "/square-viz/", headers={"Accept-Encoding": "*;q=1"}
    )
    assert status == 200
    assert response.getheader("Cache-Control") == "no-store"
    assert response.getheader("Content-Encoding") == "gzip"
    assert response.getheader("Vary") == "Accept-Encoding"
    assert b"<!doctype html>" in gzip.decompress(compressed)


def test_square_sprites_are_never_gzip_encoded(client: Client, app: App) -> None:
    source = app.square_visualiser_dir / "base_gold.png"
    path = (
        "/square-viz/_sprites/"
        f"{app.square_visualiser_sprite_revision}/{source.name}"
    )
    status, body, response = client.get(
        path, headers={"Accept-Encoding": "gzip"}
    )
    assert status == 200
    assert body == source.read_bytes()
    assert response.getheader("Content-Encoding") is None
    assert response.getheader("Vary") is None


def test_square_gzip_does_not_change_dashboard_static_responses(client: Client) -> None:
    status, body, response = client.get(
        "/static/app.css", headers={"Accept-Encoding": "gzip"}
    )
    assert status == 200
    assert body
    assert response.getheader("Content-Encoding") is None
    assert response.getheader("Vary") is None


def test_square_gzip_does_not_change_official_visualiser_assets(
    client: Client, app: App
) -> None:
    if app.viz_dir is None:
        pytest.skip("this fcode ships no bundled visualiser")
    source = next(app.viz_dir.rglob("*.js"), None)
    if source is None:
        pytest.skip("this fcode visualiser ships no JavaScript asset")
    relative = source.relative_to(app.viz_dir).as_posix()

    status, body, response = client.get(
        f"/viz/{relative}", headers={"Accept-Encoding": "gzip"}
    )
    assert status == 200
    assert body == source.read_bytes()
    assert response.getheader("Content-Encoding") is None
    assert response.getheader("Vary") is None


def test_every_asset_the_dashboard_references_is_servable(client: Client, app: App) -> None:
    """The shell and every ES module it pulls in must resolve under /static/."""
    import re

    index = (app.web_dir / "index.html").read_text(encoding="utf-8")
    referenced = set(re.findall(r'(?:src|href)="(/static/[^"]+)"', index))
    assert referenced, "index.html references no static assets at all"

    seen: set[str] = set()
    queue = list(referenced)
    while queue:
        path = queue.pop()
        if path in seen:
            continue
        seen.add(path)
        status, body, _response = client.get(path)
        assert status == 200, path
        if path.endswith(".js"):
            for rel in re.findall(r'from\s+"\./([^"]+)"', body.decode("utf-8")):
                queue.append(f"/static/{rel}")

    assert {p.rsplit("/", 1)[-1] for p in seen} >= {"app.css", "app.js"}


def test_oarena_favicon_is_the_packaged_svg(client: Client, app: App) -> None:
    index = (app.web_dir / "index.html").read_text(encoding="utf-8")
    assert '<link rel="icon" type="image/svg+xml" href="/favicon.ico">' in index

    status, body, response = client.get("/favicon.ico")

    assert status == 200
    assert body == (app.web_dir / "favicon.svg").read_bytes()
    assert response.getheader("Content-Type") == "image/svg+xml"
    assert response.getheader("Cache-Control") == "max-age=3600"


def test_dashboard_javascript_parses() -> None:
    """Every shipped dashboard module must at least parse in a JS engine.

    Static-file tests only prove that the browser can download a module.  A
    syntax error prevents it from evaluating at all, which otherwise shows up
    only as an empty dashboard and a console error.  ``node --check`` performs
    exactly the parser step without running any browser-facing code.
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed; cannot syntax-check dashboard JS")

    web_dir = Path(servermod.__file__).resolve().parent / "web"
    modules = sorted(web_dir.glob("*.js"))
    assert modules, "dashboard ships no JavaScript modules"
    for module in modules:
        result = subprocess.run(
            [node, "--check", str(module)], text=True, capture_output=True, check=False
        )
        assert result.returncode == 0, f"{module.name}:\n{result.stderr or result.stdout}"


def test_profiler_telemetry_is_normalised_and_removed_from_visible_log(
    tmp_path: Path,
) -> None:
    """The dashboard accepts schema 2 and repairs v1's legacy 1,000x unit bug."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed; cannot execute dashboard telemetry parser")

    source = Path(servermod.__file__).resolve().parent / "web" / "telemetry.js"
    module = tmp_path / "telemetry.mjs"
    shutil.copy2(source, module)
    script = f"""
const {{ extractProfilerReports, normaliseProfilerRecords }} = await import({json.dumps(module.as_uri())});
const modern = '[OARENA:ProfilerReport] ' + JSON.stringify({{
  schema: 2, clock: 'cpu_us', team: 'a', unit_id: 7, unit_type: 'core',
  from_round: 0, to_round: 999, interrupted: 0, bad_nesting: 0,
  spans: {{ think: {{ calls: 2, total_us: 123, self_us: 100, max_total_us: 70 }} }}
}});
const legacy = 'OARENA_TELEMETRY ' + JSON.stringify({{
  schema: 1, kind: 'profile', team: 'b', unit_id: 8, unit_type: 'builder_bot',
  spans: {{ move: {{ calls: 1, total_us: 5, self_us: 4, max_total_us: 5 }} }}
}});
const malformed = '[OARENA:ProfilerReport] {{not-json';
const result = extractProfilerReports(['before', modern, malformed, legacy, 'after'].join('\\n'));
if (result.reports.length !== 2) throw new Error('expected two profiler reports');
if (result.reports[0].spans.think.total_us !== 123) throw new Error('schema 2 time changed');
if (result.reports[1].spans.move.total_us !== 5000) throw new Error('legacy time was not repaired');
if (result.text !== ['before', malformed, 'after'].join('\\n')) throw new Error('visible log stripping was not exact');
const bridged = normaliseProfilerRecords([{{ payload: JSON.parse(legacy.slice('OARENA_TELEMETRY '.length)), legacy: true }}]);
if (bridged[0].spans.move.self_us !== 4000) throw new Error('bridged legacy time was not repaired');
"""
    result = subprocess.run(
        [node, "--input-type=module", "--eval", script],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_interval_chart_bounds_long_names_and_keeps_the_full_accessible_name(
    tmp_path: Path,
) -> None:
    """Long labels stay in their gutter without losing identity or keyboard access."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed; cannot execute dashboard charts")

    source = Path(servermod.__file__).resolve().parent / "web" / "charts.js"
    module = tmp_path / "charts.mjs"
    shutil.copy2(source, module)
    script = f"""
class FakeElement {{
  constructor(tag) {{ this.tagName = tag; this.attrs = new Map(); this.children = []; this.listeners = new Map(); this.style = {{}}; this.textContent = ""; }}
  setAttribute(key, value) {{ this.attrs.set(key, String(value)); }}
  getAttribute(key) {{ return this.attrs.get(key) ?? null; }}
  appendChild(child) {{ this.children.push(child); return child; }}
  addEventListener(kind, fn) {{ this.listeners.set(kind, fn); }}
}}
globalThis.document = {{ createElementNS: (_ns, tag) => new FakeElement(tag) }};
const {{ intervalChart }} = await import({json.dumps(module.as_uri())});
const full = "codex_fcode_champion_scoped_" + "very_long_variant_name_".repeat(5) + "final_suffix";
const selected = [];
const chart = intervalChart([{{ name: full, rank: 1, mu: 31, sigma: 1, lcb95: 29 }}], {{ onSelect: (name) => selected.push(name) }});
if (chart.getAttribute("role") !== "group") throw new Error("interactive chart must expose descendants");
const group = chart.children.find((node) => node.tagName === "g");
if (!group || group.getAttribute("role") !== "link" || group.getAttribute("tabindex") !== "0") throw new Error("row is not keyboard reachable");
if (!group.getAttribute("aria-label").includes(full)) throw new Error("full name missing from accessible label");
const title = group.children.find((node) => node.tagName === "title");
if (!title || !title.textContent.includes(full)) throw new Error("full name missing from native tooltip");
const label = group.children.find((node) => node.tagName === "text" && node.getAttribute("class") === "band-label");
if (!label || !label.textContent.includes("…") || label.textContent.includes(full)) throw new Error("visible name was not bounded");
let prevented = false;
group.listeners.get("keydown")({{ key: " ", preventDefault: () => {{ prevented = true; }} }});
if (!prevented || selected[0] !== full) throw new Error("Space did not activate the full-name row");
"""
    result = subprocess.run(
        [node, "--input-type=module", "--eval", script],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_game_detail_static_layout_contract() -> None:
    """The replay and report retain their responsive/accessible integration hooks."""
    web_dir = Path(servermod.__file__).resolve().parent / "web"
    source = (web_dir / "views.js").read_text(encoding="utf-8")
    css = (web_dir / "app.css").read_text(encoding="utf-8")

    assert '"&render=square"' not in source
    assert '/^2\\.2\\./' not in source
    assert 'text: "2D"' in source
    assert 'text: "Official 3D"' in source
    assert 'state.config && state.config.visualiser === true' in source
    assert '"oarena.replay.viewer"' in source
    assert "squareViewer.show(vizSlot, data, theme())" in source
    assert "squareViewer?.hide(vizSlot)" in source
    assert "squareViewer.getGame(id)" in source
    assert "squareViewer.prefetch(id)" not in source
    assert "/square-viz/" not in source
    assert '/static/replay2d.html?replayUrl=' not in source
    assert 'src: `/viz/?replayUrl=' in source
    assert 'class: "game-report"' in source
    assert 'text: "Score and rating change"' in source
    assert 'heading("LCB95 change"' in source
    assert 'class: "game-facts"' in source
    assert 'class: "game-score-wrap"' in source
    assert 'class: "game-log-body"' in source
    assert 'class: "game-profiler-body"' in source
    assert "extractProfilerReports" in source
    assert "requestFullscreen" in source
    assert ".viz-frame:fullscreen" in css
    assert '.viz-frame[data-viewer="official"]' in css
    assert ".replay-viewer-picker" in css
    assert "aspect-ratio: 1" not in css[css.index(".viz-frame {"):css.index(".viz-iframe")]
    assert ".game-score-wrap" in css and "overflow-x: auto" in css
    assert ".profile-bar-self" in css


def test_ladder_distinguishes_last_played_from_source_changed() -> None:
    views = (
        Path(servermod.__file__).resolve().parent / "web" / "views.js"
    ).read_text(encoding="utf-8")

    assert 'headerCell("Last played", "last"' in views
    assert 'headerCell("Source changed", "source"' in views
    assert 'source: (r) => r.source_updated || ""' in views
    assert "refs.source.textContent = row.source_updated ? fmt.ago(row.source_updated)" in views


def test_persistent_square_viewer_host_and_single_prime_contract() -> None:
    """One connected viewer primes one likely replay and switches in place."""
    web_dir = Path(servermod.__file__).resolve().parent / "web"
    index = (web_dir / "index.html").read_text(encoding="utf-8")
    app = (web_dir / "app.js").read_text(encoding="utf-8")
    views = (web_dir / "views.js").read_text(encoding="utf-8")
    css = (web_dir / "app.css").read_text(encoding="utf-8")

    assert index.count('id="square-viewer-frame"') == 1
    assert index.count('id="square-viewer-host"') == 1
    assert 'src="/square-viz/?metadataUrl=%2Fapi%2Ffcode-metadata"' in index
    assert 'loading="eager"' in index
    assert "replayUrl=" not in index
    assert index.index('id="square-viewer-host"') > index.index('id="drawer-host"')

    assert "SQUARE_REPLAY_CACHE_ENTRIES" not in app
    assert "SQUARE_PREPARED_ENTRIES" not in app
    assert "pendingPrepares" not in app
    assert "prepared = new Map" not in app
    assert "primeLikelyReplay" in app
    assert "const page = await preloadGames()" in app
    assert "const PAGE = 30" in views
    assert 'q.set("summary", "1")' in views
    assert "export function preloadGames()" in views
    assert "sendLoad(localSource(game), { backgroundPrime: true })" in app
    assert "replayUrl: `/api/games/${encodeURIComponent(key)}/replay`" in app
    assert "event.origin !== location.origin" in app
    assert "event.source !== frame.contentWindow" in app
    for message_type in (
        "oarena:square:hello",
        "oarena:square:ready",
        "oarena:square:visibility",
        "oarena:square:theme",
        "oarena:square:load",
        "oarena:square:loading",
        "oarena:square:loaded",
        "oarena:square:error",
    ):
        assert message_type in app
    assert "currentLoad?.requestId !== message.requestId" in app
    assert "loadedKey === key && currentLoad === null" in app
    assert '"oarena.square.last-game"' in app
    assert "oarena:square:prepare" not in app
    assert "squareViewer.warmRecent" not in app
    assert "squareViewer," in app

    assert "squareReplayIntent" not in views
    assert "squareViewer.show(vizSlot, data, theme())" in views
    assert "squareViewer?.hide(vizSlot)" in views
    assert "squareViewer.requestFullscreen()" in views
    assert 'src: `/viz/?replayUrl=' in views

    assert ".square-viewer-host" in css
    assert "top: -10000px" in css
    assert '.square-viewer-host[data-active="true"]' in css
    assert ".square-viewer-host:fullscreen" in css
    assert "visibility: hidden" in css
    assert "width: max(320px, calc(100vw - var(--rail-w) - 32px))" in css
    assert "height: clamp(420px, calc(100dvh - 105px), 960px)" in css
    assert "function parkedDimensions()" in app
    assert "(dom.view?.clientWidth || window.innerWidth) - 32" in app
    assert "temporaryWake" in app
    assert "{ backgroundPrime: true }" in app


def test_map_ui_separates_official_and_extra_catalogs() -> None:
    web_dir = Path(servermod.__file__).resolve().parent / "web"
    index = (web_dir / "index.html").read_text(encoding="utf-8")
    app_source = (web_dir / "app.js").read_text(encoding="utf-8")
    views_source = (web_dir / "views.js").read_text(encoding="utf-8")

    assert 'id="run-maps-official"' in index
    assert 'id="run-maps-extra"' in index
    assert 'id="run-extra-maps-all"' in index
    assert 'id="run-extra-maps-none"' in index
    for input_id, list_id in (
        ("run-bot-a", "run-bot-a-options"),
        ("run-bot-b", "run-bot-b-options"),
        ("arena-target", "arena-target-options"),
    ):
        assert f'id="{input_id}" type="text" role="combobox"' in index
        assert f'aria-controls="{list_id}"' in index
        assert f'id="{list_id}" role="listbox"' in index
    assert "<datalist" not in index
    assert 'map.source === "extra"' in app_source
    assert 'loadRunDialogDraft(storage, project)' in app_source
    assert 'saveRunDialogDraft(storage, project, {' in app_source
    assert 'maps: selectedMaps()' in app_source
    assert 'createBotCombobox(botB, botBOptions, { everyone: true })' in app_source
    assert 'botSuggestions(state.ladder, input.value, { everyone, limit: 10 })' in app_source
    assert 'event.key === "ArrowDown" || event.key === "ArrowUp"' in app_source
    assert 'event.key === "Escape" && !list.hidden' in app_source
    assert '"Official maps"' in views_source
    assert '"Extra maps"' in views_source


def test_run_submit_cannot_overwrite_a_faster_completed_sse_status() -> None:
    """An ultra-fast failed match may finish before its POST returns."""
    source = (
        Path(servermod.__file__).resolve().parent / "web" / "app.js"
    ).read_text(encoding="utf-8")
    start = source.index("  async function start() {")
    end = source.index('\n  tabMatch.addEventListener("click"', start)
    body = source[start:end]

    capture = "const eventSeqAtSubmit = state.seq;"
    guard = "if (state.seq === eventSeqAtSubmit) {"
    optimistic_write = "state.status = { ...(state.status || {}), running: true"
    assert capture in body
    assert guard in body
    assert body.index(capture) < body.index('await api("/api/')
    assert body.index(guard) < body.index(optimistic_write)


def test_dashboard_live_ladder_ignores_unrated_records_but_matrix_keeps_them(
    tmp_path: Path,
) -> None:
    """The SSE fast path must match a subsequent API refresh for both views."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed; cannot execute dashboard state")

    source = Path(servermod.__file__).resolve().parent / "web" / "state.js"
    module = tmp_path / "state.mjs"
    shutil.copy2(source, module)
    script = f"""
import {{ applyGame, state }} from {json.dumps(module.as_uri())};
const row = (name) => ({{
  name, score: 8, lcb95: 8, mu: 25, sigma: 8, lo: 8, hi: 42,
  games: 0, wins: 0, losses: 0, draws: 0, winrate: null,
  err_games: 0, err_total: 0,
}});
state.ladder = [row("alpha"), row("beta")];
state.counts = {{ games: 0 }};
state.matrix = {{ cells: {{
  alpha: {{ beta: {{ games: 0, wins: 0, losses: 0, draws: 0, winrate: null }} }},
  beta: {{ alpha: {{ games: 0, wins: 0, losses: 0, draws: 0, winrate: null }} }},
}} }};

applyGame({{
  id: 901, a: "alpha", b: "beta", rated: false, winner: "a",
  a_errors: 2, b_errors: 0, ts: "2026-07-30T00:00:00+00:00",
}});
const alpha = state.ladder.find((row) => row.name === "alpha");
const beta = state.ladder.find((row) => row.name === "beta");
if (alpha.games !== 0 || alpha.wins !== 0 || beta.games !== 0 || beta.losses !== 0)
  throw new Error("unrated game changed the ladder record");
if (alpha.err_total !== 2 || alpha.err_games !== 1 || state.counts.games !== 1)
  throw new Error("unrated diagnostics were not retained");
if (state.matrix.cells.alpha.beta.wins !== 1 || state.matrix.cells.beta.alpha.losses !== 1)
  throw new Error("unrated result did not update the diagnostic matrix");

applyGame({{
  id: 902, a: "alpha", b: "beta", rated: true, winner: "a",
  a_errors: 0, b_errors: 0, ts: "2026-07-30T00:00:01+00:00",
  a_mu_after: 29, a_sigma_after: 1,
  b_mu_after: 30, b_sigma_after: 10,
}});
if (alpha.games !== 1 || alpha.wins !== 1 || beta.games !== 1 || beta.losses !== 1)
  throw new Error("rated game did not update the ladder record");
if (state.matrix.cells.alpha.beta.games !== 2 || state.matrix.cells.beta.alpha.games !== 2)
  throw new Error("matrix did not retain both decided results");
if (state.ladder[0] !== beta || beta.rank !== 1 || state.ladder[1] !== alpha || alpha.rank !== 2)
  throw new Error("rated game did not rerank the live ladder by postgame mu");
if (beta.score >= alpha.score)
  throw new Error("test setup no longer makes mu and LCB95 orders disagree");
if (alpha.lcb95 !== alpha.score || beta.lcb95 !== beta.score)
  throw new Error("live LCB95 drifted from the legacy score alias");
"""
    result = subprocess.run(
        [node, "--input-type=module", "--eval", script],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


@pytest.mark.parametrize(
    "path",
    [
        "/static/%2e%2e%2foarena.toml",
        "/static/%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
        "/static/../../../etc/passwd",
        "/square-viz/%2e%2e%2fserver.py",
        "/square-viz/%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
        "/viz/%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    ],
)
def test_path_traversal_is_rejected(client: Client, path: str) -> None:
    status, _body, _response = client.get(path)
    assert status in (404, 503), path


def test_static_refuses_a_non_asset_suffix(client: Client, app: App) -> None:
    (app.web_dir / "secret.pem").write_text("nope", encoding="utf-8")
    try:
        assert client.get("/static/secret.pem")[0] == 404
    finally:
        (app.web_dir / "secret.pem").unlink()


def test_unknown_paths_are_json_404s(client: Client) -> None:
    status, payload = client.send("GET", "/nope")
    assert status == 404
    assert "error" in payload


def test_viz_index_rewrites_absolute_asset_paths(client: Client, app: App) -> None:
    if app.viz_dir is None:
        pytest.skip("this fcode ships no bundled visualiser")
    status, body, _response = client.get("/viz/")
    assert status == 200
    assert b'"/assets/' not in body
    assert b'"/viz/assets/' in body
    assert b"<title>oarena replay</title>" in body
    assert b'id="oarena-viz-keyboard-inspection"' in body
    assert b"Shift plus arrow moves the inspection cursor" in body
    assert b'new MouseEvent(type' in body
    assert b'mouse(canvas, "mousemove", 0)' in body
    assert b'mouse(canvas, "mousedown", 1)' in body
    assert b'mouse(canvas, "mouseup", 0)' in body
    assert b'announce(["Selected", "Clicked"], "Selection cleared")' in body
    assert b'announceNow("Selection cleared")' in body
    assert b'`${label} tile`' not in body
    assert b'canvas.matches(":focus-visible")' in body
    assert b'event.isTrusted' in body
    assert b'pointer(canvas, "pointermove", 0)' not in body
    # The iframe is already an interaction/style boundary. Broad injected CSS
    # used to hide the wide-layout board and disable native tile inspection.
    assert b"main > div.order-2" not in body
    assert b"absolute.inset-x-3.bottom-3.z-50" not in body
    assert b"#root canvas" not in body
    if str(app.fcode_version or "").startswith("2.2."):
        assert b"oarena-square-render-default" in body
    else:
        assert b"oarena-square-render-default" not in body


def test_injected_viz_keyboard_inspection_javascript_parses(
    client: Client, app: App,
) -> None:
    if app.viz_dir is None:
        pytest.skip("this fcode ships no bundled visualiser")
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed; cannot syntax-check viewer integration")

    import re

    body = client.get("/viz/")[1].decode("utf-8")
    match = re.search(
        r'<script id="oarena-viz-keyboard-inspection">(.*?)</script>',
        body,
        flags=re.DOTALL,
    )
    assert match is not None
    script = match.group(1)
    assert 'new MouseEvent(type' in script
    assert 'mouse(canvas, "mousemove", 0)' in script
    assert 'mouse(canvas, "mousedown", 1)' in script
    assert 'mouse(canvas, "mouseup", 0)' in script
    assert 'announce(["Selected", "Clicked"], "Selection cleared")' in script
    assert 'announce("Hovered", "No tile under the inspection cursor")' in script
    assert 'announceNow("Selection cleared")' in script
    assert '`${label} tile`' not in script
    assert 'canvas.matches(":focus-visible")' in script
    assert 'if (isActive(canvas)) notePointerIntent(event);' in script
    assert 'const installedCanvases = new WeakSet();' in script
    assert 'new PointerEvent(' not in script
    assert 'mouse(canvas, "pointermove"' not in script
    assert 'mouse(canvas, "pointerdown"' not in script
    assert 'mouse(canvas, "pointerup"' not in script
    result = subprocess.run(
        [node, "--check", "-"],
        input=script,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_injected_viz_keyboard_inspection_canvas_lifecycle(
    client: Client, app: App,
) -> None:
    if app.viz_dir is None:
        pytest.skip("this fcode ships no bundled visualiser")
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed; cannot exercise viewer integration")

    import re

    body = client.get("/viz/")[1].decode("utf-8")
    match = re.search(
        r'<script id="oarena-viz-keyboard-inspection">(.*?)</script>',
        body,
        flags=re.DOTALL,
    )
    assert match is not None
    harness = r"""
class Target {
  constructor() {
    this.listeners = {}; this.style = {}; this.dataset = {}; this.children = [];
    this.attributes = {}; this.isConnected = false; this.tabIndex = -1;
  }
  addEventListener(type, callback) { (this.listeners[type] ||= []).push(callback); }
  dispatchEvent(event) {
    this.events ||= []; this.events.push(event);
    for (const callback of this.listeners[event.type] || []) callback(event);
    return true;
  }
  emit(type, fields = {}) {
    this.dispatchEvent({type, isTrusted: false, preventDefault() {},
      stopPropagation() {}, stopImmediatePropagation() {}, ...fields});
  }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  matches() { return false; }
  append(node) { node.isConnected = true; this.children.push(node); }
}
let currentCanvas;
const makeCanvas = (left = 0, top = 0, width = 100, height = 100) => {
  const node = new Target(); node.isConnected = true; node.events = [];
  node.rect = {left, top, width, height};
  node.getBoundingClientRect = () => node.rect;
  return node;
};
const bodyNode = new Target(); bodyNode.isConnected = true;
const rootNode = new Target(); rootNode.isConnected = true;
rootNode.querySelector = () => currentCanvas;
const documentNode = new Target();
documentNode.body = bodyNode;
documentNode.querySelector = () => rootNode;
documentNode.querySelectorAll = () => [];
documentNode.getElementById = (id) => id === "root" ? rootNode :
  bodyNode.children.find((node) => node.id === id) || null;
documentNode.createElement = () => new Target();
globalThis.document = documentNode;
globalThis.window = new Target();
globalThis.MouseEvent = class {
  constructor(type, fields) { this.type = type; this.isTrusted = false; Object.assign(this, fields); }
};
let mutationCallback; let observedTarget;
globalThis.MutationObserver = class {
  constructor(callback) { mutationCallback = callback; }
  observe(target) { observedTarget = target; }
};
let nextTask = 1;
const timers = new Map(); const frames = new Map();
globalThis.setTimeout = (callback) => { const id = nextTask++; timers.set(id, callback); return id; };
globalThis.clearTimeout = (id) => timers.delete(id);
globalThis.requestAnimationFrame = (callback) => { const id = nextTask++; frames.set(id, callback); return id; };
globalThis.cancelAnimationFrame = (id) => frames.delete(id);
const flush = () => {
  while (timers.size || frames.size) {
    for (const [id, callback] of [...timers]) { timers.delete(id); callback(); }
    for (const [id, callback] of [...frames]) { frames.delete(id); callback(); }
  }
};
const check = (value, message) => { if (!value) throw new Error(message); };
const key = (target, name, shiftKey = false) => target.emit("keydown", {key: name, shiftKey});

currentCanvas = makeCanvas();
"""
    checks = r"""
const first = currentCanvas;
const cursor = document.getElementById("oarena-inspection-cursor");
const status = document.getElementById("oarena-inspection-status");
check(observedTarget === document.body, "observer cannot see root replacement");
check(first.dataset.oarenaKeyboardMap === "true", "initial canvas was not installed");
status.textContent = "preserved";
key(first, "ArrowRight", true);
check(cursor.style.display === "block", "keyboard cursor was not shown");
currentCanvas = null; first.isConnected = false; mutationCallback(); flush();
check(cursor.style.display === "none", "removed canvas left its cursor visible");
check(status.textContent === "preserved", "removed canvas did not cancel its announcement");

const replacement = makeCanvas(10, 20, 200, 100);
currentCanvas = replacement; mutationCallback();
check(replacement.dataset.oarenaKeyboardMap === "true", "replacement canvas was not installed");
check(replacement.tabIndex === 0 && replacement.attributes.role === "application",
  "replacement canvas is not keyboard accessible");
key(replacement, "ArrowRight", true); flush();
replacement.isConnected = false; first.isConnected = true; currentCanvas = first; mutationCallback();
check(first.listeners.keydown.length === 1, "reactivated canvas duplicated its listeners");
first.events = []; key(first, "ArrowRight", true);
check(first.events.filter((event) => event.type === "mousemove").length === 1,
  "reactivated canvas handled one key more than once");
first.isConnected = false; replacement.isConnected = true; currentCanvas = replacement; mutationCallback();
check(replacement.listeners.keydown.length === 1, "replacement canvas duplicated its listeners");
key(replacement, "ArrowRight", true); flush();
const replacementLeft = cursor.style.left;
const oldMousemoves = first.events.filter((event) => event.type === "mousemove").length;
first.emit("mousemove", {isTrusted: true}); first.emit("blur"); key(first, "ArrowLeft", true);
check(cursor.style.display === "block" && cursor.style.left === replacementLeft,
  "detached canvas changed replacement cursor state");
check(first.events.filter((event) => event.type === "mousemove").length === oldMousemoves + 1,
  "detached canvas synthesized a mousemove");

replacement.events = []; status.textContent = "stale";
replacement.rect = {left: 30, top: 40, width: 240, height: 120};
window.emit("resize");
check(cursor.style.left !== replacementLeft, "resize did not reposition the keyboard cursor");
check(replacement.events.filter((event) => event.type === "mousemove").length === 1,
  "resize did not refresh Phaser hover");
flush();
check(status.textContent === "No tile under the inspection cursor",
  "resize did not refresh hover announcement");

document.emit("mousedown", {isTrusted: true});
replacement.events = []; status.textContent = "hidden"; window.emit("resize"); flush();
check(cursor.style.display === "none", "pointer modality did not hide keyboard cursor");
check(replacement.events.every((event) => event.type !== "mousemove"),
  "hidden cursor synthesized hover on resize");
check(status.textContent === "hidden", "hidden cursor announced hover on resize");
"""
    result = subprocess.run(
        [node, "-"],
        input=harness + match.group(1) + checks,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_viz_square_default_is_limited_to_the_legacy_viewer(
    client: Client, app: App,
) -> None:
    if app.viz_dir is None:
        pytest.skip("this fcode ships no bundled visualiser")
    actual = app.fcode_version
    try:
        app.fcode_version = "2.2.0"
        assert b"oarena-square-render-default" in client.get("/viz/")[1]
        assert b"oarena-square-render-default" not in client.get("/viz/?render=iso")[1]

        app.fcode_version = "2.3.3"
        assert b"oarena-square-render-default" not in client.get("/viz/")[1]
    finally:
        app.fcode_version = actual


def test_viz_serves_its_root_relative_font_paths(client: Client, app: App) -> None:
    if app.viz_dir is None or not (app.viz_dir / "fonts" / "HKGrotesk-Regular.otf").is_file():
        pytest.skip("this fcode ships no bundled viewer font")
    status, body, response = client.get("/fonts/HKGrotesk-Regular.otf")
    assert status == 200
    assert body
    assert response.getheader("Content-Type", "").startswith("font/") or response.getheader("Content-Type", "").startswith("application/")


def test_viz_redirects_the_bare_prefix(client: Client) -> None:
    conn = HTTPConnection(client.host, client.port, timeout=10)
    conn.request("GET", "/viz")
    response = conn.getresponse()
    response.read()
    conn.close()
    assert response.status == 301
    assert response.getheader("Location") == "/viz/"


def test_square_viz_redirects_the_bare_prefix(client: Client) -> None:
    conn = HTTPConnection(client.host, client.port, timeout=10)
    conn.request("GET", "/square-viz")
    response = conn.getresponse()
    response.read()
    conn.close()
    assert response.status == 301
    assert response.getheader("Location") == "/square-viz/"


# --------------------------------------------------------------------------- #
# GET /api
# --------------------------------------------------------------------------- #


def test_api_state_shape(client: Client) -> None:
    state = client.json("/api/state")

    assert set(state) >= {"config", "status", "ladder", "maps", "counts", "fcode", "seq"}
    assert state["config"]["name"] == "proj"
    assert state["counts"]["bots"] == 3
    assert state["counts"]["maps"] == 3
    assert state["counts"]["games"] == 0
    assert isinstance(state["seq"], int)
    assert [row["name"] for row in state["ladder"]] == ["alpha", "beta", "gamma"]


def test_api_fcode_metadata_matches_installed_pure_python_package(client: Client) -> None:
    fcode = pytest.importorskip("fcode")

    payload = client.json("/api/fcode-metadata")
    expected_constants = {}
    for name in dir(fcode.GameConstants):
        if not name.isupper():
            continue
        value = getattr(fcode.GameConstants, name)
        if value is None or type(value) in (bool, int, float, str):
            expected_constants[name] = value

    assert payload["metadata_version"] == 1
    assert payload["version"] == str(fcode.__version__)
    assert payload["game_constants"] == expected_constants
    for enum_name in ("EntityType", "Environment", "ResourceType", "Team", "Direction"):
        enum_type = getattr(fcode, enum_name)
        assert payload["enums"][enum_name] == [
            {"name": member.name, "value": member.value} for member in enum_type
        ]
    assert payload["direction_deltas"] == {
        member.name: list(member.delta()) for member in fcode.Direction
    }


def test_api_fcode_metadata_is_503_when_fcode_cannot_load(
    client: Client, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable() -> Any:
        raise RuntimeError("test package is unavailable")

    monkeypatch.setattr(servermod.config, "_import_fcode", unavailable)
    status, payload = client.send("GET", "/api/fcode-metadata")

    assert status == 503
    assert payload == {"error": "fcode metadata unavailable: test package is unavailable"}


def test_api_ladder_row_shape(client: Client) -> None:
    rows = client.json("/api/ladder")
    assert len(rows) == 3
    assert set(rows[0]) >= {
        "rank", "name", "active", "broken", "broken_reason", "score", "lcb95",
        "mu", "sigma", "lo", "hi", "games", "wins", "losses", "draws", "winrate",
        "err_games", "err_total", "note", "last_played", "source_updated",
        "source_version_id",
    }
    assert rows[0]["lcb95"] == pytest.approx(rows[0]["score"])
    assert rows[0]["source_updated"]
    assert rows[0]["source_version_id"] is None or isinstance(rows[0]["source_version_id"], int)


def test_api_ladder_source_recency_comes_from_versions_not_bot_updates(
    live: tuple[App, Client],
) -> None:
    app, client = live
    version_id = app.store.versions("alpha", limit=1)[0][0]
    app.store._conn.execute(
        "UPDATE bot_versions SET ts = ? WHERE id = ?",
        ("2026-01-02T03:04:05+00:00", version_id),
    )
    # Ratings, health and notes mutate bots.updated; none of them are source edits.
    app.store._conn.execute(
        "UPDATE bots SET updated = ? WHERE name = ?",
        ("2099-12-31T23:59:59+00:00", "alpha"),
    )
    app.store._conn.commit()

    alpha = next(row for row in client.json("/api/ladder") if row["name"] == "alpha")

    assert alpha["source_updated"] == "2026-01-02T03:04:05+00:00"
    assert alpha["source_version_id"] == version_id


def test_api_ladder_ranks_by_mu_when_lcb95_disagrees(
    live: tuple[App, Client],
) -> None:
    from oarena.ratings import Rating

    app, client = live
    app.store.set_rating("alpha", Rating(mu=30.0, sigma=10.0))
    app.store.set_rating("beta", Rating(mu=29.0, sigma=1.0))
    app.store.set_rating("gamma", Rating(mu=28.0, sigma=1.0))

    rows = client.json("/api/ladder")

    assert [row["name"] for row in rows] == ["alpha", "beta", "gamma"]
    assert rows[0]["lcb95"] == pytest.approx(rows[0]["score"])
    assert rows[0]["lcb95"] < rows[1]["lcb95"]
    timeline = client.json("/api/timeline?top=1")
    assert [row["name"] for row in timeline["bots"]] == ["alpha"]
    assert timeline["bots"][0]["lcb95"] == pytest.approx(timeline["bots"][0]["score"])


def test_api_ladder_record_is_rated_while_bot_detail_keeps_all_games(
    live: tuple[App, Client],
) -> None:
    app, client = live
    app.league.finish(
        Job("alpha", "beta", "sprint", 1, rated=True),
        GameOutcome(status="ok", winner="a", win_condition="core_destroyed"),
    )
    app.league.finish(
        Job("alpha", "beta", "sprint", 2, rated=False),
        GameOutcome(status="ok", winner="b", win_condition="core_destroyed"),
    )

    ladder = {row["name"]: row for row in client.json("/api/ladder")}
    assert {
        key: ladder["alpha"][key]
        for key in ("games", "wins", "losses", "draws", "winrate")
    } == {"games": 1, "wins": 1, "losses": 0, "draws": 0, "winrate": 1.0}

    detail = client.json("/api/bots/alpha")
    assert {
        key: detail["record"][key]
        for key in ("games", "wins", "losses", "draws", "winrate")
    } == {"games": 2, "wins": 1, "losses": 1, "draws": 0, "winrate": 0.5}


def test_api_ladder_health_resets_for_a_new_source_version(
    live: tuple[App, Client],
) -> None:
    app, client = live
    alpha = app.store.get_bot("alpha")
    beta = app.store.get_bot("beta")
    assert alpha is not None and beta is not None
    app.store.add_game(
        Game(
            a="alpha",
            b="beta",
            a_src_hash=alpha.src_hash,
            b_src_hash=beta.src_hash,
            map="sprint",
            rated=True,
            status="ok",
            winner="a",
            a_errors=3,
        )
    )

    before = {row["name"]: row for row in client.json("/api/ladder")}
    assert (before["alpha"]["games"], before["alpha"]["err_total"]) == (1, 3)
    assert before["alpha"]["last_played"] is not None

    app.store.set_hash("alpha", "new-alpha-source")

    after = {row["name"]: row for row in client.json("/api/ladder")}
    assert {
        key: after["alpha"][key]
        for key in ("games", "wins", "losses", "draws", "err_games", "err_total")
    } == {
        "games": 0,
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "err_games": 0,
        "err_total": 0,
    }
    assert after["alpha"]["winrate"] is None
    assert after["alpha"]["last_played"] is None
    # The opponent's source did not change, so the same historical game still
    # belongs to beta's current-version record.
    assert after["beta"]["games"] == 1


def test_competitive_apis_exclude_inactive_bots(client: Client, app: App) -> None:
    app.store.set_active("gamma", False)
    # State retains the complete administration catalog, while competitive
    # summaries use only bots that can participate in arena matchmaking.
    active_ladder = client.json("/api/ladder")
    assert [r["name"] for r in active_ladder] == ["alpha", "beta"]
    assert [r["rank"] for r in active_ladder] == [1, 2]
    assert len(client.json("/api/ladder?all=1")) == 3
    assert [r["name"] for r in client.json("/api/ladder?all=0")] == ["alpha", "beta"]
    assert len(client.json("/api/state")["ladder"]) == 3
    assert client.json("/api/matrix")["names"] == ["alpha", "beta"]
    assert [row["name"] for row in client.json("/api/timeline?top=0")["bots"]] == [
        "alpha",
        "beta",
    ]


def test_api_matrix_shape(seeded: tuple[App, Client]) -> None:
    _app, client = seeded
    matrix = client.json("/api/matrix")

    assert set(matrix) == {"names", "cells"}
    assert set(matrix["names"]) == {"alpha", "beta", "gamma"}
    assert matrix["cells"]["alpha"]["beta"]["wins"] == 1
    assert matrix["cells"]["beta"]["alpha"]["losses"] == 1


def test_api_matrix_min_drops_thin_cells(seeded: tuple[App, Client]) -> None:
    _app, client = seeded
    assert client.json("/api/matrix?min=5")["cells"]["alpha"] == {}


def test_api_matrix_rejects_a_non_integer_min(client: Client) -> None:
    status, payload = client.send("GET", "/api/matrix?min=lots")
    assert status == 400 and "error" in payload


def test_api_pair_matrix_is_keyed_by_map_and_is_symmetric(seeded: tuple[App, Client]) -> None:
    _app, client = seeded
    payload = client.json("/api/pair-matrix?a=alpha&b=beta")

    assert payload["names"] == ["alpha", "beta"]
    assert set(payload["columns"]) == {"sprint", "duel", "pinch"}
    assert payload["cells"]["alpha"]["sprint"]["wins"] == 1
    assert payload["cells"]["beta"]["sprint"]["losses"] == 1


def test_api_pair_matrix_validates_the_pair(client: Client) -> None:
    assert client.send("GET", "/api/pair-matrix?a=alpha")[0] == 400
    assert client.send("GET", "/api/pair-matrix?a=alpha&b=alpha")[0] == 400
    assert client.send("GET", "/api/pair-matrix?a=alpha&b=nope")[0] == 404


def test_api_maps(client: Client) -> None:
    payload = client.json("/api/maps")
    assert {m["name"] for m in payload} == {"sprint", "duel", "pinch"}
    assert all({"source", "width", "height", "tiles", "spawns", "games"} <= set(m) for m in payload)


def test_api_maps_and_file_endpoint_include_extra_maps(client: Client, app: App) -> None:
    app.cfg.extra_maps_dir.mkdir(parents=True)
    extra = app.cfg.extra_maps_dir / "generated.map26"
    shutil.copy2(app.cfg.maps_dir / "sprint.map26", extra)

    payload = client.json("/api/maps")
    generated = next(game_map for game_map in payload if game_map["name"] == "generated")
    assert generated["source"] == "extra"

    status, body, _response = client.get("/api/maps/generated/file")
    assert status == 200
    assert body == extra.read_bytes()


def test_map_file_endpoint_only_serves_project_maps(client: Client, app: App) -> None:
    status, body, response = client.get("/api/maps/sprint/file")
    assert status == 200
    assert response.getheader("Content-Type", "").startswith("application/octet-stream")
    assert body == (app.cfg.maps_dir / "sprint.map26").read_bytes()
    assert client.get("/api/maps/%2e%2e%2foarena.toml/file")[0] == 404


def test_map_editor_can_preload_a_project_map(client: Client, app: App) -> None:
    if app.viz_dir is None:
        pytest.skip("this fcode ships no bundled map editor")
    status, body, response = client.get("/map-editor/?map=sprint")
    assert status == 200
    assert response.getheader("Content-Type", "").startswith("text/html")
    assert b'oarena-map-import' in body
    assert b'/api/maps/sprint/file' in body
    assert b'response.arrayBuffer()' in body
    assert b'bytes.byteLength' in body
    assert b'__oarenaMapImportFile' in body
    assert b'waitForEditorScene' in body
    assert b'dispatchImport' in body


def test_storage_reports_usage_and_can_prune_retained_replays(seeded: tuple[App, Client]) -> None:
    app, client = seeded
    game = next(game for game in app.store.list_games() if game.replay)
    replay = app.cfg.replay_dir / game.replay
    assert replay.is_file()

    usage = client.json("/api/storage")
    assert set(usage) == {"replays", "logs", "temporary", "database"}
    assert usage["replays"]["retained"] == 1
    assert usage["replays"]["bytes"] == replay.stat().st_size

    status, payload = client.send("POST", "/api/storage/replays", {"keep": 0})
    assert status == 200
    assert payload["removed"] == 1
    assert payload["freed"] > 0
    assert not replay.exists()
    assert app.store.get_game(game.id).replay == ""  # type: ignore[union-attr]


def test_storage_replay_prune_rejects_a_bad_keep(client: Client) -> None:
    status, payload = client.send("POST", "/api/storage/replays", {"keep": "many"})
    assert status == 400 and "keep" in payload["error"]


def test_storage_budget_can_be_changed_or_made_unlimited(live: tuple[App, Client]) -> None:
    app, client = live
    status, payload = client.send("POST", "/api/storage/budget", {"budget_mb": 7})
    assert status == 200
    assert payload["budget_mb"] == 7
    assert app.cfg.replay_budget_mb == app.league.cfg.replay_budget_mb == 7
    assert "replay_budget_mb = 7" in app.cfg.config_path.read_text(encoding="utf-8")

    status, payload = client.send("POST", "/api/storage/budget", {"budget_mb": None})
    assert status == 200
    assert payload["budget_mb"] is None
    assert payload["storage"]["replays"]["budget_bytes"] is None
    assert app.cfg.replay_budget_mb is None


def test_theme_is_saved_in_project_config_and_served_on_the_next_load(live: tuple[App, Client]) -> None:
    app, client = live
    status, payload = client.send("POST", "/api/theme", {"theme": "light"})
    assert status == 200
    assert payload == {"ok": True, "theme": "light"}
    assert app.cfg.ui_theme == app.league.cfg.ui_theme == "light"
    assert 'ui_theme = "light"' in app.cfg.config_path.read_text(encoding="utf-8")
    assert client.json("/api/state")["config"]["ui_theme"] == "light"

    status, body, _response = client.get("/")
    assert status == 200
    assert b'data-theme="light"' in body


def test_theme_rejects_unknown_values(client: Client) -> None:
    status, payload = client.send("POST", "/api/theme", {"theme": "violet"})
    assert status == 400
    assert "theme" in payload["error"]


def test_api_games_list_and_cursor(seeded: tuple[App, Client]) -> None:
    _app, client = seeded
    payload = client.json("/api/games")

    assert set(payload) == {"games", "next"}
    assert len(payload["games"]) == 2
    assert payload["next"] is None
    assert payload["games"][0]["id"] > payload["games"][1]["id"]
    assert all("fcode_metadata" not in game for game in payload["games"])
    recorded = next(game for game in payload["games"] if game["status"] == "ok")
    assert recorded["fcode_version"] == FAKE_FCODE_VERSION
    assert recorded["has_fcode_metadata"] is True

    page = client.json("/api/games?limit=1")
    assert len(page["games"]) == 1
    assert page["next"] == page["games"][0]["id"]


def test_api_games_summary_has_only_table_fields(seeded: tuple[App, Client]) -> None:
    _app, client = seeded
    payload = client.json("/api/games?summary=1")

    expected = {
        "id", "a", "b", "map", "rated", "status", "winner",
        "win_condition", "turns", "duration_ms", "resign_message", "error",
        "has_replay", "tag", "batch_ordinal", "ts",
    }
    assert len(payload["games"]) == 2
    assert all(set(game) == expected for game in payload["games"])
    assert all(game["batch_ordinal"] is None for game in payload["games"])
    assert next(game for game in payload["games"] if game["status"] == "ok")[
        "has_replay"
    ] is True
    assert next(game for game in payload["games"] if game["status"] == "timeout")[
        "has_replay"
    ] is False

    # The optional representation must not narrow the established default API.
    default_game = client.json("/api/games?summary=0")["games"][0]
    assert "a_src_hash" in default_game
    assert "fcode_version" in default_game
    assert "a_mu_before" in default_game


def test_game_summary_preserves_batch_ordinal() -> None:
    payload = servermod.reporting.game_summary_json(
        Game(tag="webui-match-identity", batch_ordinal=7)
    )

    assert payload["tag"] == "webui-match-identity"
    assert payload["batch_ordinal"] == 7


def test_api_batch_reports_status_and_limits_in_plan_order(
    live: tuple[App, Client],
) -> None:
    app, client = live
    tag = "web-match-recovery"
    app.store.reserve_batch(tag, mode="match", requested_games=3)
    alpha = app.store.get_bot("alpha")
    beta = app.store.get_bot("beta")
    assert alpha is not None and beta is not None
    for ordinal in (2, 0):
        app.store.record_game(
            Game(
                a="alpha",
                b="beta",
                a_src_hash=alpha.src_hash,
                b_src_hash=beta.src_hash,
                map="sprint",
                seed=ordinal,
                rated=False,
                winner="a",
                tag=tag,
                batch_ordinal=ordinal,
            ),
            app.rater,
        )

    payload = client.json(f"/api/batch?tag={tag}&limit=1")

    assert set(payload) == {
        "tag",
        "mode",
        "status",
        "requested_games",
        "played_games",
        "started",
        "finished",
        "games",
        "more",
    }
    assert payload["tag"] == tag
    assert payload["mode"] == "match"
    assert payload["status"] == "running"
    assert payload["requested_games"] == 3
    assert payload["played_games"] == 2
    assert payload["started"]
    assert payload["finished"] == ""
    assert [game["batch_ordinal"] for game in payload["games"]] == [0]
    assert payload["more"] is True

    app.store.finish_batch(tag, status="stopped")
    finished = client.json(f"/api/batch?tag={tag}")
    assert finished["status"] == "stopped"
    assert finished["finished"]
    assert [game["batch_ordinal"] for game in finished["games"]] == [0, 2]
    assert finished["more"] is False


@pytest.mark.parametrize(
    ("path", "expected_status"),
    [
        ("/api/batch", 400),
        ("/api/batch?tag=", 400),
        ("/api/batch?tag=unknown", 404),
        ("/api/batch?tag=unknown&extra=1", 400),
        ("/api/batch?tag=unknown&limit=0", 400),
        ("/api/batch?tag=unknown&limit=501", 400),
        ("/api/batch?tag=unknown&limit=nope", 400),
    ],
)
def test_api_batch_validates_query_and_unknown_tags(
    client: Client, path: str, expected_status: int
) -> None:
    status, payload = client.send("GET", path)

    assert status == expected_status
    assert "error" in payload


@pytest.mark.parametrize(
    ("header", "accepted"),
    [
        ("gzip", True),
        ("br, GZip; q=0.25", True),
        ("br, *;q=0.5", True),
        ("gzip;q=0, *;q=1", False),
        ("*;q=0", False),
        ("br", False),
        ("gzip;q=1.5", False),
        ("gzip;q=invalid", False),
    ],
)
def test_accept_encoding_gzip_quality(header: str, accepted: bool) -> None:
    assert servermod._accepts_gzip(header) is accepted


def test_large_dynamic_json_negotiates_gzip(seeded: tuple[App, Client]) -> None:
    _app, client = seeded
    status, identity, response = client.get("/api/games")
    assert status == 200
    assert len(identity) >= servermod._JSON_GZIP_MIN_BYTES
    assert response.getheader("Content-Encoding") is None
    assert response.getheader("Vary") == "Accept-Encoding"

    status, compressed, response = client.get(
        "/api/games", headers={"Accept-Encoding": "br, gzip;q=0.8"}
    )
    assert status == 200
    assert response.getheader("Content-Encoding") == "gzip"
    assert response.getheader("Vary") == "Accept-Encoding"
    assert int(response.getheader("Content-Length", "-1")) == len(compressed)
    assert gzip.decompress(compressed) == identity
    assert len(compressed) < len(identity)

    status, explicit_identity, response = client.get(
        "/api/games", headers={"Accept-Encoding": "gzip;q=0, *;q=1"}
    )
    assert status == 200
    assert response.getheader("Content-Encoding") is None
    assert response.getheader("Vary") == "Accept-Encoding"
    assert explicit_identity == identity


def test_small_dynamic_json_is_not_varied_or_compressed(
    seeded: tuple[App, Client],
) -> None:
    _app, client = seeded
    path = "/api/games?limit=1&summary=1"
    status, identity, response = client.get(path)
    assert status == 200
    assert len(identity) < servermod._JSON_GZIP_MIN_BYTES
    assert response.getheader("Content-Encoding") is None
    assert response.getheader("Vary") is None

    status, encoded_request, response = client.get(
        path, headers={"Accept-Encoding": "gzip"}
    )
    assert status == 200
    assert response.getheader("Content-Encoding") is None
    assert response.getheader("Vary") is None
    assert encoded_request == identity


def test_api_games_filters(seeded: tuple[App, Client]) -> None:
    _app, client = seeded
    assert len(client.json("/api/games?failed=1")["games"]) == 1
    assert len(client.json("/api/games?map=sprint")["games"]) == 1
    assert len(client.json("/api/games?bot=alpha")["games"]) == 1
    assert len(client.json("/api/games?status=timeout")["games"]) == 1


def test_api_game_detail_includes_the_log_tail(seeded: tuple[App, Client]) -> None:
    app, client = seeded
    gid = app.store.list_games(limit=10)[-1].id
    payload = client.json(f"/api/games/{gid}")

    assert payload["id"] == gid
    assert payload["winner_name"] == "alpha"
    assert payload["rated"] is True
    assert payload["status"] == "ok"
    assert payload["turns"] == 500
    assert payload["map"] == "sprint"
    assert payload["seed"] == 1
    assert payload["win_condition"] == "core_destroyed"
    assert payload["a_delta"] is not None and payload["b_delta"] is not None
    assert payload["has_replay"] is True
    assert payload["fcode_version"] == FAKE_FCODE_VERSION
    assert payload["has_fcode_metadata"] is True
    assert payload["fcode_metadata"] == FAKE_FCODE_METADATA
    assert "ValueError: nope" in payload["log_tail"]
    assert {
        "status", "winner", "rated", "turns", "duration_ms", "win_condition",
        "seed", "map", "ts", "resign_message", "error", "tag",
        "a_titanium", "a_mined", "a_units", "a_buildings", "a_errors",
        "b_titanium", "b_mined", "b_units", "b_buildings", "b_errors",
        "a_mu_before", "a_sigma_before", "a_mu_after", "a_sigma_after", "a_delta",
        "b_mu_before", "b_sigma_before", "b_mu_after", "b_sigma_after", "b_delta",
        "has_log", "has_replay", "log_tail",
    } <= payload.keys()


def test_api_game_detail_returns_null_metadata_for_a_legacy_game(
    live: tuple[App, Client],
) -> None:
    app, client = live
    game = app.league.finish(
        Job("alpha", "beta", "sprint", 9, rated=False),
        GameOutcome(status="ok", winner="a", win_condition="core_destroyed"),
    )

    payload = client.json(f"/api/games/{game.id}")

    assert payload["fcode_version"] == ""
    assert payload["has_fcode_metadata"] is False
    assert payload["fcode_metadata"] is None


def test_api_failed_game_has_unrated_null_rating_change(
    seeded: tuple[App, Client],
) -> None:
    app, client = seeded
    failed = app.store.list_games(limit=1)[0]
    payload = client.json(f"/api/games/{failed.id}")

    assert payload["status"] == "timeout"
    assert payload["rated"] is False
    assert payload["winner"] is None
    assert payload["has_replay"] is False
    assert payload["a_mu_before"] is None and payload["a_delta"] is None
    assert payload["b_mu_before"] is None and payload["b_delta"] is None


def test_api_game_404(client: Client) -> None:
    status, payload = client.send("GET", "/api/games/999")
    assert status == 404 and "error" in payload


def test_api_replay_streams_bytes(seeded: tuple[App, Client]) -> None:
    app, client = seeded
    gid = app.store.list_games(limit=10)[-1].id

    status, body, response = client.get(f"/api/games/{gid}/replay")

    assert status == 200
    assert response.getheader("Content-Type") == "application/octet-stream"
    assert body == b"REPLAY" * 20
    assert int(response.getheader("Content-Length")) == len(body)


def test_api_replay_404_when_pruned(seeded: tuple[App, Client]) -> None:
    app, client = seeded
    gid = app.store.list_games(limit=10)[-1].id
    app.store.clear_replay(gid)

    assert client.get(f"/api/games/{gid}/replay")[0] == 404


def test_api_log_is_plain_text(seeded: tuple[App, Client]) -> None:
    app, client = seeded
    gid = app.store.list_games(limit=10)[-1].id

    status, body, response = client.get(f"/api/games/{gid}/log")

    assert status == 200
    assert response.getheader("Content-Type", "").startswith("text/plain")
    assert b"ValueError" in body


def test_api_log_404_without_one(seeded: tuple[App, Client]) -> None:
    app, client = seeded
    gid = app.store.list_games(limit=10)[0].id  # the timeout kept no log
    assert client.get(f"/api/games/{gid}/log")[0] == 404


def test_api_bot_detail_shape(seeded: tuple[App, Client]) -> None:
    _app, client = seeded
    detail = client.json("/api/bots/alpha")

    assert set(detail) == {"bot", "record", "h2h", "maps", "history", "versions", "crashes"}
    assert detail["bot"]["name"] == "alpha"
    assert detail["record"]["wins"] == 1
    assert detail["h2h"][0]["opponent"] == "beta"
    assert detail["maps"][0]["map"] == "sprint"
    assert detail["history"]


def test_api_timeline_returns_ranked_histories(seeded: tuple[App, Client]) -> None:
    _app, client = seeded
    payload = client.json("/api/timeline?top=2")

    assert len(payload["bots"]) == 2
    assert [row["rank"] for row in payload["bots"]] == [1, 2]
    assert all({"name", "history", "versions"} <= set(row) for row in payload["bots"])


def test_app_close_force_stops_a_live_arena(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ctrl-C/server shutdown must cancel workers rather than drain them."""
    calls: list[object] = []
    monkeypatch.setattr(
        app.league,
        "force_stop",
        lambda **kwargs: calls.append(("force", kwargs)) or 0,
    )
    monkeypatch.setattr(
        app.league, "wait", lambda timeout=None: calls.append(("wait", timeout)) or True
    )

    app.close()

    assert calls == [("force", {"discard_cancelled": True}), ("wait", 0.25)]


def test_api_bot_404(client: Client) -> None:
    status, payload = client.send("GET", "/api/bots/ghost")
    assert status == 404 and "error" in payload


# --------------------------------------------------------------------------- #
# SSE
# --------------------------------------------------------------------------- #


def test_events_streams_hello_then_live_events(live: tuple[App, Client]) -> None:
    app, client = live
    conn = HTTPConnection(client.host, client.port, timeout=10)
    # Resume from "now" so the first live frame is not a replayed sync event.
    conn.request("GET", f"/api/events?since={app.bus.last_seq}")
    response = conn.getresponse()

    try:
        assert response.status == 200
        assert response.getheader("Content-Type", "").startswith("text/event-stream")
        assert response.getheader("Cache-Control") == "no-store"

        hello = _read_frame(response)
        assert hello["event"] == "hello"
        assert "seq" in json.loads(hello["data"])["data"]

        app.bus.emit("log", level="info", msg="hello from the test")
        frame = _read_frame(response)
        assert frame["event"] == "log"
        assert json.loads(frame["data"])["data"]["msg"] == "hello from the test"
    finally:
        conn.close()


def test_events_replays_the_gap_from_since(live: tuple[App, Client]) -> None:
    app, client = live
    first = app.bus.emit("log", level="info", msg="one")
    app.bus.emit("log", level="info", msg="two")

    conn = HTTPConnection(client.host, client.port, timeout=10)
    conn.request("GET", f"/api/events?since={first.seq}")
    response = conn.getresponse()
    try:
        assert _read_frame(response)["event"] == "hello"
        replayed = _read_frame(response)
        assert json.loads(replayed["data"])["data"]["msg"] == "two"
    finally:
        conn.close()


def _read_frame(response: HTTPResponse, timeout: float = 10.0) -> dict[str, str]:
    """Read SSE lines until one complete frame has arrived."""
    frame: dict[str, str] = {}
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        raw = response.fp.readline()  # type: ignore[union-attr]
        if not raw:
            break
        line = raw.decode("utf-8").rstrip("\n")
        if line.startswith(":") or line.startswith("retry:"):
            continue
        if line == "":
            if frame:
                return frame
            continue
        key, _, value = line.partition(":")
        frame[key.strip()] = value.strip()
    raise AssertionError(f"no complete SSE frame arrived (partial: {frame})")


# --------------------------------------------------------------------------- #
# POST
# --------------------------------------------------------------------------- #


def test_post_match_accepts_and_reports_the_total(live: tuple[App, Client]) -> None:
    app, client = live
    status, payload = client.send(
        "POST", "/api/match", {"a": "alpha", "b": "beta", "maps": ["sprint"], "mirror": True}
    )
    assert status == 202
    assert payload == {"total": 2}
    assert app.league.wait(timeout=30.0)
    assert app.store.game_count() == 2


def test_post_match_can_reserve_an_immutable_tag(
    live: tuple[App, Client],
) -> None:
    app, client = live
    status, payload = client.send(
        "POST",
        "/api/match",
        {
            "a": "alpha",
            "b": "beta",
            "maps": ["sprint"],
            "mirror": True,
            "tag": "codex_api_gate_v1",
        },
    )

    assert status == 202
    assert payload == {"total": 2, "tag": "codex_api_gate_v1"}
    assert app.league.wait(timeout=30.0)
    batch = app.store.batch("codex_api_gate_v1")
    assert batch is not None and batch["status"] == "completed"
    assert app.store.game_count(tag="codex_api_gate_v1") == 2


def test_post_match_requires_both_bots(client: Client) -> None:
    status, payload = client.send("POST", "/api/match", {"a": "alpha"})
    assert status == 400 and "error" in payload


def test_post_match_rejects_an_unknown_bot(client: Client) -> None:
    status, payload = client.send("POST", "/api/match", {"a": "alpha", "b": "ghost"})
    assert status == 400 and "ghost" in payload["error"]


def test_a_second_run_is_a_409(live: tuple[App, Client]) -> None:
    app, client = live
    app.league.start_arena("ladder")
    try:
        assert client.send("POST", "/api/arena", {})[0] == 409
        assert client.send(
            "POST", "/api/match", {"a": "alpha", "b": "beta", "maps": ["sprint"]}
        )[0] == 409
        assert client.send("POST", "/api/sync")[0] == 409
        assert client.send(
            "POST", "/api/bots/alpha/note", {"note": "must wait"}
        )[0] == 409
        assert client.send(
            "POST", "/api/bots/alpha/active", {"active": False}
        )[0] == 409
        assert client.send("POST", "/api/recompute")[0] == 409
        assert client.send("POST", "/api/reset")[0] == 409
    finally:
        app.league.stop()
        app.league.wait(timeout=30.0)


def test_post_arena_and_stop(live: tuple[App, Client]) -> None:
    app, client = live
    status, payload = client.send("POST", "/api/arena", {"kind": "rr"})
    assert status == 202 and payload == {"ok": True}
    assert app.league.running

    assert client.send("POST", "/api/stop")[0] == 202
    assert app.league.wait(timeout=30.0)


def test_post_force_stop_requests_an_immediate_abort(live: tuple[App, Client]) -> None:
    app, client = live
    app.league.start_arena("ladder")
    status, payload = client.send("POST", "/api/stop", {"force": True})

    assert status == 202
    assert payload["ok"] is True
    assert payload["force"] is True
    assert app.league.wait(timeout=30.0)


def test_post_arena_rejects_a_bad_kind(client: Client) -> None:
    assert client.send("POST", "/api/arena", {"kind": "telepathy"})[0] == 400


def test_post_arena_vs_needs_a_target(client: Client) -> None:
    assert client.send("POST", "/api/arena", {"kind": "vs"})[0] == 400


def test_post_sync_returns_a_report(live: tuple[App, Client]) -> None:
    app, client = live
    (app.cfg.bots_dir / "delta").mkdir()
    (app.cfg.bots_dir / "delta" / "main.py").write_text("pass\n", encoding="utf-8")

    status, payload = client.send("POST", "/api/sync")

    assert status == 200
    assert set(payload) == {"added", "changed", "missing", "unbroken"}
    assert payload["added"] == ["delta"]


def test_post_bot_active(live: tuple[App, Client]) -> None:
    app, client = live
    status, payload = client.send("POST", "/api/bots/alpha/active", {"active": False})

    assert status == 200 and payload["active"] is False
    assert app.store.get_bot("alpha").active is False  # type: ignore[union-attr]


def test_post_bot_note(live: tuple[App, Client]) -> None:
    app, client = live
    status, payload = client.send("POST", "/api/bots/alpha/note", {"note": "champion"})

    assert status == 200 and payload["note"] == "champion"
    assert app.store.get_bot("alpha").note == "champion"  # type: ignore[union-attr]


def test_post_bot_actions_404_on_an_unknown_bot(client: Client) -> None:
    assert client.send("POST", "/api/bots/ghost/active", {"active": True})[0] == 404
    assert client.send("POST", "/api/bots/ghost/note", {"note": "x"})[0] == 404


def test_post_recompute(seeded: tuple[App, Client]) -> None:
    _app, client = seeded
    status, payload = client.send("POST", "/api/recompute")
    assert status == 200 and payload["ok"] is True


def test_post_reset_keeps_bots(seeded: tuple[App, Client]) -> None:
    app, client = seeded
    status, payload = client.send("POST", "/api/reset", {})

    assert status == 200 and payload["all"] is False
    assert app.store.game_count() == 0
    assert len(app.store.bots()) == 3
    assert app.store.get_bot("alpha").rating == app.rater.initial()  # type: ignore[union-attr]


def test_post_reset_all_wipes_the_files(seeded: tuple[App, Client]) -> None:
    app, client = seeded
    assert list(app.cfg.replay_dir.glob("*.replay26"))

    status, payload = client.send("POST", "/api/reset", {"all": True})

    assert status == 200 and payload["all"] is True
    assert list(app.cfg.replay_dir.glob("*.replay26")) == []
    assert list(app.cfg.log_dir.glob("*.log")) == []
    # sync re-registers the bots that are still on disk
    assert len(app.store.bots()) == 3


def test_post_reset_clean_recreates_a_fresh_ladder(seeded: tuple[App, Client]) -> None:
    app, client = seeded
    status, payload = client.send("POST", "/api/reset", {"all": True, "clean": True})

    assert status == 200 and payload["clean"] is True
    assert app.store.game_count() == 0
    # Bot rows are immediately rediscovered from bots/, with fresh initial ratings.
    assert len(app.store.bots()) == 3
    assert all(bot.rating == app.rater.initial() for bot in app.store.bots())


def test_post_map_editor_launches_fcode(live: tuple[App, Client], monkeypatch: pytest.MonkeyPatch) -> None:
    _app, client = live
    launched: list[list[str]] = []

    def fake_popen(args: list[str], **_kwargs: Any) -> object:
        launched.append(args)
        return object()

    monkeypatch.setattr(servermod.subprocess, "Popen", fake_popen)
    status, payload = client.send("POST", "/api/maps/editor")

    assert status == 202 and payload["ok"] is True
    assert launched and Path(launched[0][0]).name == "fcode" and launched[0][1:] == ["map-editor"]


def test_delete_bot(seeded: tuple[App, Client]) -> None:
    app, client = seeded
    status, payload = client.send("DELETE", "/api/bots/alpha")

    assert status == 200 and payload["name"] == "alpha"
    assert app.store.get_bot("alpha") is None
    assert all("alpha" not in (g.a, g.b) for g in app.store.list_games())


def test_external_shared_server_cannot_delete_owner_history_or_replays(
    seeded: tuple[App, Client], tmp_path: Path
) -> None:
    app, client = seeded
    game = next(game for game in app.store.list_games() if game.replay)
    replay = app.cfg.replay_dir / game.replay
    before_games = app.store.game_count()
    borrower_root = tmp_path / "borrower"
    borrower_root.mkdir()
    borrower_config = borrower_root / "oarena.toml"
    borrower_config.write_text(
        app.cfg.config_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    borrowed = replace(
        app.cfg,
        root=borrower_root,
        state_dir_override=app.cfg.state_dir,
    )
    assert borrowed.owns_state_dir is False
    app.cfg = borrowed
    app.league.cfg = borrowed

    responses = (
        client.send("DELETE", "/api/bots/alpha"),
        client.send("POST", "/api/storage/replays", {"keep": 0}),
        client.send("POST", "/api/storage/budget", {"budget_mb": 0}),
    )

    assert [status for status, _payload in responses] == [403, 403, 403]
    assert all("external shared state" in payload["error"] for _status, payload in responses)
    assert app.store.get_bot("alpha") is not None
    assert app.store.game_count() == before_games
    assert replay.is_file()
    assert app.store.get_game(game.id).replay == game.replay  # type: ignore[union-attr]


def test_delete_unknown_bot_is_404(client: Client) -> None:
    assert client.send("DELETE", "/api/bots/ghost")[0] == 404


def test_delete_on_a_non_bot_path_is_404(client: Client) -> None:
    assert client.send("DELETE", "/api/state")[0] == 404


def test_a_malformed_body_is_a_400(client: Client) -> None:
    conn = HTTPConnection(client.host, client.port, timeout=10)
    conn.request("POST", "/api/match", body=b"{not json", headers={"Content-Type": "application/json"})
    response = conn.getresponse()
    body = response.read()
    conn.close()

    assert response.status == 400
    assert b"error" in body


# --------------------------------------------------------------------------- #
# authenticated FCode platform proxy
# --------------------------------------------------------------------------- #


_PLATFORM_MATCH_ID = "123e4567-e89b-42d3-a456-426614174000"
_PLATFORM_TEAM_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


class _PlatformStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def session(self) -> dict[str, Any]:
        self.calls.append(("session", None))
        return {"authenticated": True, "team": {"id": _PLATFORM_TEAM_ID, "name": "Alpha"}}

    def matches(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("matches", kwargs))
        return {"matches": [{"id": _PLATFORM_MATCH_ID}], "next_cursor": "next"}

    def match(self, match_id: str) -> dict[str, Any]:
        self.calls.append(("match", match_id))
        return {"match": {"id": match_id}, "games": [{"number": 1}]}

    def replay(self, match_id: str, game: int) -> bytes:
        self.calls.append(("replay", (match_id, game)))
        return b"REMOTE-REPLAY"

    def ladder(self, *, limit: int) -> dict[str, Any]:
        self.calls.append(("ladder", limit))
        return {"rankings": [{"rank": 1}], "total": 250}

    def test_runs(self, *, limit: int) -> dict[str, Any]:
        self.calls.append(("test_runs", limit))
        return {"test_runs": [{"id": "test-run-one"}], "total": 1}


def test_platform_json_routes_validate_and_forward_narrow_arguments(
    app: App, client: Client
) -> None:
    platform = _PlatformStub()
    app.platform = platform  # type: ignore[assignment]

    assert client.json("/api/platform/session")["team"]["name"] == "Alpha"
    matches = client.json(
        "/api/platform/matches?limit=999&type=ladder&mine=1&cursor=page-two"
    )
    assert matches["next_cursor"] == "next"
    assert platform.calls[-1] == (
        "matches",
        {
            "limit": 100,
            "match_type": "ladder",
            "mine": True,
            "team_id": None,
            "cursor": "page-two",
        },
    )
    detail = client.json(f"/api/platform/matches/{_PLATFORM_MATCH_ID}")
    assert detail["games"] == [{"number": 1}]
    ladder = client.json("/api/platform/ladder?limit=0")
    assert ladder["total"] == 250
    assert platform.calls[-1] == ("ladder", 1)
    test_runs = client.json("/api/platform/test-runs?limit=999")
    assert test_runs["test_runs"] == [{"id": "test-run-one"}]
    assert platform.calls[-1] == ("test_runs", 100)
    client.json("/api/platform/test-runs?limit=0")
    assert platform.calls[-1] == ("test_runs", 1)
    client.json("/api/platform/test-runs")
    assert platform.calls[-1] == ("test_runs", 50)


def test_platform_team_filter_is_a_canonical_uuid(app: App, client: Client) -> None:
    platform = _PlatformStub()
    app.platform = platform  # type: ignore[assignment]
    client.json(f"/api/platform/matches?team_id={_PLATFORM_TEAM_ID}")
    assert platform.calls[-1][1]["team_id"] == _PLATFORM_TEAM_ID


def test_platform_replay_is_same_origin_immutable_and_octet_stream(
    app: App, client: Client
) -> None:
    platform = _PlatformStub()
    app.platform = platform  # type: ignore[assignment]

    status, body, response = client.get(
        f"/api/platform/matches/{_PLATFORM_MATCH_ID}/games/3/replay"
    )
    assert status == 200
    assert body == b"REMOTE-REPLAY"
    assert response.getheader("Content-Type") == "application/octet-stream"
    assert response.getheader("Cache-Control") == servermod._PRIVATE_IMMUTABLE
    assert response.getheader("X-Content-Type-Options") == "nosniff"
    assert _PLATFORM_MATCH_ID in response.getheader("Content-Disposition", "")
    assert platform.calls == [("replay", (_PLATFORM_MATCH_ID, 3))]


@pytest.mark.parametrize(
    "path",
    [
        "/api/platform/session?surprise=1",
        "/api/platform/matches?limit=not-a-number",
        "/api/platform/matches?limit=1&limit=2",
        "/api/platform/matches?type=tournament",
        f"/api/platform/matches?mine=1&team_id={_PLATFORM_TEAM_ID}",
        f"/api/platform/matches?team_id={_PLATFORM_TEAM_ID.upper()}",
        "/api/platform/ladder?cursor=unexpected",
        "/api/platform/test-runs?cursor=unexpected",
        "/api/platform/test-runs?limit=not-a-number",
        "/api/platform/test-runs?limit=1&limit=2",
    ],
)
def test_platform_query_validation_is_a_400(client: Client, path: str) -> None:
    status, payload = client.send("GET", path)
    assert status == 400
    assert "error" in payload


@pytest.mark.parametrize(
    "path",
    [
        "/api/platform/matches/not-a-uuid",
        f"/api/platform/matches/{_PLATFORM_MATCH_ID.upper()}",
        f"/api/platform/matches/{_PLATFORM_MATCH_ID}/games/0/replay",
        f"/api/platform/matches/{_PLATFORM_MATCH_ID}/games/6/replay",
    ],
)
def test_platform_noncanonical_resource_paths_are_404(client: Client, path: str) -> None:
    status, _payload = client.send("GET", path)
    assert status == 404


def test_typed_platform_errors_keep_their_status(app: App, client: Client) -> None:
    class Limited(_PlatformStub):
        def matches(self, **kwargs: Any) -> dict[str, Any]:
            raise servermod.PlatformError(429, "FCode platform rate limit reached")

    app.platform = Limited()  # type: ignore[assignment]
    status, payload = client.send("GET", "/api/platform/matches")
    assert status == 429
    assert payload == {"error": "FCode platform rate limit reached"}


# --------------------------------------------------------------------------- #
# wiring
# --------------------------------------------------------------------------- #


def test_app_create_builds_the_whole_stack(project: Project) -> None:
    app = App.create(project.cfg, workers=2)
    try:
        assert app.cfg.workers == 2
        assert app.league.cfg is app.cfg
        assert app.config_json()["workers"] == 2
    finally:
        app.close()


def test_make_server_falls_back_to_a_free_port(app: App) -> None:
    first = make_server(app, "127.0.0.1", 0)
    try:
        busy = int(first.server_address[1])
        second = make_server(app, "127.0.0.1", busy)
        try:
            assert int(second.server_address[1]) != busy
        finally:
            second.server_close()
    finally:
        first.server_close()


def test_make_server_strict_port_refuses_to_fall_back(app: App) -> None:
    first = make_server(app, "127.0.0.1", 0)
    try:
        busy = int(first.server_address[1])
        with pytest.raises(OSError):
            make_server(app, "127.0.0.1", busy, strict_port=True)
    finally:
        first.server_close()


def test_safe_join_refuses_to_escape(tmp_path: Path) -> None:
    (tmp_path / "inside.txt").write_text("x", encoding="utf-8")
    assert servermod._safe_join(tmp_path, "inside.txt") == (tmp_path / "inside.txt").resolve()
    assert servermod._safe_join(tmp_path, "../outside") is None
    assert servermod._safe_join(tmp_path, "") is None
