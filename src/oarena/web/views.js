/**
 * views.js — the five oarena views (ladder, matrix, games, game, bots, maps).
 *
 * Each renderer owns everything inside the `<main id="view">` element it is
 * handed: it paints a synchronous skeleton first (so a route change never shows
 * a blank panel or shifts layout when the data lands), kicks off its own fetches
 * through `state.api`, and returns a cleanup function that tears down every
 * subscription and timer it opened.
 *
 * Rendering rule of the module: no `innerHTML`. Every node comes from `el()` and
 * every piece of server-supplied text — bot names, notes, error strings, raw bot
 * stderr — goes through `textContent`. There is no path from arena data to
 * parsed markup.
 */

import { state, on, api, fmt } from "./state.js";
import { CI, barChart, heatCell, intervalChart, lineChart, mapThumb, multiRatingChart, sparkline } from "./charts.js";
import {
  isPlatformMatchId,
  loadPlatformSelection,
  normalizePlatformGame,
  parsePlatformMatchInput,
  platformGameWinnerName,
  platformTeamOutcome,
  platformViewHash,
  savePlatformSelection,
} from "./platform-form.js";
import { isLatestMatchGame } from "./run-form.js";
import { createMapPreview } from "./map-preview.js";
import { batchOverallResult, batchScore, batchScoreTitle } from "./match-score.js";
import { playedRunOrdinal as resolvePlayedRunOrdinal } from "./version-runs.js";
import {
  buildAutoscrimConfig,
  buildScrimRequest,
  canonicalScrimUuid,
  newScrimRequestKey,
  normalizeScrimMaps,
  SCRIM_MAP_MAX,
} from "./scrim-form.js";
import {
  extractProfilerReports,
  normaliseProfilerRecords,
  PROFILER_SPAN_MODES,
  profilerSpanMetric,
} from "./telemetry.js";

/* -------------------------------------------------------------------------- */
/* DOM helpers                                                                */
/* -------------------------------------------------------------------------- */

/**
 * Build an element. `attrs` understands `class`, `text`, `dataset`, `style`
 * (string or object), `onclick`-style listeners and plain attributes; `false`,
 * `null` and `undefined` values are skipped. Children may be nodes, strings,
 * arrays or nullish (dropped), and strings always become text nodes.
 */
function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  if (attrs) {
    for (const key of Object.keys(attrs)) {
      const value = attrs[key];
      if (value === null || value === undefined || value === false) continue;
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = String(value);
      else if (key === "dataset") Object.assign(node.dataset, value);
      else if (key === "style") {
        if (typeof value === "string") node.style.cssText = value;
        else Object.assign(node.style, value);
      } else if (key.startsWith("on") && typeof value === "function") {
        node.addEventListener(key.slice(2).toLowerCase(), value);
      } else node.setAttribute(key, value === true ? "" : String(value));
    }
  }
  append(node, children);
  return node;
}

function append(node, children) {
  for (const child of children) {
    if (child === null || child === undefined || child === false) continue;
    if (Array.isArray(child)) append(node, child);
    else if (child instanceof Node) node.appendChild(child);
    else node.appendChild(document.createTextNode(String(child)));
  }
}

/**
 * Replace a node's contents, dropping nullish children.
 *
 * Use this instead of the native `replaceChildren`: that one stringifies its
 * arguments, so the very common `cond ? el(...) : null` idiom silently renders
 * the literal text "null" into the page.
 */
function fill(node, ...children) {
  node.textContent = "";
  append(node, children);
  return node;
}

const code = (text) => el("code", { text });

/** A `.btn` with an optional leading icon path. */
function btn(label, attrs = {}) {
  const { class: cls, ...rest } = attrs;
  return el("button", { class: cls || "btn btn-sm", type: "button", ...rest }, label);
}

/** Toggle button whose pressed state drives the accent styling. */
function toggleBtn(label, pressed, onToggle, extra = {}) {
  return el(
    "button",
    {
      class: "btn btn-sm",
      type: "button",
      "aria-pressed": pressed ? "true" : "false",
      onclick(event) {
        const next = event.currentTarget.getAttribute("aria-pressed") !== "true";
        event.currentTarget.setAttribute("aria-pressed", next ? "true" : "false");
        onToggle(next);
      },
      ...extra,
    },
    label
  );
}

/** The shared search box (`/` focuses the first one in the view). */
function searchBox(value, placeholder, onInput) {
  const input = el("input", {
    class: "input",
    type: "search",
    value: value || "",
    placeholder,
    "aria-label": placeholder,
    oninput: (event) => onInput(event.currentTarget.value),
  });
  return { wrap: el("div", { class: "search" }, input, el("span", { class: "search-hint", text: "/" })), input };
}

/* -------------------------------------------------------------------------- */
/* shared view furniture                                                      */
/* -------------------------------------------------------------------------- */

function viewRoot({ title = "", sub = "", crumbs = null, toolbar = null, full = false } = {}, ...children) {
  const subEl = el("span", { class: "view-sub", text: sub || "" });
  const head = el(
    "header",
    { class: "view-head" },
    el("h1", { class: "view-title" }, title, subEl),
    crumbs || null,
    toolbar ? el("div", { class: "toolbar" }, toolbar) : null
  );
  const view = el("div", { class: full ? "view view-full" : "view" }, head, ...children);
  view.setSub = (text) => {
    subEl.textContent = text || "";
  };
  return view;
}

function crumbs(...parts) {
  const nodes = [];
  parts.forEach((part, index) => {
    if (index) nodes.push(el("span", { text: "/" }));
    nodes.push(part);
  });
  return el("nav", { class: "view-crumbs", "aria-label": "Breadcrumb" }, nodes);
}

function emptyState({ title = "", hint = null, actions = null } = {}) {
  return el(
    "div",
    { class: "empty" },
    el(
      "div",
      { class: "empty-icon" },
      (() => {
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("viewBox", "0 0 24 24");
        svg.setAttribute("fill", "none");
        svg.setAttribute("stroke", "currentColor");
        svg.setAttribute("stroke-width", "1.4");
        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.setAttribute("d", "M4 6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v11a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 17.5zM8 12h8");
        svg.appendChild(path);
        return svg;
      })()
    ),
    el("div", { class: "empty-title", text: title }),
    hint ? el("div", { class: "empty-hint" }, hint) : null,
    actions && actions.length ? el("div", { class: "empty-actions" }, actions) : null
  );
}

function skeletonRows(count = 6) {
  return el(
    "div",
    { class: "panel" },
    Array.from({ length: count }, () => el("div", { class: "skeleton skeleton-row" }))
  );
}

function crashPanel(err) {
  return el(
    "div",
    { class: "view" },
    emptyState({
      title: "This view failed to render",
      hint: [String((err && err.message) || err)],
      actions: [btn("Reload", { class: "btn btn-sm btn-primary", onclick: () => refreshView() })],
    })
  );
}

/** Append a toast to the shared host (views report their own action results). */
function toast(message, level = "info") {
  const host = document.getElementById("toast-host");
  if (!host) return;
  const node = el(
    "div",
    { class: "toast", "data-level": level },
    el("span", { class: "toast-msg", text: message })
  );
  const close = el("button", { class: "toast-close", type: "button", "aria-label": "Dismiss", text: "✕" });
  const remove = () => {
    node.classList.add("is-leaving");
    setTimeout(() => node.remove(), 160);
  };
  close.addEventListener("click", remove);
  node.appendChild(close);
  host.appendChild(node);
  setTimeout(remove, level === "error" ? 9000 : 4500);
}

function errorMessage(err) {
  if (!err) return "unknown error";
  if (err.payload && err.payload.error) return String(err.payload.error);
  return String(err.message || err);
}

/* -------------------------------------------------------------------------- */
/* small data-shaped components                                               */
/* -------------------------------------------------------------------------- */

const nameHref = (name) => `#/bots/${encodeURIComponent(name)}`;
const gameHref = (id) => `#/games/${encodeURIComponent(id)}`;
const isWebMatchTag = (tag) => typeof tag === "string" && tag.startsWith("web-match-");

/** A bot identity is always a route to its detail page, including inside a game row. */
function botLink(name, { class: className = "", title = name, ...attrs } = {}) {
  return el(
    "a",
    {
      class: ["bot-link", className].filter(Boolean).join(" "),
      href: nameHref(name),
      title,
      ...attrs,
      // Most uses live inside a clickable game row/card. Let the anchor own
      // this interaction so a click or Enter follows the bot, not its parent.
      onclick: (event) => event.stopPropagation(),
      onkeydown: (event) => event.stopPropagation(),
    },
    name
  );
}

/** `.bot-name` cell contents: the name plus its broken / off chips. */
function botName(row) {
  const chips = [];
  if (row.broken) {
    chips.push(
      el("span", {
        class: "chip chip-broken",
        text: "broken",
        title: row.broken_reason || "this bot failed to load",
      })
    );
  }
  if (row.active === false) chips.push(el("span", { class: "chip chip-inactive", text: "off" }));
  return el("span", { class: "bot-name" }, botLink(row.name, { class: "name" }), chips);
}

function wldSpan(wins, losses, draws) {
  return el(
    "span",
    { class: "wld" },
    el("span", { class: "w", text: String(wins || 0) }),
    el("span", { class: "sep", text: "-" }),
    el("span", { class: "l", text: String(losses || 0) }),
    el("span", { class: "sep", text: "-" }),
    el("span", { class: "d", text: String(draws || 0) })
  );
}

const STATUS_LABEL = {
  ok: "ok",
  timeout: "timeout",
  killed: "killed",
  loadfail_a: "loadfail A",
  loadfail_b: "loadfail B",
  loadfail_both: "loadfail both",
  bot_error: "bot error",
  engine_error: "engine",
};

/** Short badge labels for the engine's win conditions; the full name is the title. */
const CONDITION_LABEL = {
  core_destroyed: "core",
  resigned: "resign",
  resources: "resources",
  titanium_collected: "titanium",
  titanium_stored: "stored",
  harvesters: "harvest",
  coinflip: "coinflip",
  timeout: "timeout",
};

const conditionLabel = (condition) =>
  CONDITION_LABEL[condition] || String(condition || "").replace(/_/g, " ");

function statusBadge(game) {
  const errors = (Number(game.a_errors) || 0) + (Number(game.b_errors) || 0);
  if (game.status === "ok" && errors > 0) {
    return el("span", {
      class: "badge",
      "data-status": "bot_error",
      text: game.a_errors && game.b_errors ? "bot errors" : "bot error",
      title: `${errors} attributed bot ${errors === 1 ? "error" : "errors"}`,
    });
  }
  if (game.status === "ok") {
    const drawn = game.winner === "draw" || !game.winner;
    return el("span", {
      class: "badge",
      "data-result": drawn ? "draw" : "win",
      text: drawn ? "draw" : conditionLabel(game.win_condition) || "win",
      title: game.win_condition || "",
    });
  }
  return el("span", {
    class: "badge",
    "data-status": game.status,
    text: STATUS_LABEL[game.status] || game.status,
    title: game.error || "",
  });
}

function gameHasError(game) {
  return Boolean(
    game &&
    (game.status !== "ok" ||
      (Number(game.a_errors) || 0) > 0 ||
      (Number(game.b_errors) || 0) > 0)
  );
}

function matchup(game) {
  const winner = game.winner;
  const side = (slot, name) =>
    botLink(name, {
      class:
        "side" +
        (winner === slot ? " is-winner" : winner && winner !== "draw" ? " is-loser" : ""),
      "data-side": slot,
      title: name,
    });
  return el(
    "span",
    { class: "matchup" },
    side("a", game.a),
    el("span", { class: "vs", text: "vs" }),
    side("b", game.b)
  );
}

function mapChip(name, onPick) {
  return el("span", {
    class: "chip chip-map",
    text: name,
    title: onPick ? `filter games by ${name}` : name,
    role: onPick ? "button" : null,
    tabindex: onPick ? "0" : null,
    onclick: onPick
      ? (event) => {
          event.stopPropagation();
          onPick(name);
        }
      : null,
    onkeydown: onPick
      ? (event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            event.stopPropagation();
            onPick(name);
          }
        }
      : null,
  });
}

function statTile(label, value, extra) {
  // Labels carrying a symbol (μ, σ, …) must not be CSS-uppercased.
  const plain = /[^\x00-\x7F]/.test(label);
  return el(
    "div",
    { class: "stat" },
    el("div", { class: plain ? "stat-label no-caps" : "stat-label", text: label }),
    el("div", { class: "stat-value num" }, value),
    extra ? el("div", { class: "small mute" }, extra) : null
  );
}

function fmtBytes(value) {
  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes < 0) return "–";
  if (bytes < 1024) return `${Math.round(bytes)} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let size = bytes / 1024;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size < 10 ? size.toFixed(1) : Math.round(size)} ${units[index]}`;
}

function card({ title = "", actions = null, foot = null, flush = false, ...rest } = {}, ...body) {
  return el(
    "div",
    { class: "card", ...rest },
    title
      ? el(
          "div",
          { class: "card-head" },
          el("span", { class: "card-title", text: title }),
          actions ? el("span", { class: "card-actions" }, actions) : null
        )
      : null,
    el("div", { class: flush ? "card-body card-body-flush" : "card-body" }, ...body),
    foot ? el("div", { class: "card-foot" }, foot) : null
  );
}

function chartCard(title, node) {
  return el("div", { class: "chart" }, el("div", { class: "chart-title", text: title }), node);
}

function tableWrap(table) {
  return el("div", { class: "table-wrap" }, table);
}

/* -------------------------------------------------------------------------- */
/* mount machinery                                                            */
/* -------------------------------------------------------------------------- */

const current = { name: "", root: null, params: {}, render: null, cleanup: null, token: 0 };
let tokenSeq = 0;

function disposeCurrent() {
  const fn = current.cleanup;
  current.cleanup = null;
  if (fn) {
    try {
      fn();
    } catch (err) {
      console.error("view cleanup failed", err);
    }
  }
}

/**
 * Wrap a renderer so it gets a lifecycle context and a cleanup contract.
 *
 * `ctx.alive()` is false as soon as another view (or a re-render of this one)
 * takes over, which is how every `await` in a renderer avoids writing into a
 * detached tree. The cleanup returned to the caller is idempotent and inert once
 * superseded, so an app.js that stashes it cannot tear down a newer view.
 */
function mount(name, render) {
  const wrapped = (root, params) => {
    disposeCurrent();
    const token = ++tokenSeq;
    const jobs = [];
    const ctx = {
      alive: () => current.token === token,
      add(fn) {
        if (typeof fn === "function") jobs.push(fn);
        return fn;
      },
      on(event, handler) {
        jobs.push(
          on(event, (payload) => {
            if (current.token === token) handler(payload);
          })
        );
      },
      timer(fn, ms) {
        const id = setInterval(fn, ms);
        jobs.push(() => clearInterval(id));
        return id;
      },
    };
    current.name = name;
    current.root = root;
    current.params = params && typeof params === "object" ? params : {};
    current.render = wrapped;
    current.token = token;
    current.cleanup = () => {
      while (jobs.length) {
        const job = jobs.pop();
        try {
          job();
        } catch (err) {
          console.error("view cleanup failed", err);
        }
      }
    };
    fill(root);
    try {
      render(root, current.params, ctx);
    } catch (err) {
      console.error(err);
      fill(root, crashPanel(err));
    }
    return () => {
      if (current.token === token) disposeCurrent();
    };
  };
  return wrapped;
}

/** Re-render the current view in place, keeping its route parameters. */
export function refreshView() {
  if (current.render && current.root) current.render(current.root, current.params);
}

/** Coalesce bursts of live events into one repaint per `ms`. */
function throttled(fn, ms) {
  let timer = null;
  let pending = false;
  const run = () => {
    timer = setTimeout(() => {
      timer = null;
      if (pending) {
        pending = false;
        fn();
        run();
      }
    }, ms);
  };
  const call = () => {
    if (timer) {
      pending = true;
      return;
    }
    fn();
    run();
  };
  call.cancel = () => {
    if (timer) clearTimeout(timer);
    timer = null;
    pending = false;
  };
  return call;
}

/* -------------------------------------------------------------------------- */
/* cross-view navigation                                                      */
/* -------------------------------------------------------------------------- */

const EMPTY_GAME_FILTER = { bot: "", opponent: "", map: "", tag: "", failed: false, rated: false };
let gameFilter = { ...EMPTY_GAME_FILTER };
let pendingGameFilter = null;

/**
 * Jump to the Games view with a filter applied.
 *
 * The filter travels in a module variable rather than the hash so it works
 * whatever shape app.js's route parser has; the route itself stays the plain
 * `#/games` documented in the contract.
 */
function gotoGames(filter) {
  pendingGameFilter = { ...EMPTY_GAME_FILTER, ...filter };
  if (location.hash === "#/games" && current.root) views.games(current.root, {});
  else location.hash = "#/games";
}

/* -------------------------------------------------------------------------- */
/* 1. Ladder                                                                  */
/* -------------------------------------------------------------------------- */

function rememberedTopK() {
  try {
    const value = Number(localStorage.getItem("oarena.timeline.top-k"));
    return Number.isInteger(value) && value >= 1 && value <= 50 ? value : 5;
  } catch {
    return 5;
  }
}

function rememberTopK(value) {
  try {
    localStorage.setItem("oarena.timeline.top-k", String(value));
  } catch {
    // Private browsing or a blocked storage policy should not break the chart.
  }
}

function rememberedTimeline() {
  try {
    const saved = JSON.parse(localStorage.getItem("oarena.timeline.view") || "null");
    const axis = saved && saved.axis === "time" ? "time" : "games";
    const zoom = saved && saved.zoom;
    if (zoom && zoom.axis === axis && Number.isFinite(Number(zoom.lo)) && Number.isFinite(Number(zoom.hi))
      && Number(zoom.hi) > Number(zoom.lo)) {
      return { axis, zoom: { axis, lo: Number(zoom.lo), hi: Number(zoom.hi) } };
    }
    return { axis, zoom: null };
  } catch {
    return { axis: "games", zoom: null };
  }
}

function rememberTimeline() {
  try {
    localStorage.setItem("oarena.timeline.view", JSON.stringify({
      axis: ladderUi.historyAxis,
      zoom: ladderUi.historyZoom,
    }));
  } catch {
    // Storage can be disabled (for example, private browsing); the chart stays usable.
  }
}

const savedTimeline = rememberedTimeline();

const ladderUi = {
  query: "",
  sort: "mu",
  dir: "desc",
  historyTop: rememberedTopK(),
  // A game-count axis puts each bot's rating updates at equal distance. Time
  // remains available when wall-clock pacing is what matters.  Game count is
  // global: game 543 means the 543rd recorded rated game in the whole league.
  historyAxis: savedTimeline.axis,
  historyZoom: savedTimeline.zoom,
  // The last full x-domain lets a live refresh distinguish “right handle is
  // pinned to now” from “the user deliberately stopped before the newest
  // game”. It is session state, not a preference worth persisting.
  historyDomain: null,
};
/**
 * The one-line explanation of the ranking and its uncertainty diagnostic.
 *
 * LCB95 and the band's left edge are the same statement, read two ways.
 */
function scoreLegend() {
  return el(
    "div",
    { class: "chart-note" },
    "Ranked by ",
    el("b", null, "μ"),
    " · LCB95 = μ − 1.96σ",
  );
}

const CHART_TITLE =
  "Skill estimate - 95% CI";

function timelineTitle(axis = "games") {
  return axis === "time"
    ? "Ratings vs time, 95% CI, outlined dots = source changes"
    : "Ratings vs nth game, 95% CI, outlined dots = source changes";
}

const LADDER_SORTS = {
  rank: (r) => r.rank,
  name: (r) => r.name.toLowerCase(),
  lcb95: (r) => r.lcb95 ?? r.score,
  // Compatibility for a dashboard tab opened before the column was renamed.
  score: (r) => r.score,
  mu: (r) => r.mu,
  games: (r) => r.games,
  winrate: (r) => (r.winrate === null || r.winrate === undefined ? -1 : r.winrate),
  err: (r) => r.err_total,
  last: (r) => r.last_played || "",
  source: (r) => r.source_updated || "",
};

function sortLadder(rows) {
  const key = LADDER_SORTS[ladderUi.sort] || LADDER_SORTS.mu;
  const sign = ladderUi.dir === "asc" ? 1 : -1;
  return rows.slice().sort((x, y) => {
    const a = key(x);
    const b = key(y);
    if (a < b) return -sign;
    if (a > b) return sign;
    return x.name.localeCompare(y.name);
  });
}

function visibleLadder(rows) {
  const query = ladderUi.query.trim().toLowerCase();
  return rows.filter((row) => {
    if (query && !row.name.toLowerCase().includes(query)) return false;
    return true;
  });
}

function topLadder(rows) {
  const k = Math.max(1, ladderUi.historyTop);
  return rows
    .slice()
    .sort((a, b) => (a.rank - b.rank) || (b.mu - a.mu) || a.name.localeCompare(b.name))
    .slice(0, k);
}

const ladder = mount("ladder", (root, params, ctx) => {
  const activeRows = (value) =>
    (Array.isArray(value) ? value : [])
      .filter((row) => row.active !== false)
      .map((row, index) => ({ ...row, rank: index + 1 }));
  let rows = activeRows(state.ladder);

  const search = searchBox(ladderUi.query, "filter bots", (value) => {
    ladderUi.query = value;
    sync();
  });
  const historyTopRange = el("input", {
    class: "timeline-top-range",
    type: "range",
    min: "1",
    max: "50",
    step: "1",
    value: String(ladderUi.historyTop),
    "aria-label": "Top K bots shown across the ladder",
  });
  const historyTopNumber = el("input", {
    class: "input timeline-top-number num",
    type: "number",
    min: "1",
    max: "50",
    step: "1",
    value: String(ladderUi.historyTop),
    "aria-label": "Top K bots shown across the ladder",
  });
  const setHistoryTop = (raw) => {
    const next = Math.max(1, Math.min(50, Math.round(Number(raw) || ladderUi.historyTop)));
    ladderUi.historyTop = next;
    historyTopRange.value = String(next);
    historyTopNumber.value = String(next);
    rememberTopK(next);
    sync();
    loadTimeline();
  };
  historyTopRange.addEventListener("input", (event) => setHistoryTop(event.currentTarget.value));
  historyTopNumber.addEventListener("change", (event) => setHistoryTop(event.currentTarget.value));
  const historyTop = el(
    "label",
    { class: "timeline-top-control", title: "Number of leading bots shown throughout the Ladder view" },
    el("span", { class: "timeline-top-label", text: "Top" }),
    historyTopRange,
    historyTopNumber
  );
  const historyAxis = el(
    "select",
    {
      class: "select select-compact",
      "aria-label": "Rating history horizontal axis",
      onchange: (event) => {
        ladderUi.historyAxis = event.currentTarget.value === "time" ? "time" : "games";
        ladderUi.historyZoom = null;
        ladderUi.historyDomain = null;
        rememberTimeline();
        if (timelineData) renderTimeline(timelineData);
        else loadTimeline();
      },
    },
    el("option", { value: "games", text: "By games" }),
    el("option", { value: "time", text: "By time" })
  );
  historyAxis.value = ladderUi.historyAxis;

  const chartSlot = el(
    "div",
    { class: "chart" },
    el("div", { class: "chart-title", text: CHART_TITLE }),
    el("div", { class: "skeleton skeleton-block" }),
    scoreLegend()
  );
  const timelineSlot = el(
    "div",
    { class: "chart" },
    el("div", { class: "chart-title", text: timelineTitle(ladderUi.historyAxis) }),
    el("div", { class: "skeleton skeleton-block" })
  );
  const tbody = el("tbody");
  const table = el(
    "table",
    { class: "table table-clickable ladder-table" },
    el(
      "thead",
      null,
      el(
        "tr",
        null,
        headerCell("#", "rank", "num"),
        headerCell("Bot", "name"),
        headerCell("μ ±σ", "mu", "num", "text-transform:none",
          "Mean skill estimate and its standard deviation. The ladder ranks by μ."),
        headerCell("LCB95", "lcb95", "num", null,
          "Conservative lower bound: \u03bc \u2212 1.96\u03c3, the bottom of the 95% interval."),
        el("th", { text: "Range", style: "width:150px" }),
        headerCell("Rated", "games", "num", null,
          "Rated, decided games played by this bot's current source version."),
        el("th", { class: "num", text: "W-L-D", title: "Current source version only." }),
        headerCell("Win%", "winrate", "num", null, "Current source version only."),
        headerCell("Err", "err", "num", null,
          "Runtime and validation errors attributed to the current source version."),
        headerCell("Last played", "last", "num", null,
          "Newest game played by the current source version."),
        headerCell("Source changed", "source", "num", null,
          "When oarena most recently detected a new source-code version.")
      )
    ),
    tbody
  );
  const tableSlot = el("div", { class: "stack" }, tableWrap(table));

  const view = viewRoot(
    {
      title: "Ladder",
      sub: "",
      toolbar: [search.wrap, historyTop, historyAxis],
    },
    chartSlot,
    timelineSlot,
    tableSlot
  );
  root.appendChild(view);

  // `style` exists for the one header that must not be upper-cased: CSS would
  // turn "μ ±σ" into "Μ ±Σ", and a capital mu is indistinguishable from an M.
  function headerCell(label, key, cls, style, title) {
    const th = el("th", {
      class: cls || null,
      style: style || null,
      title: title || null,
      "data-sort": key,
      text: label,
    });
    if (ladderUi.sort === key) th.setAttribute("aria-sort", ladderUi.dir === "asc" ? "ascending" : "descending");
    th.addEventListener("click", () => {
      if (ladderUi.sort === key) ladderUi.dir = ladderUi.dir === "asc" ? "desc" : "asc";
      else {
        ladderUi.sort = key;
        ladderUi.dir = key === "name" || key === "rank" ? "asc" : "desc";
      }
      for (const other of table.querySelectorAll("th[aria-sort]")) other.removeAttribute("aria-sort");
      th.setAttribute("aria-sort", ladderUi.dir === "asc" ? "ascending" : "descending");
      sync();
    });
    return th;
  }

  // -- row bookkeeping ----------------------------------------------------
  const built = new Map(); // name -> {tr, refs}
  let order = "";

  function buildRow(row) {
    const rank = el("span", { class: "rank", text: String(row.rank) });
    const deltaSlot = el("span", { class: "nowrap ladder-name-delta" });
    const nameWrap = el("span", { class: "ladder-name-wrap" }, botName(row), deltaSlot);
    const nameCell = el("td", { class: "ladder-name-cell" }, nameWrap);
    const score = el("td", { class: "num" });
    const mu = el("td", { class: "num" });
    const bar = el(
      "span",
      { class: "sigmaband" },
      el("span", { class: "sigmaband-bar" }),
      el("span", { class: "sigmaband-mu" })
    );
    const games = el("td", { class: "num" });
    const record = el("td", { class: "num" });
    const winrate = el("td", { class: "num" });
    const errors = el("td", { class: "num" });
    const last = el("td", { class: "num" });
    const source = el("td", { class: "num" });
    const tr = el(
      "tr",
      {
        "data-name": row.name,
        tabindex: "0",
        onclick: () => {
          location.hash = nameHref(row.name);
        },
        onkeydown: (event) => {
          if (event.key === "Enter") location.hash = nameHref(row.name);
        },
      },
      el("td", { class: "num" }, rank),
      nameCell,
      mu,
      score,
      el("td", { style: "width:150px" }, bar),
      games,
      record,
      winrate,
      errors,
      last,
      source
    );
    const refs = {
      tr, rank, nameCell, nameWrap, deltaSlot, score, mu, bar, games,
      record, winrate, errors, last, source,
    };
    built.set(row.name, refs);
    return refs;
  }

  function fillRow(refs, row, lo, span) {
    const tr = refs.tr;
    tr.dataset.broken = row.broken ? "true" : "false";
    tr.dataset.inactive = row.active ? "false" : "true";
    if (row.broken && row.broken_reason) tr.title = row.broken_reason;
    refs.rank.textContent = String(row.rank);
    refs.score.textContent = fmt.num(row.lcb95 ?? row.score, 2);
    refs.mu.textContent = `${fmt.num(row.mu, 2)} ±${fmt.num(row.sigma, 2)}`;
    refs.bar.style.setProperty("--lo", String((row.lo - lo) / span));
    refs.bar.style.setProperty("--hi", String((row.hi - lo) / span));
    refs.bar.style.setProperty("--mu", String((row.mu - lo) / span));
    refs.bar.title = `${fmt.num(row.lo, 2)} … ${fmt.num(row.hi, 2)}`;
    refs.games.textContent = fmt.int(row.games);
    fill(refs.record, wldSpan(row.wins, row.losses, row.draws));
    refs.winrate.textContent = fmt.pct(row.winrate);
    fill(refs.errors, 
      row.err_total
        ? el("span", {
            class: "chip chip-err",
            text: String(row.err_total),
            title: `${row.err_total} attributed errors over ${row.err_games} games by the current source version`,
          })
        : el("span", { class: "mute", text: "0" })
    );
    refs.last.textContent = row.last_played ? fmt.ago(row.last_played) : "–";
    refs.last.title = row.last_played || "never played";
    refs.source.textContent = row.source_updated ? fmt.ago(row.source_updated) : "–";
    refs.source.title = row.source_updated || "source change unknown";
    // The name cell's chips can change (a bot breaks, is disabled) but the
    // delta slot must survive, so only the first child is replaced.
    refs.nameWrap.replaceChild(botName(row), refs.nameWrap.firstChild);
  }

  function sync() {
    const visible = sortLadder(visibleLadder(topLadder(rows)));
    view.setSub(
      `Top ${Math.min(ladderUi.historyTop, rows.length)} of ${rows.length} bots · ${fmt.int(
        (state.counts && state.counts.games) || 0
      )} games`
    );

    if (!rows.length) {
      chartSlot.hidden = true;
      timelineSlot.hidden = true;
      fill(tableSlot, 
        emptyState({
          title: "No bots yet",
          hint: [
            "Drop a directory containing ",
            code("main.py"),
            " into ",
            code((state.config && state.config.bots_dir) || "bots/"),
            " and rescan.",
          ],
          actions: [
            btn("Rescan", {
              class: "btn btn-sm btn-primary",
              onclick: async (event) => {
                const button = event.currentTarget;
                button.disabled = true;
                try {
                  await api("/api/sync", { method: "POST" });
                  await load();
                } catch (err) {
                  toast(errorMessage(err), "error");
                } finally {
                  button.disabled = false;
                }
              },
            }),
          ],
        })
      );
      return;
    }

    chartSlot.hidden = false;
    timelineSlot.hidden = false;
    if (tableSlot.firstChild !== table.parentNode) fill(tableSlot, tableWrap(table));

    let lo = Infinity;
    let hi = -Infinity;
    for (const row of rows) {
      lo = Math.min(lo, row.lo);
      hi = Math.max(hi, row.hi);
    }
    const span = hi - lo || 1;

    const alive = new Set();
    for (const row of visible) {
      alive.add(row.name);
      const refs = built.get(row.name) || buildRow(row);
      fillRow(refs, row, lo, span);
    }
    for (const [name, refs] of built) {
      if (!alive.has(name)) {
        refs.tr.remove();
        built.delete(name);
      }
    }
    // Only touch the DOM order when it actually changed: moving rows restarts
    // the delta-chip animations that just fired.
    const key = visible.map((row) => row.name).join("\u0000");
    if (key !== order) {
      order = key;
      tbody.append(...visible.map((row) => built.get(row.name).tr));
    }
    if (!visible.length) {
      fill(tbody, 
        el("tr", null, el("td", { colspan: "11", class: "center mute", text: "No bot matches this filter." }))
      );
      order = "";
      built.clear();
    }
    drawChart();
  }

  const drawChart = throttled(() => {
    if (!ctx.alive() || !rows.length) return;
    const visible = visibleLadder(topLadder(rows)).slice().sort(
      (a, b) => (b.mu - a.mu) || a.name.localeCompare(b.name)
    );
    fill(chartSlot,
      el("div", { class: "chart-title", text: CHART_TITLE }),
      el(
        "div",
        { class: "bandchart-scroll" },
        intervalChart(visible, { onSelect: (name) => { location.hash = nameHref(name); } })
      ),
      scoreLegend()
    );
  }, 700);
  ctx.add(() => drawChart.cancel());

  let timelineData = null;
  const timelineRefresh = throttled(() => loadTimeline(), 1200);
  ctx.add(() => timelineRefresh.cancel());

  function timelineSeries(data, axis) {
    const colours = ["var(--accent)", "var(--b)", "var(--win)", "var(--warn)", "#cf8cff", "#64d7d2", "#ff778d", "#a9c15e"];
    return (data.bots || []).map((bot, index) => {
      const points = (bot.history || []).map((point) => ({
        // ``game`` is the global id of the rated game which produced this
        // update.  Gaps are intentional: a bot's line moves only on games it
        // played, while every line shares the same league-wide x-axis.
        x: axis === "time" ? Date.parse(point.ts || "") : Number(point.game),
        at: Date.parse(point.ts || ""),
        y: Number(point.mu),
        sigma: Number(point.sigma),
      })).filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
      const versions = (bot.versions || []).slice().sort((a, b) => Number(a.id) - Number(b.id));
      const markers = versions.slice(1).map((version) => {
        const changed = Date.parse(version.ts || "");
        const pointIndex = Number.isFinite(changed)
          ? points.findIndex((entry) => entry.at >= changed)
          : -1;
        // A change at or before the visible history's first point is the
        // starting source for this graph, not a change within it. This is most
        // noticeable after resetting the ladder while retaining bot versions.
        const point = pointIndex > 0 ? points[pointIndex] : null;
        return point ? { x: point.x, y: point.y, title: `${bot.name}: source changed to ${String(version.hash || "").slice(0, 12)}` } : null;
      }).filter(Boolean);
      return { name: bot.name, colour: colours[index % colours.length], points, markers };
    // rating_history returns one prior point for an unplayed bot. That is not
    // history, and rendering it produced a misleading lone dot at game 0,
    // μ=25. A played bot always has the prior plus at least one update.
    }).filter((series) => series.points.length > 1);
  }

  function seriesDomain(series) {
    let lo = Infinity;
    let hi = -Infinity;
    for (const row of series) for (const point of row.points) {
      lo = Math.min(lo, point.x);
      hi = Math.max(hi, point.x);
    }
    return Number.isFinite(lo) && Number.isFinite(hi) ? { lo, hi } : null;
  }

  function timelineBound(value, axis) {
    if (axis === "games") return `game ${Math.round(value)}`;
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "–" : date.toLocaleString(undefined, {
      month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
    });
  }

  function currentTimelineZoom(domain, axis) {
    const zoom = ladderUi.historyZoom;
    if (!domain) return domain;
    const previous = ladderUi.historyDomain;
    if (!zoom || zoom.axis !== axis) {
      ladderUi.historyDomain = { axis, lo: domain.lo, hi: domain.hi };
      return domain;
    }
    const lo = Math.max(domain.lo, Math.min(domain.hi, Number(zoom.lo)));
    const oldSpan = previous && previous.axis === axis ? previous.hi - previous.lo : 0;
    const tolerance = axis === "games" ? 0.5 : Math.max(1_000, oldSpan * 0.001);
    const followsLatest = Boolean(
      previous && previous.axis === axis && Math.abs(Number(zoom.hi) - previous.hi) <= tolerance
    );
    // New games extend only a range whose right handle was already at the old
    // right edge. A manually selected end stays fixed; the left handle never
    // moves just because the league played another game.
    const hi = followsLatest
      ? domain.hi
      : Math.max(domain.lo, Math.min(domain.hi, Number(zoom.hi)));
    ladderUi.historyDomain = { axis, lo: domain.lo, hi: domain.hi };
    return hi > lo ? { lo, hi } : domain;
  }

  function timelineRange(domain, zoom, axis, change, previewChange) {
    if (!domain || domain.hi <= domain.lo) return null;
    const step = axis === "games" ? 1 : Math.max(1000, Math.round((domain.hi - domain.lo) / 1000));
    const makeRange = (value, label) => el("input", {
      class: "timeline-range-input",
      type: "range",
      min: String(domain.lo), max: String(domain.hi), step: String(step), value: String(value),
      "aria-label": `${label} of visible rating-history range`,
    });
    const from = makeRange(zoom.lo, "Start");
    const to = makeRange(zoom.hi, "End");
    const fromValue = el("span", { class: "timeline-range-value", text: timelineBound(zoom.lo, axis) });
    const toValue = el("span", { class: "timeline-range-value", text: timelineBound(zoom.hi, axis) });
    const dual = el("div", { class: "timeline-dual-range" }, from, to);
    const bounds = (event) => {
      let lo = Number(from.value);
      let hi = Number(to.value);
      if (lo >= hi) {
        if (event.currentTarget === from) lo = Math.max(domain.lo, hi - step);
        else hi = Math.min(domain.hi, lo + step);
        from.value = String(lo);
        to.value = String(hi);
      }
      return { lo, hi };
    };
    const preview = (event) => {
      const { lo, hi } = bounds(event);
      const span = domain.hi - domain.lo;
      dual.style.setProperty("--from", `${((lo - domain.lo) / span) * 100}%`);
      dual.style.setProperty("--to", `${((hi - domain.lo) / span) * 100}%`);
      fromValue.textContent = timelineBound(lo, axis);
      toValue.textContent = timelineBound(hi, axis);
      previewChange({ lo, hi });
    };
    const update = (event) => {
      const { lo, hi } = bounds(event);
      preview(event);
      change({ lo, hi });
    };
    from.addEventListener("input", preview);
    to.addEventListener("input", preview);
    from.addEventListener("change", update);
    to.addEventListener("change", update);
    preview({ currentTarget: from });
    return el(
      "div",
      { class: "timeline-range" },
      el("span", { class: "timeline-range-label", text: "Visible" }),
      dual,
      fromValue,
      el("span", { class: "timeline-range-sep", text: "to" }),
      toValue,
      btn("Reset zoom", { class: "btn btn-sm btn-ghost", disabled: zoom.lo === domain.lo && zoom.hi === domain.hi, onclick: () => change(domain) })
    );
  }

  function renderTimeline(data) {
    const axis = ladderUi.historyAxis;
    const series = timelineSeries(data || {}, axis);
    const domain = seriesDomain(series);
    const zoom = currentTimelineZoom(domain, axis);
    const colours = series.map((item) => item.colour);
    const chart = el("div", { class: "timeline-chart-slot" });
    let previewFrame = 0;
    let pendingZoom = zoom;
    const draw = (xDomain) => fill(chart, multiRatingChart(series, {
      xMode: axis,
      xDomain,
      onZoom: setZoom,
      onReset: () => setZoom(domain),
      label: `Top bot ratings by ${axis === "time" ? "time" : "global rated game"} with 95 percent intervals`,
    }));
    const setZoom = (next) => {
      if (previewFrame) cancelAnimationFrame(previewFrame);
      ladderUi.historyZoom = { axis, lo: next.lo, hi: next.hi };
      rememberTimeline();
      renderTimeline(data);
    };
    const previewZoom = (next) => {
      // `input` fires while a thumb is held, whereas `change` waits for the
      // release. Commit the value immediately so an SSE game event arriving
      // during that drag cannot redraw from the old full-range selection.
      ladderUi.historyZoom = { axis, lo: next.lo, hi: next.hi };
      rememberTimeline();
      pendingZoom = next;
      if (previewFrame) return;
      // The control itself stays mounted. Only the lightweight SVG is rebuilt,
      // once per paint frame at most, so a held slider feels immediate rather
      // than waiting for the `change` event when the thumb is released.
      previewFrame = requestAnimationFrame(() => {
        previewFrame = 0;
        draw(pendingZoom);
      });
    };
    ctx.add(() => { if (previewFrame) cancelAnimationFrame(previewFrame); });
    draw(zoom);
    fill(
      timelineSlot,
      el("div", { class: "chart-title", text: timelineTitle(axis) }),
      chart,
      timelineRange(domain, zoom, axis, setZoom, previewZoom),
      el(
        "div",
        { class: "timeline-legend" },
        ...series.map((item, index) => el(
          "span",
          { class: "timeline-legend-item" },
          el("span", { class: "timeline-swatch", style: { background: colours[index] } }),
          botLink(item.name)
        ))
      )
    );
  }

  async function loadTimeline() {
    try {
      const data = await api(`/api/timeline?top=${encodeURIComponent(String(ladderUi.historyTop))}`);
      if (!ctx.alive()) return;
      timelineData = data || {};
      renderTimeline(timelineData);
    } catch (err) {
      if (ctx.alive()) fill(timelineSlot, el("div", { class: "chart-title", text: "Ratings history" }), emptyState({ title: "Could not load rating history", hint: [errorMessage(err)] }));
    }
  }

  function flash(name, delta) {
    const refs = built.get(name);
    if (!refs) return;
    refs.tr.classList.remove("is-flash");
    void refs.tr.offsetWidth;
    refs.tr.classList.add("is-flash");
    setTimeout(() => refs.tr.classList.remove("is-flash"), 1000);
    if (typeof delta === "number" && Number.isFinite(delta)) {
      const chip = el("span", {
        class: "delta-chip is-fading",
        "data-dir": delta > 0.005 ? "up" : delta < -0.005 ? "down" : "flat",
        text: fmt.signed(delta),
      });
      fill(refs.deltaSlot, chip);
      setTimeout(() => chip.remove(), 2100);
    }
  }

  async function load() {
    try {
      const fresh = await api("/api/ladder");
      if (!ctx.alive()) return;
      rows = activeRows(fresh);
      sync();
      loadTimeline();
    } catch (err) {
      if (ctx.alive()) toast(`Could not load the ladder: ${errorMessage(err)}`, "error");
    }
  }

  sync();
  if (!rows.length) fill(tableSlot, skeletonRows(5));
  load();

  ctx.on("state", () => {
    rows = activeRows(state.ladder);
    sync();
  });
  ctx.on("ladder", () => {
    rows = activeRows(state.ladder);
    sync();
  });
  ctx.on("game", (payload) => {
    rows = activeRows(state.ladder);
    sync();
    const delta = (payload && payload.delta) || {};
    for (const name of Object.keys(delta)) flash(name, delta[name]);
    timelineRefresh();
  });
  ctx.on("bot", timelineRefresh);
});

/* -------------------------------------------------------------------------- */
/* 2. Matrix                                                                  */
/* -------------------------------------------------------------------------- */

/**
 * Shared crosstable renderer.  The league view supplies bots on both axes;
 * the Games pairing view supplies bots as rows and maps as columns.  Keeping
 * the geometry and heat cells here means their reading rules never drift.
 */
function matrixTable({
  rows,
  columns,
  cells,
  minGames = 0,
  diagonal = null,
  rowLabel = (value) => el("span", { text: value }),
  columnLabel = (value) => el("span", { class: "matrix-col-label", text: value }),
  describe = (row, column) => `${row} vs ${column}`,
  onCellClick = null,
}) {
  const tip = document.getElementById("tooltip");
  const cellNodes = new Map();
  const recordOf = (row, column) => (cells[row] && cells[row][column]) || null;

  function paint(td, row, column, threshold = minGames) {
    const rec = recordOf(row, column);
    if (!rec || !rec.games) {
      td.dataset.empty = "1";
      td.textContent = "·";
      delete td.dataset.thin;
      td.style.removeProperty("--wr");
      td.style.removeProperty("--conf");
      td.style.removeProperty("--thin");
      return;
    }
    delete td.dataset.empty;
    const winrate = rec.winrate === null || rec.winrate === undefined ? 0.5 : rec.winrate;
    td.style.setProperty("--wr", String(winrate));
    td.style.setProperty("--conf", String(Math.min(1, rec.games / 8)));
    td.textContent = String(Math.round(winrate * 100));
    const thin = rec.games < threshold;
    if (thin) td.dataset.thin = "1";
    else delete td.dataset.thin;
    // The sample-size filter softens only the colour. Keep the percentage
    // fully legible rather than fading the whole cell into grey-on-green/red.
    td.style.setProperty("--thin", thin ? ".35" : "1");
  }

  const head = el("tr", null, el("th", { class: "matrix-corner", text: "" }));
  for (const column of columns) {
    head.appendChild(el("th", { class: "matrix-header", title: column }, columnLabel(column)));
  }

  const tbody = el("tbody");
  for (const row of rows) {
    const tr = el("tr", null, el("th", { class: "matrix-row" }, rowLabel(row)));
    for (const column of columns) {
      if (diagonal && diagonal(row, column)) {
        tr.appendChild(el("td", { class: "matrix-cell", "data-diag": "1" }));
        continue;
      }
      const td = el("td", {
        class: "matrix-cell",
        dataset: { row, column },
        "aria-label": describe(row, column),
      });
      paint(td, row, column);
      if (!cellNodes.has(row)) cellNodes.set(row, new Map());
      cellNodes.get(row).set(column, td);
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }

  const table = el(
    "table",
    { class: "matrix", "data-rotate": columns.length >= 8 ? "1" : null },
    el("thead", null, head),
    tbody
  );

  function hideTip() {
    if (tip) tip.hidden = true;
  }

  table.addEventListener("mouseover", (event) => {
    const td = event.target.closest(".matrix-cell");
    const row = td && td.dataset.row;
    const column = td && td.dataset.column;
    if (!td || !row || !column || !tip) return hideTip();
    const rec = recordOf(row, column);
    tip.textContent = rec && rec.games
      ? `${describe(row, column)}\n${rec.wins}–${rec.losses}–${rec.draws} (${rec.games} game${rec.games === 1 ? "" : "s"})\nwin rate ${fmt.pct(rec.winrate)}`
      : `${describe(row, column)}\nnever played`;
    tip.hidden = false;
    const box = td.getBoundingClientRect();
    const tipBox = tip.getBoundingClientRect();
    const left = Math.min(window.innerWidth - tipBox.width - 8, Math.max(8, box.left + box.width / 2 - tipBox.width / 2));
    const top = box.top - tipBox.height - 6 < 8 ? box.bottom + 6 : box.top - tipBox.height - 6;
    tip.style.left = `${Math.round(left)}px`;
    tip.style.top = `${Math.round(top)}px`;
  });
  table.addEventListener("mouseleave", hideTip);
  table.addEventListener("click", (event) => {
    const td = event.target.closest(".matrix-cell");
    const row = td && td.dataset.row;
    const column = td && td.dataset.column;
    if (!td || !row || !column || !onCellClick) return;
    hideTip();
    onCellClick(row, column, recordOf(row, column));
  });

  return {
    node: el("div", { class: "matrix-wrap" }, table),
    hideTip,
    repaint(threshold = minGames) {
      for (const [row, byColumn] of cellNodes) {
        for (const [column, td] of byColumn) paint(td, row, column, threshold);
      }
    },
  };
}

const matrixUi = { min: 0 };

const matrix = mount("matrix", (root, params, ctx) => {
  let data = { names: [], cells: {} };
  let grid = null;

  const minLabel = el("span", { class: "small mute num", text: `≥ ${matrixUi.min}` });
  const slider = el("input", {
    class: "range",
    type: "range",
    min: "0",
    max: "20",
    step: "1",
    value: String(matrixUi.min),
    "aria-label": "Minimum games per cell",
    oninput: (event) => {
      matrixUi.min = Number(event.currentTarget.value) || 0;
      minLabel.textContent = `≥ ${matrixUi.min}`;
      grid?.repaint(matrixUi.min);
    },
  });

  const body = el("div", { class: "stack" }, skeletonRows(6));
  const view = viewRoot(
    {
      title: "Matrix",
      sub: "",
      toolbar: [el("span", { class: "small mute", text: "min games" }), slider, minLabel],
    },
    body,
    el(
      "span",
      { class: "matrix-legend" },
      "loss",
      el("span", { class: "matrix-scale" }),
      "win",
      el("span", { class: "small mute", text: "· opacity = sample size · click a cell for its games" })
    )
  );
  root.appendChild(view);

  function render() {
    const names = data.names || [];
    view.setSub(`${names.length} bot${names.length === 1 ? "" : "s"}`);

    if (names.length < 2) {
      fill(body, 
        emptyState({
          title: names.length ? "Only one bot on the ladder" : "No bots yet",
          hint: names.length
            ? ["A crosstable needs at least two bots. Add another directory to ", code((state.config && state.config.bots_dir) || "bots/"), "."]
            : ["Drop a directory containing ", code("main.py"), " into ", code((state.config && state.config.bots_dir) || "bots/"), "."],
        })
      );
      return;
    }

    grid = matrixTable({
      rows: names,
      columns: names,
      cells: data.cells || {},
      minGames: matrixUi.min,
      diagonal: (a, b) => a === b,
      rowLabel: (name) => botLink(name),
      columnLabel: (name) => botLink(name, { class: "matrix-col-label" }),
      onCellClick: (a, b) => gotoGames({ bot: a, opponent: b }),
    });
    fill(body, grid.node);
  }
  ctx.add(() => grid?.hideTip());

  async function load() {
    try {
      const fresh = await api("/api/matrix?min=0");
      if (!ctx.alive()) return;
      data = fresh && fresh.names ? fresh : { names: [], cells: {} };
      state.matrix = data;
      render();
    } catch (err) {
      if (!ctx.alive()) return;
      fill(body, 
        emptyState({ title: "Could not load the crosstable", hint: [errorMessage(err)] })
      );
    }
  }

  if (state.matrix && state.matrix.names) {
    data = state.matrix;
    render();
  }
  load();

  // A finished game changes exactly two cells; fold it in rather than refetch.
  ctx.on("game", (payload) => {
    const game = payload && payload.game;
    if (!game || !game.winner || game.a === game.b) return;
    const bump = (x, y, result) => {
      const row = data.cells && data.cells[x];
      if (!row) return;
      const rec = row[y] || { wins: 0, losses: 0, draws: 0, games: 0, winrate: null, score: 0 };
      if (result === "win") rec.wins += 1;
      else if (result === "loss") rec.losses += 1;
      else rec.draws += 1;
      rec.games += 1;
      rec.score = rec.wins + 0.5 * rec.draws;
      rec.winrate = rec.games ? rec.score / rec.games : null;
      row[y] = rec;
      grid?.repaint(matrixUi.min);
    };
    const outcome = game.winner === "draw" ? "draw" : game.winner === "a" ? "win" : "loss";
    bump(game.a, game.b, outcome);
    bump(game.b, game.a, outcome === "draw" ? "draw" : outcome === "win" ? "loss" : "win");
  });
  ctx.on("state", load);
  ctx.on("bot", load);
});

/* -------------------------------------------------------------------------- */
/* 3. Games                                                                   */
/* -------------------------------------------------------------------------- */

// A normal viewport shows fewer than 30 rows. Avoid eagerly laying out a large
// off-screen history; the rest stays one click away through the existing
// cursor-based "Load more" path.
const PAGE = 30;
const STREAM_CAP = 200;
const GAMES_CACHE_MAX_AGE_MS = 5_000;
const MATCH_GAMES_CACHE_MAX_AGE_MS = 60_000;
const MATCH_GAMES_CACHE_LIMIT = 16;
const GAME_BATCH_PREVIEW_LIMIT = 12;

let gamesFirstPageCache = null;
let gamesFirstPageInflight = null;
let latestMatchRunRevision = 0;
let latestMatchLiveTag = "";
const matchGamesCache = new Map();

function startedMatchTag(payload) {
  const tag = payload?.batch_tag;
  return payload?.mode === "match" &&
    typeof tag === "string" &&
    tag.length > 0 &&
    tag.length <= 200 &&
    tag.trim() === tag &&
    !/[\u0000-\u001f\u007f]/.test(tag)
    ? tag
    : "";
}

function gameQuery(filter, before) {
  const q = new URLSearchParams();
  q.set("limit", String(PAGE));
  q.set("summary", "1");
  if (before) q.set("before", String(before));
  if (filter.bot) q.set("bot", filter.bot);
  if (filter.opponent) q.set("opponent", filter.opponent);
  if (filter.map) q.set("map", filter.map);
  if (filter.tag) q.set("tag", filter.tag);
  if (filter.failed) q.set("failed", "1");
  if (filter.rated) q.set("rated", "1");
  return `/api/games?${q.toString()}`;
}

function isDefaultGameFilter(filter) {
  return !(
    filter.bot ||
    filter.opponent ||
    filter.map ||
    filter.tag ||
    filter.failed ||
    filter.rated
  );
}

function rememberGamesFirstPage(page) {
  gamesFirstPageCache = { page, at: Date.now() };
  return page;
}

function sameGamesPage(left, right) {
  const a = left?.games;
  const b = right?.games;
  return (
    left?.next === right?.next &&
    left?.latest_match_tag === right?.latest_match_tag &&
    Array.isArray(a) &&
    Array.isArray(b) &&
    a.length === b.length &&
    a.every((game, index) => game.id === b[index]?.id)
  );
}

function requestGamesFirstPage({ force = false } = {}) {
  if (
    !force &&
    gamesFirstPageCache &&
    Date.now() - gamesFirstPageCache.at <= GAMES_CACHE_MAX_AGE_MS
  ) {
    return Promise.resolve(gamesFirstPageCache.page);
  }
  if (gamesFirstPageInflight) return gamesFirstPageInflight;
  const requestRevision = latestMatchRunRevision;
  gamesFirstPageInflight = api(gameQuery(EMPTY_GAME_FILTER, null))
    .then((page) => rememberGamesFirstPage(
      requestRevision === latestMatchRunRevision
        ? page
        : { ...page, latest_match_tag: latestMatchLiveTag },
    ))
    .finally(() => {
      gamesFirstPageInflight = null;
    });
  return gamesFirstPageInflight;
}

/** Warm the common unfiltered Games route without delaying dashboard boot. */
export function preloadGames() {
  return requestGamesFirstPage().catch(() => null);
}

function requestMatchBatch(tag) {
  const cached = matchGamesCache.get(tag);
  if (cached?.page && Date.now() - cached.at <= MATCH_GAMES_CACHE_MAX_AGE_MS) {
    return Promise.resolve(cached.page);
  }
  if (cached?.inflight) return cached.inflight;

  const query = new URLSearchParams({ limit: "500", tag });
  const entry = cached || { page: null, at: 0, inflight: null };
  entry.inflight = api(`/api/batch?${query.toString()}`)
    .then((page) => {
      entry.page = page;
      // Completed batches are immutable. A manually opened running batch is
      // deliberately not cached, so its game strip can fill on the next view.
      entry.at = page?.status === "running" ? 0 : Date.now();
      while (matchGamesCache.size > MATCH_GAMES_CACHE_LIMIT) {
        matchGamesCache.delete(matchGamesCache.keys().next().value);
      }
      return page;
    })
    .finally(() => {
      entry.inflight = null;
    });
  matchGamesCache.delete(tag);
  matchGamesCache.set(tag, entry);
  return entry.inflight;
}

// Keep the warmed page current while an arena runs. Completed game rows are
// immutable, so folding the SSE result in is equivalent to refetching page 1.
on("game", (payload) => {
  const game = payload?.game;
  const cached = gamesFirstPageCache?.page;
  if (!game || !cached || !Array.isArray(cached.games)) return;
  const games = [game, ...cached.games.filter((row) => row.id !== game.id)].slice(
    0,
    PAGE,
  );
  rememberGamesFirstPage({
    ...cached,
    games,
    next: games.length === PAGE ? games.at(-1)?.id ?? null : null,
  });
});

// A newly reserved finite Match supersedes the previous highlight even before
// its first game finishes. This also keeps the short-lived warm cache honest.
on("run_started", (payload) => {
  const tag = startedMatchTag(payload);
  if (!tag) return;
  latestMatchRunRevision += 1;
  latestMatchLiveTag = tag;
  if (!gamesFirstPageCache?.page) return;
  rememberGamesFirstPage({
    ...gamesFirstPageCache.page,
    latest_match_tag: tag,
  });
});

function matchesFilter(game, filter) {
  if (filter.bot && game.a !== filter.bot && game.b !== filter.bot) return false;
  if (filter.opponent && game.a !== filter.opponent && game.b !== filter.opponent) return false;
  if (filter.map && game.map !== filter.map) return false;
  if (filter.tag && game.tag !== filter.tag) return false;
  if (filter.failed && game.status === "ok" && !game.a_errors && !game.b_errors) return false;
  if (filter.rated && !game.rated) return false;
  return true;
}

const games = mount("games", (root, params, ctx) => {
  const routedTag = typeof params?.tag === "string" ? params.tag : "";
  if (routedTag && gameFilter.tag !== routedTag) {
    // A completed-Match handoff is an explicit result set, not an addition to
    // whatever bot/map filters happened to be left over from an earlier visit.
    gameFilter = { ...EMPTY_GAME_FILTER, tag: routedTag };
    pendingGameFilter = null;
  } else if (pendingGameFilter) {
    gameFilter = pendingGameFilter;
    pendingGameFilter = null;
  }
  for (const key of ["bot", "opponent", "map", "tag"]) {
    if (params && typeof params[key] === "string" && params[key]) gameFilter[key] = params[key];
  }

  let rows = [];
  let next = null;
  let cap = STREAM_CAP;
  let latestMatchTag = "";

  const tbody = el("tbody");
  const table = el(
    "table",
    { class: "table table-clickable" },
    el(
      "thead",
      null,
      el(
        "tr",
        null,
        el("th", { text: "Time" }),
        el("th", { text: "Matchup" }),
        el("th", { text: "Map" }),
        el("th", { text: "Result" }),
        el("th", { class: "num", text: "Turns" }),
        el("th", { class: "num", text: "Dur" }),
        el("th", { text: "Detail" })
      )
    ),
    tbody
  );

  const listSlot = el("div", { class: "stack" }, skeletonRows(8));
  const moreSlot = el("div", { class: "load-more" });
  const pairMatrixSlot = el("section", { class: "pair-matrix", hidden: true });

  const botSelect = el(
    "select",
    { class: "select", "aria-label": "Filter by bot", onchange: (e) => setFilter({ bot: e.currentTarget.value }) },
    el("option", { value: "", text: "every bot" }),
    (state.ladder || []).map((row) =>
      el("option", { value: row.name, text: row.name, selected: row.name === gameFilter.bot })
    )
  );
  const mapSelect = el(
    "select",
    { class: "select", "aria-label": "Filter by map", onchange: (e) => setFilter({ map: e.currentTarget.value }) },
    el("option", { value: "", text: "every map" }),
    (state.maps || []).map((m) =>
      el("option", { value: m.name, text: m.name, selected: m.name === gameFilter.map })
    )
  );
  const failedBtn = toggleBtn("Failed only", gameFilter.failed, (on_) => setFilter({ failed: on_ }));
  const ratedBtn = toggleBtn("Rated only", gameFilter.rated, (on_) => setFilter({ rated: on_ }));
  const clearBtn = btn("Clear", {
    class: "btn btn-sm btn-ghost",
    onclick: () => setFilter({ ...EMPTY_GAME_FILTER }),
  });

  const pairChip = gameFilter.opponent
    ? el(
        "span",
        { class: "chip chip-accent" },
        gameFilter.bot ? botLink(gameFilter.bot) : "?",
        " vs ",
        botLink(gameFilter.opponent),
        el("button", {
          class: "btn btn-xs btn-ghost",
          type: "button",
          text: "✕",
          "aria-label": "Clear the pairing filter",
          onclick: () => setFilter({ opponent: "" }),
        })
      )
    : null;
  const tagChip = gameFilter.tag
    ? el(
        "span",
        { class: "chip chip-accent", title: gameFilter.tag },
        isWebMatchTag(gameFilter.tag)
          ? "this match"
          : ["run ", el("span", { class: "num", text: gameFilter.tag })],
        el("button", {
          class: "btn btn-xs btn-ghost",
          type: "button",
          text: "✕",
          "aria-label": "Clear the run tag filter",
          onclick: () => setFilter({ tag: "" }),
        })
      )
    : null;

  const view = viewRoot(
    {
      title: "Games",
      sub: "",
      toolbar: [
        el("div", { class: "filters" }, botSelect, mapSelect, pairChip, tagChip, failedBtn, ratedBtn, clearBtn),
      ],
    },
    pairMatrixSlot,
    listSlot,
    moreSlot
  );
  root.appendChild(view);

  function setFilter(patch) {
    gameFilter = { ...gameFilter, ...patch };
    if (routedTag && Object.hasOwn(patch, "tag") && !patch.tag) {
      location.hash = "#/games";
      return;
    }
    refreshView();
  }

  function buildRow(game, fresh) {
    const failed = gameHasError(game);
    const latestMatch = isLatestMatchGame(game, latestMatchTag);
    const detail = failed
      ? game.error || game.resign_message || conditionLabel(game.win_condition) || ""
      : game.resign_message || game.win_condition || "";
    const detailHref = gameFilter.tag
      ? `${gameHref(game.id)}?tag=${encodeURIComponent(gameFilter.tag)}`
      : gameHref(game.id);
    const tr = el(
      "tr",
      {
        class: `game-row${latestMatch ? " is-latest-match" : ""}${fresh ? " is-new" : ""}`,
        "data-status": game.status === "ok" && (game.a_errors || game.b_errors)
          ? "bot_error"
          : game.status,
        "data-rated": game.rated ? "true" : "false",
        "data-latest-match": latestMatch ? "true" : null,
        "data-id": String(game.id),
        title: latestMatch ? "Game from the most recent match" : null,
        tabindex: "0",
        onclick: () => {
          location.hash = detailHref;
        },
        onkeydown: (event) => {
          if (event.key === "Enter") location.hash = detailHref;
        },
      },
      el("td", { class: "col-time", text: fmt.time(game.ts), title: game.ts }),
      el("td", null, matchup(game)),
      el("td", null, mapChip(game.map, (name) => setFilter({ map: name }))),
      el("td", null, statusBadge(game)),
      el("td", { class: "num col-turns", text: game.turns ? fmt.int(game.turns) : "–" }),
      el("td", { class: "num col-dur", text: game.duration_ms ? fmt.dur(game.duration_ms) : "–" }),
      el("td", { class: "game-reason", text: detail, title: detail })
    );
    if (fresh) setTimeout(() => tr.classList.remove("is-new"), 1400);
    return tr;
  }

  function renderAll() {
    view.setSub(describeFilter());
    if (!rows.length) {
      fill(listSlot, 
        emptyState({
          title: "No games yet",
          hint: hasFilter()
            ? ["Nothing matches this filter."]
            : ["Press ", code("r"), " to run a match, or start an arena from the Run dialog."],
          actions: hasFilter()
            ? [btn("Clear filters", { class: "btn btn-sm", onclick: () => setFilter({ ...EMPTY_GAME_FILTER }) })]
            : [],
        })
      );
      fill(moreSlot);
      return;
    }
    fill(tbody, ...rows.map((game) => buildRow(game, false)));
    fill(listSlot, tableWrap(table));
    renderMore();
  }

  function renderMore() {
    fill(moreSlot);
    if (!next) return;
    moreSlot.appendChild(
      btn("Load more", {
        class: "btn btn-sm",
        onclick: async (event) => {
          const button = event.currentTarget;
          button.disabled = true;
          button.textContent = "Loading…";
          try {
            const page = await api(gameQuery(gameFilter, next));
            if (!ctx.alive()) return;
            rows = rows.concat(page.games || []);
            cap = Math.max(cap, rows.length);
            next = page.next || null;
            tbody.append(...(page.games || []).map((game) => buildRow(game, false)));
            renderMore();
          } catch (err) {
            toast(errorMessage(err), "error");
            button.disabled = false;
            button.textContent = "Load more";
          }
        },
      })
    );
  }

  function hasFilter() {
    return Boolean(gameFilter.bot || gameFilter.opponent || gameFilter.map || gameFilter.tag || gameFilter.failed || gameFilter.rated);
  }

  function describeFilter() {
    const parts = [];
    if (gameFilter.bot) parts.push(gameFilter.bot);
    if (gameFilter.opponent) parts.push(`vs ${gameFilter.opponent}`);
    if (gameFilter.map) parts.push(`on ${gameFilter.map}`);
    if (gameFilter.tag) {
      parts.push(isWebMatchTag(gameFilter.tag) ? "this match" : `run ${gameFilter.tag}`);
    }
    if (gameFilter.failed) parts.push("failed only");
    if (gameFilter.rated) parts.push("rated only");
    const shown = `${rows.length} shown`;
    const description = parts.length
      ? `${shown} · ${parts.join(" · ")}`
      : `${shown} of ${fmt.int((state.counts && state.counts.games) || 0)}`;
    return rows.some((game) => isLatestMatchGame(game, latestMatchTag))
      ? `${description} · latest match highlighted`
      : description;
  }

  async function loadPairMatrix() {
    const first = gameFilter.bot;
    const second = gameFilter.opponent;
    if (!first || !second || first === second) {
      pairMatrixSlot.hidden = true;
      fill(pairMatrixSlot);
      return;
    }
    pairMatrixSlot.hidden = false;
    fill(pairMatrixSlot, skeletonRows(3));
    try {
      const query = new URLSearchParams({ a: first, b: second });
      const data = await api(`/api/pair-matrix?${query.toString()}`);
      if (!ctx.alive()) return;
      const grid = matrixTable({
        rows: data.names || [first, second],
        columns: data.columns || [],
        cells: data.cells || {},
        rowLabel: (name) => botLink(name),
        columnLabel: (name) => el("span", { class: "matrix-col-label", text: name }),
        describe: (name, map) => `${name} vs ${name === first ? second : first} on ${map}`,
        onCellClick: (_name, map) => setFilter({ map }),
      });
      fill(
        pairMatrixSlot,
        el(
          "div",
          { class: "pair-matrix-head" },
          el("h2", { class: "section-title", text: "Pairing by map" }),
          el("span", { class: "small mute", text: "click a cell to filter the games below" })
        ),
        grid.node,
        el(
          "span",
          { class: "matrix-legend" },
          "loss",
          el("span", { class: "matrix-scale" }),
          "win",
          el("span", { class: "small mute", text: "· each row is that bot’s win rate on the map" })
        )
      );
      ctx.add(grid.hideTip);
    } catch (err) {
      if (!ctx.alive()) return;
      fill(pairMatrixSlot, el("span", { class: "small mute", text: `Could not load pairing matrix: ${errorMessage(err)}` }));
    }
  }

  async function load() {
    loadPairMatrix();
    const cacheable = isDefaultGameFilter(gameFilter);
    const cached = cacheable ? gamesFirstPageCache?.page ?? null : null;
    const applyPage = (page, requestRevision = latestMatchRunRevision) => {
      rows = page.games || [];
      next = page.next || null;
      latestMatchTag = requestRevision !== latestMatchRunRevision
        ? latestMatchLiveTag
        : typeof page?.latest_match_tag === "string"
        ? page.latest_match_tag
        : "";
      cap = Math.max(STREAM_CAP, rows.length);
      renderAll();
    };
    if (cached) applyPage(cached);
    try {
      const requestRevision = latestMatchRunRevision;
      const page = cacheable
        ? await requestGamesFirstPage({
            force:
              Boolean(cached) &&
              Date.now() - gamesFirstPageCache.at > GAMES_CACHE_MAX_AGE_MS,
          })
        : await api(gameQuery(gameFilter, null));
      if (!ctx.alive()) return;
      if (!sameGamesPage(page, cached)) applyPage(page, requestRevision);
    } catch (err) {
      if (!ctx.alive()) return;
      if (!cached) {
        fill(listSlot, emptyState({ title: "Could not load games", hint: [errorMessage(err)] }));
      }
    }
  }

  load();

  ctx.on("game", (payload) => {
    const game = payload && payload.game;
    if (!game || !matchesFilter(game, gameFilter)) return;
    if (rows.some((existing) => existing.id === game.id)) return;
    rows.unshift(game);
    if (!tbody.isConnected) {
      renderAll();
      return;
    }
    tbody.prepend(buildRow(game, true));
    while (rows.length > cap) {
      rows.pop();
      if (tbody.lastElementChild) tbody.lastElementChild.remove();
    }
    view.setSub(describeFilter());
    if (
      gameFilter.bot && gameFilter.opponent &&
      ((game.a === gameFilter.bot && game.b === gameFilter.opponent) ||
        (game.a === gameFilter.opponent && game.b === gameFilter.bot))
    ) loadPairMatrix();
  });

  ctx.on("run_started", (payload) => {
    const tag = startedMatchTag(payload);
    if (!tag) return;
    latestMatchTag = tag;
    if (tbody.isConnected) renderAll();
  });
});

/* -------------------------------------------------------------------------- */
/* 4. Game detail                                                             */
/* -------------------------------------------------------------------------- */

/** Split raw stderr into plain runs and traceback blocks, in order. */
function splitLog(text) {
  const lines = String(text || "").split("\n");
  const blocks = [];
  let plain = [];
  const flushPlain = () => {
    while (plain.length && !plain[plain.length - 1].trim()) plain.pop();
    while (plain.length && !plain[0].trim()) plain.shift();
    if (plain.length) blocks.push({ kind: "text", lines: plain });
    plain = [];
  };

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    if (/^(?:Bot [AB]|Both bots) failed (?:to load|validation):/.test(line)) {
      flushPlain();
      blocks.push({ kind: "loadfail", lines: [line] });
      continue;
    }
    if (!/^\s*Traceback \(most recent call last\):\s*$/.test(line)) {
      plain.push(line);
      continue;
    }
    flushPlain();
    const block = [line];
    i += 1;
    // Frames are indented; the first unindented line closes the traceback and
    // is its exception line. A chained traceback ("During handling of…")
    // continues the same block.
    while (i < lines.length) {
      const next = lines[i];
      if (/^\s/.test(next) || !next.trim()) {
        block.push(next);
        i += 1;
        continue;
      }
      block.push(next);
      i += 1;
      const lookahead = lines[i];
      if (
        lookahead !== undefined &&
        /^(During handling of the above exception|The above exception was the direct cause)/.test(lookahead.trim())
      ) {
        continue;
      }
      break;
    }
    i -= 1;
    while (block.length && !block[block.length - 1].trim()) block.pop();
    blocks.push({ kind: "traceback", lines: block });
  }
  flushPlain();
  return blocks;
}

const EXC_RE = /^([A-Za-z_][A-Za-z0-9_.]*)(: (.*))?$/;
const FILE_RE = /^(\s*)File "([^"]*)", line (\d+)(, in (.*))?$/;

/** Syntax-colour one traceback into a `<pre>`; every fragment is textContent. */
function tracebackPre(lines) {
  const pre = el("pre", { class: "logview-text" });
  lines.forEach((line, index) => {
    const file = FILE_RE.exec(line);
    if (file) {
      pre.append(
        file[1],
        'File "',
        el("span", { class: "tb-file", text: file[2] }),
        '", line ',
        el("span", { class: "tb-line", text: file[3] }),
        file[5] ? `, in ${file[5]}` : "",
        "\n"
      );
      return;
    }
    if (/^\s/.test(line) && line.trim()) {
      pre.append(el("span", { class: "tb-src", text: line }), "\n");
      return;
    }
    const exc = EXC_RE.exec(line.trim());
    if (exc && index > 0 && !/^\s/.test(line)) {
      pre.append(el("span", { class: "tb-exc", text: exc[1] }));
      if (exc[3] !== undefined) pre.append(": ", el("span", { class: "tb-msg", text: exc[3] }));
      pre.append("\n");
      return;
    }
    pre.append(`${line}\n`);
  });
  return pre;
}

/** Which bot a traceback belongs to, matched on its `/<botname>/` path segment. */
function attributeBlock(lines, a, b) {
  const text = lines.join("\n").replace(/\\/g, "/");
  const owns = (name) => name && (text.includes(`/${name}/`) || text.includes(`/${name}"`));
  const hitA = owns(a);
  const hitB = a === b ? false : owns(b);
  if (hitA && !hitB) return "a";
  if (hitB && !hitA) return "b";
  return null;
}

/** The stderr panel: identical tracebacks collapse to one entry with a ×N badge. */
function logView(text, game) {
  const blocks = splitLog(text);
  const root = el("div", {
    class: "logview",
    tabindex: "0",
    "aria-label": `Captured stderr for ${game.a} versus ${game.b}`,
  });
  if (!blocks.length) {
    root.appendChild(el("div", { class: "logview-empty", text: "No stderr captured." }));
    return root;
  }

  const seen = new Map();
  const ordered = [];
  for (const block of blocks) {
    if (block.kind === "text") {
      ordered.push({ ...block, count: 1 });
      continue;
    }
    const key = `${block.kind}\u0000${block.lines.join("\n")}`;
    const existing = seen.get(key);
    if (existing) {
      existing.count += 1;
      continue;
    }
    const entry = { ...block, count: 1 };
    seen.set(key, entry);
    ordered.push(entry);
  }

  for (const block of ordered) {
    if (block.kind === "text") {
      root.appendChild(el("pre", { class: "logview-text", text: block.lines.join("\n") }));
      continue;
    }
    const owner = block.kind === "loadfail"
      ? /^Bot A/.test(block.lines[0])
        ? "a"
        : /^Bot B/.test(block.lines[0])
          ? "b"
          : "both"
      : attributeBlock(block.lines, game.a, game.b);
    const pre = block.kind === "traceback" ? tracebackPre(block.lines) : el("pre", { class: "logview-text", text: block.lines.join("\n") });
    const collapsed = block.count > 1;
    pre.hidden = collapsed;

    const expand = el("button", {
      class: "btn btn-xs btn-ghost",
      type: "button",
      "aria-expanded": collapsed ? "false" : "true",
      text: collapsed ? "show" : "hide",
      onclick: (event) => {
        pre.hidden = !pre.hidden;
        event.currentTarget.textContent = pre.hidden ? "show" : "hide";
        event.currentTarget.setAttribute("aria-expanded", pre.hidden ? "false" : "true");
      },
    });

    const head = el(
      "div",
      { class: "logview-head" },
      el("span", {
        class: "badge",
        "data-status": block.kind === "loadfail" ? `loadfail_${owner}` : "engine_error",
        text: block.kind === "loadfail" ? "Load failure" : "Traceback",
      }),
      owner === "both"
        ? el("span", {
            class: "logview-owner",
            text: "both bots",
            title: game.a === game.b ? game.a : `${game.a} and ${game.b}`,
          })
        : owner
        ? botLink(owner === "a" ? game.a : game.b, {
            class: `logview-owner slot-${owner}`,
          })
        : el("span", { class: "logview-owner mute", text: "engine" }),
      block.count > 1
        ? el("span", { class: "repeat-badge", text: `×${block.count}`, title: `${block.count} identical occurrences` })
        : el("span", { class: "spacer" }),
      expand
    );
    root.appendChild(el("div", { class: "logview-block", "data-kind": "traceback" }, head, pre));
  }
  return root;
}

function profileTime(us) {
  const value = Number(us) || 0;
  if (value < 1_000) return `${fmt.num(value, 0)} µs`;
  if (value < 1_000_000) return `${fmt.num(value / 1_000, 2)} ms`;
  return `${fmt.num(value / 1_000_000, 2)} s`;
}

function aggregateProfilerReports(reports) {
  const groups = new Map();
  for (const report of reports) {
    const team = report.team === "a" || report.team === "b" ? report.team : "unknown";
    let group = groups.get(team);
    if (!group) {
      group = {
        team,
        reports: 0,
        unitIds: new Set(),
        types: new Map(),
        interrupted: 0,
        badNesting: 0,
        spans: new Map(),
      };
      groups.set(team, group);
    }
    group.reports += 1;
    group.unitIds.add(String(report.unit_id));
    group.types.set(report.unit_type, (group.types.get(report.unit_type) || 0) + 1);
    group.interrupted += report.interrupted;
    group.badNesting += report.bad_nesting;
    for (const [name, span] of Object.entries(report.spans)) {
      let aggregate = group.spans.get(name);
      if (!aggregate) {
        aggregate = { name, calls: 0, total_us: 0, self_us: 0, max_total_us: 0 };
        group.spans.set(name, aggregate);
      }
      aggregate.calls += span.calls;
      aggregate.total_us += span.total_us;
      aggregate.self_us += span.self_us;
      aggregate.max_total_us = Math.max(aggregate.max_total_us, span.max_total_us);
    }
  }
  return [...groups.values()].sort((left, right) => {
    const order = { a: 0, b: 1, unknown: 2 };
    return order[left.team] - order[right.team];
  });
}

function profilerGroup(group, game, spanMode) {
  const spans = [...group.spans.values()]
    .map((span) => ({ span, metric: profilerSpanMetric(span, spanMode) }))
    .sort(
      (left, right) =>
        right.metric.inclusive_us - left.metric.inclusive_us ||
        (right.metric.exclusive_us ?? 0) - (left.metric.exclusive_us ?? 0) ||
        left.span.name.localeCompare(right.span.name)
    );
  const scale = Math.max(1, ...spans.map(({ metric }) => metric.inclusive_us));
  const typeSummary = [...group.types.entries()]
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .map(([name, count]) => `${name} ×${count}`)
    .join(" · ");
  const side = group.team === "a" || group.team === "b" ? group.team : null;
  const botName = side ? game[side] : "unknown team";
  const warnings = group.interrupted + group.badNesting;

  const tbody = el("tbody");
  for (const { span, metric } of spans) {
    const average = span.calls ? span.total_us / span.calls : 0;
    tbody.appendChild(
      el(
        "tr",
        null,
        el(
          "th",
          { scope: "row", title: span.name },
          el("span", { class: "profile-span-name", text: span.name }),
          el(
            "span",
            { class: "profile-bar", "aria-hidden": "true" },
            el("span", { class: "profile-bar-total", style: { width: `${(metric.inclusive_us / scale) * 100}%` } }),
            metric.exclusive_us === null
              ? null
              : el("span", {
                  class: "profile-bar-self",
                  style: { width: `${(metric.exclusive_us / scale) * 100}%` },
                })
          )
        ),
        el("td", { class: "num", text: profileTime(span.self_us) }),
        el("td", { class: "num", text: profileTime(span.total_us) }),
        el("td", { class: "num", text: fmt.int(span.calls) }),
        el("td", { class: "num", text: profileTime(average) }),
        el("td", { class: "num", text: profileTime(span.max_total_us) })
      )
    );
  }

  return el(
    "section",
    { class: "profile-group", dataset: { side: side || "unknown" } },
    el(
      "div",
      { class: "profile-group-head" },
      side ? el("span", { class: `badge badge-${side}`, text: side.toUpperCase() }) : null,
      side ? botLink(botName, { class: `strong slot-${side}` }) : el("span", { class: "strong", text: botName }),
      el("span", {
        class: "small mute",
        text: `${fmt.int(group.unitIds.size)} unit report${group.unitIds.size === 1 ? "" : "s"} · ${typeSummary}`,
      }),
      warnings
        ? el("span", {
            class: "chip chip-err",
            text: `${fmt.int(warnings)} incomplete span${warnings === 1 ? "" : "s"}`,
            title: `${group.interrupted} interrupted; ${group.badNesting} bad nesting`,
          })
        : null
    ),
    el(
      "div",
      { class: "profile-table-wrap" },
      el(
        "table",
        { class: "table profile-table" },
        el(
          "thead",
          null,
          el(
            "tr",
            null,
            el("th", { scope: "col", text: "Span" }),
            el("th", {
              scope: "col",
              class: "num",
              text: "Self",
              title: "Exclusive CPU time across all calls",
            }),
            el("th", {
              scope: "col",
              class: "num",
              text: "Total",
              title: "Inclusive CPU time across all calls",
            }),
            el("th", { scope: "col", class: "num", text: "Calls" }),
            el("th", {
              scope: "col",
              class: "num",
              text: "Avg",
              title: "Average inclusive CPU time per call",
            }),
            el("th", {
              scope: "col",
              class: "num",
              text: "Max",
              title: "Maximum inclusive CPU time for one call",
            })
          )
        ),
        tbody
      )
    )
  );
}

function profilerView(reports, game, spanMode = "avg") {
  const groups = aggregateProfilerReports(reports);
  const barNote = spanMode === "total"
    ? "Bars show cumulative self (exclusive) time over cumulative total (inclusive) time."
    : spanMode === "max"
      ? "Bars show maximum inclusive time for one call; maximum self time is not recorded."
      : "Bars show average self (exclusive) time over average total (inclusive) time per call.";
  return el(
    "div",
    { class: "profile-view" },
    el(
      "p",
      { class: "small mute profile-note" },
      `CPU time from surviving units that emitted a final report. ${barNote} Nested spans can overlap their parents.`
    ),
    ...groups.map((group) => profilerGroup(group, game, spanMode))
  );
}

function ratingChange(game, slot, name) {
  const before = game[`${slot}_mu_before`];
  const beforeSigma = game[`${slot}_sigma_before`];
  const after = game[`${slot}_mu_after`];
  const afterSigma = game[`${slot}_sigma_after`];
  const delta = game[`${slot}_delta`];
  if ([before, beforeSigma, after, afterSigma].some((value) => value === null || value === undefined)) {
    return el("span", { class: "mute small", text: "unrated", "aria-label": `${name}: unrated` });
  }
  const from = before - CI * beforeSigma;
  const to = after - CI * afterSigma;
  const change = delta === null || delta === undefined ? to - from : delta;
  return el(
    "span",
    {
      class: "rating-change nowrap",
      "aria-label": `${name}: LCB95 ${fmt.num(from, 2)} to ${fmt.num(to, 2)}, change ${fmt.signed(change)}`,
    },
    el("span", { class: "num mute", text: fmt.num(from, 2) }),
    el("span", { class: "mute", text: "→" }),
    el("span", { class: "num", text: fmt.num(to, 2) }),
    el("span", {
      class: "delta-chip",
      "data-dir": change > 0.005 ? "up" : change < -0.005 ? "down" : "flat",
      text: fmt.signed(change),
    })
  );
}

function gamePlayerTable(game) {
  const heading = (label, attrs = {}) => el("th", { scope: "col", ...attrs }, label);
  const row = (slot, name) =>
    el(
      "tr",
      null,
      el("td", null, el("span", { class: `badge badge-${slot}`, text: slot.toUpperCase() })),
      el("th", { scope: "row", class: "ellipsis" }, botLink(name, { class: "ellipsis" })),
      el("td", { class: "num", text: fmt.int(game[`${slot}_titanium`]) }),
      el("td", { class: "num", text: fmt.int(game[`${slot}_mined`]) }),
      el("td", { class: "num", text: fmt.int(game[`${slot}_units`]) }),
      el("td", { class: "num", text: fmt.int(game[`${slot}_buildings`]) }),
      el(
        "td",
        { class: "num" },
        game[`${slot}_errors`]
          ? el("span", { class: "chip chip-err", text: String(game[`${slot}_errors`]) })
          : el("span", { class: "mute", text: "0" })
      ),
      el("td", { class: "num" }, ratingChange(game, slot, name))
    );
  return el(
    "div",
    { class: "game-score-wrap" },
    el(
      "table",
      { class: "table table-compact game-score-table" },
      el("caption", { class: "sr-only", text: "Player score and LCB95 rating change" }),
      el(
        "thead",
        null,
        el(
          "tr",
          null,
          heading("Side"),
          heading("Bot"),
          heading(el("abbr", { title: "Titanium", text: "Ti" }), { class: "num" }),
          heading("Mined", { class: "num" }),
          heading("Units", { class: "num" }),
          heading(el("abbr", { title: "Buildings", text: "Bldg" }), { class: "num" }),
          heading(el("abbr", { title: "Errors", text: "Err" }), { class: "num" }),
          heading("LCB95 change", { class: "num" })
        )
      ),
      el("tbody", null, row("a", game.a), row("b", game.b))
    )
  );
}

const game = mount("game", (root, params, ctx) => {
  const id = Number(params && (params.id || params.game));
  const batchTag = typeof params?.tag === "string" ? params.tag : "";
  const taggedGamesHref = batchTag
    ? `#/games?tag=${encodeURIComponent(batchTag)}`
    : "#/games";
  const taggedGameHref = (gameId) => batchTag
    ? `#/games/${encodeURIComponent(gameId)}?tag=${encodeURIComponent(batchTag)}`
    : gameHref(gameId);
  const theme = () => document.documentElement.dataset.theme || state.theme || "dark";
  const squareViewer = globalThis.oarena?.squareViewer;
  let replayProfilerReports = normaliseProfilerRecords(squareViewer?.getProfiler?.(String(id)));
  let profilerSpanMode = "avg";
  let renderProfilerReports = () => {};
  const stopProfiler = squareViewer?.onProfiler?.(({ key, records }) => {
    if (String(key) !== String(id) || !ctx.alive()) return;
    replayProfilerReports = normaliseProfilerRecords(records);
    renderProfilerReports();
  });
  if (typeof stopProfiler === "function") ctx.add(stopProfiler);
  const officialAvailable = Boolean(state.config && state.config.visualiser === true);
  const viewerStorageKey = "oarena.replay.viewer";
  let viewerChoice = "2d";
  try {
    if (localStorage.getItem(viewerStorageKey) === "official" && officialAvailable) {
      viewerChoice = "official";
    }
  } catch {
    /* Browser privacy settings may disable storage; 2D remains the default. */
  }

  const vizSlot = el("div", { class: "viz-frame" });
  const viewerSelect = el(
    "select",
    {
      class: "select replay-viewer-select",
      "aria-label": "Replay viewer",
      title: "Choose the replay viewer",
    },
    el("option", { value: "2d", text: "2D", selected: viewerChoice === "2d" }),
    officialAvailable
      ? el("option", {
          value: "official",
          text: "Official 3D",
          selected: viewerChoice === "official",
        })
      : null,
  );
  const viewerPicker = el(
    "label",
    { class: "replay-viewer-picker" },
    el("span", { class: "replay-viewer-label", text: "Viewer" }),
    viewerSelect,
  );
  viewerPicker.hidden = true;
  const fullscreen = btn("Fullscreen", {
    class: "btn btn-sm btn-ghost",
    title: "Fill the screen with the replay viewer",
    onclick: async () => {
      try {
        if (viewerChoice === "2d" && squareViewer) {
          await squareViewer.requestFullscreen();
        } else if (typeof vizSlot.requestFullscreen === "function") {
          await vizSlot.requestFullscreen();
        } else {
          throw new Error("Fullscreen is not supported by this browser");
        }
      } catch (err) {
        toast(`Could not enter fullscreen: ${errorMessage(err)}`, "error");
      }
    },
  });
  fullscreen.hidden = true;
  const batchSelectorSlot = el("div", { class: "game-batch-selector-slot", hidden: true });
  const detailSlot = el("div", { class: "game-report-slot" }, skeletonRows(4));
  let batchLinksExpanded = false;
  const gameErrorMark = el("span", {
    class: "badge game-error-mark",
    "data-status": "bot_error",
    text: "!",
    role: "img",
    hidden: true,
  });
  const view = viewRoot(
    {
      title: [`Game #${Number.isFinite(id) ? id : "?"}`, gameErrorMark],
      sub: "",
      full: true,
      crumbs: crumbs(el("a", { href: taggedGamesHref, text: "Games" }), el("span", { text: `#${id}` })),
      toolbar: [
        viewerPicker,
        fullscreen,
        btn("Replay file", {
          class: "btn btn-sm btn-ghost",
          title: "Download the replay",
          onclick: () => window.open(`/api/games/${id}/replay`, "_blank", "noopener"),
        }),
      ],
    },
    el("div", { class: "game-detail" }, batchSelectorSlot, vizSlot, detailSlot)
  );
  root.appendChild(view);

  let replayData = null;
  let batchReplayRows = null;
  viewerSelect.addEventListener("change", (event) => {
    const requested = event.currentTarget.value;
    viewerChoice = requested === "official" && officialAvailable ? "official" : "2d";
    viewerSelect.value = viewerChoice;
    try {
      localStorage.setItem(viewerStorageKey, viewerChoice);
    } catch {
      /* The choice still applies to this page when storage is unavailable. */
    }
    if (replayData && ctx.alive()) mountViz(replayData);
    if (viewerChoice === "2d" && batchReplayRows) {
      squareViewer?.prepareGames(batchReplayRows, id);
    } else if (viewerChoice !== "2d") {
      squareViewer?.prepareGames([], id);
    }
  });

  async function loadBatchSelector(selected) {
    try {
      const page = await requestMatchBatch(batchTag);
      if (!ctx.alive()) return;
      const games = (Array.isArray(page?.games) ? page.games : [])
        .filter((entry) => entry?.tag === batchTag && Number.isInteger(entry?.batch_ordinal))
        .sort((left, right) =>
          left.batch_ordinal - right.batch_ordinal || Number(left.id) - Number(right.id)
        );
      const selectedRow = games.find((entry) => Number(entry.id) === id);
      if (!selectedRow || selectedRow.batch_ordinal !== selected.batch_ordinal) return;
      batchReplayRows = games;
      if (viewerChoice === "2d") squareViewer?.prepareGames(games, id);

      const score = batchScore(games);
      const overall = batchOverallResult(score);
      const resultCounts = [
        score.draw ? `${score.draw} draw${score.draw === 1 ? "" : "s"}` : null,
        score.errors ? `${score.errors} error${score.errors === 1 ? "" : "s"}` : null,
      ].filter(Boolean);
      const resultCountsLabel = resultCounts.length ? resultCounts.join(", ") : null;
      const linkEntries = (() => {
        if (!batchLinksExpanded && games.length > GAME_BATCH_PREVIEW_LIMIT) {
          const keep = Math.max(1, GAME_BATCH_PREVIEW_LIMIT - 1);
          const leading = games.slice(0, keep);
          const includeSelected = !leading.some((entry) => Number(entry.id) === id);
          if (includeSelected) {
            return [...leading, selectedRow];
          }
          return leading;
        }
        return games;
      })();
      const links = linkEntries.map((entry) => {
        const active = Number(entry.id) === id;
        const winnerName = entry.winner === "a" || entry.winner === "b"
          ? fmt.winner(entry)
          : null;
        const resultKind = entry.status !== "ok"
          ? "error"
          : winnerName
            ? "winner"
            : "draw";
        const result = resultKind === "error"
          ? "!"
          : resultKind === "draw"
            ? "Draw"
            : winnerName;
        const resultTitle = resultKind === "winner"
          ? `${winnerName} won`
          : resultKind === "draw"
            ? "Draw"
            : `Game ended with ${String(entry.status || "an error").replace(/_/g, " ")}`;
        const ordinal = entry.batch_ordinal + 1;
        return el(
          "a",
          {
            class: `game-batch-link${active ? " is-active" : ""}`,
            href: taggedGameHref(entry.id),
            "aria-current": active ? "page" : null,
            "data-status": entry.status || "unknown",
            title: `Game ${ordinal}: ${entry.a} vs ${entry.b} on ${entry.map} · ${resultTitle}`,
          },
          el("span", { class: "game-batch-number num", text: String(ordinal) }),
          el("span", { class: "game-batch-map", text: entry.map || "unknown map" }),
          el("span", {
            class: "game-batch-result",
            "data-result": resultKind,
            text: result,
            title: resultTitle,
          }),
        );
      });
      // Name the sides of the score so the reader never has to guess which bot
      // the left number belongs to -- the very confusion a slot tally created.
      const scoreText = `${score.a}–${score.b}`;
      const scoreTitle = batchScoreTitle(score);
      const fullList = page?.more
        ? el("a", {
            class: "game-batch-all",
            href: taggedGamesHref,
            text: "All games",
            title: "Open the full filtered Games list",
          })
        : null;
      const playedGames = Number.isInteger(page?.played_games)
        ? page.played_games
        : games.length;
      const gameCountLabel = page?.more
        ? `${games.length} of ${playedGames} games`
        : `${games.length} games`;
      const toggle = games.length > GAME_BATCH_PREVIEW_LIMIT
        ? el("button", {
            class: "btn btn-xs btn-ghost game-batch-toggle",
            type: "button",
            "aria-pressed": batchLinksExpanded ? "true" : "false",
            onclick: async () => {
              batchLinksExpanded = !batchLinksExpanded;
              await loadBatchSelector(selected);
            },
            text: batchLinksExpanded
              ? `Show first ${GAME_BATCH_PREVIEW_LIMIT} games`
              : `Show all ${games.length} games`,
          })
        : null;
      const linksRail = el("div", { class: "game-batch-links" }, links);
      fill(
        batchSelectorSlot,
        el(
          "nav",
          { class: "game-batch-selector", "aria-label": "Games in this match" },
          el(
            "span",
            { class: "game-batch-label" },
            "Match ",
            el("span", { class: "num", text: gameCountLabel }),
            " · ",
            el("span", { class: "game-batch-score", text: scoreText, title: scoreTitle }),
            " · ",
            el("span", { class: "mute", text: overall }),
            resultCountsLabel ? el("span", { class: "mute", text: ` (${resultCountsLabel})` }) : null,
          ),
          toggle,
          linksRail,
          fullList,
        ),
      );
      batchSelectorSlot.hidden = false;
      requestAnimationFrame(() => {
        if (!ctx.alive()) return;
        linksRail.querySelector('[aria-current="page"]')?.scrollIntoView({
          block: "nearest",
          inline: "center",
        });
      });
    } catch {
      // The selected game remains fully usable if the optional batch index fails.
    }
  }

  function mountViz(data) {
    viewerPicker.hidden = !data.has_replay;
    viewerSelect.disabled = !data.has_replay;
    fullscreen.hidden =
      typeof vizSlot.requestFullscreen !== "function" || !data.has_replay;
    if (!data.has_replay) {
      squareViewer?.hide(vizSlot);
      delete vizSlot.dataset.viewer;
      fill(vizSlot, 
        emptyState({
          title: "Replay unavailable",
          hint:
            data.status === "ok"
              ? ["This replay was pruned automatically or deleted from Storage."]
              : ["Replays are only kept for games that finished cleanly; this one ended as ", code(data.status), "."],
        })
      );
      return;
    }

    // A saved official-viewer preference cannot strand the replay when this
    // fcode install has no bundled viewer. The Square viewer ships with oarena.
    if (viewerChoice === "official" && !officialAvailable) viewerChoice = "2d";
    viewerSelect.value = viewerChoice;
    vizSlot.dataset.viewer = viewerChoice;

    if (viewerChoice === "2d") {
      fill(vizSlot);
      if (squareViewer) {
        squareViewer.show(vizSlot, data, theme());
      } else {
        fill(vizSlot, emptyState({ title: "2D viewer unavailable" }));
      }
      return;
    }

    squareViewer?.hide(vizSlot);
    const frame = el("iframe", {
      class: "viz-iframe",
      title: `Interactive replay of game ${id}; hover or click for details, or focus the map and use Shift plus arrow keys then Enter`,
      src: `/viz/?replayUrl=${encodeURIComponent(`/api/games/${id}/replay`)}&assetBaseUrl=/viz/&theme=${encodeURIComponent(theme())}`,
      allow: "fullscreen",
    });
    fill(vizSlot, frame);
  }

  async function load() {
    let data;
    try {
      if (viewerChoice === "2d" && squareViewer) {
        data = await squareViewer.getGame(id);
      } else {
        data = await api(`/api/games/${id}`);
      }
    } catch (err) {
      if (!ctx.alive()) return;
      fill(root, 
        el(
          "div",
          { class: "view" },
          emptyState({
            title: `No game #${id}`,
            hint: [errorMessage(err)],
            actions: [btn("Back to games", { class: "btn btn-sm", onclick: () => (location.hash = taggedGamesHref) })],
          })
        )
      );
      return;
    }
    if (!ctx.alive()) return;

    view.setSub(`${data.a} vs ${data.b} · ${data.map}`);
    if (gameHasError(data)) {
      const errors = (Number(data.a_errors) || 0) + (Number(data.b_errors) || 0);
      const status = data.status !== "ok"
        ? STATUS_LABEL[data.status] || conditionLabel(data.status)
        : "";
      const label = [
        status ? `Game ended with ${status}` : "",
        errors ? `${fmt.int(errors)} attributed bot ${errors === 1 ? "error" : "errors"}` : "",
      ].filter(Boolean).join("; ") || "Game error";
      gameErrorMark.title = label;
      gameErrorMark.setAttribute("aria-label", label);
      gameErrorMark.hidden = false;
    }
    replayData = data;
    mountViz(data);
    if (
      batchTag &&
      data.tag === batchTag &&
      Number.isInteger(data.batch_ordinal)
    ) {
      void loadBatchSelector(data);
    }
    ctx.add(() => {
      squareViewer?.hide(vizSlot);
      fill(vizSlot);
    });

    const onTheme = () => {
      if (!ctx.alive()) return;
      if (viewerChoice === "2d") squareViewer?.setTheme(theme());
      else mountViz(data);
    };
    document.addEventListener("themechange", onTheme);
    ctx.add(() => document.removeEventListener("themechange", onTheme));

    // Let the already-primed canvas paint before formatting profiler output
    // and the rest of the game report. Large stderr tails must not hold the
    // replay reveal hostage to one long route task.
    await new Promise((resolve) =>
      requestAnimationFrame(() => requestAnimationFrame(resolve)),
    );
    if (!ctx.alive()) return;

    const winnerName =
      data.winner === "draw" || !data.winner ? "draw" : data.winner === "a" ? data.a : data.b;
    const resultTitle = `game-${id}-result`;
    const playersTitle = `game-${id}-players`;
    const profilerTitle = `game-${id}-profiler`;
    const stderrTitle = `game-${id}-stderr`;
    const legacyReplayWarning =
      data.has_replay && !data.has_fcode_metadata
        ? `This legacy replay has no recorded engine metadata; rendering uses installed FCode${
            state.fcode ? ` ${state.fcode}` : ""
          } and may be inaccurate.`
        : null;
    const logBody = el(
      "div",
      { class: "game-log-body" },
      el("div", { class: "logview-empty", text: "Loading…" })
    );
    const profilerBody = el("div", { class: "game-profiler-body" });
    const profilerModeButtons = new Map();
    const profilerModeTitles = {
      avg: "Scale and sort spans by average inclusive time per call",
      total: "Scale and sort spans by cumulative inclusive time",
      max: "Scale and sort spans by maximum inclusive time for one call",
    };
    const profilerModeControl = el(
      "span",
      {
        class: "seg",
        role: "group",
        "aria-label": "Profiler span bar metric",
      },
      PROFILER_SPAN_MODES.map((mode) => {
        const button = el("button", {
          class: "seg-btn",
          type: "button",
          text: mode === "avg" ? "Avg" : mode === "total" ? "Total" : "Max",
          title: profilerModeTitles[mode],
          "aria-pressed": mode === profilerSpanMode ? "true" : "false",
          onclick: () => {
            if (mode === profilerSpanMode) return;
            profilerSpanMode = mode;
            for (const [candidate, candidateButton] of profilerModeButtons) {
              candidateButton.setAttribute("aria-pressed", candidate === mode ? "true" : "false");
            }
            renderProfilerReports();
          },
        });
        profilerModeButtons.set(mode, button);
        return button;
      })
    );
    const profilerSection = el(
      "section",
      {
        class: "game-report-section game-profiler",
        "aria-labelledby": profilerTitle,
        hidden: true,
      },
      el(
        "div",
        { class: "game-report-head" },
        el("h2", { class: "game-report-title", id: profilerTitle, text: "Profiler" }),
        profilerModeControl,
        el("span", { class: "chip", text: "CPU µs", title: "Controller CPU clock, measured in microseconds" })
      ),
      profilerBody
    );
    const report = el(
      "section",
      { class: "game-report", "aria-labelledby": resultTitle },
      el(
        "section",
        { class: "game-report-section game-result" },
        el("h2", { class: "game-report-title", id: resultTitle, text: "Result" }),
        el(
          "div",
          { class: "game-outcome" },
          statusBadge(data),
          el(
            "span",
            { class: "game-winner strong" },
            winnerName === "draw" ? "Draw" : [botLink(winnerName), " wins"]
          ),
          data.rated ? null : el("span", { class: "chip chip-tag", text: "unrated" }),
          data.tag
            ? el("span", {
                class: "chip chip-tag",
                text: isWebMatchTag(data.tag) ? "match run" : data.tag,
                title: data.tag,
              })
            : null
        ),
        data.error ? el("p", { class: "form-error", text: data.error }) : null,
        data.resign_message
          ? el("p", { class: "game-resign small mute", text: `resign: ${data.resign_message}` })
          : null,
        legacyReplayWarning
          ? el("p", {
              class: "game-resign small warn",
              role: "note",
              text: legacyReplayWarning,
            })
          : null,
        el(
          "dl",
          { class: "game-facts" },
          ...[
            ["Turns", el("span", { class: "num", text: fmt.int(data.turns) })],
            ["Duration", el("span", { class: "num", text: fmt.dur(data.duration_ms) })],
            ["Condition", el("span", { text: conditionLabel(data.win_condition) || "–", title: data.win_condition || "" })],
            ["Seed", el("span", { class: "num", text: fmt.int(data.seed) })],
            ["Map", mapChip(data.map, (name) => gotoGames({ map: name }))],
            [
              "Played",
              el(
                "time",
                { class: "num", datetime: data.ts || "", title: data.ts || "" },
                `${fmt.time(data.ts)} · ${fmt.ago(data.ts)}`
              ),
            ],
          ].map(([label, value]) =>
            el("div", { class: "game-fact" }, el("dt", { text: label }), el("dd", null, value))
          )
        )
      ),
      el(
        "section",
        { class: "game-report-section", "aria-labelledby": playersTitle },
        el("h2", { class: "game-report-title", id: playersTitle, text: "Score and rating change" }),
        gamePlayerTable(data)
      ),
      profilerSection,
      el(
        "section",
        { class: "game-report-section game-stderr", "aria-labelledby": stderrTitle },
        el(
          "div",
          { class: "game-report-head" },
          el("h2", { class: "game-report-title", id: stderrTitle, text: "stderr" }),
          btn("Raw", {
            class: "btn btn-xs btn-ghost",
            onclick: () => window.open(`/api/games/${id}/log`, "_blank", "noopener"),
          })
        ),
        logBody
      )
    );

    fill(detailSlot, report);

    let logProfilerReports = [];
    renderProfilerReports = () => {
      const reports = replayProfilerReports.length ? replayProfilerReports : logProfilerReports;
      profilerSection.hidden = reports.length === 0;
      fill(profilerBody, reports.length ? profilerView(reports, data, profilerSpanMode) : null);
    };
    const renderCapturedOutput = (text) => {
      const captured = extractProfilerReports(text);
      fill(logBody, logView(captured.text, data));
      logProfilerReports = captured.reports;
      renderProfilerReports();
    };

    // The inline tail is instant; the full capture replaces it when it lands.
    renderCapturedOutput(data.log_tail || "");
    if (data.has_log) {
      try {
        const response = await fetch(`/api/games/${id}/log`, { headers: { Accept: "text/plain" } });
        if (response.ok) {
          const full = await response.text();
          if (ctx.alive()) renderCapturedOutput(full);
        }
      } catch (err) {
        /* the tail is already on screen; a failed full read is not worth a toast */
      }
    }
  }

  load();
});

/* -------------------------------------------------------------------------- */
/* 5. Bots                                                                    */
/* -------------------------------------------------------------------------- */

/** Run `worker` over `items` with a small concurrency cap (keeps the UI live). */
async function pool(items, limit, worker) {
  let index = 0;
  const runners = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (index < items.length) {
      const mine = index;
      index += 1;
      await worker(items[mine]);
    }
  });
  await Promise.all(runners);
}

async function botDetail(name) {
  const cached = state.bots && state.bots[name];
  const detail = await api(`/api/bots/${encodeURIComponent(name)}`);
  if (state.bots) state.bots[name] = detail;
  return detail || cached;
}

const botsUi = { query: "" };

const bots = mount("bots", (root, params, ctx) => {
  let rows = (state.ladder || []).slice();
  const grid = el("div", { class: "bot-grid" });
  const slot = el("div", { class: "stack" }, grid);
  const search = searchBox(botsUi.query, "filter bots", (value) => {
    botsUi.query = value;
    render();
  });
  const view = viewRoot({ title: "Bots", sub: "", toolbar: [search.wrap] }, slot);
  root.appendChild(view);

  const sparkSlots = new Map();
  const botNodes = new Map();

  const visibleRows = () => {
    const query = botsUi.query.trim().toLowerCase();
    return rows.filter((row) => !query || row.name.toLowerCase().includes(query));
  };

  function botCard(row) {
    const spark = el("div", { class: "spark" }, el("span", { class: "spark-empty", text: "no history yet" }));
    sparkSlots.set(row.name, spark);
    const scoreValue = el("span", {
      class: "num",
      "data-bot-score": "",
      text: fmt.num(row.lcb95 ?? row.score, 2),
    });
    const score = el(
      "span",
      { class: "bot-card-score", title: "95% lower confidence bound" },
      el("span", { class: "mute small", text: "LCB95 " }),
      scoreValue
    );
    const broken = el("span", {
      class: "chip chip-broken", "data-bot-broken": "", hidden: !row.broken,
      text: "broken", title: row.broken_reason || "",
    });
    const rating = el("span", { class: "chip", "data-bot-rating": "", text: `μ ${fmt.num(row.mu, 1)} ±${fmt.num(row.sigma, 1)}` });
    const games = el("span", { "data-bot-games": "", text: `${fmt.int(row.games)} rated games` });
    const record = el("span", { "data-bot-record": "" }, wldSpan(row.wins, row.losses, row.draws));
    const errors = el("span", { "data-bot-errors": "", class: row.err_total ? "warn" : "", text: `${fmt.int(row.err_total)} err` });

    const activeToggle = el(
      "label",
      { class: "toggle", onclick: (event) => event.stopPropagation() },
      el("input", {
        type: "checkbox",
        checked: row.active,
        "data-bot-active": "",
        "aria-label": `${row.name} active`,
        onchange: async (event) => {
          const input = event.currentTarget;
          const active = input.checked;
          try {
            await api(`/api/bots/${encodeURIComponent(row.name)}/active`, {
              method: "POST",
              body: { active },
            });
            row.active = active;
            node.dataset.inactive = active ? "false" : "true";
            toast(`${row.name} ${active ? "enabled" : "disabled"}`, "ok");
          } catch (err) {
            input.checked = !active;
            toast(errorMessage(err), "error");
          }
        },
      }),
      el("span", { class: "toggle-track" }, el("span", { class: "toggle-thumb" })),
      el("span", { class: "toggle-label", text: "active" })
    );
    const node = el(
      "div",
      {
        class: "card card-link",
        "data-bot": row.name,
        "data-broken": row.broken ? "true" : "false",
        "data-inactive": row.active ? "false" : "true",
        tabindex: "0",
        role: "link",
        onclick: () => {
          location.hash = nameHref(row.name);
        },
        onkeydown: (event) => {
          if (event.key === "Enter") location.hash = nameHref(row.name);
        },
      },
      el(
        "div",
        { class: "card-body" },
        el(
          "div",
          { class: "bot-card-head" },
          botLink(row.name, { class: "bot-card-name" }),
          score
        ),
        el(
          "div",
          { class: "row wrap", style: "margin:4px 0 6px" },
          broken,
          rating
        ),
        spark,
        el(
          "div",
          { class: "bot-card-meta" },
          games,
          record,
          errors
        )
      ),
      el("div", { class: "card-foot" }, activeToggle)
    );
    botNodes.set(row.name, node);
    return node;
  }

  function patchCard(row) {
    const node = botNodes.get(row.name);
    if (!node) return false;
    node.dataset.broken = row.broken ? "true" : "false";
    node.dataset.inactive = row.active ? "false" : "true";
    node.querySelector("[data-bot-score]").textContent = fmt.num(row.lcb95 ?? row.score, 2);
    node.querySelector("[data-bot-rating]").textContent = `μ ${fmt.num(row.mu, 1)} ±${fmt.num(row.sigma, 1)}`;
    node.querySelector("[data-bot-games]").textContent = `${fmt.int(row.games)} rated games`;
    fill(node.querySelector("[data-bot-record]"), wldSpan(row.wins, row.losses, row.draws));
    const errors = node.querySelector("[data-bot-errors]");
    errors.textContent = `${fmt.int(row.err_total)} err`;
    errors.className = row.err_total ? "warn" : "";
    const broken = node.querySelector("[data-bot-broken]");
    broken.hidden = !row.broken;
    broken.title = row.broken_reason || "";
    node.querySelector("[data-bot-active]").checked = Boolean(row.active);
    return true;
  }

  function render() {
    const visible = visibleRows();
    view.setSub(`${rows.length} bot${rows.length === 1 ? "" : "s"}`);
    sparkSlots.clear();
    botNodes.clear();

    if (!rows.length) {
      fill(slot, 
        emptyState({
          title: "No bots yet",
          hint: [
            "Every directory below ",
            code((state.config && state.config.bots_dir) || "bots/"),
            " that holds a ",
            code("main.py"),
            " is a bot. Add one, then rescan.",
          ],
        })
      );
      return;
    }
    if (!visible.length) {
      fill(slot, emptyState({ title: "No bot matches this filter" }));
      return;
    }
    fill(grid, ...visible.map(botCard));
    fill(slot, grid);
    loadSparks(visible);
  }

  function patchRows() {
    const visible = visibleRows();
    view.setSub(`${rows.length} bot${rows.length === 1 ? "" : "s"}`);
    // Game events used to rebuild every card (and every async sparkline),
    // which made the page visibly flash while an arena was running. Reuse
    // each existing node and simply move it if its rank changed.
    if (!visible.length || botNodes.size !== visible.length || !visible.every((row) => botNodes.has(row.name))) {
      render();
      return;
    }
    for (const row of visible) {
      if (!patchCard(row)) return render();
      grid.appendChild(botNodes.get(row.name));
    }
  }

  async function loadSparks(visible) {
    await pool(visible.slice(0, 40), 4, async (row) => {
      if (!ctx.alive()) return;
      try {
        const detail = await botDetail(row.name);
        if (!ctx.alive()) return;
        const slotEl = sparkSlots.get(row.name);
        const history = (detail && detail.history) || [];
        if (!slotEl || history.length < 2) return;
        fill(slotEl, sparkline(history.map((point) => point.score)));
      } catch (err) {
        /* a missing spark is cosmetic */
      }
    });
  }

  render();
  ctx.on("state", () => {
    rows = (state.ladder || []).slice();
    patchRows();
  });
  ctx.on("ladder", () => {
    rows = (state.ladder || []).slice();
    patchRows();
  });

  const changedSparks = new Set();
  const refreshChangedSparks = throttled(() => {
    const names = new Set(changedSparks);
    changedSparks.clear();
    loadSparks(rows.filter((row) => names.has(row.name)));
  }, 700);
  ctx.add(() => refreshChangedSparks.cancel());
  ctx.on("game", (payload) => {
    const finished = payload && payload.game;
    if (!finished) return;
    changedSparks.add(finished.a);
    changedSparks.add(finished.b);
    refreshChangedSparks();
  });
});

/* -------------------------------------------------------------------------- */
/* 6. Bot detail                                                              */
/* -------------------------------------------------------------------------- */

const bot = mount("bot", (root, params, ctx) => {
  const name = String((params && (params.name || params.bot)) || "");
  const body = el("div", { class: "stack" }, skeletonRows(6));
  const view = viewRoot(
    {
      title: name || "Bot",
      sub: "",
      crumbs: crumbs(el("a", { href: "#/bots", text: "Bots" }), el("span", { text: name })),
      toolbar: [
        btn("Games", {
          class: "btn btn-sm btn-ghost",
          onclick: () => gotoGames({ bot: name }),
        }),
      ],
    },
    body
  );
  root.appendChild(view);

  function render(detail) {
    const info = detail.bot || {};
    const record = detail.record || { wins: 0, losses: 0, draws: 0, games: 0, winrate: null };
    view.setSub(
      `μ ${fmt.num(info.mu, 2)} · LCB95 ${fmt.num(info.lcb95 ?? info.score, 2)} · ${fmt.int(record.games)} games`
    );

    const history = (detail.history || []).map((point, index) => ({
      x: index + 1,
      y: point.mu,
      sigma: point.sigma,
      score: point.score,
      // Keep the server timestamp: source-version markers are placed at the
      // first rating point after the edit.  Dropping it made every marker fall
      // back to the newest point, where its dashed rule sat on the chart edge.
      ts: point.ts,
    }));
    const band = history.map((point) => ({
      x: point.x,
      lo: point.y - CI * point.sigma,
      hi: point.y + CI * point.sigma,
    }));
    const versions = (detail.versions || []).slice().sort((a, b) => Number(a.id) - Number(b.id));
    // The first hash is the bot's initial source, so the useful markers are
    // subsequent edits. A change takes effect before its next game; attach it
    // to that first post-change point. Changes at/before the first visible
    // rating are the graph's starting source, so they do not get a marker.
    const sourceMarkers = versions.slice(1).map((version) => {
      const changedAt = Date.parse(version.ts || "");
      const pointIndex = Number.isFinite(changedAt)
        ? history.findIndex((entry) => Date.parse(entry.ts || "") >= changedAt)
        : -1;
      const at = pointIndex > 0 ? history[pointIndex] : null;
      if (!at) return null;
      const hash = String(version.hash || "");
      return {
        x: at.x,
        label: hash.slice(0, 12),
        title: `Source changed to ${hash.slice(0, 12)}${version.ts ? ` on ${version.ts}` : ""}`,
      };
    }).filter(Boolean);

    const mapItems = (detail.maps || []).map((row) => ({
      label: row.map,
      value: row.winrate,
      n: row.games,
    }));

    const h2hRows = (detail.h2h || []).map((row) => {
      const heat = heatCell(row.winrate, row.games);
      const cell = el("td", { class: "num", text: fmt.pct(row.winrate) });
      cell.style.background = `color-mix(in srgb, ${heat.bg} ${Math.round(heat.opacity * 100)}%, transparent)`;
      cell.style.color = heat.fg;
      return el(
        "tr",
        {
          tabindex: "0",
          onclick: () => gotoGames({ bot: name, opponent: row.opponent }),
          onkeydown: (event) => {
            if (event.key === "Enter") gotoGames({ bot: name, opponent: row.opponent });
          },
        },
        el("td", null, botLink(row.opponent)),
        el("td", { class: "num", text: fmt.int(row.games) }),
        el("td", { class: "num" }, wldSpan(row.wins, row.losses, row.draws)),
        cell
      );
    });

    const note = el("textarea", {
      class: "textarea",
      rows: "2",
      placeholder: "a note to self about this bot…",
      "aria-label": `Note for ${name}`,
    });
    note.value = info.note || "";
    const saveNote = btn("Save note", {
      class: "btn btn-sm",
      onclick: async (event) => {
        const button = event.currentTarget;
        button.disabled = true;
        try {
          await api(`/api/bots/${encodeURIComponent(name)}/note`, {
            method: "POST",
            body: { note: note.value },
          });
          toast("Note saved", "ok");
        } catch (err) {
          toast(errorMessage(err), "error");
        } finally {
          button.disabled = false;
        }
      },
    });

    const activeToggle = el(
      "label",
      { class: "toggle" },
      el("input", {
        type: "checkbox",
        checked: info.active,
        onchange: async (event) => {
          const input = event.currentTarget;
          try {
            await api(`/api/bots/${encodeURIComponent(name)}/active`, {
              method: "POST",
              body: { active: input.checked },
            });
            toast(`${name} ${input.checked ? "enabled" : "disabled"}`, "ok");
          } catch (err) {
            input.checked = !input.checked;
            toast(errorMessage(err), "error");
          }
        },
      }),
      el("span", { class: "toggle-track" }, el("span", { class: "toggle-thumb" })),
      el("span", { class: "toggle-label", text: "active" })
    );


    fill(body, 
      el(
        "div",
        { class: "row wrap" },
        info.broken
          ? el("span", { class: "chip chip-broken", text: "broken", title: info.broken_reason })
          : null,
        el("span", { class: "chip", text: info.dir || "", title: info.dir || "" }),
        el("span", { class: "spacer" }),
        activeToggle
      ),
      info.broken && info.broken_reason ? el("p", { class: "form-error", text: info.broken_reason }) : null,
      el(
        "div",
        { class: "stats" },
        statTile("μ ±σ", `${fmt.num(info.mu, 2)} ±${fmt.num(info.sigma, 2)}`),
        statTile("LCB95", fmt.num(info.lcb95 ?? info.score, 2)),
        statTile("Games", fmt.int(record.games)),
        statTile("W-L-D", wldSpan(record.wins, record.losses, record.draws)),
        statTile("Win rate", fmt.pct(record.winrate)),
        statTile("Errors", `${fmt.int(info.err_total || 0)}`, `${fmt.int(info.err_games || 0)} games`)
      ),
      el(
        "div",
        { class: "grid grid-2" },
        chartCard(
          "Rating over games — 95% interval (μ ± 1.96σ); dashed line = source change",
          history.length
            ? lineChart(history, {
                band,
                markers: sourceMarkers,
                height: 190,
                label: `${name} rating history; dashed lines mark source changes`,
              })
            : emptyState({ title: "No rated games yet", hint: ["Run a match to start the history."] })
        ),
        chartCard("Win rate per map", barChart(mapItems, { rowHeight: 20 }))
      ),
      el(
        "div",
        { class: "grid grid-2" },
        card(
          { title: "Head to head", flush: true, foot: `${(detail.h2h || []).length} opponents` },
          h2hRows.length
            ? tableWrap(
                el(
                  "table",
                  { class: "table table-compact table-clickable" },
                  el(
                    "thead",
                    null,
                    el(
                      "tr",
                      null,
                      el("th", { text: "Opponent" }),
                      el("th", { class: "num", text: "Games" }),
                      el("th", { class: "num", text: "W-L-D" }),
                      el("th", { class: "num", text: "Win%" })
                    )
                  ),
                  el("tbody", null, ...h2hRows)
                )
              )
            : el("div", { class: "card-body" }, el("p", { class: "mute", text: "No decided games yet." }))
        ),
        card(
          { title: "Source versions" },
          (detail.versions || []).length
            ? el(
                "div",
                { class: "timeline" },
                ...(detail.versions || []).map((version) =>
                  el(
                    "div",
                    { class: "timeline-item", "data-current": version.hash === info.src_hash ? "true" : null },
                    el("span", { class: "timeline-ts", text: fmt.time(version.ts) || version.ts }),
                    el(
                      "span",
                      { class: "timeline-body num", text: String(version.hash || "").slice(0, 12) },
                    )
                  )
                )
              )
            : el("p", { class: "mute", text: "No source changes recorded yet." })
        )
      ),
      card(
        { title: "Recent crashes", actions: [btn("all failures →", { class: "btn btn-xs btn-ghost", onclick: () => gotoGames({ bot: name, failed: true }) })] },
        (detail.crashes || []).length
          ? el(
              "div",
              { class: "stack" },
              ...(detail.crashes || []).map((crash) =>
                el(
                  "div",
                  { class: "panel" },
                  el(
                    "div",
                    { class: "row wrap" },
                    statusBadge(crash),
                    el("a", { href: gameHref(crash.id), text: `#${crash.id}` }),
                    matchup(crash),
                    mapChip(crash.map),
                    el("span", { class: "spacer" }),
                    el("span", { class: "small mute", text: fmt.ago(crash.ts) })
                  ),
                  crash.error
                    ? el("pre", { class: "logview-text", style: "margin-top:6px", text: crash.error })
                    : null
                )
              )
            )
          : el("p", { class: "mute", text: "No crashes recorded." })
      ),
      card({ title: "Note" }, el("div", { class: "stack" }, note, el("div", { class: "row" }, el("span", { class: "spacer" }), saveNote)))
    );
  }

  async function load() {
    const cached = state.bots && state.bots[name];
    if (cached) {
      try {
        render(cached);
      } catch (err) {
        console.error(err);
      }
    }
    try {
      const detail = await botDetail(name);
      if (!ctx.alive()) return;
      render(detail);
    } catch (err) {
      if (!ctx.alive()) return;
      fill(body, 
        emptyState({
          title: `No bot named ${name}`,
          hint: [errorMessage(err)],
          actions: [btn("Back to bots", { class: "btn btn-sm", onclick: () => (location.hash = "#/bots") })],
        })
      );
    }
  }

  load();

  const reload = throttled(() => {
    if (ctx.alive()) load();
  }, 4000);
  ctx.add(() => reload.cancel());
  ctx.on("game", (payload) => {
    const finished = payload && payload.game;
    if (finished && (finished.a === name || finished.b === name)) reload();
  });
});

/* -------------------------------------------------------------------------- */
/* 7. Maps                                                                    */
/* -------------------------------------------------------------------------- */

const maps = mount("maps", (root, params, ctx) => {
  let rows = (state.maps || []).slice();
  const slot = el("div", { class: "stack" }, rows.length ? null : skeletonRows(4));
  const openEditor = btn("Open fcode editor", {
    class: "btn btn-sm btn-ghost",
    title: "Open the official fcode map editor in a new tab",
    onclick: () => window.open("/map-editor/", "_blank", "noopener"),
  });
  const view = viewRoot({ title: "Maps", sub: "", toolbar: [openEditor] }, slot);
  root.appendChild(view);

  const turnSlots = new Map();

  function mapCard(map) {
    const analysis = map.analysis || {};
    const pct = (value) => `${Math.round(Number(value || 0) * 100)}%`;
    const turns = el("span", null, el("span", { class: "k", text: "turns" }), " –");
    const edit = btn("Edit", {
      class: "btn btn-sm btn-ghost",
      title: `Open ${map.name} in the fcode map editor`,
      onclick: (event) => {
        event.stopPropagation();
        window.open(`/map-editor/?map=${encodeURIComponent(map.name)}`, "_blank", "noopener");
      },
      onkeydown: (event) => event.stopPropagation(),
    });
    turnSlots.set(map.name, turns);
    return el(
      "div",
      {
        class: "card card-link",
        tabindex: "0",
        role: "link",
        title: `Show games played on ${map.name}`,
        onclick: () => gotoGames({ map: map.name }),
        onkeydown: (event) => {
          if (event.key === "Enter") gotoGames({ map: map.name });
        },
      },
      mapThumb(map, { size: 260 }),
      el(
        "div",
        { class: "card-body" },
        el("div", { class: "map-name", text: map.name }),
        el("div", {
          class: "map-dims",
          text: map.width
            ? `${map.width}×${map.height} · ${map.walls} walls · ${map.ore} ore`
            : "unreadable map file",
        }),
          el(
            "div",
            { class: "map-stats" },
            el("span", null, el("span", { class: "k", text: "games" }), ` ${fmt.int(map.games || 0)}`),
            turns
          ),
          el(
            "div",
            { class: "map-analysis", title: "Terrain analysis from the decoded .map26 grid" },
            el("span", null, el("span", { class: "k", text: "ore" }), ` ${pct(analysis.ore_pct)}`),
            el("span", null, el("span", { class: "k", text: "walls" }), ` ${pct(analysis.wall_pct)}`),
            el("span", null, el("span", { class: "k", text: "spawns" }), ` ${fmt.int(analysis.spawn_count || 0)}`),
            el("span", null, el("span", { class: "k", text: "regions" }), ` ${fmt.int(analysis.components || 0)}`),
            el("span", { class: "map-symmetry", text: String(analysis.symmetry || "unreadable") })
          ),
          el("div", { class: "row", style: { marginTop: "8px" } }, edit)
        )
    );
  }

  function render() {
    const officialRows = rows.filter((map) => map.source !== "extra");
    const extraRows = rows.filter((map) => map.source === "extra");
    view.setSub(
      `${officialRows.length} official · ${extraRows.length} extra`,
    );
    turnSlots.clear();
    if (!rows.length) {
      fill(slot, 
        emptyState({
          title: "No maps found",
          hint: [
            "oarena plays ",
            code("*.map26"),
            " files from ",
            code((state.config && state.config.maps_dir) || "maps/"),
            " and generated/local maps from ",
            code((state.config && state.config.extra_maps_dir) || "more_maps/"),
            ". Copy the stock maps out of your fcode project to get started.",
          ],
        })
      );
      return;
    }
    const mapSection = (title, directory, sectionRows) => {
      if (!sectionRows.length) return null;
      return el(
        "section",
        { class: "map-section" },
        el(
          "div",
          { class: "map-section-head" },
          el("h2", { class: "section-title", text: title }),
          el("span", { class: "map-section-path", text: directory }),
        ),
        el("div", { class: "map-grid" }, ...sectionRows.map(mapCard)),
      );
    };
    fill(
      slot,
      mapSection(
        "Official maps",
        (state.config && state.config.maps_dir) || "maps/",
        officialRows,
      ),
      mapSection(
        "Extra maps",
        (state.config && state.config.extra_maps_dir) || "more_maps/",
        extraRows,
      ),
    );
  }

  /** Mean turn count per map, sampled from the most recent completed games. */
  async function loadTurns() {
    try {
      const page = await api("/api/games?limit=500&status=ok");
      if (!ctx.alive()) return;
      const totals = new Map();
      for (const finished of page.games || []) {
        if (!finished.turns) continue;
        const entry = totals.get(finished.map) || { sum: 0, n: 0 };
        entry.sum += finished.turns;
        entry.n += 1;
        totals.set(finished.map, entry);
      }
      for (const [name, node] of turnSlots) {
        const entry = totals.get(name);
        fill(node, 
          el("span", { class: "k", text: "turns" }),
          ` ${entry ? fmt.int(Math.round(entry.sum / entry.n)) : "–"}`
        );
        if (entry) node.title = `mean over the last ${entry.n} clean games`;
      }
    } catch (err) {
      /* the cards are already useful without a mean */
    }
  }

  async function load() {
    try {
      const fresh = await api("/api/maps");
      if (!ctx.alive()) return;
      rows = Array.isArray(fresh) ? fresh : [];
      state.maps = rows;
      render();
      loadTurns();
    } catch (err) {
      if (!ctx.alive()) return;
      fill(slot, emptyState({ title: "Could not load maps", hint: [errorMessage(err)] }));
    }
  }

  if (rows.length) {
    render();
    loadTurns();
  }
  load();

  const onTheme = () => {
    if (!ctx.alive()) return;
    render();
    loadTurns();
  };
  document.addEventListener("themechange", onTheme);
  ctx.add(() => document.removeEventListener("themechange", onTheme));
});

/* -------------------------------------------------------------------------- */

/* 8. FCode platform matches                                                   */
/* -------------------------------------------------------------------------- */

const PLATFORM_RECENT_LIMIT = 20;
const PLATFORM_CACHE_TTL = 15_000;
const PLATFORM_LADDER_TTL = 60_000;
const PLATFORM_RELATIVE_TIME_REFRESH_MS = 15_000;
const PLATFORM_VERSION_SYNC_POLL_MS = 1_000;
const PLATFORM_VERSION_SYNC_MAX_POLLS = 30;
const PLATFORM_VERSION_SYNC_SLOW_POLL_MS = 5_000;
const PLATFORM_VERSION_SYNC_ERROR_RETRY_MS = 10_000;
const platformResponseCache = new Map();
const platformRecentUi = { mode: "all", teamId: "", teamName: "", outcome: "all" };

function cachedPlatformApi(key, path, ttl) {
  const now = Date.now();
  const cached = platformResponseCache.get(key);
  if (cached?.data && now - cached.at <= ttl) return Promise.resolve(cached.data);
  if (cached?.promise) return cached.promise;
  let promise;
  promise = api(path)
    .then((data) => {
      if (platformResponseCache.get(key)?.promise === promise) {
        platformResponseCache.set(key, { data, at: Date.now(), promise: null });
      }
      return data;
    })
    .catch((err) => {
      if (platformResponseCache.get(key)?.promise === promise) {
        platformResponseCache.delete(key);
      }
      throw err;
    });
  platformResponseCache.set(key, {
    data: cached?.data || null,
    at: cached?.at || 0,
    promise,
  });
  return promise;
}

function platformMatchDetail(matchId, { refresh = false } = {}) {
  const id = String(matchId).toLowerCase();
  const key = `match:${id}`;
  if (refresh) platformResponseCache.delete(key);
  return cachedPlatformApi(
    key,
    `/api/platform/matches/${encodeURIComponent(id)}`,
    PLATFORM_CACHE_TTL,
  );
}

function platformMatchTeams(match) {
  return {
    a: match?.team_a || { id: "", name: "Team A" },
    b: match?.team_b || { id: "", name: "Team B" },
  };
}

function platformMatchTimestamp(match) {
  return match?.completed_at || match?.created_at || null;
}

function platformRelativeTime(timestamp) {
  const value = typeof timestamp === "string" ? timestamp : "";
  return el("time", {
    "data-platform-relative-time": "",
    datetime: value,
    title: value,
    text: fmt.ago(value),
  });
}

function platformBotVersionSnapshot(row) {
  const version = Number.isSafeInteger(row?.bot_version) ? row.bot_version : null;
  const firstSeenAt = typeof row?.version_first_seen_at === "string"
    && Number.isFinite(Date.parse(row.version_first_seen_at))
    ? row.version_first_seen_at
    : "";
  if (version === null || !firstSeenAt) return null;
  const history = (Array.isArray(row?.version_history) ? row.version_history : [])
    .map((entry) => {
      const entryVersion = Number.isSafeInteger(entry?.version) ? entry.version : null;
      const entryFirstSeenAt = typeof entry?.first_seen_at === "string"
        && Number.isFinite(Date.parse(entry.first_seen_at))
        ? entry.first_seen_at
        : "";
      if (entryVersion === null || !entryFirstSeenAt) return null;
      return {
        version: entryVersion,
        firstSeenAt: entryFirstSeenAt,
        transitionKnown: entry?.transition_known === true,
      };
    })
    .filter(Boolean)
    .slice(0, 3);
  return {
    version,
    firstSeenAt,
    transitionKnown: row?.version_transition_known === true,
    history,
  };
}

function platformBotVersionLabel(snapshot) {
  if (!snapshot) return "–";
  const age = fmt.ago(snapshot.firstSeenAt);
  return snapshot.transitionKnown
    ? `v${snapshot.version} · ≈${age}`
    : `v${snapshot.version} · seen ${age}`;
}

function platformBotVersionTooltip(snapshot) {
  if (!snapshot) return "Bot version history is not available.";
  const lines = [
    `v${snapshot.version} became the observed active version by ${fmt.ago(snapshot.firstSeenAt)}.`,
    "This can be a new upload or an older version being reactivated; the upload may be earlier.",
  ];
  if (!snapshot.transitionKnown) {
    lines.push("This is a baseline observation; its version transition was not observed.");
  }
  if (snapshot.history.length) {
    lines.push("", "Recent active-version observations:");
    for (const entry of snapshot.history) {
      const qualifier = entry.transitionKnown ? "version switch observed" : "baseline; switch unknown";
      lines.push(`v${entry.version} — ${fmt.ago(entry.firstSeenAt)} (${qualifier})`);
    }
  }
  return lines.join("\n");
}

function refreshPlatformBotVersionTime(node) {
  let snapshot = null;
  try {
    snapshot = JSON.parse(node.dataset.botVersionSnapshot || "null");
  } catch {
    // A malformed data attribute should degrade to the unknown marker.
  }
  node.textContent = platformBotVersionLabel(snapshot);
  node.title = platformBotVersionTooltip(snapshot);
}

function platformBotVersionTime(row) {
  const snapshot = platformBotVersionSnapshot(row);
  if (!snapshot) {
    return el("span", {
      class: "fcode-bot-version mute",
      text: "–",
      title: "Bot version history is not available.",
    });
  }
  const node = el("time", {
    class: "fcode-bot-version",
    "data-platform-version-time": "",
    datetime: snapshot.firstSeenAt,
    dataset: { botVersionSnapshot: JSON.stringify(snapshot) },
  });
  refreshPlatformBotVersionTime(node);
  return node;
}

function platformMatchScore(match) {
  const left = Number.isFinite(match?.score_a) ? String(match.score_a) : "–";
  const right = Number.isFinite(match?.score_b) ? String(match.score_b) : "–";
  return `${left}–${right}`;
}

function platformMatchLabel(match) {
  if (match?.status && match.status !== "complete") return String(match.status).replace(/_/g, " ");
  return match?.rated ? "ladder" : (match?.type || "unrated");
}

function mountPlatformView(root, params, ctx, { officialTests = false } = {}) {
  const squareViewer = globalThis.oarena?.squareViewer;
  const theme = () => document.documentElement.dataset.theme || state.theme || "dark";
  const routeName = officialTests ? "test-runs" : "fcode";
  const routeBase = officialTests ? "#/test-runs" : "#/fcode";
  platformRecentUi.mode = officialTests
    ? "tests"
    : (platformRecentUi.mode === "tests" ? "all" : platformRecentUi.mode);
  if (officialTests) platformRecentUi.outcome = "all";

  let session = null;
  let recentRows = [];
  let recentCursor = null;
  let recentRequest = 0;
  let detailRequest = 0;
  let activeDetail = null;
  let activeGame = null;
  let userSelected = false;
  let autoSelectRecent = false;
  let matchPollTimer = null;
  let recentPollTimer = null;
  let versionSyncTimer = null;
  let versionSyncPolls = 0;
  let versionHistoryData = null;
  let selectedVersionTeamId = "";
  let selectedVersionTeamName = "";
  let versionTeamSelectionExplicit = false;
  let selectedVersionRequest = 0;
  let selectedVersionLoading = false;
  let selectedVersionError = null;
  let ladderRankByTeamId = new Map();
  // Expansion survives the timeline's periodic re-render, and each run's games
  // are fetched once. Keys carry the team so switching teams cannot show one
  // team's games under another's run.
  const expandedRuns = new Set();
  const runGamesCache = new Map();
  const runGamesPending = new Set();
  let scrolledPlayingKey = "";
  // What each team actually played in the open match, read from oarena's own
  // records because the platform's match detail does not carry versions.
  let matchRuns = null;
  let matchRunsFor = "";

  const officialLink = el("a", {
    class: "btn btn-sm btn-ghost",
    target: "_blank",
    rel: "noopener noreferrer",
    text: "Open official",
    hidden: true,
  });
  const replayLink = el("a", {
    class: "btn btn-sm btn-ghost",
    text: "Replay file",
    download: true,
    hidden: true,
  });
  const fullscreenButton = btn("Fullscreen", {
    class: "btn btn-sm btn-ghost",
    disabled: true,
    onclick: async () => {
      try {
        await squareViewer?.requestFullscreen();
      } catch (err) {
        toast(`Could not enter fullscreen: ${errorMessage(err)}`, "error");
      }
    },
  });

  const matchInput = el("input", {
    class: "input",
    type: "text",
    autocomplete: "off",
    spellcheck: "false",
    placeholder: "Match UUID or game.code.florent.vc visualiser URL",
    "aria-label": "Match ID or official FCode visualiser URL",
  });
  const gameInput = el("input", {
    class: "input num",
    type: "number",
    min: "1",
    max: "5",
    step: "1",
    value: "1",
    inputmode: "numeric",
    "aria-label": "Game number",
  });
  const formError = el("div", { class: "form-error", role: "alert", hidden: true });
  const loadButton = el("button", { class: "btn btn-primary", type: "submit", text: "Load" });
  const matchForm = el(
    "form",
    { class: "fcode-match-form" },
    el(
      "label",
      { class: "field fcode-match-id" },
      el("span", { class: "field-label", text: "Open a match by ID or visualiser URL" }),
      matchInput,
    ),
    el(
      "label",
      { class: "field field-narrow fcode-game-number" },
      el("span", { class: "field-label", text: "Game" }),
      gameInput,
    ),
    loadButton,
    formError,
  );

  const sessionSlot = el("div", { class: "fcode-session", "aria-live": "polite" });
  const vizSlot = el("div", { class: "viz-frame fcode-viz" });
  fill(
    vizSlot,
    emptyState({
      title: officialTests ? "Looking for a recent test…" : "Looking for a recent match…",
      hint: ["Or paste a match ID below."],
    }),
  );
  const matchBar = el("section", {
    class: "fcode-match-bar",
    "aria-label": "Selected FCode match",
    hidden: true,
  });
  const recentSlot = el("div", { class: "fcode-panel-body" }, skeletonRows(7));
  const recentFilterSlot = el("div", { class: "fcode-recent-filters" });
  const ladderSlot = el("div", { class: "fcode-panel-body" }, skeletonRows(7));
  const versionHistorySlot = el("div", { class: "fcode-version-history" }, skeletonRows(4));
  const versionTeamSelect = el("select", {
    class: "select select-compact fcode-version-team-select",
    "aria-label": "Team bot-version history",
    disabled: true,
    onchange: (event) => {
      const teamId = event.currentTarget.value;
      const team = (versionHistoryData?.teams || []).find((candidate) => candidate.team_id === teamId);
      selectVersionHistoryTeam(
        { id: teamId, name: team?.team_name || teamId },
        { explicit: true },
      );
    },
  });
  // Jumping between the two teams of the open match is the common move; the
  // full dropdown stays for every other team on the ladder.
  const versionQuickSwitch = el("div", {
    class: "seg fcode-version-quick",
    role: "group",
    "aria-label": "Teams in the open match",
    hidden: true,
  });
  const versionHistoryActions = el(
    "div",
    { class: "fcode-version-actions" },
    versionQuickSwitch,
    versionTeamSelect,
  );
  const versionHistoryFoot = el(
    "span",
    {
      text: "Built from the ladder and unrated matches oarena has seen, so each time is a first sighting rather than an upload. A version that comes back later appears again. Click a version to list its games.",
    },
  );

  const view = viewRoot(
    {
      title: officialTests ? "Test runs" : "FCode",
      sub: officialTests ? "your team's official test games" : "matches on the official server",
      toolbar: [officialLink, replayLink, fullscreenButton],
    },
    vizSlot,
    matchBar,
    el("div", { class: "panel fcode-match-loader" }, matchForm, sessionSlot),
    el(
      "div",
      { class: `fcode-browse-grid${officialTests ? " is-single" : ""}` },
      officialTests
        ? card(
            { title: "Official test runs", actions: recentFilterSlot, flush: true },
            recentSlot,
          )
        : el(
            "div",
            { class: "fcode-side-stack" },
            card(
              { title: "Recent matches", actions: recentFilterSlot, flush: true },
              recentSlot,
            ),
            card(
              { title: "Bot versions", actions: versionHistoryActions, foot: versionHistoryFoot },
              versionHistorySlot,
            ),
          ),
      officialTests ? null : card({ title: "FCode ladder", flush: true }, ladderSlot),
    ),
  );
  root.appendChild(view);

  function showFormError(message) {
    formError.textContent = message || "";
    formError.hidden = !message;
  }

  function platformErrorState(title, err, actions = []) {
    const login = Number(err?.status) === 401
      ? ["Run ", code("fcode login"), " on this machine, then retry."]
      : [errorMessage(err)];
    return emptyState({ title, hint: login, actions });
  }

  function updateRouteAndStorage(matchId, game) {
    const hash = platformViewHash(matchId, game, routeBase);
    history.replaceState(null, "", hash);
    const nextParams = { matchId, game: String(game) };
    if (current.name === routeName) current.params = nextParams;
    if (state.route?.view === routeName) {
      state.route = { ...state.route, params: nextParams, hash };
    }
    if (!officialTests) savePlatformSelection(globalThis.localStorage, { matchId, game });
  }

  function officialUrl(matchId, game) {
    const query = new URLSearchParams({ matchId, game: String(game) });
    return `https://game.code.florent.vc/visualiser?${query.toString()}`;
  }

  function pickTeam(team) {
    if (!team?.id) return;
    platformRecentUi.teamId = team.id;
    platformRecentUi.teamName = team.name || team.id;
    selectVersionHistoryTeam(team, { explicit: true });
    if (platformRecentUi.mode === "mine") platformRecentUi.mode = "all";
    void loadRecent({ reset: true });
  }

  function teamButton(team, match) {
    const outcome = platformTeamOutcome(match, team?.id);
    const won = outcome === "win";
    const lost = outcome === "loss";
    const className = `fcode-team${won ? " is-winner" : lost ? " is-loser" : ""}`;
    if (!team?.id) {
      return el("span", {
        class: className,
        text: team?.name || "unknown bot",
        title: team?.name || "unknown bot",
      });
    }
    return el(
      "button",
      {
        class: className,
        type: "button",
        title: `Show matches for ${team?.name || "this team"}`,
        onclick: (event) => {
          event.stopPropagation();
          pickTeam(team);
        },
      },
      team?.name || "unknown team",
    );
  }

  function renderSession(data, err = null) {
    session = data || null;
    if (err) {
      fill(
        sessionSlot,
        el("span", { class: "fcode-auth fcode-auth-warn" }, "FCode session unavailable: ", errorMessage(err)),
      );
    } else if (!data?.authenticated) {
      fill(
        sessionSlot,
        el(
          "span",
          { class: "fcode-auth fcode-auth-warn" },
          "Not signed in. Run ",
          code("fcode login"),
          " to see your own matches and replays. The public ladder works either way.",
        ),
      );
    } else {
      fill(
        sessionSlot,
        el("span", { class: "fcode-auth" }, "Signed in as ", el("strong", { text: data.team?.name || "your FCode team" })),
      );
    }
    if (!officialTests && !versionTeamSelectionExplicit && versionHistoryData) {
      if (!ensureDefaultVersionTeam()) renderVersionHistory();
    }
    if (recentRows.length) renderRecent();
    else renderRecentFilters();
  }

  function recentOutcomeTeam() {
    if (officialTests || platformRecentUi.mode === "tests") return null;
    if (platformRecentUi.mode === "mine") {
      const team = session?.authenticated ? session.team : null;
      return team?.id ? { id: team.id, name: team.name || team.id } : null;
    }
    return platformRecentUi.teamId
      ? {
          id: platformRecentUi.teamId,
          name: platformRecentUi.teamName || platformRecentUi.teamId,
        }
      : null;
  }

  function visibleRecentRows() {
    const team = recentOutcomeTeam();
    const outcome = platformRecentUi.outcome;
    if (!team || (outcome !== "win" && outcome !== "loss")) return recentRows;
    return recentRows.filter((match) => platformTeamOutcome(match, team.id) === outcome);
  }

  function renderRecentFilters() {
    const options = [
      ["all", "All"],
      ["ladder", "Ladder"],
      ["unrated", "Unrated"],
      ["mine", "Mine"],
      ["tests", "Tests"],
    ];
    const filterButtons = options.map(([value, label]) =>
      el("button", {
        class: "seg-btn",
        type: "button",
        text: label,
        "aria-pressed": platformRecentUi.mode === value ? "true" : "false",
        disabled: value === "mine" && !(session?.authenticated && session?.team?.id),
        onclick: () => {
          platformRecentUi.mode = value;
          if (value === "mine" || value === "tests") {
            platformRecentUi.teamId = "";
            platformRecentUi.teamName = "";
          }
          if (value === "tests" || (value !== "mine" && !platformRecentUi.teamId)) {
            platformRecentUi.outcome = "all";
          }
          if (value === "tests" && !officialTests) {
            location.hash = "#/test-runs";
            return;
          }
          if (value !== "tests" && officialTests) {
            location.hash = "#/fcode";
            return;
          }
          void loadRecent({ reset: true });
        },
      }),
    );
    const teamChip = platformRecentUi.teamId && platformRecentUi.mode !== "tests"
      ? el(
          "span",
          { class: "chip chip-accent", title: platformRecentUi.teamId },
          platformRecentUi.teamName || "team",
          el("button", {
            class: "fcode-chip-clear",
            type: "button",
            text: "×",
            "aria-label": "Clear team filter",
            onclick: () => {
              platformRecentUi.teamId = "";
              platformRecentUi.teamName = "";
              platformRecentUi.outcome = "all";
              void loadRecent({ reset: true });
            },
          }),
        )
      : null;
    const outcomeTeam = recentOutcomeTeam();
    const outcomeFilter = outcomeTeam
      ? el(
          "span",
          {
            class: "seg",
            role: "group",
            "aria-label": `Result for ${outcomeTeam.name}`,
          },
          [
            ["all", "All results"],
            ["win", "Wins"],
            ["loss", "Losses"],
          ].map(([value, label]) =>
            el("button", {
              class: "seg-btn",
              type: "button",
              text: label,
              "aria-pressed": platformRecentUi.outcome === value ? "true" : "false",
              onclick: () => {
                platformRecentUi.outcome = value;
                renderRecent();
              },
            }),
          ),
        )
      : null;
    const refresh = btn("Refresh", {
      class: "btn btn-xs btn-ghost",
      title: officialTests ? "Refresh official test runs" : "Refresh recent FCode matches",
      onclick: async (event) => {
        const button = event.currentTarget;
        button.disabled = true;
        refreshRecentTimestamps();
        try {
          await loadRecent({ reset: true, quiet: true, force: true });
        } finally {
          if (ctx.alive() && button.isConnected) button.disabled = false;
        }
      },
    });
    fill(
      recentFilterSlot,
      el("span", { class: "seg" }, filterButtons),
      teamChip,
      outcomeFilter,
      refresh,
    );
  }

  function recentPath(cursor = null) {
    if (platformRecentUi.mode === "tests") {
      return `/api/platform/test-runs?limit=${PLATFORM_RECENT_LIMIT}`;
    }
    const query = new URLSearchParams({ limit: String(PLATFORM_RECENT_LIMIT) });
    if (platformRecentUi.mode === "ladder" || platformRecentUi.mode === "unrated") {
      query.set("type", platformRecentUi.mode);
    } else if (platformRecentUi.mode === "mine") {
      query.set("mine", "true");
    }
    if (platformRecentUi.teamId && platformRecentUi.mode !== "mine") {
      query.set("team_id", platformRecentUi.teamId);
    }
    if (cursor) query.set("cursor", cursor);
    return `/api/platform/matches?${query.toString()}`;
  }

  function renderRecent() {
    renderRecentFilters();
    const showingTests = platformRecentUi.mode === "tests";
    if (!recentRows.length) {
      fill(
        recentSlot,
        emptyState({
          title: showingTests ? "No official test runs yet" : "No matching FCode matches",
          hint: showingTests
            ? ["Create one with ", code("fcode match test BOT_A BOT_B"), "."]
            : platformRecentUi.mode === "mine"
              ? ["Your team has no matches in this window."]
              : ["Try another recent-match filter."],
        }),
      );
      return;
    }
    const visibleRows = visibleRecentRows();
    const tbody = el("tbody");
    for (const match of visibleRows) {
      const teams = platformMatchTeams(match);
      const openLabel = `Open ${teams.a.name || "Team A"} versus ${teams.b.name || "Team B"}`;
      const openMatch = () => {
        userSelected = true;
        void selectMatch({ matchId: match.id, game: 1 });
      };
      if (showingTests) {
        const scoreA = Number.isFinite(match.score_a) ? match.score_a : null;
        const scoreB = Number.isFinite(match.score_b) ? match.score_b : null;
        const resultClass = (side) => {
          if (scoreA === null || scoreB === null || scoreA === scoreB) return "";
          return (side === "a" ? scoreA > scoreB : scoreB > scoreA) ? " is-winner" : " is-loser";
        };
        const status = String(match.status || "unknown").replace(/_/g, " ");
        const stage = String(match.stage || "").replace(/_/g, " ");
        tbody.appendChild(
          el(
            "tr",
            {
              class: "fcode-match-row",
              "data-match-id": match.id,
              tabindex: "0",
              onclick: openMatch,
              onkeydown: (event) => {
                if (event.key === "Enter") openMatch();
              },
            },
            el("td", { class: "col-time" }, platformRelativeTime(platformMatchTimestamp(match))),
            el(
              "td",
              null,
              el(
                "span",
                { class: "fcode-matchup" },
                el("span", { class: `fcode-team${resultClass("a")}`, text: teams.a.name || "Bot A" }),
                el("span", { class: "vs", text: "vs" }),
                el("span", { class: `fcode-team${resultClass("b")}`, text: teams.b.name || "Bot B" }),
              ),
            ),
            el("td", { class: "num strong", text: platformMatchScore(match) }),
            // Status, the stage it reached and why it stopped are one story.
            el(
              "td",
              { class: "fcode-test-state" },
              el("span", { class: "badge", text: status }),
              stage ? el("span", { class: "small mute", text: stage }) : null,
              match.error
                ? el("span", {
                    class: `fcode-test-error ${match.error ? "err" : "mute"}`,
                    text: match.error,
                    title: match.error,
                  })
                : null,
            ),
            el("td", { text: match.requested_by_name || "–" }),
            el(
              "td",
              { class: "col-action" },
              btn("View", {
                class: "btn btn-xs btn-ghost",
                "aria-label": openLabel,
                onclick: (event) => {
                  event.stopPropagation();
                  openMatch();
                },
              }),
            ),
          ),
        );
        continue;
      }
      const row = el(
        "tr",
        { class: "fcode-match-row", "data-match-id": match.id },
        el("td", { class: "col-time" }, platformRelativeTime(platformMatchTimestamp(match))),
        el(
          "td",
          null,
          el("span", { class: "fcode-matchup" }, teamButton(teams.a, match), el("span", { class: "vs", text: "vs" }), teamButton(teams.b, match)),
        ),
        el("td", { class: "num strong", text: platformMatchScore(match) }),
        el("td", null, el("span", { class: "badge", text: platformMatchLabel(match) })),
        el(
          "td",
          { class: "col-action" },
          btn("View", {
            class: "btn btn-xs btn-ghost",
            "aria-label": openLabel,
            onclick: () => {
              userSelected = true;
              void selectMatch({ matchId: match.id, game: 1 });
            },
          }),
        ),
      );
      tbody.appendChild(row);
    }
    if (!visibleRows.length) {
      const outcome = platformRecentUi.outcome === "win" ? "wins" : "losses";
      tbody.appendChild(
        el(
          "tr",
          null,
          el("td", {
            class: "center mute",
            colspan: showingTests ? "6" : "5",
            text: `No ${outcome} in ${fmt.int(recentRows.length)} loaded matches${
              recentCursor ? "; load more to search older matches" : ""
            }.`,
          }),
        ),
      );
    }
    const table = el(
      "table",
      { class: `table table-compact fcode-recent-table${showingTests ? " table-clickable" : ""}` },
      el(
        "thead",
        null,
        showingTests
          ? el(
              "tr",
              null,
              el("th", { text: "When" }),
              el("th", { text: "Bots" }),
              el("th", { class: "num", text: "Score" }),
              el("th", { text: "Status" }),
              el("th", { text: "Started by" }),
              el("th", { text: "" }),
            )
          : el("tr", null, el("th", { text: "When" }), el("th", { text: "Teams" }), el("th", { class: "num", text: "Score" }), el("th", { text: "Type" }), el("th", { text: "" })),
      ),
      tbody,
    );
    const more = recentCursor
      ? el(
          "div",
          { class: "load-more" },
          btn("Load more", {
            onclick: (event) => {
              event.currentTarget.disabled = true;
              void loadRecent({ reset: false });
            },
          }),
        )
      : null;
    fill(recentSlot, tableWrap(table), more);
  }

  function refreshRecentTimestamps() {
    for (const node of recentSlot.querySelectorAll("time[data-platform-relative-time]")) {
      node.textContent = fmt.ago(node.getAttribute("datetime") || "");
    }
    for (const node of versionHistorySlot.querySelectorAll("time[data-platform-relative-time]")) {
      node.textContent = fmt.ago(node.getAttribute("datetime") || "");
    }
    for (const node of ladderSlot.querySelectorAll("time[data-platform-version-time]")) {
      refreshPlatformBotVersionTime(node);
    }
  }

  function maybeSelectRecentMatch() {
    if (!autoSelectRecent || userSelected || activeDetail || !ctx.alive()) return;
    const candidates = visibleRecentRows();
    const first = platformRecentUi.mode === "tests"
      ? candidates.find((match) => match?.id)
      : candidates.find((match) => match?.status === "complete" && match?.id);
    if (first) {
      autoSelectRecent = false;
      void selectMatch({ matchId: first.id, game: 1 });
      return;
    }
    squareViewer?.hide(vizSlot);
    fill(
      vizSlot,
      emptyState({
        title: "Nothing to play yet",
        hint: [
          session?.authenticated === false
            ? "Run fcode login, or paste a match ID below."
            : "Paste a match ID below, or wait for a match to finish.",
        ],
      }),
    );
  }

  function scheduleRecentPoll() {
    if (recentPollTimer !== null) {
      clearTimeout(recentPollTimer);
      recentPollTimer = null;
    }
    if (
      !officialTests ||
      !recentRows.some((match) => ["queued", "running"].includes(String(match?.status || "").toLowerCase()))
    ) return;
    recentPollTimer = setTimeout(() => {
      recentPollTimer = null;
      if (ctx.alive()) void loadRecent({ reset: true, quiet: true });
    }, 5_000);
  }

  async function loadRecent({ reset, quiet = false, force = false }) {
    const request = ++recentRequest;
    const cursor = reset ? null : recentCursor;
    if (recentPollTimer !== null) {
      clearTimeout(recentPollTimer);
      recentPollTimer = null;
    }
    if (reset) {
      recentCursor = null;
      if (!quiet) {
        recentRows = [];
        renderRecentFilters();
        fill(recentSlot, skeletonRows(7));
      }
    }
    const path = recentPath(cursor);
    const cacheKey = `recent:${path}`;
    if (force && !officialTests && !cursor) platformResponseCache.delete(cacheKey);
    try {
      const response = officialTests || cursor
        ? await api(path)
        : await cachedPlatformApi(cacheKey, path, PLATFORM_CACHE_TTL);
      if (!ctx.alive() || request !== recentRequest) return null;
      const rows = officialTests
        ? (Array.isArray(response?.test_runs) ? response.test_runs : [])
        : (Array.isArray(response?.matches) ? response.matches : []);
      const known = new Set(recentRows.map((match) => match.id));
      recentRows = reset ? rows : recentRows.concat(rows.filter((match) => !known.has(match.id)));
      recentCursor = !officialTests && typeof response?.next_cursor === "string" && response.next_cursor
        ? response.next_cursor
        : null;
      renderRecent();
      if (reset) maybeSelectRecentMatch();
      scheduleRecentPoll();
      return response;
    } catch (err) {
      if (!ctx.alive() || request !== recentRequest) return null;
      if (quiet && recentRows.length) {
        if (force) {
          toast(
            `Could not refresh ${officialTests ? "official test runs" : "recent matches"}: ${errorMessage(err)}`,
            "error",
          );
        }
        scheduleRecentPoll();
        return null;
      }
      if (!reset && recentRows.length) {
        renderRecent();
        toast(`Could not load more FCode matches: ${errorMessage(err)}`, "error");
        return null;
      }
      fill(
        recentSlot,
        platformErrorState(
          Number(err?.status) === 401
            ? `Sign in to list ${officialTests ? "official tests" : "FCode matches"}`
            : `Could not load ${officialTests ? "official test runs" : "recent matches"}`,
          err,
          [btn("Retry", { onclick: () => void loadRecent({ reset: true }) })],
        ),
      );
      return null;
    }
  }

  function renderLadder(data) {
    const rankings = Array.isArray(data?.rankings) ? data.rankings : [];
    ladderRankByTeamId = new Map(
      rankings
        .filter((row) => row?.team_id && Number.isSafeInteger(row.rank))
        .map((row) => [row.team_id, row.rank]),
    );
    if (versionHistoryData) renderVersionHistory();
    if (!rankings.length) {
      fill(ladderSlot, emptyState({ title: "FCode ladder is empty" }));
      return;
    }
    const tbody = el("tbody");
    for (const row of rankings) {
      tbody.appendChild(
        el(
          "tr",
          null,
          el("td", { class: "num mute", text: fmt.int(row.rank) }),
          el(
            "td",
            null,
            el("button", {
              class: "fcode-team",
              type: "button",
              text: row.team_name || row.team_id,
              title: `Show recent matches for ${row.team_name || row.team_id}`,
              onclick: () => pickTeam({ id: row.team_id, name: row.team_name }),
            }),
          ),
          el("td", null, platformBotVersionTime(row)),
          el("td", { class: "num", text: fmt.num(row.rating, 0) }),
          el("td", { class: "num mute", text: fmt.int(row.matches_played) }),
        ),
      );
    }
    const table = el(
      "table",
      { class: "table table-compact fcode-ladder-table" },
      el("thead", null, el("tr", null, el("th", { class: "num", text: "#" }), el("th", { text: "Team" }), el("th", { text: "Bot" }), el("th", { class: "num", text: "Rating" }), el("th", { class: "num", text: "Matches" }))),
      tbody,
      Number(data?.total) > rankings.length
        ? el("caption", { text: `Top ${rankings.length} of ${fmt.int(data.total)} teams` })
        : null,
    );
    const trackingError = typeof data?.version_tracking?.last_error === "string"
      ? data.version_tracking.last_error
      : "";
    fill(
      ladderSlot,
      trackingError
        ? el("div", {
            class: "fcode-version-status err",
            text: "Could not refresh bot versions. Showing what was saved earlier.",
            title: trackingError,
          })
        : null,
      tableWrap(table),
    );
  }

  function selectVersionHistoryTeam(team, { explicit = false } = {}) {
    if (!team?.id || officialTests) return;
    selectedVersionTeamId = String(team.id);
    selectedVersionTeamName = team.name || selectedVersionTeamId;
    if (explicit) versionTeamSelectionExplicit = true;
    selectedVersionRequest += 1;
    selectedVersionLoading = false;
    selectedVersionError = null;
    if (versionHistoryData) {
      renderVersionHistory();
      const known = (versionHistoryData.teams || []).some(
        (candidate) => candidate.team_id === selectedVersionTeamId,
      );
      if (!known) void loadSelectedVersionHistory(selectedVersionTeamId);
    }
  }

  async function loadSelectedVersionHistory(teamId) {
    const request = ++selectedVersionRequest;
    selectedVersionLoading = true;
    selectedVersionError = null;
    renderVersionHistory();
    try {
      const key = `version-history-team:${teamId}`;
      const data = await cachedPlatformApi(
        key,
        `/api/platform/version-history?team_id=${encodeURIComponent(teamId)}&limit=1`,
        PLATFORM_LADDER_TTL,
      );
      if (!ctx.alive() || request !== selectedVersionRequest || teamId !== selectedVersionTeamId) return;
      const selected = Array.isArray(data?.teams) ? data.teams[0] : null;
      if (selected) {
        const teams = Array.isArray(versionHistoryData?.teams)
          ? versionHistoryData.teams.filter((candidate) => candidate.team_id !== selected.team_id)
          : [];
        versionHistoryData = { ...(versionHistoryData || {}), teams: [selected, ...teams] };
      }
    } catch (err) {
      if (ctx.alive() && request === selectedVersionRequest && teamId === selectedVersionTeamId) {
        selectedVersionError = err;
      }
    } finally {
      if (ctx.alive() && request === selectedVersionRequest && teamId === selectedVersionTeamId) {
        selectedVersionLoading = false;
        renderVersionHistory();
      }
    }
  }

  function preferredVersionTeam() {
    const signedTeam = session?.authenticated && session.team?.id ? session.team : null;
    const match = activeDetail?.match;
    if (match) {
      const teams = platformMatchTeams(match);
      const sides = ["a", "b"]
        .map((side) => teams[side])
        .filter((team) => team?.id);
      // Your own team stays selected whenever it is one of the two playing;
      // otherwise the panel follows the match, which is the only way the
      // highlight can show anything for a match between other teams.
      const own = sides.find(
        (team) => signedTeam && String(team.id) === String(signedTeam.id),
      );
      const chosen = own || sides[0];
      if (chosen) return { id: String(chosen.id), name: chosen.name || String(chosen.id) };
    }
    return signedTeam
      ? { id: String(signedTeam.id), name: signedTeam.name || String(signedTeam.id) }
      : null;
  }

  function ensureDefaultVersionTeam() {
    if (officialTests || versionTeamSelectionExplicit || !versionHistoryData) return false;
    const preferred = preferredVersionTeam();
    if (!preferred) return false;
    const known = (versionHistoryData.teams || []).some(
      (candidate) => candidate.team_id === preferred.id,
    );
    const changed = selectedVersionTeamId !== preferred.id;
    selectedVersionTeamId = preferred.id;
    selectedVersionTeamName = preferred.name;
    if (known) return false;
    if (!selectedVersionLoading || changed) void loadSelectedVersionHistory(preferred.id);
    return true;
  }

  function renderVersionHistory() {
    const rawTeams = Array.isArray(versionHistoryData?.teams) ? versionHistoryData.teams : [];
    const teams = rawTeams
      .map((candidate, index) => ({ candidate, index }))
      .sort((left, right) => {
        const leftRank = ladderRankByTeamId.get(left.candidate.team_id) ?? Infinity;
        const rightRank = ladderRankByTeamId.get(right.candidate.team_id) ?? Infinity;
        if (leftRank !== rightRank) return leftRank < rightRank ? -1 : 1;
        return left.index - right.index;
      })
      .map(({ candidate }) => candidate);
    const preferredTeamId = preferredVersionTeam()?.id || "";
    let team = teams.find((candidate) => candidate.team_id === selectedVersionTeamId) || null;
    if (!versionTeamSelectionExplicit) {
      const preferred = teams.find((candidate) => candidate.team_id === preferredTeamId) || null;
      const awaitingPreferred = Boolean(
        preferredTeamId
        && selectedVersionTeamId === preferredTeamId
        && (selectedVersionLoading || selectedVersionError),
      );
      team = preferred || (awaitingPreferred ? null : (teams[0] || team || null));
      if (team) {
        selectedVersionTeamId = team.team_id;
        selectedVersionTeamName = team.team_name || team.team_id;
      }
    }

    const options = [];
    if (selectedVersionTeamId && !teams.some((candidate) => candidate.team_id === selectedVersionTeamId)) {
      options.push(el("option", {
        value: selectedVersionTeamId,
        text: selectedVersionTeamName || selectedVersionTeamId,
      }));
    }
    for (const candidate of teams) {
      const rank = ladderRankByTeamId.get(candidate.team_id);
      const version = Number.isSafeInteger(candidate?.current_version)
        ? ` · v${candidate.current_version}`
        : "";
      options.push(el("option", {
        value: candidate.team_id,
        text: `${Number.isSafeInteger(rank) ? `#${rank} · ` : ""}${candidate.team_name || candidate.team_id}${version}`,
      }));
    }
    fill(versionTeamSelect, options);
    versionTeamSelect.disabled = !options.length;
    if (selectedVersionTeamId) versionTeamSelect.value = selectedVersionTeamId;

    if (!team && selectedVersionLoading) {
      fill(versionHistorySlot, skeletonRows(3));
      return;
    }
    if (!team && selectedVersionError) {
      fill(
        versionHistorySlot,
        platformErrorState(
          `Could not load bot-version history for ${selectedVersionTeamName || "this team"}`,
          selectedVersionError,
          [btn("Retry", { onclick: () => void loadSelectedVersionHistory(selectedVersionTeamId) })],
        ),
      );
      return;
    }
    if (!teams.length) {
      fill(
        versionHistorySlot,
        emptyState({
          title: "No versions seen yet",
          hint: ["Entries appear once this team has played ladder matches."],
        }),
      );
      return;
    }
    if (!team) {
      fill(
        versionHistorySlot,
        emptyState({
          title: `No saved version history for ${selectedVersionTeamName || "this team"}`,
        }),
      );
      return;
    }

    const runs = Array.isArray(team.runs) ? team.runs : [];
    if (!runs.length) {
      fill(versionHistorySlot, emptyState({ title: "No saved version periods for this team" }));
      return;
    }
    const playingOrdinal = playedRunOrdinal(team);
    const timeline = el("div", { class: "timeline fcode-version-timeline" });
    for (const [index, run] of runs.entries()) {
      const firstSeenAt = typeof run?.first_seen_at === "string" ? run.first_seen_at : "";
      const lastSeenAt = typeof run?.last_seen_at === "string" ? run.last_seen_at : "";
      const firstSeen = platformRelativeTime(firstSeenAt);
      firstSeen.classList.add("timeline-ts", "num");
      const isCurrent = index === 0;
      const ordinal = Number.isSafeInteger(run?.ordinal) ? run.ordinal : null;
      const isPlaying = ordinal !== null && ordinal === playingOrdinal;
      const key = ordinal === null ? "" : runKey(team.team_id, ordinal);
      const expanded = Boolean(key) && expandedRuns.has(key);
      const toggle = el(
        "button",
        {
          class: "fcode-version-run-head",
          type: "button",
          disabled: ordinal === null,
          "aria-expanded": expanded ? "true" : "false",
          title: ordinal === null
            ? ""
            : expanded
              ? "Hide the games played on this version"
              : "Show the games played on this version",
          onclick: () => {
            if (!key) return;
            if (expandedRuns.has(key)) expandedRuns.delete(key);
            else {
              expandedRuns.add(key);
              void loadRunGames(team.team_id, ordinal);
            }
            renderVersionHistory();
          },
        },
        el("span", { class: "fcode-run-caret", "aria-hidden": "true", text: expanded ? "▾" : "▸" }),
        el("strong", {
          class: "num",
          text: Number.isSafeInteger(run?.version) ? `v${run.version}` : "unknown version",
        }),
        isCurrent ? el("span", { class: "badge", text: "latest observed" }) : null,
        isPlaying
          ? el("span", {
              class: "badge fcode-version-playing",
              text: "this match",
              title: "The version this team played in the match open above",
            })
          : null,
      );
      timeline.appendChild(
        el(
          "div",
          {
            class: "timeline-item",
            "data-current": isCurrent ? "true" : null,
            "data-playing": isPlaying ? "true" : null,
          },
          firstSeen,
          el(
            "div",
            { class: "timeline-body" },
            toggle,
            el("div", {
              class: "small",
              text: run?.transition_known === true
                ? "Version change observed"
                : "Baseline observation",
            }),
            lastSeenAt && lastSeenAt !== firstSeenAt
              ? el(
                  "div",
                  { class: "tiny mute" },
                  "Last seen ",
                  platformRelativeTime(lastSeenAt),
                )
              : null,
            expanded ? runGamesNode(team.team_id, ordinal) : null,
          ),
        ),
      );
    }
    const refreshWarning = selectedVersionError
      ? el(
          "div",
          { class: "fcode-version-status err" },
          el("span", { text: "Could not refresh this timeline. Showing what was saved earlier." }),
          btn("Retry", {
            class: "btn btn-xs btn-ghost",
            onclick: () => void loadSelectedVersionHistory(selectedVersionTeamId),
          }),
        )
      : null;
    fill(versionHistorySlot, refreshWarning, timeline);
    renderVersionQuickSwitch();
    // Bring the highlighted run into view when it changes -- switching team, or
    // opening a different match -- but not on every background refresh.
    const playingKey = playingOrdinal === null
      ? ""
      : runKey(team.team_id, playingOrdinal);
    if (playingKey && playingKey !== scrolledPlayingKey) {
      scrolledPlayingKey = playingKey;
      requestAnimationFrame(() => {
        if (!ctx.alive()) return;
        timeline
          .querySelector('[data-playing="true"]')
          ?.scrollIntoView({ block: "nearest" });
      });
    } else if (!playingKey) {
      scrolledPlayingKey = "";
    }
  }

  function matchRunFor(teamId) {
    const teams = Array.isArray(matchRuns?.teams) ? matchRuns.teams : [];
    return teams.find((row) => String(row?.team_id || "") === String(teamId)) || null;
  }

  async function loadMatchRuns(matchId) {
    const wanted = String(matchId || "").toLowerCase();
    if (!wanted || officialTests || matchRunsFor === wanted) return;
    matchRunsFor = wanted;
    matchRuns = null;
    try {
      const data = await api(
        `/api/platform/version-history/match?match_id=${encodeURIComponent(wanted)}`,
      );
      if (!ctx.alive() || matchRunsFor !== wanted) return;
      matchRuns = data && typeof data === "object" ? data : null;
    } catch {
      if (ctx.alive() && matchRunsFor === wanted) matchRuns = null;
    } finally {
      if (ctx.alive() && matchRunsFor === wanted) syncVersionPanelToMatch();
    }
  }

  function renderVersionQuickSwitch() {
    const match = activeDetail?.match;
    if (officialTests || !match) {
      fill(versionQuickSwitch);
      versionQuickSwitch.hidden = true;
      return;
    }
    const teams = platformMatchTeams(match);
    const buttons = ["a", "b"]
      .map((side) => {
        const team = teams[side];
        const id = team?.id ? String(team.id) : "";
        if (!id) return null;
        const name = team.name || id;
        const recorded = matchRunFor(id);
        const version = Number.isSafeInteger(recorded?.version)
          ? recorded.version
          : Number.isSafeInteger(team?.version)
            ? team.version
            : null;
        return el(
          "button",
          {
            class: "seg-btn fcode-version-quick-btn",
            type: "button",
            "aria-pressed": id === selectedVersionTeamId ? "true" : "false",
            title: `Show ${name}'s bot versions`,
            onclick: () => selectVersionHistoryTeam({ id, name }, { explicit: true }),
          },
          el("span", { class: "fcode-version-quick-name", text: name }),
          version !== null ? el("span", { class: "tiny num", text: `v${version}` }) : null,
        );
      })
      .filter(Boolean);
    fill(versionQuickSwitch, buttons);
    versionQuickSwitch.hidden = !buttons.length;
  }

  function playedRunOrdinal(team) {
    const match = activeDetail?.match;
    if (officialTests || !match || !team) return null;
    const teams = platformMatchTeams(match);
    const side = ["a", "b"].find(
      (candidate) => String(teams[candidate]?.id || "") === String(team.team_id),
    );
    if (!side) return null;
    // The recorded run is exact: it comes from this match's own observation,
    // located by position in the team's series rather than by timestamp.
    const recorded = matchRunFor(team.team_id);
    if (Number.isSafeInteger(recorded?.ordinal)) return recorded.ordinal;
    // Nothing recorded -- a pinned side, or a match older than the collected
    // window. Fall back to whatever the match itself claims.
    return resolvePlayedRunOrdinal({
      runs: team.runs,
      version: Number.isSafeInteger(recorded?.version)
        ? recorded.version
        : teams[side]?.version,
      // Observations are keyed on when a match was created, so containment has
      // to be tested against the same instant.
      at: match.created_at || match.completed_at,
    });
  }

  function runKey(teamId, ordinal) {
    return `${teamId}:${ordinal}`;
  }

  async function loadRunGames(teamId, ordinal) {
    const key = runKey(teamId, ordinal);
    if (runGamesCache.has(key) || runGamesPending.has(key)) return;
    runGamesPending.add(key);
    try {
      const query = new URLSearchParams({
        team_id: teamId,
        ordinal: String(ordinal),
      });
      const data = await api(`/api/platform/version-history/games?${query.toString()}`);
      if (!ctx.alive()) return;
      runGamesCache.set(key, data && typeof data === "object" ? data : null);
    } catch (err) {
      if (ctx.alive()) runGamesCache.set(key, { error: errorMessage(err) });
    } finally {
      runGamesPending.delete(key);
      if (ctx.alive()) renderVersionHistory();
    }
  }

  function runGamesNode(teamId, ordinal) {
    const key = runKey(teamId, ordinal);
    const data = runGamesCache.get(key);
    if (!data) {
      return el("div", { class: "fcode-run-games" }, skeletonRows(2));
    }
    if (data.error) {
      return el("div", { class: "fcode-run-games err small", text: data.error });
    }
    const games = Array.isArray(data.games) ? data.games : [];
    if (!games.length) {
      return el("div", {
        class: "fcode-run-games small mute",
        text: "No games recorded for this version.",
      });
    }
    const record = data.record || {};
    const rows = games.map((game) => {
      const score = Number.isFinite(game?.score_for) && Number.isFinite(game?.score_against)
        ? `${game.score_for}–${game.score_against}`
        : "–";
      const opponent = game?.opponent_name || "unknown team";
      const opponentVersion = Number.isSafeInteger(game?.opponent_version)
        ? `v${game.opponent_version}`
        : "";
      const matchId = typeof game?.match_id === "string" ? game.match_id : "";
      const when = platformRelativeTime(game?.match_at);
      when.classList.add("num");
      return el(
        "a",
        {
          class: "fcode-run-game",
          "data-result": game?.result || "pending",
          href: matchId ? platformViewHash(matchId, 1) : null,
          title: matchId ? `Open ${opponent} on the FCode viewer` : "",
        },
        when,
        el("span", {
          class: "badge fcode-run-kind",
          text: game?.match_type === "unrated" ? "unrated" : "ladder",
        }),
        el("span", { class: "fcode-run-opponent", text: opponent }),
        el("span", { class: "tiny mute num", text: opponentVersion }),
        el("span", { class: "fcode-run-score num", text: score }),
        el("span", {
          class: "fcode-run-result",
          // "unknown" is a match recorded before outcomes were tracked; a blank
          // result is one that genuinely has not finished.
          text: game?.result === "unknown"
            ? "no result"
            : game?.result || "in progress",
          title: game?.result === "unknown"
            ? "This match was recorded before oarena tracked outcomes."
            : "",
        }),
      );
    });
    return el(
      "div",
      { class: "fcode-run-games" },
      el(
        "div",
        { class: "fcode-run-summary small" },
        wldSpan(record.wins || 0, record.losses || 0, record.draws || 0),
        el("span", {
          class: "mute",
          text: `${fmt.int(data.total)} game${data.total === 1 ? "" : "s"}`
            + (record.undecided ? ` · ${fmt.int(record.undecided)} unfinished` : "")
            + (record.unknown ? ` · ${fmt.int(record.unknown)} without a result` : "")
            + (data.truncated ? ` · showing ${fmt.int(games.length)}` : ""),
        }),
      ),
      el("div", { class: "fcode-run-game-list" }, rows),
    );
  }

  function armVersionSync(delay, callback) {
    if (versionSyncTimer !== null) {
      clearTimeout(versionSyncTimer);
      versionSyncTimer = null;
    }
    if (!Number.isFinite(delay)) return;
    versionSyncTimer = setTimeout(() => {
      versionSyncTimer = null;
      if (ctx.alive()) callback();
    }, Math.max(1_000, delay));
  }

  function invalidateVersionHistoryCache() {
    platformResponseCache.delete("version-history:100");
    if (selectedVersionTeamId) {
      platformResponseCache.delete(`version-history-team:${selectedVersionTeamId}`);
    }
  }

  function scheduleVersionSync(tracking) {
    if (tracking?.refreshing) {
      const delay = versionSyncPolls < PLATFORM_VERSION_SYNC_MAX_POLLS
        ? PLATFORM_VERSION_SYNC_POLL_MS
        : PLATFORM_VERSION_SYNC_SLOW_POLL_MS;
      versionSyncPolls += 1;
      armVersionSync(delay, () => void pollVersionSync());
    } else {
      versionSyncPolls = 0;
      const next = Date.parse(String(tracking?.next_refresh_at || ""));
      if (Number.isFinite(next)) {
        armVersionSync(next - Date.now() + 100, () => {
          platformResponseCache.delete("ladder:100");
          invalidateVersionHistoryCache();
          void loadLadder({ trackingPoll: true });
          void loadVersionHistory({ trackingPoll: true });
        });
      } else if (tracking?.last_error || tracking?.error) {
        armVersionSync(PLATFORM_VERSION_SYNC_ERROR_RETRY_MS, () => {
          platformResponseCache.delete("ladder:100");
          invalidateVersionHistoryCache();
          void loadLadder({ trackingPoll: true });
          void loadVersionHistory({ trackingPoll: true });
        });
      }
    }
  }

  async function pollVersionSync() {
    try {
      const tracking = await api("/api/platform/version-tracking");
      if (!ctx.alive()) return;
      if (tracking?.refreshing) {
        scheduleVersionSync(tracking);
        return;
      }
      platformResponseCache.delete("ladder:100");
      invalidateVersionHistoryCache();
      void loadLadder({ trackingPoll: true });
      void loadVersionHistory({ trackingPoll: true });
    } catch {
      if (ctx.alive()) {
        armVersionSync(PLATFORM_VERSION_SYNC_ERROR_RETRY_MS, () => void pollVersionSync());
      }
    }
  }

  async function loadLadder({ trackingPoll = false } = {}) {
    try {
      const data = await cachedPlatformApi(
        "ladder:100",
        "/api/platform/ladder?limit=100",
        PLATFORM_LADDER_TTL,
      );
      if (ctx.alive()) {
        renderLadder(data);
        scheduleVersionSync(data?.version_tracking);
      }
    } catch (err) {
      if (ctx.alive() && !trackingPoll) {
        fill(
          ladderSlot,
          platformErrorState("Could not load the FCode ladder", err, [btn("Retry", { onclick: loadLadder })]),
        );
      } else if (ctx.alive()) {
        armVersionSync(PLATFORM_VERSION_SYNC_ERROR_RETRY_MS, () => void pollVersionSync());
      }
    }
  }

  async function loadVersionHistory({ trackingPoll = false } = {}) {
    try {
      const data = await cachedPlatformApi(
        "version-history:100",
        "/api/platform/version-history?limit=100",
        PLATFORM_LADDER_TTL,
      );
      if (ctx.alive()) {
        const freshTeams = Array.isArray(data?.teams) ? data.teams : [];
        const selectedMissingFromFresh = Boolean(
          selectedVersionTeamId
          && !freshTeams.some((candidate) => candidate.team_id === selectedVersionTeamId),
        );
        if (!selectedMissingFromFresh) {
          selectedVersionRequest += 1;
          selectedVersionLoading = false;
          selectedVersionError = null;
        }
        const previousSelected = (versionHistoryData?.teams || []).find(
          (candidate) => candidate.team_id === selectedVersionTeamId,
        );
        versionHistoryData = data || {};
        if (
          previousSelected
          && !(versionHistoryData.teams || []).some(
            (candidate) => candidate.team_id === previousSelected.team_id,
          )
        ) {
          versionHistoryData = {
            ...versionHistoryData,
            teams: [previousSelected, ...(versionHistoryData.teams || [])],
          };
        }
        const loadingSignedTeam = ensureDefaultVersionTeam();
        if (!loadingSignedTeam) renderVersionHistory();
        const selectedIsSignedIn = Boolean(
          preferredVersionTeam()?.id
          && preferredVersionTeam().id === selectedVersionTeamId,
        );
        if (
          !loadingSignedTeam
          && selectedVersionTeamId
          && selectedMissingFromFresh
          && (versionTeamSelectionExplicit || selectedIsSignedIn)
        ) {
          void loadSelectedVersionHistory(selectedVersionTeamId);
        }
      }
    } catch (err) {
      if (ctx.alive() && !trackingPoll) {
        fill(
          versionHistorySlot,
          platformErrorState(
            "Could not load bot-version history",
            err,
            [btn("Retry", { onclick: loadVersionHistory })],
          ),
        );
      }
    }
  }

  function syncVersionPanelToMatch() {
    // The open match decides both the quick-switch buttons and which run is
    // highlighted, so a new selection has to repaint the panel.
    if (officialTests) return;
    void loadMatchRuns(activeDetail?.match?.id);
    if (!versionHistoryData) {
      renderVersionQuickSwitch();
      return;
    }
    // A different match can change which team the panel should be showing, so
    // the default is re-resolved before repainting.
    if (!ensureDefaultVersionTeam()) renderVersionHistory();
  }

  function renderMatchBar() {
    const detail = activeDetail;
    const match = detail?.match;
    if (!match || !activeGame) {
      matchBar.hidden = true;
      syncVersionPanelToMatch();
      return;
    }
    const teams = platformMatchTeams(match);
    const games = new Map((detail.games || []).map((game) => [Number(game.number), game]));
    const gameButtons = [];
    for (let number = 1; number <= 5; number += 1) {
      const game = games.get(number);
      const winnerName = platformGameWinnerName(game, match);
      gameButtons.push(
        el(
          "button",
          {
            class: "fcode-game-btn",
            type: "button",
            disabled: !game,
            "aria-pressed": Number(activeGame.number) === number ? "true" : "false",
            title: game
              ? `${game.map_name || "unknown map"}${game.win_condition ? ` · ${game.win_condition}` : ""}`
              : `Game ${number} is not available`,
            onclick: () => {
              if (!game) return;
              userSelected = true;
              showGame(game);
            },
          },
          el("span", { class: "fcode-game-label", text: `Game ${number}` }),
          winnerName
            ? el("span", {
                class: "fcode-game-result",
                text: winnerName,
                title: `${winnerName} won`,
              })
            : null,
        ),
      );
    }
    fill(
      matchBar,
      el(
        "div",
        { class: "fcode-score" },
        teamButton(teams.a, match),
        el("strong", { class: "fcode-score-value num", text: platformMatchScore(match) }),
        teamButton(teams.b, match),
        el("span", { class: "badge", text: platformMatchLabel(match) }),
      ),
      el("div", { class: "fcode-game-tabs", role: "group", "aria-label": "Games in this match" }, gameButtons),
      el(
        "p",
        { class: "fcode-provenance" },
        `Drawn with your installed FCode${state.fcode ? ` ${state.fcode}` : ""} constants, because remote replays do not include a recorded engine-metadata snapshot.`,
      ),
    );
    matchBar.hidden = false;
    syncVersionPanelToMatch();
  }

  function showGame(game) {
    const match = activeDetail?.match;
    if (!match || !game) return;
    activeGame = game;
    const number = normalizePlatformGame(game.number);
    const matchId = String(match.id).toLowerCase();
    const teams = platformMatchTeams(match);
    matchInput.value = matchId;
    gameInput.value = String(number);
    view.setSub(`${teams.a.name} vs ${teams.b.name}`);
    officialLink.href = officialUrl(matchId, number);
    officialLink.hidden = false;
    replayLink.href = `/api/platform/matches/${encodeURIComponent(matchId)}/games/${number}/replay`;
    replayLink.download = `${matchId}-game-${number}.replay26`;
    replayLink.hidden = !game.has_replay;
    fullscreenButton.disabled = !game.has_replay || !squareViewer;
    updateRouteAndStorage(matchId, number);
    renderMatchBar();

    if (!game.has_replay) {
      squareViewer?.hide(vizSlot);
      fill(
        vizSlot,
        emptyState({
          title: `Game ${number} replay unavailable`,
          hint: [match.status === "complete" ? "The platform did not provide a replay for this game." : "This match may still be running."],
        }),
      );
      return;
    }

    fill(vizSlot);
    if (!squareViewer?.showReplay) {
      fill(vizSlot, emptyState({ title: "2D viewer unavailable" }));
      return;
    }
    squareViewer.showReplay(
      vizSlot,
      {
        key: `fcode:${matchId}:${number}`,
        replayUrl: `/api/platform/matches/${encodeURIComponent(matchId)}/games/${number}/replay`,
        game: {
          id: number,
          a: teams.a.name,
          b: teams.b.name,
          map: game.map_name || "FCode map",
          fcode_metadata: null,
        },
        localGameId: null,
      },
      theme(),
    );
  }

  function scheduleMatchPoll(matchId, fallbackGame) {
    if (matchPollTimer !== null) {
      clearTimeout(matchPollTimer);
      matchPollTimer = null;
    }
    const match = activeDetail?.match;
    if (
      !match ||
      String(match.id || "").toLowerCase() !== matchId ||
      ["complete", "error"].includes(String(match.status || "").toLowerCase())
    ) return;
    matchPollTimer = setTimeout(() => {
      matchPollTimer = null;
      if (!ctx.alive()) return;
      const nextGame = normalizePlatformGame(activeGame?.number, fallbackGame);
      void selectMatch(
        { matchId, game: nextGame },
        { refresh: true, quiet: true },
      );
    }, 5_000);
  }

  async function selectMatch(selection, { refresh = false, quiet = false } = {}) {
    const request = ++detailRequest;
    const matchId = String(selection.matchId || "").toLowerCase();
    const wantedGame = normalizePlatformGame(selection.game);
    const background = Boolean(
      quiet && String(activeDetail?.match?.id || "").toLowerCase() === matchId,
    );
    if (matchPollTimer !== null) {
      clearTimeout(matchPollTimer);
      matchPollTimer = null;
    }
    if (!background) {
      showFormError("");
      loadButton.disabled = true;
      officialLink.hidden = true;
      replayLink.hidden = true;
      fullscreenButton.disabled = true;
      squareViewer?.hide(vizSlot);
      fill(vizSlot, emptyState({ title: "Loading FCode match…", hint: [matchId] }));
      matchBar.hidden = true;
    }
    try {
      const detail = await platformMatchDetail(matchId, { refresh });
      if (!ctx.alive() || request !== detailRequest) return false;
      const games = Array.isArray(detail?.games) ? detail.games : [];
      // A tab click can happen while a quiet refresh is in flight. Resolve the
      // selected number again after the await so fresh detail never snaps the
      // viewer back to the game that happened to be active when polling began.
      const selectedGame = background
        ? normalizePlatformGame(activeGame?.number, wantedGame)
        : wantedGame;
      const game = games.find((item) => Number(item.number) === selectedGame)
        || games.find((item) => item.has_replay)
        || games[0];
      if (!detail?.match) throw new Error("The platform returned no match details");
      activeDetail = detail;
      if (!game && !["complete", "error"].includes(detail.match.status)) {
        activeGame = null;
        squareViewer?.hide(vizSlot);
        matchBar.hidden = true;
        const teams = platformMatchTeams(detail.match);
        matchInput.value = matchId;
        gameInput.value = String(wantedGame);
        view.setSub(`${teams.a.name} vs ${teams.b.name}`);
        officialLink.href = officialUrl(matchId, wantedGame);
        officialLink.hidden = false;
        updateRouteAndStorage(matchId, wantedGame);
        fill(
          vizSlot,
          emptyState({
            title: `Match ${platformMatchLabel(detail.match)}`,
            hint: ["No game replay is available yet. This view will refresh automatically."],
            actions: [btn("Refresh now", {
              onclick: () => void selectMatch(
                { matchId, game: wantedGame },
                { refresh: true },
              ),
            })],
          }),
        );
        scheduleMatchPoll(matchId, wantedGame);
        return true;
      }
      if (!game) {
        activeGame = null;
        squareViewer?.hide(vizSlot);
        matchBar.hidden = true;
        const teams = platformMatchTeams(detail.match);
        const status = String(detail.match.status || "complete").replace(/_/g, " ");
        matchInput.value = matchId;
        gameInput.value = String(wantedGame);
        view.setSub(`${teams.a.name} vs ${teams.b.name}`);
        officialLink.href = officialUrl(matchId, wantedGame);
        officialLink.hidden = false;
        updateRouteAndStorage(matchId, wantedGame);
        fill(
          vizSlot,
          emptyState({
            title: `Match ${status}`,
            hint: [detail.match.error || "This match finished without a game replay."],
          }),
        );
        return true;
      }
      const keepRenderedReplay = Boolean(
        background &&
        activeGame?.has_replay &&
        game.has_replay &&
        Number(activeGame.number) === Number(game.number),
      );
      if (keepRenderedReplay) {
        activeGame = game;
        renderMatchBar();
      } else {
        showGame(game);
      }
      scheduleMatchPoll(matchId, wantedGame);
      return true;
    } catch (err) {
      if (!ctx.alive() || request !== detailRequest) return false;
      if (background) {
        scheduleMatchPoll(matchId, wantedGame);
        return false;
      }
      activeDetail = null;
      activeGame = null;
      officialLink.hidden = true;
      replayLink.hidden = true;
      fullscreenButton.disabled = true;
      fill(
        vizSlot,
        platformErrorState(
          Number(err?.status) === 401 ? "Sign in to load this FCode match" : "Could not load this FCode match",
          err,
          [btn("Retry", {
            onclick: () => void selectMatch(
              { matchId, game: wantedGame },
              { refresh: true },
            ),
          })],
        ),
      );
      showFormError(errorMessage(err));
      return false;
    } finally {
      if (ctx.alive() && request === detailRequest) loadButton.disabled = false;
    }
  }

  matchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    try {
      const selection = parsePlatformMatchInput(matchInput.value, gameInput.value);
      userSelected = true;
      gameInput.value = String(selection.game);
      void selectMatch(selection);
    } catch (err) {
      showFormError(errorMessage(err));
      matchInput.focus();
    }
  });

  let initialSelection = null;
  const hasExplicitMatch = Boolean(params && Object.prototype.hasOwnProperty.call(params, "matchId"));
  if (hasExplicitMatch) {
    try {
      if (params.game !== undefined) {
        const parsedGame = Number(params.game);
        if (!Number.isInteger(parsedGame) || parsedGame < 1 || parsedGame > 5) {
          throw new Error("Game must be between 1 and 5");
        }
      }
      initialSelection = parsePlatformMatchInput(params.matchId, params.game || 1);
    } catch (err) {
      showFormError(errorMessage(err));
      fill(
        vizSlot,
        emptyState({
          title: "That match link did not parse",
          hint: [errorMessage(err), "Paste a match UUID or an official visualiser URL."],
        }),
      );
    }
  }
  if (!officialTests && !hasExplicitMatch && !initialSelection) {
    initialSelection = loadPlatformSelection(globalThis.localStorage);
  }
  if (initialSelection) {
    matchInput.value = initialSelection.matchId;
    gameInput.value = String(initialSelection.game);
  }

  renderRecentFilters();
  ctx.timer(refreshRecentTimestamps, PLATFORM_RELATIVE_TIME_REFRESH_MS);
  const sessionPromise = cachedPlatformApi(
    "session",
    "/api/platform/session",
    PLATFORM_CACHE_TTL,
  )
    .then((data) => {
      if (ctx.alive()) renderSession(data);
      return data;
    })
    .catch((err) => {
      if (ctx.alive()) renderSession(null, err);
      return null;
    });
  const recentPromise = loadRecent({ reset: true });
  if (!officialTests) void loadLadder();
  if (!officialTests) void loadVersionHistory();
  void sessionPromise;

  void (async () => {
    if (initialSelection && (await selectMatch(initialSelection))) return;
    if (hasExplicitMatch) return;
    await recentPromise;
    if (!ctx.alive() || userSelected || activeDetail) return;
    autoSelectRecent = true;
    maybeSelectRecentMatch();
  })();

  const onTheme = () => {
    if (ctx.alive()) squareViewer?.setTheme(theme());
  };
  document.addEventListener("themechange", onTheme);
  ctx.add(() => document.removeEventListener("themechange", onTheme));
  ctx.add(() => {
    if (matchPollTimer !== null) clearTimeout(matchPollTimer);
    if (recentPollTimer !== null) clearTimeout(recentPollTimer);
    if (versionSyncTimer !== null) clearTimeout(versionSyncTimer);
    squareViewer?.hide(vizSlot);
    fill(vizSlot);
  });
}

const fcode = mount("fcode", (root, params, ctx) => {
  mountPlatformView(root, params, ctx);
});

const testRuns = mount("test-runs", (root, params, ctx) => {
  mountPlatformView(root, params, ctx, { officialTests: true });
});

/* -------------------------------------------------------------------------- */

/* 9. Official unrated scrims                                                  */
/* -------------------------------------------------------------------------- */

const SCRIM_POLL_MS = 8_000;
const SCRIM_CLOCK_MS = 1_000;
const SCRIM_TEAM_SEARCH_DELAY_MS = 450;
const SCRIM_AUTO_TOP_K_DEFAULT = 10;
const SCRIM_AUTO_TOP_K_MAX = 100;
let scrimTeamPickerSequence = 0;
let scrimInitialRefreshIssued = false;

function scrimTimestamp(value) {
  if (Number.isFinite(value)) {
    const number = Number(value);
    return number < 10_000_000_000 ? number * 1000 : number;
  }
  const parsed = Date.parse(String(value || ""));
  return Number.isFinite(parsed) ? parsed : null;
}

function scrimErrorText(value) {
  if (typeof value === "string") return value;
  if (value && typeof value === "object") {
    return String(value.message || value.error || value.detail || "");
  }
  return "";
}

function scrimFiniteNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function quotaWindowText(quota) {
  const window = Number(quota?.window_s);
  if (!Number.isFinite(window) || window <= 0) return "";
  const span = window % 3600 === 0
    ? `${window / 3600}h`
    : window >= 60
      ? `${Math.round(window / 60)} min`
      : `${Math.round(window)}s`;
  // Say when the number is a guess, so an unexpected pause is easy to explain.
  return `requests per ${span}${quota?.learned ? "" : " (assumed)"}`;
}

function scrimCountdown(deadline, now = Date.now()) {
  const at = scrimTimestamp(deadline);
  if (at === null) return "";
  const seconds = Math.max(0, Math.ceil((at - now) / 1000));
  if (seconds <= 0) return "now";
  if (seconds < 60) return `in ${seconds}s`;
  const minutes = Math.ceil(seconds / 60);
  if (minutes < 60) return `in ${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return `in ${hours}h${remainder ? ` ${remainder}m` : ""}`;
}

const scrims = mount("scrims", (root, params, ctx) => {
  void params;
  let dashboard = null;
  let selectedVersion = "current";
  let dashboardRequest = 0;
  let mapsRequest = 0;
  let allowedMaps = [];
  let mapPreviews = new Map(
    (state.maps || []).map((map) => [String(map?.name || ""), map]),
  );
  let manualPending = false;
  let manualRequestKey = null;
  let manualRequestFingerprint = null;
  let autoscrimPending = false;
  let topTeamsRequest = 0;
  let topTeamsPending = false;
  let topSeedTeamsRequest = 0;
  let topSeedTeamsPending = false;
  let topTeamsSeed = [];
  let topSeededFor = "";
  let refreshPending = false;
  let autoscrimDraftLoaded = false;
  let autoscrimDirty = false;
  const knownTeams = new Map();
  const teamSearchCache = new Map();
  const manualMaps = new Set();
  const autoscrimMaps = new Set();
  const autoscrimTargets = new Map();
  const mapPreview = createMapPreview(root);
  ctx.add(() => mapPreview.destroy());

  const versionSelect = el("select", {
    class: "select select-compact scrim-version-select",
    "aria-label": "Bot version for scrim statistics",
    onchange: (event) => {
      selectedVersion = event.currentTarget.value || "current";
      void loadDashboard({ quiet: false });
    },
  });
  const refreshButton = btn("Refresh", {
    class: "btn btn-sm btn-ghost",
    title: "Refresh official unrated matches now",
    onclick: () => void refreshOfficial({ reportError: true }),
  });

  const sessionSlot = el("div", { class: "scrim-session", "aria-live": "polite" });
  const bannerSlot = el("div", { class: "scrim-banner-slot", "aria-live": "polite" });
  const summarySlot = el("div", { class: "stats scrim-summary" }, skeletonRows(2));
  const manualError = el("div", { class: "form-error", role: "alert", hidden: true });
  const manualBlocked = el("div", { class: "field-hint scrim-blocked", "aria-live": "polite" });
  const manualMapSlot = el("div", { class: "scrim-map-slot" });
  const manualTopTeamsSlot = el("div", { class: "scrim-top-teams" });
  const autoscrimMapSlot = el("div", { class: "scrim-map-slot" });
  const autoscrimTopKInput = el("input", {
    class: "input num scrim-topk",
    type: "number",
    min: "1",
    max: String(SCRIM_AUTO_TOP_K_MAX),
    step: "1",
    value: String(SCRIM_AUTO_TOP_K_DEFAULT),
    inputmode: "numeric",
    "aria-label": "Top teams to add",
  });
  const autoscrimTopKButton = btn("Add top teams", { class: "btn" });
  const autoscrimTopTeamsSlot = el("div", { class: "scrim-top-teams" });
  const autoscrimTargetsSlot = el("div", { class: "scrim-targets" });
  const autoscrimError = el("div", { class: "form-error", role: "alert", hidden: true });
  const autoscrimStateSlot = el("div", { class: "scrim-status-line", "aria-live": "polite" });
  const opponentStatsSlot = el("div", { class: "scrim-panel-body" }, skeletonRows(6));
  const historySlot = el("div", { class: "scrim-panel-body" }, skeletonRows(8));

  function rememberTeam(raw) {
    const id = canonicalScrimUuid(raw?.id || raw?.team_id || raw?.teamId);
    if (!id) return null;
    const previous = knownTeams.get(id);
    const name = String(raw?.name || raw?.team_name || raw?.teamName || previous?.name || "").trim();
    const team = {
      id,
      name,
      rating: Number.isFinite(raw?.rating) ? raw.rating : previous?.rating,
      matches_played: Number.isFinite(raw?.matches_played)
        ? raw.matches_played
        : Number.isFinite(raw?.matchesPlayed)
          ? raw.matchesPlayed
          : previous?.matches_played,
    };
    knownTeams.set(id, team);
    const target = autoscrimTargets.get(id);
    if (target && name && !target.name) autoscrimTargets.set(id, { ...target, name });
    return team;
  }

  function makeTeamPicker({ label, placeholder, onSelect }) {
    const sequence = ++scrimTeamPickerSequence;
    const listId = `scrim-team-options-${sequence}`;
    let searchTimer = null;
    let searchRequest = 0;
    let selected = null;
    let active = -1;
    let options = [];
    const list = el("div", {
      class: "bot-combobox-list",
      id: listId,
      role: "listbox",
      hidden: true,
    });
    const input = el("input", {
      class: "input",
      type: "text",
      autocomplete: "off",
      spellcheck: "false",
      placeholder,
      role: "combobox",
      "aria-label": label,
      "aria-autocomplete": "list",
      "aria-controls": listId,
      "aria-expanded": "false",
    });

    function close() {
      list.hidden = true;
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
      active = -1;
    }

    function choose(team) {
      selected = rememberTeam(team);
      if (!selected) return;
      input.value = selected.name || selected.id;
      close();
      onSelect(selected);
    }

    function paint() {
      fill(list);
      if (!options.length) {
        close();
        return;
      }
      options.forEach((team, index) => {
        const optionId = `${listId}-${index}`;
        const option = el(
          "div",
          {
            class: "bot-combobox-option",
            id: optionId,
            role: "option",
            "aria-selected": index === active ? "true" : "false",
            onmousedown: (event) => event.preventDefault(),
            onclick: () => choose(team),
          },
          el("span", { class: "bot-combobox-name", text: team.name || team.id }),
          el("span", {
            class: "bot-combobox-tag num",
            text: Number.isFinite(team.rating) ? fmt.num(team.rating, 0) : team.id.slice(0, 8),
            title: team.id,
          }),
        );
        list.appendChild(option);
      });
      list.hidden = false;
      input.setAttribute("aria-expanded", "true");
      if (active >= 0) input.setAttribute("aria-activedescendant", `${listId}-${active}`);
    }

    function useSearchResults(rawTeams) {
      const ownId = canonicalScrimUuid(dashboard?.session?.team?.id);
      options = (Array.isArray(rawTeams) ? rawTeams : [])
        .map(rememberTeam)
        .filter((team) => team && team.id !== ownId);
      active = options.length ? 0 : -1;
      paint();
    }

    async function search(query) {
      const request = ++searchRequest;
      const cacheKey = query.toLocaleLowerCase();
      const cached = teamSearchCache.get(cacheKey);
      if (cached) {
        useSearchResults(cached);
        return;
      }
      try {
        const response = await api(`/api/platform/teams?q=${encodeURIComponent(query)}&limit=10`);
        if (!ctx.alive() || request !== searchRequest) return;
        const teams = Array.isArray(response?.teams) ? response.teams : [];
        teamSearchCache.set(cacheKey, teams);
        useSearchResults(teams);
      } catch {
        if (ctx.alive() && request === searchRequest) close();
      }
    }

    input.addEventListener("input", () => {
      // Invalidate an already in-flight query immediately; waiting for the
      // next debounced request would let stale results repaint under new text.
      searchRequest += 1;
      close();
      if (selected && input.value !== selected.name && input.value !== selected.id) selected = null;
      if (searchTimer !== null) clearTimeout(searchTimer);
      const query = input.value.trim();
      if (query.length < 2 || canonicalScrimUuid(query)) {
        close();
        return;
      }
      searchTimer = setTimeout(() => {
        searchTimer = null;
        void search(query);
      }, SCRIM_TEAM_SEARCH_DELAY_MS);
    });
    input.addEventListener("keydown", (event) => {
      if (list.hidden || !options.length) return;
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const direction = event.key === "ArrowDown" ? 1 : -1;
        active = (active + direction + options.length) % options.length;
        paint();
      } else if (event.key === "Enter" && active >= 0) {
        event.preventDefault();
        choose(options[active]);
      } else if (event.key === "Escape") {
        event.preventDefault();
        close();
      }
    });
    input.addEventListener("blur", () => {
      searchRequest += 1;
      if (searchTimer !== null) clearTimeout(searchTimer);
      searchTimer = null;
      setTimeout(close, 100);
    });
    ctx.add(() => {
      if (searchTimer !== null) clearTimeout(searchTimer);
      searchRequest += 1;
    });

    return {
      wrap: el("div", { class: "bot-combobox scrim-team-picker" }, input, list),
      input,
      value() {
        if (selected) return selected;
        const id = canonicalScrimUuid(input.value);
        return id ? { id, name: knownTeams.get(id)?.name || "" } : null;
      },
      set(team) {
        selected = rememberTeam(team);
        input.value = selected?.name || selected?.id || "";
      },
      clear() {
        selected = null;
        input.value = "";
        close();
      },
    };
  }

  let manualPicker;
  let autoscrimPicker;
  manualPicker = makeTeamPicker({
    label: "Opponent team",
    placeholder: "Search team name or paste UUID",
    onSelect: () => showManualError(""),
  });
  autoscrimPicker = makeTeamPicker({
    label: "Add autoscrim target",
    placeholder: "Search and add a team",
    onSelect: (team) => {
      autoscrimTargets.set(team.id, team);
      autoscrimDirty = true;
      autoscrimPicker.clear();
      renderAutoscrimTargets();
    },
  });

  const sourceMatchInput = el("input", {
    class: "input num",
    type: "text",
    autocomplete: "off",
    spellcheck: "false",
    placeholder: "Optional match UUID",
    "aria-label": "Opponent source match UUID",
  });
  const manualSubmit = btn("Request scrim", { class: "btn btn-primary", type: "submit" });
  const manualForm = el(
    "form",
    { class: "stack scrim-form" },
    el(
      "label",
      { class: "field" },
      el("span", { class: "field-label", text: "Opponent" }),
      manualPicker.wrap,
    ),
    el(
      "div",
      { class: "field" },
      el("span", { class: "field-label", text: "Ladder leaders" }),
      manualTopTeamsSlot,
      el("span", { class: "field-hint", text: "Click one to fill the opponent above." }),
    ),
    el(
      "label",
      { class: "field" },
      el("span", { class: "field-label", text: "Pin their bot version" }),
      sourceMatchInput,
      el("span", {
        class: "field-hint",
        text: "Blank plays their latest bot. Paste an earlier match ID to replay the version from that match.",
      }),
    ),
    el(
      "div",
      { class: "field" },
      el("span", { class: "field-label", text: "Maps" }),
      manualMapSlot,
    ),
    manualError,
    el("div", { class: "row wrap scrim-submit-row" }, manualSubmit, manualBlocked),
  );

  const autoscrimEnabled = el("input", {
    type: "checkbox",
    "aria-label": "Enable autoscrim",
  });
  const autoscrimToggle = el(
    "label",
    { class: "toggle" },
    autoscrimEnabled,
    el("span", { class: "toggle-track" }, el("span", { class: "toggle-thumb" })),
    el("span", { class: "toggle-label", text: "Enabled" }),
  );
  const saveAutoscrimButton = btn("Save autoscrim", { class: "btn btn-primary" });
  const autoscrimForm = el(
    "div",
    { class: "stack scrim-form" },
    el("div", { class: "row wrap" }, autoscrimToggle, autoscrimStateSlot),
    el(
      "div",
      { class: "field" },
      el("span", { class: "field-label", text: "Opponents" }),
      autoscrimPicker.wrap,
      autoscrimTargetsSlot,
      el(
        "div",
        { class: "field-row" },
        autoscrimTopKInput,
        autoscrimTopKButton,
      ),
      el("span", {
        class: "field-hint",
        text: "Runs one match at a time, always picking the opponent you have played least. Your own team is skipped.",
      }),
    ),
    el(
      "div",
      { class: "field" },
      el("span", { class: "field-label", text: "Ladder leaders" }),
      autoscrimTopTeamsSlot,
      el("span", { class: "field-hint", text: "Click to add or remove." }),
    ),
    el(
      "div",
      { class: "field" },
      el("span", { class: "field-label", text: "Maps" }),
      autoscrimMapSlot,
    ),
    autoscrimError,
    el("div", { class: "row wrap" }, saveAutoscrimButton),
  );

  const view = viewRoot(
    {
      title: "Scrims",
      sub: "official unrated matches",
      toolbar: [refreshButton],
    },
    sessionSlot,
    bannerSlot,
    summarySlot,
    el(
      "div",
      { class: "grid grid-2 scrim-config-grid" },
      card({ title: "Request scrim" }, manualForm),
      card({ title: "Autoscrim" }, autoscrimForm),
    ),
    card({ title: "Results by opponent", actions: versionSelect, flush: true }, opponentStatsSlot),
    card({ title: "Recent requests", flush: true }, historySlot),
  );
  root.appendChild(view);

  function showManualError(message) {
    manualError.textContent = message || "";
    manualError.hidden = !message;
  }

  function showAutoscrimError(message) {
    autoscrimError.textContent = message || "";
    autoscrimError.hidden = !message;
  }

  function ownTeamId() {
    return canonicalScrimUuid(dashboard?.session?.team?.id);
  }

  function parseTopK(raw) {
    const parsed = Number.parseInt(String(raw || "").trim(), 10);
    if (!Number.isFinite(parsed)) {
      return null;
    }
    if (parsed <= 0) return null;
    return Math.max(1, Math.min(SCRIM_AUTO_TOP_K_MAX, parsed));
  }

  function renderScrimTopTeamChips() {
    if (!topTeamsSeed.length) {
      const text = topSeedTeamsPending ? "Loading top teams…" : "No top teams available.";
      fill(manualTopTeamsSlot, el("span", { class: "field-hint", text }));
      fill(autoscrimTopTeamsSlot, el("span", { class: "field-hint", text }));
      return;
    }
    const teams = topTeamsSeed.slice(0, SCRIM_AUTO_TOP_K_DEFAULT);
    fill(
      manualTopTeamsSlot,
      el(
        "div",
        { class: "chip-set" },
        teams.map((team) =>
          el(
            "button",
            {
              type: "button",
              class: "chip chip-accent",
              onclick: () => {
                manualPicker.set(team);
                showManualError("");
              },
            },
            team.name || team.id,
            team.rating !== undefined && Number.isFinite(team.rating)
              ? el("span", { class: "chip-tag", text: fmt.num(team.rating, 0) })
              : null,
          ),
        ),
      ),
    );
    fill(
      autoscrimTopTeamsSlot,
      el(
        "div",
        { class: "chip-set" },
        teams.map((team) => {
          return el(
            "button",
            {
              type: "button",
              class: "chip chip-toggle chip-accent",
              "aria-pressed": autoscrimTargets.has(team.id) ? "true" : "false",
              onclick: () => {
                if (autoscrimTargets.has(team.id)) {
                  autoscrimTargets.delete(team.id);
                } else {
                  autoscrimTargets.set(team.id, team);
                }
                autoscrimDirty = true;
                renderAutoscrimTargets();
                renderScrimTopTeamChips();
              },
            },
            team.name || team.id,
          );
        }),
      ),
    );
  }

  async function preloadTopSeedTeams() {
    const owner = ownTeamId() || "anon";
    const request = ++topSeedTeamsRequest;
    if (topSeededFor === `${owner}:${SCRIM_AUTO_TOP_K_DEFAULT}` && topTeamsSeed.length > 0) return;
    topSeededFor = `${owner}:${SCRIM_AUTO_TOP_K_DEFAULT}`;
    topSeedTeamsPending = true;
    renderScrimTopTeamChips();
    try {
      const ladder = await cachedPlatformApi(
        `scrim-ladder-top:${SCRIM_AUTO_TOP_K_DEFAULT}`,
        `/api/platform/ladder?${new URLSearchParams({ limit: String(SCRIM_AUTO_TOP_K_DEFAULT) }).toString()}`,
        PLATFORM_LADDER_TTL,
      );
      if (!ctx.alive() || request !== topSeedTeamsRequest) return;
      const rankings = Array.isArray(ladder?.rankings) ? ladder.rankings : [];
      const own = owner !== "anon" ? owner : "";
      const teams = [];
      const seen = new Set();
      for (const row of rankings) {
        const team = rememberTeam({
          id: row?.team_id,
          name: row?.team_name || row?.team_id,
          rating: row?.rating,
          matches_played: row?.matches_played,
        });
        if (!team || team.id === own || seen.has(team.id)) continue;
        seen.add(team.id);
        teams.push(team);
      }
      topTeamsSeed = teams.slice(0, SCRIM_AUTO_TOP_K_DEFAULT);
    } catch (error) {
      if (ctx.alive() && request === topSeedTeamsRequest && !topTeamsSeed.length) {
        topTeamsSeed = [];
      }
    } finally {
      if (!ctx.alive() || request !== topSeedTeamsRequest) return;
      topSeedTeamsPending = false;
      renderScrimTopTeamChips();
      renderAvailability();
    }
  }

  async function addTopScrimTargets() {
    if (topTeamsPending) return;
    if (!dashboard) {
      showAutoscrimError("Wait for scrim state to finish loading.");
      return;
    }
    const limit = parseTopK(autoscrimTopKInput.value);
    if (limit === null) {
      showAutoscrimError("Top teams must be a positive number.");
      return;
    }
    const request = ++topTeamsRequest;
    topTeamsPending = true;
    showAutoscrimError("");
    autoscrimTopKButton.disabled = true;
    autoscrimTopKButton.textContent = "Adding…";
    const own = ownTeamId();
    try {
      const ladder = await cachedPlatformApi(
        `scrim-ladder-top:${limit}`,
        `/api/platform/ladder?${new URLSearchParams({ limit: String(limit) }).toString()}`,
        PLATFORM_LADDER_TTL,
      );
      if (!ctx.alive() || request !== topTeamsRequest) return;
      const rankings = Array.isArray(ladder?.rankings) ? ladder.rankings : [];
      const added = new Set();
      for (const row of rankings) {
        const team = rememberTeam({
          id: row?.team_id,
          name: row?.team_name || row?.team_id,
          rating: row?.rating,
          matches_played: row?.matches_played,
        });
        if (!team) continue;
        if (team.id === own) continue;
        if (autoscrimTargets.has(team.id)) continue;
        autoscrimTargets.set(team.id, team);
        added.add(team.id);
        autoscrimDirty = true;
        if (added.size >= limit) break;
      }
      if (added.size === 0) {
        showAutoscrimError(`No new teams available in top ${limit}.`);
      }
      renderAutoscrimTargets();
      renderScrimTopTeamChips();
    } catch (err) {
      if (ctx.alive() && request === topTeamsRequest) {
        showAutoscrimError(errorMessage(err));
      }
    } finally {
      if (!ctx.alive() || request !== topTeamsRequest) return;
      topTeamsPending = false;
      autoscrimTopKButton.disabled = false;
      autoscrimTopKButton.textContent = "Add top teams";
      renderAvailability();
    }
  }

  function displayTeam(team, fallbackId = "") {
    const remembered = rememberTeam(team);
    if (remembered) return remembered;
    const id = canonicalScrimUuid(fallbackId);
    return id ? knownTeams.get(id) || { id, name: "" } : { id: "", name: "Unknown team" };
  }

  function renderMapPicker(slot, selected, onChange) {
    const available = [...new Set([
      ...allowedMaps,
      ...selected,
    ])].sort((left, right) => left.localeCompare(right));
    const label = selected.size
      ? `${selected.size}/${SCRIM_MAP_MAX} selected · ${available.length} available`
      : `Random from all ${available.length} maps`;
    const clear = selected.size
      ? btn("Random", {
          class: "btn btn-xs btn-ghost",
          title: "Clear map choices and let FCode choose random maps",
          onclick: () => {
            selected.clear();
            onChange();
            renderMapPickers();
          },
        })
      : null;
    if (!available.length) {
      fill(
        slot,
        el("div", { class: "row wrap" }, el("span", { class: "field-hint", text: "Random maps (official map list unavailable)" })),
      );
      return;
    }
    const chips = available.map((name) => {
      const map = mapPreviews.get(name) || { name };
      const chip = el(
        "button",
        {
          class: "chip chip-toggle",
          type: "button",
          "aria-pressed": selected.has(name) ? "true" : "false",
          onclick: () => {
            if (selected.has(name)) selected.delete(name);
            else if (selected.size >= SCRIM_MAP_MAX) {
              toast(`Choose at most ${SCRIM_MAP_MAX} maps`, "error");
              return;
            } else selected.add(name);
            onChange();
            renderMapPickers();
          },
        },
        name,
        map.width
          ? [" ", el("span", { class: "chip-dim" }, `${map.width}×${map.height}`)]
          : null,
      );
      mapPreview.bind(chip, map);
      return chip;
    });
    fill(
      slot,
      el(
        "div",
        { class: "map-picker-head" },
        el("span", { class: "field-hint", text: label }),
        clear,
      ),
      el(
        "div",
        { class: "chip-set", role: "group", "aria-label": "Official FCode maps" },
        chips,
      ),
    );
  }

  function renderMapPickers() {
    mapPreview.hide();
    renderMapPicker(manualMapSlot, manualMaps, () => {});
    renderMapPicker(autoscrimMapSlot, autoscrimMaps, () => { autoscrimDirty = true; });
  }

  function renderAutoscrimTargets() {
    if (!autoscrimTargets.size) {
      fill(autoscrimTargetsSlot, el("span", { class: "field-hint", text: "No target teams yet." }));
      return;
    }
    fill(
      autoscrimTargetsSlot,
      el(
        "div",
        { class: "chip-set", "aria-label": "Autoscrim target teams" },
        [...autoscrimTargets.values()].map((team) =>
          el(
            "span",
            { class: "chip chip-accent", title: team.id },
            team.name || team.id.slice(0, 8),
            el("button", {
              class: "fcode-chip-clear",
              type: "button",
              text: "×",
              "aria-label": `Remove ${team.name || team.id} from autoscrim targets`,
              onclick: () => {
                autoscrimTargets.delete(team.id);
                autoscrimDirty = true;
                renderAutoscrimTargets();
              },
            }),
          ),
        ),
      ),
    );
  }

  function deadlineNode(value, prefix = "retry") {
    const at = scrimTimestamp(value);
    return at === null
      ? null
      : el("time", {
          class: "num",
          datetime: new Date(at).toISOString(),
          "data-scrim-deadline": String(at),
          "data-scrim-prefix": prefix,
          text: `${prefix} ${scrimCountdown(at)}`,
        });
  }

  // One sentence per state, written so the tab answers "is it still scrimming?"
  // at a glance. `tone` drives the colour; `action` is the one thing worth
  // clicking from here.
  function autoscrimStatus() {
    const auto = dashboard?.autoscrim || {};
    const state = String(auto.state || (auto.enabled ? "ready" : "off"));
    const error = scrimErrorText(auto.last_error);
    if (!dashboard) return { state, tone: "idle", label: "Loading…" };
    if (dashboard.session?.authenticated !== true) {
      return { state, tone: "warn", label: "Not signed in to FCode", detail: "Run fcode login on this machine." };
    }
    if (state === "paused") {
      return {
        state,
        tone: "bad",
        label: auto.blocked_reason || "Autoscrim is paused",
        detail: error,
        action: "resume",
      };
    }
    if (!auto.enabled) {
      return { state, tone: "idle", label: "Autoscrim is off", detail: "Add opponents and switch it on to scrim continuously." };
    }
    if (state === "backoff") {
      return auto.rate_limited
        ? {
            state,
            tone: "wait",
            label: "Waiting for the shared FCode quota",
            detail: error,
            countdown: auto.backoff_until,
            action: "pause",
          }
        : {
            state,
            tone: "warn",
            label: "Retrying after a failed request",
            detail: error,
            countdown: auto.backoff_until,
            action: "pause",
          };
    }
    if (state === "submitting") return { state, tone: "good", label: "Sending a scrim request…", action: "pause" };
    if (state === "waiting") {
      return { state, tone: "good", label: "Scrim queued, waiting on FCode", countdown: auto.next_attempt_at, action: "pause" };
    }
    if (state === "coverage_complete") {
      return { state, tone: "good", label: "Every opponent has been covered", action: "pause" };
    }
    return {
      state,
      tone: "good",
      label: "Scrimming",
      detail: error,
      countdown: auto.next_attempt_at,
      action: "pause",
    };
  }

  function autoscrimStateText(auto) {
    const stateName = String(auto?.state || (auto?.enabled ? "ready" : "off")).replace(/_/g, " ");
    return stateName.charAt(0).toUpperCase() + stateName.slice(1);
  }

  function renderBanner() {
    const status = autoscrimStatus();
    const countdown = status.countdown ? deadlineNode(status.countdown, status.tone === "wait" ? "resumes" : "next") : null;
    // A paused session is the one state the tab cannot recover from on its own,
    // so it always carries the button that restarts it.
    const action = status.action === "resume"
      ? btn("Resume autoscrim", {
          class: "btn btn-sm btn-primary",
          disabled: autoscrimPending || !dashboard,
          onclick: () => {
            autoscrimEnabled.checked = true;
            autoscrimDirty = true;
            void saveAutoscrim({ restoreEnabled: false });
          },
        })
      : status.action === "pause"
        ? btn("Pause", {
            class: "btn btn-sm btn-ghost",
            disabled: autoscrimPending || !dashboard,
            title: "Stop scheduling new autoscrim requests",
            onclick: () => {
              autoscrimEnabled.checked = false;
              void saveAutoscrim({ restoreEnabled: true, disableOnly: true, preserveDraft: true });
            },
          })
        : null;
    fill(
      bannerSlot,
      el(
        "div",
        { class: "scrim-banner", "data-tone": status.tone },
        el("span", { class: "scrim-banner-dot", "aria-hidden": "true" }),
        el(
          "div",
          { class: "scrim-banner-text" },
          el("strong", { text: status.label }),
          status.detail ? el("span", { class: "scrim-banner-detail", text: status.detail }) : null,
        ),
        countdown,
        action,
      ),
    );
  }

  function renderSummary() {
    const session = dashboard?.session || {};
    const own = session.team || {};
    const submission = dashboard?.active_submission || null;
    const auto = dashboard?.autoscrim || {};
    const summary = dashboard?.summary || {};
    const authenticated = session.authenticated === true;
    fill(
      sessionSlot,
      authenticated
        ? el(
            "span",
            { class: "fcode-auth" },
            "Signed in as ",
            el("strong", { text: own.name || "your FCode team" }),
            submission?.version !== null && submission?.version !== undefined
              ? ` · active v${submission.version}${submission.name ? ` (${submission.name})` : ""}`
              : " · no active submission",
          )
        : el(
            "span",
            { class: "fcode-auth fcode-auth-warn" },
            "Not signed in. Run ",
            code("fcode login"),
            " to request scrims.",
          ),
    );
    view.setSub(
      submission?.version !== null && submission?.version !== undefined
        ? `active v${submission.version}`
        : "official unrated matches",
    );

    const matchWins = scrimFiniteNumber(summary.match_wins ?? summary.wins);
    const matchLosses = scrimFiniteNumber(summary.match_losses ?? summary.losses);
    const matchDraws = scrimFiniteNumber(summary.match_draws ?? summary.draws);
    const gamesWon = scrimFiniteNumber(summary.games_won ?? summary.game_wins);
    const gamesLost = scrimFiniteNumber(summary.games_lost ?? summary.game_losses);
    const gamesDrawn = scrimFiniteNumber(summary.games_drawn ?? summary.game_draws);
    let winRate = scrimFiniteNumber(summary.win_rate);
    if (winRate === null && gamesWon !== null && gamesLost !== null) {
      const total = gamesWon + gamesLost + (gamesDrawn ?? 0);
      winRate = total > 0 ? gamesWon / total : NaN;
    }
    // The banner already narrates autoscrim, so this row spends its space on the
    // shared quota instead -- the number that actually explains a quiet period.
    const quota = dashboard?.quota || {};
    const quotaLimit = scrimFiniteNumber(quota.limit);
    const quotaUsed = scrimFiniteNumber(quota.used);
    fill(
      summarySlot,
      statTile(
        "Active bot",
        submission?.version !== null && submission?.version !== undefined ? `v${submission.version}` : "–",
        submission?.name || submission?.status || "",
      ),
      statTile(
        "FCode quota",
        quotaLimit !== null ? `${quotaUsed ?? 0}/${quotaLimit}` : "–",
        quotaWindowText(quota),
      ),
      statTile(
        "Matches W-L-D",
        matchWins !== null ? wldSpan(matchWins, matchLosses ?? 0, matchDraws ?? 0) : "–",
      ),
      statTile(
        "Games W-L-D",
        gamesWon !== null ? wldSpan(gamesWon, gamesLost ?? 0, gamesDrawn ?? 0) : "–",
      ),
      statTile("Game win rate", fmt.pct(winRate)),
    );
  }

  function renderVersions() {
    const activeVersion = dashboard?.active_submission?.version;
    const parsedActiveVersion = scrimFiniteNumber(activeVersion);
    const hasActiveVersion = Number.isInteger(parsedActiveVersion) && parsedActiveVersion > 0;
    const versions = [];
    const seen = new Set();
    for (const raw of Array.isArray(dashboard?.versions) ? dashboard.versions : []) {
      const version = Number(typeof raw === "object" ? raw?.version : raw);
      if (!Number.isInteger(version) || version <= 0 || seen.has(version)) continue;
      seen.add(version);
      versions.push({ version, name: typeof raw === "object" ? String(raw?.name || "") : "" });
    }
    if (hasActiveVersion && !seen.has(parsedActiveVersion)) {
      versions.push({ version: parsedActiveVersion, name: dashboard?.active_submission?.name || "" });
    }
    versions.sort((left, right) => right.version - left.version);
    const options = [
      el("option", {
        value: "current",
        text: hasActiveVersion ? `Current · v${parsedActiveVersion}` : "Current version",
      }),
      ...versions.map((row) =>
        el("option", {
          value: String(row.version),
          text: `v${row.version}${row.name ? ` · ${row.name}` : ""}`,
        }),
      ),
    ];
    fill(versionSelect, options);
    if ([...versionSelect.options].some((option) => option.value === selectedVersion)) {
      versionSelect.value = selectedVersion;
    } else {
      selectedVersion = "current";
      versionSelect.value = selectedVersion;
    }
  }

  function renderOpponentStats() {
    const rows = Array.isArray(dashboard?.by_opponent) ? dashboard.by_opponent : [];
    if (!rows.length) {
      fill(
        opponentStatsSlot,
        emptyState({
          title: "No finished scrims for this bot version",
          hint: ["Request one above, or add opponents and switch autoscrim on."],
        }),
      );
      return;
    }
    const tbody = el("tbody");
    for (const row of rows) {
      const opponent = displayTeam(row.opponent, row.opponent_team_id);
      const wins = Number(row.match_wins ?? row.wins) || 0;
      const losses = Number(row.match_losses ?? row.losses) || 0;
      const draws = Number(row.match_draws ?? row.draws) || 0;
      const gamesWon = Number(row.games_won ?? row.game_wins) || 0;
      const gamesLost = Number(row.games_lost ?? row.game_losses) || 0;
      const gamesDrawn = Number(row.games_drawn ?? row.game_draws) || 0;
      const opponentVersions = Array.isArray(row.opponent_versions)
        ? row.opponent_versions
        : row.opponent_version !== null && row.opponent_version !== undefined
          ? [row.opponent_version]
          : [];
      let winRate = scrimFiniteNumber(row.win_rate);
      const gameTotal = gamesWon + gamesLost + gamesDrawn;
      if (winRate === null) winRate = gameTotal ? gamesWon / gameTotal : NaN;
      tbody.appendChild(
        el(
          "tr",
          null,
          el("td", { title: opponent.id, text: opponent.name || opponent.id }),
          el("td", {
            class: "num mute",
            text: opponentVersions.length ? opponentVersions.map((version) => `v${version}`).join(", ") : "–",
          }),
          el("td", { class: "num" }, wldSpan(wins, losses, draws)),
          el("td", { class: "num" }, wldSpan(gamesWon, gamesLost, gamesDrawn)),
          el("td", { class: "num strong", text: fmt.pct(winRate) }),
          el("td", { class: "col-time" }, platformRelativeTime(row.last_played_at || row.completed_at)),
        ),
      );
    }
    fill(
      opponentStatsSlot,
      tableWrap(
        el(
          "table",
          { class: "table table-compact scrim-opponent-table" },
          el(
            "thead",
            null,
            el(
              "tr",
              null,
              el("th", { text: "Opponent" }),
              el("th", { text: "Their bot" }),
              el("th", { class: "num", text: "Matches W-L-D" }),
              el("th", { class: "num", text: "Games W-L-D" }),
              el("th", { class: "num", text: "Win rate" }),
              el("th", { text: "Last" }),
            ),
          ),
          tbody,
        ),
      ),
    );
  }

  function requestOpponent(request) {
    return displayTeam(
      request?.opponent,
      request?.opponent_team_id || request?.opponent?.id,
    );
  }

  function requestVersions(request) {
    const ours = request?.our_submission?.version ?? request?.our_version;
    const theirs = request?.opponent_version;
    const pinned = request?.source_match_id || request?.opponent_source_match_id;
    return `${ours !== null && ours !== undefined ? `v${ours}` : "v?"} vs ${
      theirs !== null && theirs !== undefined ? `v${theirs}` : pinned ? "pinned" : "latest"
    }`;
  }

  function renderHistory() {
    const requests = Array.isArray(dashboard?.requests) ? dashboard.requests : [];
    if (!requests.length) {
      fill(
        historySlot,
        emptyState({
          title: "No scrim requests yet",
          hint: ["Every attempt lands here, including the ones that fail."],
        }),
      );
      return;
    }
    const tbody = el("tbody");
    for (const request of requests) {
      const opponent = requestOpponent(request);
      const status = String(request.status || request.state || "unknown").toLowerCase();
      const error = scrimErrorText(request.error || request.last_error);
      const scoreFor = scrimFiniteNumber(request.score_for);
      const scoreAgainst = scrimFiniteNumber(request.score_against);
      const score = scoreFor !== null && scoreAgainst !== null
        ? `${scoreFor}–${scoreAgainst}`
        : "–";
      const maps = normalizeScrimMaps(request.map_names);
      const matchId = canonicalScrimUuid(request.match_id);
      tbody.appendChild(
        el(
          "tr",
          { "data-status": status },
          el("td", { class: "col-time" }, platformRelativeTime(request.requested_at || request.created_at)),
          el(
            "td",
            { class: "scrim-history-who" },
            el("span", { title: opponent.id, text: opponent.name || opponent.id }),
            // The source is a property of the row, not a column of its own.
            request.source === "auto"
              ? el("span", { class: "badge scrim-source", text: "auto" })
              : null,
          ),
          el("td", { class: "num", text: requestVersions(request) }),
          el("td", { class: "scrim-history-maps", text: maps.length ? maps.join(", ") : "random", title: maps.join(", ") }),
          el("td", { class: "num strong", text: score }),
          // Status and its explanation belong together: an error alone reads as
          // noise, and a status alone hides why a request stopped.
          el(
            "td",
            { class: "scrim-history-state" },
            el("span", { class: "badge scrim-status", "data-status": status, text: status.replace(/_/g, " ") }),
            error
              ? el("span", { class: "scrim-history-error", text: error, title: error })
              : null,
          ),
          el(
            "td",
            { class: "col-action" },
            matchId
              ? el("a", {
                  class: "btn btn-xs btn-ghost",
                  href: platformViewHash(matchId, 1),
                  text: "View",
                  title: "Open this match in the FCode viewer",
                })
              : null,
          ),
        ),
      );
    }
    fill(
      historySlot,
      tableWrap(
        el(
          "table",
          { class: "table table-compact scrim-history-table" },
          el(
            "thead",
            null,
            el(
              "tr",
              null,
              el("th", { text: "When" }),
              el("th", { text: "Opponent" }),
              el("th", { text: "Versions" }),
              el("th", { text: "Maps" }),
              el("th", { class: "num", text: "Score" }),
              el("th", { text: "Status" }),
              el("th", { text: "" }),
            ),
          ),
          tbody,
        ),
      ),
    );
  }

  function targetNames(auto) {
    const raw = auto?.target_team_names;
    if (raw && !Array.isArray(raw) && typeof raw === "object") return raw;
    const names = {};
    if (Array.isArray(raw)) {
      (Array.isArray(auto?.target_team_ids) ? auto.target_team_ids : []).forEach((id, index) => {
        if (raw[index]) names[id] = raw[index];
      });
    }
    for (const team of Array.isArray(auto?.target_teams) ? auto.target_teams : []) {
      const id = canonicalScrimUuid(team?.id);
      if (id && team?.name) names[id] = team.name;
    }
    return names;
  }

  function syncAutoscrimDraft() {
    if (autoscrimDraftLoaded && autoscrimDirty) return;
    const auto = dashboard?.autoscrim || {};
    const names = targetNames(auto);
    autoscrimTargets.clear();
    for (const rawId of Array.isArray(auto.target_team_ids) ? auto.target_team_ids : []) {
      const id = canonicalScrimUuid(rawId);
      if (!id) continue;
      const known = knownTeams.get(id);
      autoscrimTargets.set(id, { id, name: String(names[id] || known?.name || "") });
    }
    autoscrimMaps.clear();
    for (const name of normalizeScrimMaps(auto.map_names)) autoscrimMaps.add(name);
    autoscrimEnabled.checked = auto.enabled === true;
    autoscrimDraftLoaded = true;
    autoscrimDirty = false;
  }

  function requestBlockReason() {
    if (!dashboard) return "Loading scrim state…";
    const session = dashboard.session || {};
    if (session.authenticated !== true) return "Sign in with fcode login first.";
    const submission = dashboard.active_submission;
    if (!submission) return "No active FCode submission.";
    if (submission.status && submission.status !== "ready") {
      return `Active submission is ${String(submission.status).replace(/_/g, " ")}.`;
    }
    const auto = dashboard.autoscrim || {};
    // A local cooldown delays dispatch; it does not prevent safely persisting a
    // manual request. Unknown outcomes and authentication problems still block.
    if (auto.can_request === false && String(auto.state || "") !== "backoff") {
      return auto.blocked_reason || scrimErrorText(auto.last_error) || "Scrim requests are temporarily unavailable.";
    }
    return "";
  }

  function renderAutoscrimState() {
    const auto = dashboard?.autoscrim || {};
    const error = scrimErrorText(auto.last_error);
    const backoff = deadlineNode(auto.backoff_until, "retry");
    const next = !backoff ? deadlineNode(auto.next_attempt_at, "next") : null;
    fill(
      autoscrimStateSlot,
      el("span", {
        class: `badge scrim-status${error ? " scrim-status-error" : ""}`,
        "data-status": String(auto.state || (auto.enabled ? "ready" : "off")),
        text: autoscrimStateText(auto),
        title: error,
      }),
      backoff || next,
    );
  }

  function renderAvailability() {
    const reason = requestBlockReason();
    manualForm.inert = manualPending || !dashboard;
    manualSubmit.disabled = manualPending || Boolean(reason);
    manualSubmit.textContent = manualPending ? "Requesting…" : "Request scrim";
    const backoff = scrimTimestamp(dashboard?.autoscrim?.backoff_until);
    const rateLimitHint = String(dashboard?.autoscrim?.state || "") === "backoff"
      && backoff !== null
      && backoff > Date.now()
      ? `Queued now, sent ${scrimCountdown(backoff)} when the quota frees up.`
      : "";
    manualBlocked.textContent = reason
      || rateLimitHint
      || "Five games, unrated, played with your active FCode submission.";
    for (const control of manualForm.querySelectorAll("input, button")) {
      if (control !== manualSubmit) control.disabled = manualPending || !dashboard;
    }
    const refreshing = refreshPending || dashboard?.refreshing === true;
    refreshButton.disabled = refreshing;
    refreshButton.textContent = refreshing ? "Refreshing…" : "Refresh";
    autoscrimForm.inert = autoscrimPending || !dashboard;
    for (const control of autoscrimForm.querySelectorAll("input, button")) {
      control.disabled = autoscrimPending || !dashboard;
    }
    if (topTeamsPending) {
      autoscrimTopKButton.disabled = true;
      autoscrimTopKInput.disabled = true;
      autoscrimTopKButton.textContent = "Adding…";
    } else {
      autoscrimTopKButton.disabled = !dashboard;
      autoscrimTopKInput.disabled = !dashboard;
      autoscrimTopKButton.textContent = "Add top teams";
    }
    saveAutoscrimButton.disabled = autoscrimPending || !dashboard;
    saveAutoscrimButton.textContent = autoscrimPending ? "Saving…" : "Save autoscrim";
    autoscrimEnabled.disabled = autoscrimPending || !dashboard;
  }

  function refreshClocks() {
    for (const node of root.querySelectorAll("time[data-platform-relative-time]")) {
      node.textContent = fmt.ago(node.getAttribute("datetime") || "");
    }
    for (const node of root.querySelectorAll("time[data-scrim-deadline]")) {
      const deadline = Number(node.dataset.scrimDeadline);
      const prefix = node.dataset.scrimPrefix || "retry";
      node.textContent = `${prefix} ${scrimCountdown(deadline)}`;
    }
    renderAvailability();
  }

  function ingestDashboardTeams(data) {
    for (const row of Array.isArray(data?.by_opponent) ? data.by_opponent : []) {
      rememberTeam(row.opponent || { id: row.opponent_team_id, name: row.opponent_team_name });
    }
    for (const request of Array.isArray(data?.requests) ? data.requests : []) {
      rememberTeam(request.opponent || {
        id: request.opponent_team_id,
        name: request.opponent_team_name,
      });
    }
  }

  function renderDashboard() {
    ingestDashboardTeams(dashboard);
    syncAutoscrimDraft();
    void preloadTopSeedTeams();
    renderBanner();
    renderSummary();
    renderVersions();
    renderAutoscrimTargets();
    renderScrimTopTeamChips();
    renderMapPickers();
    renderAutoscrimState();
    renderOpponentStats();
    renderHistory();
    renderAvailability();
    refreshClocks();
  }

  async function loadDashboard({ quiet = true } = {}) {
    const request = ++dashboardRequest;
    if (!quiet && !dashboard) {
      fill(summarySlot, skeletonRows(2));
      fill(opponentStatsSlot, skeletonRows(6));
      fill(historySlot, skeletonRows(8));
    }
    try {
      const query = new URLSearchParams({
        limit: "100",
        our_version: selectedVersion,
      });
      const data = await api(`/api/platform/scrims?${query.toString()}`);
      if (!ctx.alive() || request !== dashboardRequest) return null;
      dashboard = data && typeof data === "object" ? data : {};
      renderDashboard();
      return dashboard;
    } catch (err) {
      if (!ctx.alive() || request !== dashboardRequest) return null;
      if (quiet && dashboard) return null;
      fill(
        summarySlot,
        emptyState({
          title: Number(err?.status) === 401 ? "Sign in to use scrims" : "Could not load scrims",
          hint: [Number(err?.status) === 401 ? ["Run ", code("fcode login"), "."] : errorMessage(err)],
          actions: [btn("Retry", { onclick: () => void loadDashboard({ quiet: false }) })],
        }),
      );
      fill(opponentStatsSlot);
      fill(historySlot);
      return null;
    }
  }

  async function loadOfficialMaps() {
    const request = ++mapsRequest;
    const [platformResult, localResult] = await Promise.allSettled([
      api("/api/platform/maps"),
      api("/api/maps"),
    ]);
    if (!ctx.alive() || request !== mapsRequest) return;
    if (platformResult.status === "fulfilled") {
      allowedMaps = (Array.isArray(platformResult.value?.maps) ? platformResult.value.maps : [])
        .map((row) => String(row?.name || row || "").trim())
        .filter(Boolean);
    }
    if (localResult.status === "fulfilled" && Array.isArray(localResult.value)) {
      mapPreviews = new Map(
        localResult.value.map((map) => [String(map?.name || ""), map]),
      );
    }
    renderMapPickers();
  }

  async function refreshOfficial({ reportError = false } = {}) {
    if (refreshPending) return false;
    refreshPending = true;
    renderAvailability();
    try {
      await api("/api/platform/scrims/refresh", { method: "POST", body: {} });
      if (!ctx.alive()) return;
      await loadDashboard({ quiet: true });
      return true;
    } catch (err) {
      if (ctx.alive() && reportError) toast(`Could not refresh scrims: ${errorMessage(err)}`, "error");
      return false;
    } finally {
      refreshPending = false;
      if (ctx.alive()) renderAvailability();
    }
  }

  manualForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (manualPending) return;
    if (!dashboard) {
      showManualError("Wait for scrim state to finish loading.");
      return;
    }
    showManualError("");
    try {
      const opponent = manualPicker.value();
      let requestKey = manualRequestKey || newScrimRequestKey();
      let payload = buildScrimRequest({
        requestKey,
        opponentTeamId: opponent?.id || manualPicker.input.value,
        opponentTeamName: opponent?.name || "",
        sourceMatchId: sourceMatchInput.value,
        mapNames: [...manualMaps],
        ownTeamId: ownTeamId(),
      });
      const fingerprint = JSON.stringify({ ...payload, request_key: undefined });
      if (manualRequestFingerprint !== null && manualRequestFingerprint !== fingerprint) {
        requestKey = newScrimRequestKey();
        payload = { ...payload, request_key: requestKey };
      }
      manualRequestKey = requestKey;
      manualRequestFingerprint = fingerprint;
      manualPending = true;
      renderAvailability();
      const response = await api("/api/platform/scrims", { method: "POST", body: payload });
      if (!ctx.alive()) return;
      const request = response?.request || response;
      const matchId = canonicalScrimUuid(request?.match_id);
      const requestState = String(request?.status || "");
      const isRateLimitedNow = String(dashboard?.autoscrim?.state || "") === "backoff"
        && scrimTimestamp(dashboard?.autoscrim?.backoff_until) !== null
        && scrimTimestamp(dashboard?.autoscrim?.backoff_until) > Date.now();
      manualRequestKey = null;
      manualRequestFingerprint = null;
      if (isRateLimitedNow || requestState === "rate_limited") {
        toast("Scrim request accepted and will retry after rate limit backoff.", "warn");
      } else if (matchId) {
        toast("Scrim queued", "ok");
      } else {
        toast("Scrim request recorded", "ok");
      }
      await loadDashboard({ quiet: true });
    } catch (err) {
      if (!ctx.alive()) return;
      const message = errorMessage(err);
      const isRateLimited = Number(err?.status) === 429 || /rate limit/i.test(message);
      if (isRateLimited) {
        toast("Scrim request rate-limited; queued for retry.", "warn");
        if (ctx.alive()) showManualError("");
        return;
      }
      if (ctx.alive()) showManualError(message);
    } finally {
      manualPending = false;
      if (ctx.alive()) renderAvailability();
    }
  });

  async function saveAutoscrim({
    restoreEnabled = null,
    disableOnly = false,
    preserveDraft = false,
  } = {}) {
    if (autoscrimPending) return false;
    showAutoscrimError("");
    if (!dashboard) {
      showAutoscrimError("Wait for scrim state to finish loading.");
      return false;
    }
    try {
      const payload = disableOnly
        ? { enabled: false }
        : buildAutoscrimConfig({
            enabled: autoscrimEnabled.checked,
            targetTeams: [...autoscrimTargets.values()],
            mapNames: [...autoscrimMaps],
            ownTeamId: ownTeamId(),
          });
      autoscrimPending = true;
      renderAvailability();
      const response = await api("/api/platform/scrims/autoscrim", {
        method: "POST",
        body: payload,
      });
      if (!ctx.alive()) return false;
      if (!disableOnly || !preserveDraft) autoscrimDirty = false;
      const saved = response?.settings || response?.autoscrim;
      if (saved && dashboard) {
        dashboard = { ...dashboard, autoscrim: saved };
        renderDashboard();
      }
      toast(payload.enabled ? "Autoscrim enabled" : "Autoscrim settings saved", "ok");
      await loadDashboard({ quiet: true });
      return true;
    } catch (err) {
      if (restoreEnabled !== null) autoscrimEnabled.checked = restoreEnabled;
      if (ctx.alive()) showAutoscrimError(errorMessage(err));
      return false;
    } finally {
      autoscrimPending = false;
      if (ctx.alive()) renderAvailability();
    }
  }

  autoscrimEnabled.addEventListener("change", () => {
    const previous = !autoscrimEnabled.checked;
    const preserveDraft = autoscrimDirty;
    autoscrimDirty = true;
    void saveAutoscrim({
      restoreEnabled: previous,
      disableOnly: autoscrimEnabled.checked === false,
      preserveDraft,
    });
  });
  autoscrimTopKButton.addEventListener("click", () => {
    void addTopScrimTargets();
  });
  saveAutoscrimButton.addEventListener("click", () => {
    autoscrimDirty = true;
    void saveAutoscrim();
  });

  renderAutoscrimTargets();
  renderScrimTopTeamChips();
  renderMapPickers();
  renderAvailability();
  ctx.timer(refreshClocks, SCRIM_CLOCK_MS);
  ctx.timer(() => void loadDashboard({ quiet: true }), SCRIM_POLL_MS);
  ctx.on("platform_scrim", () => void loadDashboard({ quiet: true }));
  void loadOfficialMaps();
  void preloadTopSeedTeams();
  void (async () => {
    // Paint persisted local state first. The one initial refresh then imports
    // existing/live official scrims without making ordinary polling upstream.
    await loadDashboard({ quiet: false });
    if (ctx.alive() && !scrimInitialRefreshIssued) {
      scrimInitialRefreshIssued = await refreshOfficial();
    }
  })();
});

/* -------------------------------------------------------------------------- */

/* 10. Storage                                                                 */
/* -------------------------------------------------------------------------- */

const storage = mount("storage", (root, params, ctx) => {
  const slot = el("div", { class: "stack" }, skeletonRows(3));
  const view = viewRoot(
    { title: "Storage", sub: "disk used by this arena" },
    slot,
  );
  root.appendChild(view);

  function render(data) {
    const replay = data.replays || {};
    const logs = data.logs || {};
    const temporary = data.temporary || {};
    const database = data.database || {};
    const retained = Number(replay.retained) || 0;
    const replayBytes = Number(replay.bytes) || 0;
    const capped = replay.budget_bytes !== null && replay.budget_bytes !== undefined
      && Number.isFinite(Number(replay.budget_bytes));
    const budgetBytes = capped ? Number(replay.budget_bytes) : 0;
    const usage = capped && budgetBytes > 0 ? Math.min(100, (replayBytes / budgetBytes) * 100) : 0;
    const total = replayBytes + (Number(logs.bytes) || 0)
      + (Number(database.bytes) || 0) + (Number(temporary.bytes) || 0);

    // -- delete now ---------------------------------------------------------
    // Two clicks, because this is the one control on the page that destroys
    // data: the second click states exactly what is about to happen.
    let armed = false;
    const keep = el("input", {
      class: "input num storage-number",
      type: "number",
      min: "0",
      max: String(retained),
      step: "1",
      value: String(Math.min(retained, 100)),
      disabled: retained === 0,
      "aria-label": "Newest replays to keep",
    });
    const purge = btn("Delete the rest", {
      class: "btn btn-danger",
      disabled: retained === 0,
      onclick: async (event) => {
        const button = event.currentTarget;
        const count = Math.max(0, Math.min(retained, Math.round(Number(keep.value) || 0)));
        if (!armed) {
          armed = true;
          button.textContent = `Delete ${fmt.int(Math.max(0, retained - count))} replays`;
          return;
        }
        button.disabled = true;
        try {
          const result = await api("/api/storage/replays", { method: "POST", body: { keep: count } });
          toast(`Deleted ${fmt.int(result.removed)} replays, freed ${fmtBytes(result.freed)}`, "ok");
          render(result.storage || data);
        } catch (err) {
          toast(errorMessage(err), "error");
          button.disabled = false;
        }
      },
    });
    keep.addEventListener("input", () => {
      armed = false;
      purge.textContent = "Delete the rest";
    });

    // -- automatic pruning --------------------------------------------------
    const budgetInput = el("input", {
      class: "input num storage-number",
      type: "number",
      min: "0",
      step: "1",
      // Re-enabling a previously uncapped budget should choose a safe ordinary
      // cap, never silently turn into 0 MB (which would delete every replay).
      value: capped ? String(replay.budget_mb) : "512",
      disabled: !capped,
      "aria-label": "Replay budget in megabytes",
    });
    const unlimited = el("input", {
      type: "checkbox",
      checked: !capped,
      "aria-label": "Keep every replay",
      onchange: (event) => { budgetInput.disabled = event.currentTarget.checked; },
    });
    const saveBudget = btn("Save", {
      class: "btn",
      onclick: async (event) => {
        const button = event.currentTarget;
        const budget = unlimited.checked ? null : Math.max(0, Math.round(Number(budgetInput.value) || 0));
        button.disabled = true;
        try {
          const result = await api("/api/storage/budget", { method: "POST", body: { budget_mb: budget } });
          state.config = { ...(state.config || {}), replay_budget_mb: result.budget_mb };
          toast(budget === null ? "Keeping every replay" : `Replay budget set to ${budget} MB`, "ok");
          render(result.storage || data);
        } catch (err) {
          toast(errorMessage(err), "error");
          button.disabled = false;
        }
      },
    });

    view.setSub(`${fmtBytes(total)} on disk`);
    fill(
      slot,
      // Where the space went, in one row, biggest first.
      el(
        "div",
        { class: "stats" },
        statTile("Replays", fmtBytes(replayBytes), `${fmt.int(retained)} kept`),
        statTile("Logs", fmtBytes(logs.bytes)),
        statTile("Database", fmtBytes(database.bytes)),
        statTile("Temporary", fmtBytes(temporary.bytes)),
      ),
      card(
        { title: "Replays" },
        el(
          "p",
          { class: "mute" },
          "Deleting a replay only removes its 2D playback. Results, ratings, source history and logs are untouched.",
        ),
        capped
          ? el(
              "div",
              { class: "storage-meter-wrap" },
              el(
                "div",
                {
                  class: "storage-meter",
                  role: "progressbar",
                  "aria-valuemin": "0",
                  "aria-valuemax": "100",
                  "aria-valuenow": String(Math.round(usage)),
                  "data-over": replayBytes > budgetBytes ? "true" : null,
                },
                el("span", { style: { width: `${usage}%` } }),
              ),
              el("span", {
                class: "small mute",
                text: replayBytes > budgetBytes
                  ? `${fmtBytes(replayBytes)} kept, over the ${fmtBytes(budgetBytes)} budget until the next prune`
                  : `${fmtBytes(replayBytes)} of the ${fmtBytes(budgetBytes)} budget used`,
              }),
            )
          : null,
        el(
          "div",
          { class: "row wrap storage-controls" },
          el("label", { class: "field-label", text: "Budget (MB)" }),
          budgetInput,
          el(
            "label",
            { class: "toggle" },
            unlimited,
            el("span", { class: "toggle-track" }, el("span", { class: "toggle-thumb" })),
            el("span", { class: "toggle-label", text: "Keep everything" }),
          ),
          saveBudget,
        ),
        el("p", {
          class: "small mute",
          text: capped
            ? "Oldest replays are pruned automatically once finished games push past the budget."
            : "Nothing is pruned automatically. Replays grow until you delete them below.",
        }),
        el(
          "div",
          { class: "row wrap storage-controls" },
          el("label", { class: "field-label", text: "Keep the newest" }),
          keep,
          purge,
        ),
      ),
      card(
        { title: "Danger zone" },
        el(
          "p",
          { class: "mute" },
          "Reset the ladder on its own, or erase every game, replay, log and tracked bot version. Your bot directories and maps are never touched.",
        ),
        el(
          "div",
          { class: "row wrap storage-controls" },
          btn("Reset arena data…", {
            class: "btn btn-danger",
            title: "Choose how much arena data to reset",
            onclick: () => globalThis.oarena?.openResetDialog?.(),
          }),
        ),
      ),
    );
  }

  async function load() {
    try {
      const data = await api("/api/storage");
      if (ctx.alive()) render(data || {});
    } catch (err) {
      if (ctx.alive()) fill(slot, emptyState({ title: "Could not read storage", hint: [errorMessage(err)] }));
    }
  }

  load();
});

/* -------------------------------------------------------------------------- */

export const views = {
  ladder,
  matrix,
  games,
  "test-runs": testRuns,
  game,
  bots,
  bot,
  maps,
  storage,
  fcode,
  scrims,
};
