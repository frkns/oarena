/**
 * Client state, event bus, API client and formatters.
 *
 * This module is the only place that knows the shape of the server's JSON and
 * the only place that mutates shared state. It touches no DOM at all, so it can
 * be imported from anywhere without creating a cycle: `charts.js` imports
 * nothing, `views.js` imports this and `charts.js`, `app.js` imports this and
 * `views.js`.
 *
 * The live feed patches state in place rather than refetching: `applyGame()`
 * folds one finished game into the ladder, the crosstable and the game list,
 * which is what keeps an arena at 40 games/minute from hammering `/api/state`.
 */

/** Newest games kept client-side; the Games view pages further back by id. */
const GAME_CAP = 400;

/**
 * Game ids already folded into the ladder.
 *
 * The server's SSE endpoint subscribes before reading the bus head, so an event
 * straddling that moment is delivered twice ("delivered twice at worst, never
 * lost"). Without this set the second copy would count the result again.
 */
const applied = new Set();
const APPLIED_CAP = 4000;

/**
 * Everything the dashboard renders from.
 *
 * `bots` and `matrix` are lazily-filled caches owned by the views; both are
 * dropped by `refresh()` so a full resync can never leave stale detail on
 * screen.
 */
/**
 * Standard-normal quantile for a two-sided 95% interval.
 *
 * Every band and every LCB95 value in the UI uses this one number, and it
 * matches `oarena.ratings.CI` on the server. LCB95 is exactly the lower edge of
 * the band.
 */
export const CI = 1.959963984540054;
export const CI_LABEL = "\u03bc \u2212 1.96\u03c3";

function loadedWebRevision() {
  if (typeof document === "undefined") return "";
  const value = document.querySelector('meta[name="oarena-web-revision"]')?.content;
  return typeof value === "string" ? value : "";
}

export const state = {
  /** Opaque identity of the Python server process that supplied this snapshot. */
  instance: "",
  /** Immutable fingerprint of the HTML/CSS/JS loaded by this document. */
  webRevision: loadedWebRevision(),
  /** Fingerprint reported by the latest `/api/state` snapshot. */
  serverWebRevision: "",
  /** `/api/state.config` — project name, root, workers, defaults. */
  config: null,
  /** The `League.status` dict: running, mode, done/total, rate, live matchups. */
  status: null,
  /** `LadderRow` JSON, best first. Re-sorted in place by `applyGame`. */
  ladder: [],
  /** Map JSON including base64 `tiles` and play counts. */
  maps: [],
  /** `{bots, games, maps}` counters for the rail. */
  counts: {},
  /** fcode engine version string, e.g. `"2.2.0"`. */
  fcode: "",
  /** Highest event sequence number folded into this state. */
  seq: 0,
  /** Newest-first window of finished games (capped at GAME_CAP). */
  games: [],
  /** `name -> /api/bots/<name>` detail, cached by the bot view. */
  bots: {},
  /** `{names, cells}` crosstable, cached by the matrix view. */
  matrix: null,
  /** True while the SSE stream is connected. */
  online: false,
  /** `"dark"` or `"light"` — mirrors `<html data-theme>`. */
  theme: "dark",
  /** `{view, params, hash}` for the route currently rendered. */
  route: null,
};

// --------------------------------------------------------------------------
// event emitter
// --------------------------------------------------------------------------

/**
 * Known event names. `app.js` also re-emits raw server event types (`log`,
 * `bot_added`, `game_started`, …) under their own names so a view can listen
 * for something specific without re-parsing the stream.
 */
const listeners = new Map();

/**
 * Subscribe to an event. Returns an unsubscribe function; call it in a view's
 * cleanup so a replaced view stops reacting to the feed.
 */
export function on(evt, fn) {
  if (typeof fn !== "function") throw new TypeError("on(evt, fn): fn must be a function");
  let set = listeners.get(evt);
  if (!set) {
    set = new Set();
    listeners.set(evt, set);
  }
  set.add(fn);
  return () => {
    const current = listeners.get(evt);
    if (current) {
      current.delete(fn);
      if (current.size === 0) listeners.delete(evt);
    }
  };
}

/**
 * Publish an event. A throwing listener is reported to the console and never
 * stops the others — one broken view must not take the live feed down with it.
 */
export function emit(evt, payload) {
  const set = listeners.get(evt);
  if (!set) return;
  for (const fn of [...set]) {
    try {
      fn(payload);
    } catch (err) {
      console.error(`oarena: listener for "${evt}" threw`, err);
    }
  }
}

// --------------------------------------------------------------------------
// API client
// --------------------------------------------------------------------------

/**
 * JSON in, JSON out. Non-2xx responses throw an `Error` carrying `.status` and
 * the decoded `.payload`, with the server's `{"error": …}` text as the message
 * so a caller can show it verbatim. A network failure throws with `.status = 0`.
 */
export async function api(path, { method = "GET", body = null } = {}) {
  const init = {
    method,
    cache: "no-store",
    headers: { Accept: "application/json" },
  };
  if (body !== null && body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(path, init);
  } catch (cause) {
    const err = new Error("the arena is unreachable");
    err.status = 0;
    err.payload = null;
    err.cause = cause;
    throw err;
  }

  const text = await response.text();
  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { error: text };
    }
  }

  if (!response.ok) {
    const message =
      payload && typeof payload.error === "string" && payload.error
        ? payload.error
        : `${response.status} ${response.statusText || "request failed"}`;
    const err = new Error(message);
    err.status = response.status;
    err.payload = payload;
    throw err;
  }
  return payload;
}

/**
 * Pull the whole world from `/api/state` and emit `"state"`.
 *
 * The per-bot and crosstable caches are dropped: a full refresh happens on
 * boot, after a sync and after an event-stream gap, and in every one of those
 * cases anything derived from older data may be wrong.
 */
export async function refresh() {
  const data = await api("/api/state");
  state.instance = typeof data.instance === "string" ? data.instance : "";
  state.serverWebRevision = typeof data.web_revision === "string" ? data.web_revision : "";
  // Legacy/custom HTML may not carry the revision stamp. Pin the first server
  // value rather than adopting later revisions without loading their modules.
  if (!state.webRevision) state.webRevision = state.serverWebRevision;
  state.config = data.config ?? null;
  state.status = data.status ?? null;
  state.ladder = Array.isArray(data.ladder) ? data.ladder : [];
  state.maps = Array.isArray(data.maps) ? data.maps : [];
  state.counts = data.counts ?? {};
  state.fcode = typeof data.fcode === "string" ? data.fcode : "";
  state.seq = Number.isFinite(data.seq) ? data.seq : 0;
  state.bots = {};
  state.matrix = null;
  emit("state", state);
  emit("status", state.status);
  return state;
}

/**
 * Classify identities in an SSE hello independently of its recyclable seq.
 *
 * Event counters start over for every Python child, so equal numeric counters
 * cannot prove that a reconnect reached the same process. Browser-code changes
 * take precedence because refreshing JSON cannot update an already-loaded
 * module graph.
 */
export function serverHelloChanges(current, hello) {
  const knownInstance = typeof current?.instance === "string" ? current.instance : "";
  const nextInstance = typeof hello?.instance === "string" ? hello.instance : "";
  const knownWebRevision = typeof current?.webRevision === "string"
    ? current.webRevision
    : "";
  const nextWebRevision = typeof hello?.web_revision === "string"
    ? hello.web_revision
    : "";
  return {
    webChanged: Boolean(
      knownWebRevision && nextWebRevision && knownWebRevision !== nextWebRevision
    ),
    instanceChanged: Boolean(
      knownInstance && nextInstance && knownInstance !== nextInstance
    ),
  };
}

// --------------------------------------------------------------------------
// formatters
// --------------------------------------------------------------------------

/** Shown wherever a number is missing rather than zero. */
const DASH = "–";

function parseTime(iso) {
  if (!iso) return null;
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? ms : null;
}

function pad2(n) {
  return String(n).padStart(2, "0");
}

/**
 * Display helpers. Every one of them tolerates `null`/`undefined`/`NaN` and
 * answers `"–"`, because half of these fields are genuinely optional (an
 * unrated game has no delta, a bot with no games has no win rate).
 */
export const fmt = {
  /** A rating-ish number at fixed precision: `28.42`. */
  num(n, digits = 2) {
    return Number.isFinite(n) ? Number(n).toFixed(digits) : DASH;
  },

  /** A count: `1284`. */
  int(n) {
    return Number.isFinite(n) ? String(Math.round(n)) : DASH;
  },

  /** A 0..1 fraction as a percentage: `62%`. */
  pct(x) {
    return Number.isFinite(x) ? `${Math.round(x * 100)}%` : DASH;
  },

  /** A signed delta with a real minus sign: `+0.42`, `−0.31`, `0.00`. */
  signed(x, digits = 2) {
    if (!Number.isFinite(x)) return DASH;
    const rounded = Number(Math.abs(x).toFixed(digits));
    if (rounded === 0) return Number(0).toFixed(digits);
    return (x > 0 ? "+" : "−") + Math.abs(x).toFixed(digits);
  },

  /** A duration in milliseconds: `412ms`, `3.1s`, `1:04`, `1:02:03`. */
  dur(ms) {
    if (!Number.isFinite(ms)) return DASH;
    const seconds = ms / 1000;
    if (seconds < 1) return `${Math.round(ms)}ms`;
    if (seconds < 10) return `${seconds.toFixed(1)}s`;
    if (seconds < 60) return `${Math.round(seconds)}s`;
    const total = Math.round(seconds);
    const minutes = Math.floor(total / 60);
    if (minutes < 60) return `${minutes}:${pad2(total % 60)}`;
    return `${Math.floor(minutes / 60)}:${pad2(minutes % 60)}:${pad2(total % 60)}`;
  },

  /** Relative age of an ISO timestamp: `just now`, `42s ago`, `3d ago`. */
  ago(iso) {
    const at = parseTime(iso);
    if (at === null) return DASH;
    const seconds = Math.max(0, (Date.now() - at) / 1000);
    if (seconds < 10) return "just now";
    if (seconds < 60) return `${Math.floor(seconds)}s ago`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;
    const d = new Date(at);
    return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
  },

  /** Local wall-clock time of an ISO timestamp: `12:04:31`. */
  time(iso) {
    const at = parseTime(iso);
    if (at === null) return DASH;
    const d = new Date(at);
    return `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
  },

  /** The winning bot's *name*, `"draw"`, or `"–"` when the game had no result. */
  winner(game) {
    if (!game) return DASH;
    if (game.winner === "draw") return "draw";
    if (game.winner === "a") return game.winner_name ?? game.a ?? DASH;
    if (game.winner === "b") return game.winner_name ?? game.b ?? DASH;
    return DASH;
  },

  /** A W-L-D tally from anything carrying `wins`/`losses`/`draws`: `260-130-22`. */
  record(r) {
    if (!r) return DASH;
    return `${r.wins ?? 0}-${r.losses ?? 0}-${r.draws ?? 0}`;
  },
};

// --------------------------------------------------------------------------
// live patching
// --------------------------------------------------------------------------

function ladderIndex() {
  const index = new Map();
  for (const row of state.ladder) index.set(row.name, row);
  return index;
}

/** Re-sort by posterior mean skill (name as tiebreak) and renumber the ranks. */
function resortLadder() {
  state.ladder.sort((x, y) => {
    const byMu = (y.mu ?? 0) - (x.mu ?? 0);
    if (byMu) return byMu;
    return String(x.name).localeCompare(String(y.name));
  });
  state.ladder.forEach((row, i) => {
    row.rank = i + 1;
  });
}

/** Fold one decided result into a `Record`-shaped object, creating it if absent. */
function bumpRecord(bucket, key, outcome) {
  let rec = bucket[key];
  if (!rec) {
    rec = { wins: 0, losses: 0, draws: 0, games: 0, winrate: null, score: 0 };
    bucket[key] = rec;
  }
  if (outcome === "win") rec.wins += 1;
  else if (outcome === "loss") rec.losses += 1;
  else rec.draws += 1;
  rec.games += 1;
  rec.score = rec.wins + 0.5 * rec.draws;
  rec.winrate = rec.games > 0 ? rec.score / rec.games : null;
  return rec;
}

/**
 * Patch the ladder, the crosstable and the game list from one `game_finished`
 * event.
 *
 * `game` is `reporting.game_json`; `delta` maps bot name to its change in
 * LCB95 (empty for an unrated game). The ratings come from the
 * game's own `*_mu_after` / `*_sigma_after` columns — `delta` is only a
 * fallback, so an unrated result never moves a row.
 *
 * A bot that is not on the ladder yet (its `bot_added` event has not landed)
 * is skipped here; `app.js` schedules a full refresh for that case.
 *
 * Applying the same game twice is a no-op beyond refreshing the stored row.
 */
export function applyGame(game, delta = {}) {
  if (!game || typeof game !== "object") return;

  // --- the game list ---
  const known = state.games.findIndex((g) => g.id === game.id);
  if (known >= 0) state.games[known] = game;
  else {
    state.games.unshift(game);
    if (state.games.length > GAME_CAP) state.games.length = GAME_CAP;
  }

  if (applied.has(game.id)) return;
  applied.add(game.id);
  if (applied.size > APPLIED_CAP) {
    // Sets iterate in insertion order, so this drops the oldest ids.
    for (const id of applied) {
      applied.delete(id);
      if (applied.size <= APPLIED_CAP) break;
    }
  }
  state.counts = { ...state.counts, games: (state.counts?.games ?? 0) + 1 };

  const index = ladderIndex();
  const selfMatch = game.a === game.b;
  const names = selfMatch ? [game.a] : [game.a, game.b];

  // --- ratings, error counters, last-played ---
  for (const name of names) {
    const row = index.get(name);
    if (!row) continue;

    let errors = 0;
    if (game.a === name) errors += game.a_errors || 0;
    if (game.b === name) errors += game.b_errors || 0;
    if (errors > 0) {
      row.err_games = (row.err_games || 0) + 1;
      row.err_total = (row.err_total || 0) + errors;
    }
    row.last_played = game.ts ?? row.last_played;

    const side = game.a === name ? "a" : "b";
    const mu = game[`${side}_mu_after`];
    const sigma = game[`${side}_sigma_after`];
    if (game.rated && Number.isFinite(mu) && Number.isFinite(sigma)) {
      row.mu = mu;
      row.sigma = sigma;
      row.score = mu - CI * sigma;
      row.lcb95 = row.score;
      row.lo = row.score;
      row.hi = mu + CI * sigma;
    } else if (delta && Number.isFinite(delta[name])) {
      row.score = (row.score ?? 0) + delta[name];
      row.lcb95 = row.score;
      row.lo = row.score;
    }
  }

  // --- results (decided games between two different bots only) ---
  if (game.winner && !selfMatch) {
    // Ladder records describe exactly the rated evidence behind TrueSkill.
    if (game.rated) {
      for (const side of ["a", "b"]) {
        const row = index.get(game[side]);
        if (!row) continue;
        row.games = (row.games || 0) + 1;
        if (game.winner === "draw") row.draws = (row.draws || 0) + 1;
        else if (game.winner === side) row.wins = (row.wins || 0) + 1;
        else row.losses = (row.losses || 0) + 1;
        row.winrate = row.games > 0 ? ((row.wins || 0) + 0.5 * (row.draws || 0)) / row.games : null;
      }
    }

    // The diagnostic crosstable retains all decided results, including unrated
    // experiments, matching Store.matrix() after a full refresh.
    const cells = state.matrix?.cells;
    if (cells && Object.hasOwn(cells, game.a) && Object.hasOwn(cells, game.b)) {
      const aOutcome =
        game.winner === "draw" ? "draw" : game.winner === "a" ? "win" : "loss";
      const bOutcome =
        game.winner === "draw" ? "draw" : game.winner === "b" ? "win" : "loss";
      bumpRecord(cells[game.a], game.b, aOutcome);
      bumpRecord(cells[game.b], game.a, bOutcome);
    }
  }

  resortLadder();

  // Cached bot detail (history, per-map records, crashes) is now stale.
  for (const name of names) delete state.bots[name];
}
