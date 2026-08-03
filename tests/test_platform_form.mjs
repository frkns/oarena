import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const modulePath = path.join(here, "../src/oarena/web/platform-form.js");
const source = fs.readFileSync(modulePath, "utf8");
const form = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);

const ID = "123e4567-e89b-42d3-a456-426614174000";

class MemoryStorage {
  constructor() { this.values = new Map(); }
  getItem(key) { return this.values.get(key) ?? null; }
  setItem(key, value) { this.values.set(key, String(value)); }
}

test("parses a raw match UUID with a one-based game", () => {
  assert.deepEqual(form.parsePlatformMatchInput(ID.toUpperCase(), 4), {
    matchId: ID,
    game: 4,
  });
});

test("extracts matchId and game from the official visualiser URL", () => {
  assert.deepEqual(
    form.parsePlatformMatchInput(
      `https://game.code.florent.vc/visualiser?matchId=${ID}&game=3`,
      1,
    ),
    { matchId: ID, game: 3 },
  );
  assert.deepEqual(
    form.parsePlatformMatchInput(
      `https://game.code.florent.vc/visualiser?matchId=${ID}`,
      2,
    ),
    { matchId: ID, game: 2 },
  );
});

test("rejects lookalike origins, invalid ids, and out-of-range URL games", () => {
  assert.throws(
    () => form.parsePlatformMatchInput(`https://evil.example/visualiser?matchId=${ID}&game=1`),
    /Only official/,
  );
  assert.throws(
    () => form.parsePlatformMatchInput("not-a-match"),
    /UUID/,
  );
  assert.throws(
    () => form.parsePlatformMatchInput(`https://game.code.florent.vc/visualiser?matchId=${ID}&game=0`),
    /1–5/,
  );
});

test("round-trips the last remote selection without accepting corrupt storage", () => {
  const storage = new MemoryStorage();
  assert.equal(form.savePlatformSelection(storage, { matchId: ID, game: 5 }), true);
  assert.deepEqual(form.loadPlatformSelection(storage), { matchId: ID, game: 5 });
  storage.setItem(form.PLATFORM_SELECTION_KEY, "not-json");
  assert.equal(form.loadPlatformSelection(storage), null);
});

test("builds a safe hash and clamps non-game fallbacks", () => {
  assert.equal(form.platformViewHash(ID, 2), `#/fcode?matchId=${ID}&game=2`);
  assert.equal(form.platformViewHash("bad", 2), "#/fcode");
  assert.equal(
    form.platformViewHash(ID, 3, "#/test-runs"),
    `#/test-runs?matchId=${ID}&game=3`,
  );
  assert.equal(form.platformViewHash("bad", 2, "#/test-runs"), "#/test-runs");
  assert.equal(form.platformViewHash(ID, 2, "#/unexpected"), `#/fcode?matchId=${ID}&game=2`);
  assert.equal(form.normalizePlatformGame("9", 1), 1);
});
