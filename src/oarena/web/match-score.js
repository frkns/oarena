/** Pure result aggregation for one tagged local match (a batch of games). */

/**
 * Tally a match by the bot that won, not by the slot it happened to play.
 *
 * A mirrored match swaps gold and silver between games, so counting the winning
 * side turns a 6-0 sweep into 3-3 and reports it as a draw. Returns the two bot
 * names alongside the counts so callers never have to re-derive which number
 * belongs to whom.
 */
export function batchScore(games) {
  const rows = Array.isArray(games) ? games : [];
  const first = rows.find((entry) => entry?.a && entry?.b) || null;
  const left = first?.a || "Side A";
  const right = first?.b || "Side B";
  // Self-play puts one name on both sides, so the slot is then the only thing
  // separating the two entrants and stays the right thing to count.
  const named = left !== right;
  const score = { a: 0, b: 0, draw: 0, errors: 0, left, right };
  for (const entry of rows) {
    const slot = entry?.winner;
    if (slot !== "a" && slot !== "b") {
      // An engine failure is not a drawn game; keeping them apart stops the
      // summary claiming a result nobody played to.
      if (entry?.status && entry.status !== "ok") score.errors += 1;
      else score.draw += 1;
      continue;
    }
    const winnerName = slot === "a" ? entry?.a : entry?.b;
    if (named && winnerName === left) score.a += 1;
    else if (named && winnerName === right) score.b += 1;
    else if (slot === "a") score.a += 1;
    else score.b += 1;
  }
  return score;
}

/** Name the winner of a whole match, or report a genuine tie. */
export function batchOverallResult(score) {
  if (score.a === score.b) return "Draw";
  return `${score.a > score.b ? score.left : score.right} won`;
}

/** "herbert6 6 – 0 osteo2", for the tooltip behind a bare "6–0". */
export function batchScoreTitle(score) {
  return `${score.left} ${score.a} – ${score.b} ${score.right}`;
}
