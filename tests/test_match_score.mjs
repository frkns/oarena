import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(
  path.join(here, "../src/oarena/web/match-score.js"),
  "utf8",
);
const { batchScore, batchOverallResult, batchScoreTitle } = await import(
  `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`
);

const game = (ordinal, a, b, winner, status = "ok") => ({
  id: 100 + ordinal,
  batch_ordinal: ordinal,
  a,
  b,
  winner,
  status,
  map: "sprint",
});

// The exact shape that reported a 6-0 sweep as "3-3 - Draw": every odd game
// swaps sides, so the winning slot alternates while the winning bot does not.
const sweep = [
  game(0, "herbert6", "osteo2", "a"),
  game(1, "osteo2", "herbert6", "b"),
  game(2, "herbert6", "osteo2", "a"),
  game(3, "osteo2", "herbert6", "b"),
  game(4, "herbert6", "osteo2", "a"),
  game(5, "osteo2", "herbert6", "b"),
];

test("a mirrored sweep is scored for the bot, not the side it played", () => {
  const score = batchScore(sweep);

  assert.equal(score.a, 6);
  assert.equal(score.b, 0);
  assert.equal(score.draw, 0);
  assert.equal(score.left, "herbert6");
  assert.equal(score.right, "osteo2");
  assert.equal(batchOverallResult(score), "herbert6 won");
  assert.equal(batchScoreTitle(score), "herbert6 6 – 0 osteo2");
});

test("a genuinely split match still reads as a draw", () => {
  const score = batchScore([
    game(0, "herbert6", "osteo2", "a"),
    game(1, "osteo2", "herbert6", "a"),
    game(2, "herbert6", "osteo2", "b"),
    game(3, "osteo2", "herbert6", "b"),
  ]);

  assert.equal(score.a, 2);
  assert.equal(score.b, 2);
  assert.equal(batchOverallResult(score), "Draw");
});

test("the loser of a swapped match is named, not its final slot", () => {
  const score = batchScore([
    game(0, "herbert6", "osteo2", "b"),
    game(1, "osteo2", "herbert6", "a"),
  ]);

  assert.equal(score.a, 0);
  assert.equal(score.b, 2);
  assert.equal(batchOverallResult(score), "osteo2 won");
});

test("self-play falls back to slots, the only thing telling the sides apart", () => {
  const score = batchScore([
    game(0, "herbert6", "herbert6", "a"),
    game(1, "herbert6", "herbert6", "a"),
    game(2, "herbert6", "herbert6", "b"),
  ]);

  assert.equal(score.a, 2);
  assert.equal(score.b, 1);
  assert.equal(score.left, "herbert6");
  assert.equal(score.right, "herbert6");
});

test("engine failures are counted apart from drawn games", () => {
  const score = batchScore([
    game(0, "herbert6", "osteo2", "a"),
    game(1, "osteo2", "herbert6", null, "engine_error"),
    game(2, "herbert6", "osteo2", "draw"),
    // A crash that still produced a winner is a real loss for the other bot.
    game(3, "osteo2", "herbert6", "b", "bot_error"),
  ]);

  assert.equal(score.a, 2);
  assert.equal(score.b, 0);
  assert.equal(score.draw, 1);
  assert.equal(score.errors, 1);
  assert.equal(batchOverallResult(score), "herbert6 won");
});

test("an empty or malformed batch does not invent a winner", () => {
  const empty = batchScore([]);
  assert.deepEqual(empty, { a: 0, b: 0, draw: 0, errors: 0, left: "Side A", right: "Side B" });
  assert.equal(batchOverallResult(empty), "Draw");
  assert.equal(batchScore(null).left, "Side A");
  assert.equal(batchScore([{ winner: "a" }]).a, 1);
});
