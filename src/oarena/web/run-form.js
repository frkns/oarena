/** Persist and reconcile the Run-games form without depending on the DOM. */

export const RUN_DIALOG_STORAGE_PREFIX = "oarena.run.dialog.v1:";
export const MIN_CUSTOM_SEED = "0";
export const MAX_CUSTOM_SEED = "9223372036854775807";

const MIN_CUSTOM_SEED_BIGINT = BigInt(MIN_CUSTOM_SEED);
const MAX_CUSTOM_SEED_BIGINT = BigInt(MAX_CUSTOM_SEED);

const ARENA_KINDS = new Set(["ladder", "top", "vs", "rr"]);
const SEED_POLICIES = new Set(["random", "fixed"]);
const MAX_BATCH_TAG_LENGTH = 200;
const MAX_TRACKED_WEB_MATCHES = 8;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
let fallbackTagSequence = 0;

function safeBatchTag(value) {
  if (
    typeof value !== "string" ||
    value.length === 0 ||
    value.length > MAX_BATCH_TAG_LENGTH ||
    value.trim() !== value ||
    /[\u0000-\u001f\u007f]/.test(value)
  ) return null;
  try {
    encodeURIComponent(value);
  } catch {
    // Lone UTF-16 surrogates cannot be represented in a URL safely.
    return null;
  }
  return value;
}

function uuidFromBytes(bytes) {
  // Match crypto.randomUUID's version/variant bits, even for an injected byte
  // source used by an older browser.
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function randomUuid(cryptoSource) {
  try {
    const uuid = cryptoSource?.randomUUID?.();
    if (typeof uuid === "string" && UUID_RE.test(uuid)) return uuid.toLowerCase();
  } catch {
    // Fall through to getRandomValues (some embedded WebViews expose only it).
  }

  try {
    const bytes = new Uint8Array(16);
    cryptoSource?.getRandomValues?.(bytes);
    if (typeof cryptoSource?.getRandomValues === "function") return uuidFromBytes(bytes);
  } catch {
    // The final fallback still combines 128 random bits, time and a counter.
  }

  const bytes = new Uint8Array(16);
  for (let index = 0; index < bytes.length; index += 1) {
    bytes[index] = Math.floor(Math.random() * 256);
  }
  fallbackTagSequence = (fallbackTagSequence + 1) >>> 0;
  const time = Date.now();
  for (let index = 0; index < 6; index += 1) {
    bytes[index] ^= Math.floor(time / (2 ** (index * 8))) & 0xff;
  }
  for (let index = 0; index < 4; index += 1) {
    bytes[12 + index] ^= (fallbackTagSequence >>> (index * 8)) & 0xff;
  }
  return uuidFromBytes(bytes);
}

/** A unique, timestamp-readable immutable tag for one finite WebUI Match. */
export function newWebMatchBatchTag(now = new Date(), cryptoSource = globalThis.crypto) {
  const suppliedMs = now instanceof Date ? now.getTime() : Number(now);
  const date = new Date(Number.isFinite(suppliedMs) ? suppliedMs : Date.now());
  const timestamp = date.toISOString().replace(/[-:.]/g, "");
  return `web-match-${timestamp}-${randomUuid(cryptoSource)}`;
}

function safeGameId(value) {
  if (typeof value === "string" && /^[1-9]\d{0,15}$/.test(value)) value = Number(value);
  return Number.isSafeInteger(value) && value > 0 ? value : null;
}

function safeBatchOrdinal(value) {
  return Number.isSafeInteger(value) && value >= 0 ? value : null;
}

/** True only for a planned game belonging to the newest finite Match batch. */
export function isLatestMatchGame(game, latestMatchTag) {
  const tag = safeBatchTag(latestMatchTag);
  return Boolean(
    tag !== null &&
    game &&
    typeof game === "object" &&
    !Array.isArray(game) &&
    game.tag === tag &&
    safeBatchOrdinal(game.batch_ordinal) !== null
  );
}

function safeCount(value) {
  return Number.isSafeInteger(value) && value >= 0 ? value : null;
}

/**
 * Build the short-lived status shown after a run POST wins the race against SSE.
 *
 * Never inherit the previous run's counters: doing so can make a newly queued
 * Match look complete and "0 in flight" until the first live status arrives.
 */
export function optimisticRunStatus(previous, run) {
  const prior = previous && typeof previous === "object" && !Array.isArray(previous)
    ? previous
    : {};
  const meta = run && typeof run === "object" && !Array.isArray(run) ? run : {};
  const total = safeCount(meta.total);
  const batchTag = safeBatchTag(meta.batchTag);
  return {
    ...prior,
    running: true,
    stopping: false,
    mode: typeof meta.mode === "string" && meta.mode ? meta.mode : "running",
    label: typeof meta.label === "string" ? meta.label : "",
    queued: total ?? 0,
    in_flight: 0,
    done: 0,
    total,
    rate: 0,
    idle_reason: "",
    live: [],
    // This client-only marker lets exact-batch fallback settle only the status
    // it created. A real server status replaces the object and drops it.
    web_match_tag: batchTag,
  };
}

/** A truthful activity label for the topbar while a run is active. */
export function runActivityLabel(status) {
  if (!status || typeof status !== "object" || !status.running) return "";
  const inFlight = safeCount(status.in_flight);
  if (inFlight !== null && inFlight > 0) return `${inFlight} in flight`;
  const queued = safeCount(status.queued);
  if (queued !== null && queued > 0) return `${queued} queued`;
  if (typeof status.idle_reason === "string" && status.idle_reason) return "";
  const done = safeCount(status.done);
  const total = safeCount(status.total);
  return total !== null && total > 0 && done !== null && done >= total
    ? "finishing"
    : "starting";
}

/**
 * Pick the first *planned* game from completion-ordered game records.
 *
 * Tagged games carry an immutable batch ordinal. Legacy or partial payloads
 * may not, in which case the oldest (lowest positive id) is the safest proxy.
 */
export function selectPlannedFirstGame(games) {
  let firstOrdered = null;
  let firstOrderedId = null;
  let firstOrdinal = null;
  let firstById = null;
  let firstId = null;

  for (const game of Array.isArray(games) ? games : []) {
    if (!game || typeof game !== "object" || Array.isArray(game)) continue;
    const id = safeGameId(game.id);
    if (id === null) continue;
    if (firstId === null || id < firstId) {
      firstById = game;
      firstId = id;
    }

    const ordinal = safeBatchOrdinal(game.batch_ordinal);
    if (
      ordinal !== null &&
      (firstOrdinal === null || ordinal < firstOrdinal ||
        (ordinal === firstOrdinal && id < firstOrderedId))
    ) {
      firstOrdered = game;
      firstOrderedId = id;
      firstOrdinal = ordinal;
    }
  }
  return firstOrdered ?? firstById;
}

/** Build a same-origin Games route for a completed tagged finite Match. */
export function completedRunHash(tag, games = []) {
  const safeTag = safeBatchTag(tag);
  if (safeTag === null) return "#/games";
  const query = `tag=${encodeURIComponent(safeTag)}`;
  const first = selectPlannedFirstGame(games);
  const id = safeGameId(first?.id);
  return id === null ? `#/games?${query}` : `#/games/${id}?${query}`;
}

/**
 * Race-proof handshake between a finite Match POST and its live events.
 *
 * A tiny broken-bot match can finish before the POST promise resolves. Arm a
 * candidate before sending, feed it game/run events, then accept or reject the
 * exact tag after the response. A completion is returned once, regardless of
 * which side of the handshake arrived first.
 */
export class WebMatchCompletionTracker {
  constructor() {
    this.candidates = new Map();
  }

  arm(tag) {
    const safeTag = safeBatchTag(tag);
    if (
      safeTag === null ||
      this.candidates.has(safeTag) ||
      this.candidates.size >= MAX_TRACKED_WEB_MATCHES
    ) return false;
    this.candidates.set(safeTag, {
      accepted: false,
      finished: false,
      firstGame: null,
    });
    return true;
  }

  captureGame(payload) {
    const envelope = payload && typeof payload === "object" ? payload : null;
    const game = envelope?.game && typeof envelope.game === "object"
      ? envelope.game
      : envelope;
    const tag = safeBatchTag(game?.tag);
    const candidate = tag === null ? null : this.candidates.get(tag);
    if (!candidate) return null;
    candidate.firstGame = selectPlannedFirstGame([candidate.firstGame, game]);
    return this.#takeReady(tag, candidate);
  }

  captureRunFinished(payload) {
    if (!payload || typeof payload !== "object" || payload.mode !== "match") return null;
    const tag = safeBatchTag(payload.batch_tag ?? payload.tag);
    const candidate = tag === null ? null : this.candidates.get(tag);
    if (!candidate) return null;
    candidate.finished = true;
    return this.#takeReady(tag, candidate);
  }

  accept(tag) {
    const safeTag = safeBatchTag(tag);
    const candidate = safeTag === null ? null : this.candidates.get(safeTag);
    if (!candidate) return null;
    candidate.accepted = true;
    return this.#takeReady(safeTag, candidate);
  }

  reject(tag) {
    const safeTag = safeBatchTag(tag);
    return safeTag !== null && this.candidates.delete(safeTag);
  }

  acceptedTags() {
    return [...this.candidates]
      .filter(([, candidate]) => candidate.accepted)
      .map(([tag]) => tag);
  }

  #takeReady(tag, candidate) {
    if (!candidate.accepted || !candidate.finished) return null;
    this.candidates.delete(tag);
    const firstGame = candidate.firstGame;
    return {
      tag,
      firstGame,
      hash: completedRunHash(tag, firstGame ? [firstGame] : []),
    };
  }
}

function sourceRecency(row) {
  const timestamp = Date.parse(typeof row?.source_updated === "string" ? row.source_updated : "");
  const version = Number.isInteger(row?.source_version_id) ? row.source_version_id : -1;
  return [Number.isFinite(timestamp) ? timestamp : 0, version];
}

/**
 * Return at most `limit` bot rows for the Run dialog's comboboxes.
 *
 * A textual match is useful enough to outrank recency: exact, prefix and then
 * substring matches appear first.  Every unoccupied slot is filled with the
 * most recently changed bot source.  The input array is copied because it is
 * the live ladder and must remain rating ordered.
 */
export function botSuggestions(
  rows,
  query = "",
  { everyone = false, includeInactive = false, limit = 10 } = {},
) {
  const cap = Math.min(10, Math.max(0, Math.trunc(Number(limit) || 0)));
  if (cap === 0) return [];

  const unique = new Map();
  for (const row of Array.isArray(rows) ? rows : []) {
    if (
      !row ||
      row.source_present === false ||
      (!includeInactive && row.active === false) ||
      typeof row.name !== "string" ||
      !row.name ||
      unique.has(row.name)
    ) continue;
    unique.set(row.name, row);
  }
  const newest = [...unique.values()].sort((a, b) => {
    const [aTime, aVersion] = sourceRecency(a);
    const [bTime, bVersion] = sourceRecency(b);
    return bTime - aTime || bVersion - aVersion || a.name.localeCompare(b.name);
  });

  const needle = String(query ?? "").trim().toLowerCase();
  const exact = [];
  const prefix = [];
  const substring = [];
  const rest = [];
  for (const row of newest) {
    const name = row.name.toLowerCase();
    if (needle && name === needle) exact.push(row);
    else if (needle && name.startsWith(needle)) prefix.push(row);
    else if (needle && name.includes(needle)) substring.push(row);
    else rest.push(row);
  }

  const suggestions = [];
  if (everyone) {
    const pseudo = {
      name: "*",
      label: "everyone",
      everyone: true,
      active: true,
      broken: false,
      source_updated: "",
      source_version_id: null,
    };
    if (needle === "" || needle === "*") exact.unshift(pseudo);
    else if (needle === "everyone") exact.push(pseudo);
    else if ("everyone".startsWith(needle)) prefix.unshift(pseudo);
    else if ("everyone".includes(needle)) substring.unshift(pseudo);
  }

  suggestions.push(...exact, ...prefix, ...substring, ...rest);
  return suggestions.slice(0, cap);
}

function record(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function booleanOr(value, fallback) {
  return typeof value === "boolean" ? value : fallback;
}

function intOr(value, min, max, fallback) {
  return Number.isInteger(value) ? Math.min(max, Math.max(min, value)) : fallback;
}

/** Canonical decimal seed, preserving values wider than JavaScript's safe integers. */
export function normalizeCustomSeed(value) {
  let text;
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value)) return null;
    text = String(value);
  } else if (typeof value === "string") {
    text = value.trim();
  } else {
    return null;
  }
  if (!/^\d+$/.test(text)) return null;
  text = text.replace(/^0+(?=\d)/, "");
  if (text.length > MAX_CUSTOM_SEED.length) return null;
  const number = BigInt(text);
  return number >= MIN_CUSTOM_SEED_BIGINT && number <= MAX_CUSTOM_SEED_BIGINT
    ? number.toString()
    : null;
}

export function customSeedFitsRounds(value, rounds) {
  const seed = normalizeCustomSeed(value);
  if (seed === null || !Number.isInteger(rounds) || rounds < 1) return false;
  return BigInt(seed) + BigInt(rounds - 1) <= MAX_CUSTOM_SEED_BIGINT;
}

function uniqueKnown(values, known) {
  if (!Array.isArray(values)) return [];
  return [...new Set(values.filter((value) => typeof value === "string" && known.has(value)))];
}

export function runDialogStorageKey(project) {
  return `${RUN_DIALOG_STORAGE_PREFIX}${encodeURIComponent(project || "default")}`;
}

export function loadRunDialogDraft(storage, project) {
  try {
    const raw = storage?.getItem(runDialogStorageKey(project));
    if (!raw) return null;
    const draft = JSON.parse(raw);
    return record(draft).version === 1 ? draft : null;
  } catch {
    return null;
  }
}

export function saveRunDialogDraft(storage, project, draft) {
  try {
    storage?.setItem(
      runDialogStorageKey(project),
      JSON.stringify({ ...record(draft), version: 1 }),
    );
    return storage !== null && storage !== undefined;
  } catch {
    return false;
  }
}

/**
 * Merge a stored draft with current project defaults and catalogs.
 *
 * Bot and map directories can be renamed or deleted between visits. Stale
 * names fall back safely; Match may use a wider bot catalog than Arena, and
 * an explicitly saved empty map list remains empty.
 */
export function normalizeRunDialogDraft(
  draft,
  { botNames, arenaBotNames = botNames, mapNames, defaults },
) {
  const knownBots = new Set(botNames);
  const knownArenaBots = new Set(arenaBotNames);
  const knownMaps = new Set(mapNames);
  const fallback = record(defaults);
  const fallbackMatch = record(fallback.match);
  const fallbackArena = record(fallback.arena);
  const saved = record(draft);
  const savedMatch = record(saved.match);
  const savedArena = record(saved.arena);

  const defaultA = knownBots.has(fallbackMatch.a) ? fallbackMatch.a : (botNames[0] ?? "");
  const defaultB = fallbackMatch.b === "*" || knownBots.has(fallbackMatch.b)
    ? fallbackMatch.b
    : (botNames[1] ?? (botNames.length ? "*" : ""));
  const defaultTarget = knownArenaBots.has(fallbackArena.target)
    ? fallbackArena.target
    : (arenaBotNames[0] ?? "");
  const defaultMaps = uniqueKnown(fallbackMatch.maps, knownMaps);

  return {
    tab: saved.tab === "arena" || saved.tab === "match"
      ? saved.tab
      : fallback.tab === "arena" ? "arena" : "match",
    match: {
      a: knownBots.has(savedMatch.a) ? savedMatch.a : defaultA,
      b: savedMatch.b === "*" || knownBots.has(savedMatch.b) ? savedMatch.b : defaultB,
      maps: Array.isArray(savedMatch.maps)
        ? uniqueKnown(savedMatch.maps, knownMaps)
        : defaultMaps,
      repeat: intOr(savedMatch.repeat, 1, 500, intOr(fallbackMatch.repeat, 1, 500, 1)),
      mirror: booleanOr(savedMatch.mirror, booleanOr(fallbackMatch.mirror, true)),
      rated: booleanOr(savedMatch.rated, booleanOr(fallbackMatch.rated, true)),
      seedPolicy: SEED_POLICIES.has(savedMatch.seedPolicy)
        ? savedMatch.seedPolicy
        : SEED_POLICIES.has(fallbackMatch.seedPolicy) ? fallbackMatch.seedPolicy : "random",
      seed: normalizeCustomSeed(savedMatch.seed)
        ?? normalizeCustomSeed(fallbackMatch.seed)
        ?? "1",
    },
    arena: {
      kind: ARENA_KINDS.has(savedArena.kind)
        ? savedArena.kind
        : ARENA_KINDS.has(fallbackArena.kind) ? fallbackArena.kind : "ladder",
      top: intOr(savedArena.top, 2, 64, intOr(fallbackArena.top, 2, 64, 8)),
      target: knownArenaBots.has(savedArena.target) ? savedArena.target : defaultTarget,
      rated: booleanOr(savedArena.rated, booleanOr(fallbackArena.rated, true)),
    },
  };
}
