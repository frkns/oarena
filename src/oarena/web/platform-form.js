/** Pure parsing and persistence helpers for the remote FCode match view. */

export const PLATFORM_SELECTION_KEY = "oarena.fcode.selection.v1";
export const PLATFORM_GAME_MIN = 1;
export const PLATFORM_GAME_MAX = 5;

// Match IDs are canonical UUID text. Do not pin the UUID version: the platform
// currently emits v4 IDs but can move to v7 without requiring a dashboard edit.
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function normalizePlatformGame(value, fallback = PLATFORM_GAME_MIN) {
  const parsed = typeof value === "number" ? value : Number(String(value || "").trim());
  if (!Number.isInteger(parsed) || parsed < PLATFORM_GAME_MIN || parsed > PLATFORM_GAME_MAX) {
    return fallback;
  }
  return parsed;
}

export function isPlatformMatchId(value) {
  return UUID_PATTERN.test(String(value || "").trim());
}

function normalizedId(value) {
  return typeof value === "string" && value.trim()
    ? value.trim().toLowerCase()
    : "";
}

/** Resolve a game's stable winner id to the match team name, never its side. */
export function platformGameWinnerName(game, match) {
  const winnerId = normalizedId(game?.winner_id);
  if (!winnerId) return null;
  for (const team of [match?.team_a, match?.team_b]) {
    if (normalizedId(team?.id) !== winnerId) continue;
    const name = typeof team?.name === "string" ? team.name.trim() : "";
    return name || null;
  }
  return null;
}

/** Return one team's outcome in a platform match, or null while unresolved. */
export function platformTeamOutcome(match, teamId) {
  const target = normalizedId(teamId);
  const teamA = normalizedId(match?.team_a?.id);
  const teamB = normalizedId(match?.team_b?.id);
  if (!target || (target !== teamA && target !== teamB)) return null;

  const winner = normalizedId(match?.winner_id);
  if (winner) {
    if (winner === target) return "win";
    return winner === teamA || winner === teamB ? "loss" : null;
  }
  if (String(match?.status || "").toLowerCase() !== "complete") return null;

  const scoreA = match?.score_a;
  const scoreB = match?.score_b;
  if (!Number.isFinite(scoreA) || !Number.isFinite(scoreB)) return null;
  if (scoreA === scoreB) return "draw";
  const winnerByScore = scoreA > scoreB ? teamA : teamB;
  return winnerByScore === target ? "win" : "loss";
}

/**
 * Accept a raw UUID or the public FCode visualiser URL. The official URL may
 * supply its own one-based game number; otherwise `fallbackGame` is used.
 */
export function parsePlatformMatchInput(value, fallbackGame = PLATFORM_GAME_MIN) {
  const raw = String(value || "").trim();
  if (!raw) throw new Error("Enter a match ID or FCode visualiser URL");

  if (isPlatformMatchId(raw)) {
    return {
      matchId: raw.toLowerCase(),
      game: normalizePlatformGame(fallbackGame),
    };
  }

  let url;
  try {
    url = new URL(raw);
  } catch {
    throw new Error("Enter a UUID or an official game.code.florent.vc visualiser URL");
  }
  if (url.protocol !== "https:" || url.hostname !== "game.code.florent.vc" || url.pathname !== "/visualiser") {
    throw new Error("Only official game.code.florent.vc visualiser URLs are accepted");
  }

  const matchId = String(url.searchParams.get("matchId") || "").trim();
  if (!isPlatformMatchId(matchId)) throw new Error("The visualiser URL has no valid matchId");

  const suppliedGame = url.searchParams.get("game");
  if (suppliedGame !== null) {
    const game = Number(suppliedGame);
    if (!Number.isInteger(game) || game < PLATFORM_GAME_MIN || game > PLATFORM_GAME_MAX) {
      throw new Error(`The visualiser game must be ${PLATFORM_GAME_MIN}–${PLATFORM_GAME_MAX}`);
    }
    return { matchId: matchId.toLowerCase(), game };
  }
  return {
    matchId: matchId.toLowerCase(),
    game: normalizePlatformGame(fallbackGame),
  };
}

export function loadPlatformSelection(storage) {
  try {
    const saved = JSON.parse(storage?.getItem(PLATFORM_SELECTION_KEY) || "null");
    if (!saved || !isPlatformMatchId(saved.matchId)) return null;
    return {
      matchId: String(saved.matchId).toLowerCase(),
      game: normalizePlatformGame(saved.game),
    };
  } catch {
    return null;
  }
}

export function savePlatformSelection(storage, selection) {
  if (!selection || !isPlatformMatchId(selection.matchId)) return false;
  try {
    storage?.setItem(
      PLATFORM_SELECTION_KEY,
      JSON.stringify({
        matchId: String(selection.matchId).toLowerCase(),
        game: normalizePlatformGame(selection.game),
      }),
    );
    return storage !== null && storage !== undefined;
  } catch {
    return false;
  }
}

export function platformViewHash(matchId, game, base = "#/fcode") {
  const route = base === "#/test-runs" ? base : "#/fcode";
  if (!isPlatformMatchId(matchId)) return route;
  const query = new URLSearchParams({
    matchId: String(matchId).toLowerCase(),
    game: String(normalizePlatformGame(game)),
  });
  return `${route}?${query.toString()}`;
}
