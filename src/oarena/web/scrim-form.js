/** Pure validation and payload helpers for official FCode unrated scrims. */

export const SCRIM_MAP_MAX = 5;
export const SCRIM_TARGET_MATCHES_DEFAULT = 0;

// Keep UUID validation aligned with platform-form.js and the server boundary.
// Do not pin a UUID version: the platform may move from v4 to v7.
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function canonicalScrimUuid(value) {
  const text = String(value || "").trim();
  return UUID_PATTERN.test(text) ? text.toLowerCase() : "";
}

export function isScrimUuid(value) {
  return Boolean(canonicalScrimUuid(value));
}

export function normalizeScrimMaps(values, { strict = false } = {}) {
  const maps = [];
  const seen = new Set();
  for (const value of Array.isArray(values) ? values : []) {
    const name = String(value || "").trim();
    if (!name || seen.has(name)) continue;
    seen.add(name);
    maps.push(name);
  }
  if (strict && maps.length > SCRIM_MAP_MAX) {
    throw new Error(`Choose at most ${SCRIM_MAP_MAX} maps`);
  }
  return maps.slice(0, SCRIM_MAP_MAX);
}

function optionalUuid(value, label) {
  const text = String(value || "").trim();
  if (!text) return null;
  const id = canonicalScrimUuid(text);
  if (!id) throw new Error(`${label} must be a UUID`);
  return id;
}

/** Build the narrow body accepted by POST /api/platform/scrims. */
export function buildScrimRequest({
  requestKey,
  opponentTeamId,
  opponentTeamName = "",
  sourceMatchId = "",
  mapNames = [],
  ownTeamId = "",
} = {}) {
  const request_key = canonicalScrimUuid(requestKey);
  if (!request_key) throw new Error("Could not create a request ID; reload and try again");
  const opponent_team_id = canonicalScrimUuid(opponentTeamId);
  if (!opponent_team_id) throw new Error("Choose a team or paste its UUID");
  const own = canonicalScrimUuid(ownTeamId);
  if (own && own === opponent_team_id) throw new Error("Choose another team");

  const body = {
    request_key,
    opponent_team_id,
    map_names: normalizeScrimMaps(mapNames, { strict: true }),
  };
  const name = String(opponentTeamName || "").trim();
  const source = optionalUuid(sourceMatchId, "Source match");
  if (name) body.opponent_team_name = name;
  if (source) body.source_match_id = source;
  return body;
}

/** Build one atomic autoscrim configuration update. */
export function buildAutoscrimConfig({
  enabled = false,
  targetTeams = [],
  targetMatchesPerVersion = SCRIM_TARGET_MATCHES_DEFAULT,
  mapNames = [],
  ownTeamId = "",
} = {}) {
  const own = canonicalScrimUuid(ownTeamId);
  const ids = [];
  const names = {};
  const seen = new Set();
  for (const raw of Array.isArray(targetTeams) ? targetTeams : []) {
    const id = canonicalScrimUuid(raw?.id ?? raw);
    if (!id || seen.has(id)) continue;
    if (own && id === own) throw new Error("Autoscrim targets cannot include your own team");
    seen.add(id);
    ids.push(id);
    const name = String(raw?.name || "").trim();
    if (name) names[id] = name;
  }
  if (enabled && !ids.length) throw new Error("Add at least one autoscrim target first");

  const target = Number(targetMatchesPerVersion);
  if (!Number.isInteger(target) || target < 0 || target > 100) {
    throw new Error("Target matches must be between 0 and 100");
  }
  const body = {
    enabled: Boolean(enabled),
    target_team_ids: ids,
    target_matches_per_version: target,
    map_names: normalizeScrimMaps(mapNames, { strict: true }),
  };
  if (Object.keys(names).length) body.target_team_names = names;
  return body;
}

/** Generate a canonical idempotency key without falling back to Math.random. */
export function newScrimRequestKey(cryptoApi = globalThis.crypto) {
  const direct = cryptoApi?.randomUUID?.();
  if (canonicalScrimUuid(direct)) return String(direct).toLowerCase();
  if (typeof cryptoApi?.getRandomValues !== "function") {
    throw new Error("Secure random IDs are unavailable in this browser");
  }
  const bytes = new Uint8Array(16);
  cryptoApi.getRandomValues(bytes);
  // RFC 4122 variant/version bits make the fallback conventional; validation
  // deliberately accepts every UUID version at the boundary.
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = [...bytes].map((value) => value.toString(16).padStart(2, "0"));
  return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex.slice(6, 8).join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10).join("")}`;
}
