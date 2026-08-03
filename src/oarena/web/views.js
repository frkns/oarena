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
  platformViewHash,
  savePlatformSelection,
} from "./platform-form.js";
import { extractProfilerReports, normaliseProfilerRecords } from "./telemetry.js";

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

let gamesFirstPageCache = null;
let gamesFirstPageInflight = null;
const matchGamesCache = new Map();

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
  gamesFirstPageInflight = api(gameQuery(EMPTY_GAME_FILTER, null))
    .then(rememberGamesFirstPage)
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
    games,
    next: games.length === PAGE ? games.at(-1)?.id ?? null : null,
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
    const failed = game.status !== "ok" || game.a_errors || game.b_errors;
    const detail = failed
      ? game.error || game.resign_message || conditionLabel(game.win_condition) || ""
      : game.resign_message || game.win_condition || "";
    const detailHref = gameFilter.tag
      ? `${gameHref(game.id)}?tag=${encodeURIComponent(gameFilter.tag)}`
      : gameHref(game.id);
    const tr = el(
      "tr",
      {
        class: "game-row" + (fresh ? " is-new" : ""),
        "data-status": game.status === "ok" && (game.a_errors || game.b_errors)
          ? "bot_error"
          : game.status,
        "data-rated": game.rated ? "true" : "false",
        "data-id": String(game.id),
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
    return parts.length ? `${shown} · ${parts.join(" · ")}` : `${shown} of ${fmt.int((state.counts && state.counts.games) || 0)}`;
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
    const applyPage = (page) => {
      rows = page.games || [];
      next = page.next || null;
      cap = Math.max(STREAM_CAP, rows.length);
      renderAll();
    };
    if (cached) applyPage(cached);
    try {
      const page = cacheable
        ? await requestGamesFirstPage({
            force:
              Boolean(cached) &&
              Date.now() - gamesFirstPageCache.at > GAMES_CACHE_MAX_AGE_MS,
          })
        : await api(gameQuery(gameFilter, null));
      if (!ctx.alive()) return;
      if (!sameGamesPage(page, cached)) applyPage(page);
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

function profilerGroup(group, game) {
  const spans = [...group.spans.values()].sort(
    (left, right) => right.self_us - left.self_us || right.total_us - left.total_us || left.name.localeCompare(right.name)
  );
  const scale = Math.max(1, ...spans.map((span) => span.total_us));
  const typeSummary = [...group.types.entries()]
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .map(([name, count]) => `${name} ×${count}`)
    .join(" · ");
  const side = group.team === "a" || group.team === "b" ? group.team : null;
  const botName = side ? game[side] : "unknown team";
  const warnings = group.interrupted + group.badNesting;

  const tbody = el("tbody");
  for (const span of spans) {
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
            el("span", { class: "profile-bar-total", style: { width: `${(span.total_us / scale) * 100}%` } }),
            el("span", { class: "profile-bar-self", style: { width: `${(span.self_us / scale) * 100}%` } })
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
            el("th", { scope: "col", class: "num", text: "Self" }),
            el("th", { scope: "col", class: "num", text: "Total" }),
            el("th", { scope: "col", class: "num", text: "Calls" }),
            el("th", { scope: "col", class: "num", text: "Avg" }),
            el("th", { scope: "col", class: "num", text: "Max" })
          )
        ),
        tbody
      )
    )
  );
}

function profilerView(reports, game) {
  const groups = aggregateProfilerReports(reports);
  return el(
    "div",
    { class: "profile-view" },
    el(
      "p",
      { class: "small mute profile-note" },
      "CPU time from surviving units that emitted a final report. Bars show self time over total time; nested spans can overlap their parents."
    ),
    ...groups.map((group) => profilerGroup(group, game))
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
  const view = viewRoot(
    {
      title: `Game #${Number.isFinite(id) ? id : "?"}`,
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

      const links = games.map((entry) => {
        const active = Number(entry.id) === id;
        const result = entry.status !== "ok"
          ? "!"
          : entry.winner === "draw" || !entry.winner
            ? "D"
            : String(entry.winner).toUpperCase();
        const ordinal = entry.batch_ordinal + 1;
        return el(
          "a",
          {
            class: `game-batch-link${active ? " is-active" : ""}`,
            href: taggedGameHref(entry.id),
            "aria-current": active ? "page" : null,
            "data-status": entry.status || "unknown",
            title: `Game ${ordinal}: ${entry.a} vs ${entry.b} on ${entry.map}`,
          },
          el("span", { class: "game-batch-number num", text: String(ordinal) }),
          el("span", { class: "game-batch-map", text: entry.map || "unknown map" }),
          el("span", { class: "game-batch-result", text: result }),
        );
      });
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
          ),
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
      fill(profilerBody, reports.length ? profilerView(reports, data) : null);
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
            "Every sub-directory of ",
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
const platformResponseCache = new Map();
const platformRecentUi = { mode: "all", teamId: "", teamName: "" };

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
      el("span", { class: "field-label", text: "Match ID or visualiser URL" }),
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
      title: officialTests ? "Finding a recent official test…" : "Finding a recent FCode match…",
      hint: ["You can also paste a match ID above."],
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

  const view = viewRoot(
    {
      title: officialTests ? "Test runs" : "FCode",
      sub: officialTests ? "official FCode tests" : "official matches",
      toolbar: [officialLink, replayLink, fullscreenButton],
    },
    el("div", { class: "panel fcode-match-loader" }, matchForm, sessionSlot),
    vizSlot,
    matchBar,
    el(
      "div",
      { class: `fcode-browse-grid${officialTests ? " is-single" : ""}` },
      card(
        { title: officialTests ? "Official test runs" : "Recent matches", actions: recentFilterSlot, flush: true },
        recentSlot,
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
    if (platformRecentUi.mode === "mine") platformRecentUi.mode = "all";
    void loadRecent({ reset: true });
  }

  function teamButton(team, match, side = null) {
    const hasScore = Number.isFinite(match?.score_a) && Number.isFinite(match?.score_b);
    const scoreWon = side === "a"
      ? match?.score_a > match?.score_b
      : side === "b" && match?.score_b > match?.score_a;
    const scoreLost = side === "a"
      ? match?.score_a < match?.score_b
      : side === "b" && match?.score_b < match?.score_a;
    const won = match?.winner_id
      ? match.winner_id === team?.id
      : Boolean(hasScore && scoreWon);
    const lost = match?.winner_id
      ? match.winner_id !== team?.id
      : Boolean(hasScore && scoreLost);
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
          " to load your recent matches and replays; the public ladder remains available.",
        ),
      );
    } else {
      fill(
        sessionSlot,
        el("span", { class: "fcode-auth" }, "Signed in as ", el("strong", { text: data.team?.name || "your FCode team" })),
      );
    }
    renderRecentFilters();
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
              void loadRecent({ reset: true });
            },
          }),
        )
      : null;
    const refresh = officialTests
      ? btn("Refresh", {
          class: "btn btn-xs btn-ghost",
          onclick: () => void loadRecent({ reset: true, quiet: true }),
        })
      : null;
    fill(recentFilterSlot, el("span", { class: "seg" }, filterButtons), teamChip, refresh);
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
    const tbody = el("tbody");
    for (const match of recentRows) {
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
            el("td", { class: "col-time", text: fmt.ago(platformMatchTimestamp(match)), title: platformMatchTimestamp(match) || "" }),
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
            el(
              "td",
              null,
              el("span", { class: "badge", text: status }),
              stage ? el("span", { class: "small mute", text: ` ${stage}` }) : null,
            ),
            el("td", { text: match.requested_by_name || "–" }),
            el("td", { class: `fcode-test-error ${match.error ? "err" : "mute"}`, text: match.error || "–", title: match.error || "" }),
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
        el("td", { class: "col-time", text: fmt.ago(platformMatchTimestamp(match)), title: platformMatchTimestamp(match) || "" }),
        el(
          "td",
          null,
          el("span", { class: "fcode-matchup" }, teamButton(teams.a, match, "a"), el("span", { class: "vs", text: "vs" }), teamButton(teams.b, match, "b")),
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
              el("th", { text: "Status / stage" }),
              el("th", { text: "Requested by" }),
              el("th", { text: "Error" }),
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

  function maybeSelectRecentMatch() {
    if (!autoSelectRecent || userSelected || activeDetail || !ctx.alive()) return;
    const first = platformRecentUi.mode === "tests"
      ? recentRows.find((match) => match?.id)
      : recentRows.find((match) => match?.status === "complete" && match?.id);
    if (first) {
      autoSelectRecent = false;
      void selectMatch({ matchId: first.id, game: 1 });
      return;
    }
    squareViewer?.hide(vizSlot);
    fill(
      vizSlot,
      emptyState({
        title: "No FCode match selected",
        hint: [
          session?.authenticated === false
            ? "Sign in with fcode login, or paste a match ID above."
            : "Paste a match ID above, or wait for a completed recent match.",
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

  async function loadRecent({ reset, quiet = false }) {
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
    try {
      const response = officialTests || cursor
        ? await api(path)
        : await cachedPlatformApi(`recent:${path}`, path, PLATFORM_CACHE_TTL);
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
          el("td", { class: "num", text: fmt.num(row.rating, 0) }),
          el("td", { class: "num mute", text: fmt.int(row.matches_played) }),
        ),
      );
    }
    const table = el(
      "table",
      { class: "table table-compact" },
      el("thead", null, el("tr", null, el("th", { class: "num", text: "#" }), el("th", { text: "Team" }), el("th", { class: "num", text: "Rating" }), el("th", { class: "num", text: "Matches" }))),
      tbody,
      Number(data?.total) > rankings.length
        ? el("caption", { text: `Top ${rankings.length} of ${fmt.int(data.total)} teams` })
        : null,
    );
    fill(ladderSlot, tableWrap(table));
  }

  async function loadLadder() {
    try {
      const data = await cachedPlatformApi(
        "ladder:100",
        "/api/platform/ladder?limit=100",
        PLATFORM_LADDER_TTL,
      );
      if (ctx.alive()) renderLadder(data);
    } catch (err) {
      if (ctx.alive()) {
        fill(
          ladderSlot,
          platformErrorState("Could not load the FCode ladder", err, [btn("Retry", { onclick: loadLadder })]),
        );
      }
    }
  }

  function renderMatchBar() {
    const detail = activeDetail;
    const match = detail?.match;
    if (!match || !activeGame) {
      matchBar.hidden = true;
      return;
    }
    const teams = platformMatchTeams(match);
    const games = new Map((detail.games || []).map((game) => [Number(game.number), game]));
    const gameButtons = [];
    for (let number = 1; number <= 5; number += 1) {
      const game = games.get(number);
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
          game?.winner_side
            ? el("span", { class: `fcode-game-result side-${String(game.winner_side).toLowerCase()}`, text: String(game.winner_side).toUpperCase() })
            : null,
        ),
      );
    }
    fill(
      matchBar,
      el(
        "div",
        { class: "fcode-score" },
        teamButton(teams.a, match, "a"),
        el("strong", { class: "fcode-score-value num", text: platformMatchScore(match) }),
        teamButton(teams.b, match, "b"),
        el("span", { class: "badge", text: platformMatchLabel(match) }),
      ),
      el("div", { class: "fcode-game-tabs", role: "group", "aria-label": "Games in this match" }, gameButtons),
      el(
        "p",
        { class: "fcode-provenance" },
        `Rendered with installed FCode${state.fcode ? ` ${state.fcode}` : ""} constants; remote replays do not include a recorded engine-metadata snapshot.`,
      ),
    );
    matchBar.hidden = false;
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
          title: "Invalid FCode match link",
          hint: [errorMessage(err), "Paste a match UUID or official visualiser URL above."],
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

/* 9. Storage                                                                  */
/* -------------------------------------------------------------------------- */

const storage = mount("storage", (root, params, ctx) => {
  const slot = el("div", { class: "stack" }, skeletonRows(3));
  const view = viewRoot({ title: "Storage", sub: "" }, slot);
  root.appendChild(view);

  function render(data) {
    const replay = data.replays || {};
    const logs = data.logs || {};
    const temporary = data.temporary || {};
    const database = data.database || {};
    const retained = Number(replay.retained) || 0;
    const capped = replay.budget_bytes !== null && replay.budget_bytes !== undefined
      && Number.isFinite(Number(replay.budget_bytes));
    const budgetBytes = capped ? Number(replay.budget_bytes) : 0;
    const usage = capped && budgetBytes > 0 ? Math.min(100, (Number(replay.bytes) / budgetBytes) * 100) : 0;
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
    const purge = btn("Delete older replays", {
      class: "btn btn-danger",
      disabled: retained === 0,
      onclick: async (event) => {
        const button = event.currentTarget;
        const count = Math.max(0, Math.min(retained, Math.round(Number(keep.value) || 0)));
        if (!armed) {
          armed = true;
          button.textContent = `Confirm: keep newest ${count}, delete ${Math.max(0, retained - count)}`;
          return;
        }
        button.disabled = true;
        try {
          const result = await api("/api/storage/replays", { method: "POST", body: { keep: count } });
          toast(`deleted ${fmt.int(result.removed)} replay(s), freed ${fmtBytes(result.freed)}`, "ok");
          render(result.storage || data);
        } catch (err) {
          toast(errorMessage(err), "error");
          button.disabled = false;
        }
      },
    });
    keep.addEventListener("input", () => {
      armed = false;
      purge.textContent = "Delete older replays";
    });

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
      "aria-label": "Disable automatic replay pruning",
      onchange: (event) => { budgetInput.disabled = event.currentTarget.checked; },
    });
    const saveBudget = btn("Save budget", {
      class: "btn",
      onclick: async (event) => {
        const button = event.currentTarget;
        const budget = unlimited.checked ? null : Math.max(0, Math.round(Number(budgetInput.value) || 0));
        button.disabled = true;
        try {
          const result = await api("/api/storage/budget", { method: "POST", body: { budget_mb: budget } });
          state.config = { ...(state.config || {}), replay_budget_mb: result.budget_mb };
          toast(budget === null ? "automatic replay pruning disabled" : `replay budget set to ${budget} MB`, "ok");
          render(result.storage || data);
        } catch (err) {
          toast(errorMessage(err), "error");
          button.disabled = false;
        }
      },
    });

    // The replay card already states the retained count; repeating it in the
    // page subtitle adds noise without adding a second useful dimension.
    view.setSub("");
    fill(
      slot,
      el(
        "div",
        { class: "grid grid-2" },
        card(
          { title: "Replay storage" },
          el("div", { class: "storage-amount num", text: fmtBytes(replay.bytes) }),
          el("p", { class: "mute", text: `${fmt.int(retained)} retained replays` }),
          capped
            ? el(
                "div",
                { class: "storage-meter-wrap" },
                el("div", { class: "storage-meter", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": String(Math.round(usage)) }, el("span", { style: { width: `${usage}%` } })),
                el("span", { class: "small mute", text: `${fmtBytes(replay.bytes)} of ${fmtBytes(budgetBytes)} budget` })
              )
            : el("p", { class: "small mute", text: "Automatic pruning is disabled." })
        ),
        card(
          { title: "Other storage" },
          el("div", { class: "storage-other" },
            el("span", null, "Logs"), el("strong", { class: "num", text: fmtBytes(logs.bytes) }),
            el("span", null, "Database"), el("strong", { class: "num", text: fmtBytes(database.bytes) }),
            el("span", null, "Temporary"), el("strong", { class: "num", text: fmtBytes(temporary.bytes) })
          )
        )
      ),
      card(
        { title: "Replay retention" },
        el("p", { class: "mute", text: "Deleting replays preserves game results, ratings, source history and logs. Only the replay viewer becomes unavailable for those games." }),
        el(
          "div",
          { class: "row wrap storage-controls" },
          el("label", { class: "field-label", text: "Keep newest replays" }),
          keep,
          purge
        )
      ),
      card(
        { title: "Replay budget" },
        el(
          "div",
          { class: "row wrap storage-controls" },
          el("label", { class: "field-label", text: "Budget (MB)" }),
          budgetInput,
          el("label", { class: "toggle" }, unlimited, el("span", { class: "toggle-track" }, el("span", { class: "toggle-thumb" })), el("span", { class: "toggle-label", text: "Uncapped" })),
          saveBudget
        ),
        el("p", { class: "small mute", text: "A cap prunes the oldest replays after games finish. Uncapped keeps replays until you remove them here." })
      ),
      card(
        { title: "Reset" },
        el(
          "p",
          { class: "mute" },
          "Choose between resetting just the ladder, or deleting all arena data including replays, logs and tracked bot history. Bot directories and maps always stay intact."
        ),
        el(
          "div",
          { class: "row wrap storage-controls" },
          btn("Choose reset…", {
            class: "btn btn-danger",
            title: "Choose how much arena data to reset",
            onclick: () => globalThis.oarena?.openResetDialog?.(),
          })
        )
      )
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
};
