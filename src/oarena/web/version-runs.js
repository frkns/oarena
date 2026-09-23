/** Pure lookup from an observed version timeline to the run a match belongs to. */

/**
 * Find which run a team was in when it played a given match.
 *
 * A version can be activated more than once, so the version alone does not
 * identify a run: `at` is tested against each candidate's observed span. When
 * the match itself was never observed -- a side pinned to an old submission, or
 * a match older than the collected window -- one candidate is still
 * unambiguous, while several are a guess, and a guess is worse than nothing.
 *
 * @returns the run's stored ordinal, or null when it cannot be identified.
 */
export function playedRunOrdinal({ runs, version, at } = {}) {
  if (!Number.isSafeInteger(version)) return null;
  const candidates = (Array.isArray(runs) ? runs : []).filter(
    (run) => run?.version === version && Number.isSafeInteger(run?.ordinal),
  );
  if (!candidates.length) return null;
  const played = Date.parse(String(at ?? ""));
  if (Number.isFinite(played)) {
    const containing = candidates.find((run) => {
      const from = Date.parse(String(run.first_seen_at ?? ""));
      const to = Date.parse(String(run.last_seen_at ?? ""));
      return Number.isFinite(from) && Number.isFinite(to) && played >= from && played <= to;
    });
    if (containing) return containing.ordinal;
  }
  return candidates.length === 1 ? candidates[0].ordinal : null;
}
