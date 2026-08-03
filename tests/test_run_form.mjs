import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const modulePath = path.join(here, "../src/oarena/web/run-form.js");
const source = fs.readFileSync(modulePath, "utf8");
const runForm = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);

class MemoryStorage {
  constructor() {
    this.values = new Map();
  }

  getItem(key) {
    return this.values.get(key) ?? null;
  }

  setItem(key, value) {
    this.values.set(key, String(value));
  }
}

const catalog = {
  botNames: ["alpha", "beta", "codex_a_very_long_bot_name"],
  mapNames: ["duel", "sprint", "generated_extra"],
  defaults: {
    tab: "match",
    match: {
      a: "alpha",
      b: "beta",
      maps: ["duel", "sprint"],
      repeat: 1,
      mirror: true,
      rated: true,
    },
    arena: { kind: "ladder", top: 8, target: "alpha", rated: true },
  },
};

test("finite WebUI Match tags are neutral, timestamp-readable, and UUID-backed", () => {
  const cryptoSource = {
    randomUUID: () => "01234567-89AB-4DEF-8123-456789ABCDEF",
  };
  const tag = runForm.newWebMatchBatchTag(
    new Date("2026-08-02T17:04:05.123Z"),
    cryptoSource,
  );

  assert.equal(
    tag,
    "web-match-20260802T170405123Z-01234567-89ab-4def-8123-456789abcdef",
  );
  assert.equal(tag.includes("test"), false);
  assert.ok(tag.length < 200);
});

test("finite WebUI Match tags remain unique without Web Crypto", () => {
  const now = new Date("2026-08-02T17:04:05.123Z");
  const tags = new Set(
    Array.from({ length: 100 }, () => runForm.newWebMatchBatchTag(now, null)),
  );

  assert.equal(tags.size, 100);
  for (const tag of tags) {
    assert.match(
      tag,
      /^web-match-20260802T170405123Z-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    );
  }
});

test("planned first game prefers ordinal zero, then the lowest ordinal and id", () => {
  const games = [
    { id: 80, batch_ordinal: 4 },
    { id: 90, batch_ordinal: 0 },
    { id: 70, batch_ordinal: 0 },
    { id: 10, batch_ordinal: null },
  ];
  const originalOrder = [...games];

  assert.equal(runForm.selectPlannedFirstGame(games), games[2]);
  assert.deepEqual(games, originalOrder, "selection must not reorder live state");
  assert.equal(
    runForm.selectPlannedFirstGame([
      { id: 30, batch_ordinal: 9 },
      { id: 40, batch_ordinal: 2 },
    ]).id,
    40,
  );
});

test("planned first game falls back to the lowest safe positive id", () => {
  const oldest = { id: "7", batch_ordinal: -1 };
  assert.equal(
    runForm.selectPlannedFirstGame([
      null,
      { id: 20 },
      { id: 3.5, batch_ordinal: 0 },
      { id: "7?next=/", batch_ordinal: 0 },
      oldest,
      { id: 11, batch_ordinal: "0" },
    ]),
    oldest,
  );
  assert.equal(runForm.selectPlannedFirstGame({ id: 1 }), null);
  assert.equal(runForm.selectPlannedFirstGame([{ id: 0 }, { id: -1 }]), null);
});

test("completed run hashes select the planned game and URL-encode the exact tag", () => {
  const tag = "web match/#? snow-雪";
  assert.equal(
    runForm.completedRunHash(tag, [
      { id: 99, batch_ordinal: 1 },
      { id: 101, batch_ordinal: 0 },
    ]),
    "#/games/101?tag=web%20match%2F%23%3F%20snow-%E9%9B%AA",
  );
  assert.equal(
    runForm.completedRunHash("web-match-valid", []),
    "#/games?tag=web-match-valid",
  );
});

test("completed run hashes drop malformed or unbounded routing input", () => {
  assert.equal(runForm.completedRunHash(" padded ", [{ id: 1 }]), "#/games");
  assert.equal(runForm.completedRunHash("line\nbreak", [{ id: 1 }]), "#/games");
  assert.equal(runForm.completedRunHash("x".repeat(201), [{ id: 1 }]), "#/games");
  assert.equal(runForm.completedRunHash("bad\ud800", [{ id: 1 }]), "#/games");
  assert.equal(
    runForm.completedRunHash("web-match-valid", [{ id: "1/../../storage", batch_ordinal: 0 }]),
    "#/games?tag=web-match-valid",
  );
});

test("completion tracker buffers instant completion until the POST is accepted", () => {
  const tracker = new runForm.WebMatchCompletionTracker();
  const tag = "web-match-instant";
  assert.equal(tracker.arm(tag), true);
  assert.equal(tracker.captureGame({ game: { id: 12, tag, batch_ordinal: 1 } }), null);
  assert.equal(tracker.captureGame({ id: 14, tag, batch_ordinal: 0 }), null);
  assert.equal(
    tracker.captureRunFinished({ mode: "match", batch_tag: tag, played: 2 }),
    null,
  );

  assert.deepEqual(tracker.accept(tag), {
    tag,
    firstGame: { id: 14, tag, batch_ordinal: 0 },
    hash: "#/games/14?tag=web-match-instant",
  });
  assert.equal(tracker.accept(tag), null, "completion is consumed exactly once");
  assert.equal(tracker.captureRunFinished({ mode: "match", batch_tag: tag }), null);
});

test("completion tracker also resolves when accepted before run_finished", () => {
  const tracker = new runForm.WebMatchCompletionTracker();
  const tag = "web-match-normal";
  tracker.arm(tag);
  assert.equal(tracker.accept(tag), null);
  assert.equal(tracker.captureGame({ id: 21, tag, batch_ordinal: 0 }), null);

  assert.deepEqual(
    tracker.captureRunFinished({ mode: "match", batch_tag: tag }),
    {
      tag,
      firstGame: { id: 21, tag, batch_ordinal: 0 },
      hash: "#/games/21?tag=web-match-normal",
    },
  );
});

test("completion tracker ignores unrelated tags and non-Match runs", () => {
  const tracker = new runForm.WebMatchCompletionTracker();
  const tag = "web-match-owned";
  tracker.arm(tag);
  tracker.accept(tag);

  assert.equal(tracker.captureGame({ id: 1, tag: "web-match-other", batch_ordinal: 0 }), null);
  assert.equal(
    tracker.captureRunFinished({ mode: "arena", batch_tag: tag, played: 1 }),
    null,
  );
  assert.equal(
    tracker.captureRunFinished({ mode: "match", batch_tag: "web-match-other" }),
    null,
  );
  assert.deepEqual(
    tracker.captureRunFinished({ mode: "match", batch_tag: tag }),
    { tag, firstGame: null, hash: "#/games?tag=web-match-owned" },
  );
});

test("completion tracker rejection is exact and does not disturb another candidate", () => {
  const tracker = new runForm.WebMatchCompletionTracker();
  tracker.arm("web-match-rejected");
  tracker.arm("web-match-kept");
  tracker.accept("web-match-kept");

  assert.equal(tracker.reject("web-match-rejected"), true);
  assert.equal(tracker.reject("web-match-missing"), false);
  assert.equal(
    tracker.captureRunFinished({ mode: "match", batch_tag: "web-match-rejected" }),
    null,
  );
  assert.deepEqual(
    tracker.captureRunFinished({ mode: "match", batch_tag: "web-match-kept" }),
    {
      tag: "web-match-kept",
      firstGame: null,
      hash: "#/games?tag=web-match-kept",
    },
  );
});

test("completion tracker exposes only accepted tags for reconnect reconciliation", () => {
  const tracker = new runForm.WebMatchCompletionTracker();
  tracker.arm("web-match-waiting-post");
  tracker.arm("web-match-accepted");
  tracker.arm("web-match-also-accepted");
  tracker.accept("web-match-accepted");
  tracker.accept("web-match-also-accepted");

  assert.deepEqual(tracker.acceptedTags(), [
    "web-match-accepted",
    "web-match-also-accepted",
  ]);
  tracker.reject("web-match-accepted");
  assert.deepEqual(tracker.acceptedTags(), ["web-match-also-accepted"]);
});

test("completion tracker rejects duplicate, malformed, and excessive candidates", () => {
  const tracker = new runForm.WebMatchCompletionTracker();
  assert.equal(tracker.arm(""), false);
  assert.equal(tracker.arm(" padded "), false);
  assert.equal(tracker.arm("web-match-0"), true);
  assert.equal(tracker.arm("web-match-0"), false);
  for (let index = 1; index < 8; index += 1) {
    assert.equal(tracker.arm(`web-match-${index}`), true);
  }
  assert.equal(tracker.arm("web-match-over-cap"), false);
});

test("round-trips every editable Match and Arena choice per project", () => {
  const storage = new MemoryStorage();
  const draft = {
    tab: "arena",
    match: {
      a: "codex_a_very_long_bot_name",
      b: "*",
      maps: ["generated_extra"],
      repeat: 37,
      mirror: false,
      rated: false,
    },
    arena: { kind: "top", top: 19, target: "beta", rated: false },
  };

  assert.equal(runForm.saveRunDialogDraft(storage, "/project/a", draft), true);
  assert.deepEqual(
    runForm.normalizeRunDialogDraft(
      runForm.loadRunDialogDraft(storage, "/project/a"),
      catalog,
    ),
    draft,
  );
  assert.equal(runForm.loadRunDialogDraft(storage, "/project/b"), null);
});

test("an explicit empty map selection stays empty", () => {
  const restored = runForm.normalizeRunDialogDraft(
    { match: { maps: [] } },
    catalog,
  );

  assert.deepEqual(restored.match.maps, []);
});

test("stale catalogs and malformed fields fall back without leaking names", () => {
  const restored = runForm.normalizeRunDialogDraft(
    {
      tab: "wrong",
      match: {
        a: "deleted",
        b: "deleted",
        maps: ["duel", "deleted", "duel"],
        repeat: 900,
        mirror: "yes",
        rated: null,
      },
      arena: { kind: "wrong", top: 1, target: "*", rated: "yes" },
    },
    catalog,
  );

  assert.deepEqual(restored, {
    tab: "match",
    match: {
      a: "alpha",
      b: "beta",
      maps: ["duel"],
      repeat: 500,
      mirror: true,
      rated: true,
    },
    arena: { kind: "ladder", top: 2, target: "alpha", rated: true },
  });
});

test("corrupt, obsolete, and blocked storage are harmless", () => {
  const storage = new MemoryStorage();
  const key = runForm.runDialogStorageKey("/project/a");
  storage.setItem(key, "not json");
  assert.equal(runForm.loadRunDialogDraft(storage, "/project/a"), null);

  storage.setItem(key, JSON.stringify({ version: 0, match: { a: "alpha" } }));
  assert.equal(runForm.loadRunDialogDraft(storage, "/project/a"), null);

  const blocked = {
    getItem() { throw new Error("blocked"); },
    setItem() { throw new Error("blocked"); },
  };
  assert.equal(runForm.loadRunDialogDraft(blocked, "/project/a"), null);
  assert.equal(runForm.saveRunDialogDraft(blocked, "/project/a", {}), false);
  assert.equal(runForm.saveRunDialogDraft(null, "/project/a", {}), false);
});

function bot(name, order, extra = {}) {
  const day = String(order).padStart(2, "0");
  return {
    name,
    active: true,
    broken: false,
    source_updated: `2026-07-${day}T12:00:00+00:00`,
    source_version_id: order,
    ...extra,
  };
}

test("exact typed bot is first and unused slots are the newest sources", () => {
  const rows = [
    bot("newest", 20),
    bot("starter", 1),
    ...Array.from({ length: 12 }, (_, index) => bot(`bot_${index}`, index + 2)),
  ];
  const ratingOrder = rows.map((row) => row.name);

  const suggestions = runForm.botSuggestions(rows, "starter");

  assert.equal(suggestions.length, 10);
  assert.equal(suggestions[0].name, "starter");
  assert.deepEqual(
    suggestions.slice(1).map((row) => row.name),
    ["newest", "bot_11", "bot_10", "bot_9", "bot_8", "bot_7", "bot_6", "bot_5", "bot_4"],
  );
  assert.deepEqual(rows.map((row) => row.name), ratingOrder, "must not reorder the live ladder");
});

test("prefix and substring matches outrank newer filler bots", () => {
  const rows = [
    bot("unrelated_new", 20),
    bot("old_starter_substring", 1),
    bot("starter_v2", 2),
    bot("Starter", 3),
    bot("another", 19),
  ];

  assert.deepEqual(
    runForm.botSuggestions(rows, "STARTER").map((row) => row.name),
    ["Starter", "starter_v2", "old_starter_substring", "unrelated_new", "another"],
  );
});

test("same-time source changes use version id and then name as stable tiebreaks", () => {
  const time = "2026-07-20T12:00:00+00:00";
  const rows = [
    bot("charlie", 1, { source_updated: time, source_version_id: 8 }),
    bot("alpha", 1, { source_updated: time, source_version_id: 7 }),
    bot("bravo", 1, { source_updated: time, source_version_id: 8 }),
  ];

  assert.deepEqual(
    runForm.botSuggestions(rows, "").map((row) => row.name),
    ["bravo", "charlie", "alpha"],
  );
});

test("disabled bots are omitted from suggestions even when they match exactly", () => {
  const rows = [
    bot("active_old", 1),
    bot("disabled_new", 20, { active: false }),
    bot("active_new", 19),
  ];

  assert.deepEqual(
    runForm.botSuggestions(rows, "disabled_new").map((row) => row.name),
    ["active_new", "active_old"],
  );
});

test("Bot B's everyone choice is available without displacing typed bot results", () => {
  const rows = Array.from({ length: 12 }, (_, index) => bot(`bot_${index}`, index + 1));
  rows.push(bot("starter", 1));

  const empty = runForm.botSuggestions(rows, "", { everyone: true });
  assert.equal(empty.length, 10);
  assert.deepEqual(empty.slice(0, 2).map((row) => row.name), ["*", "bot_11"]);

  const typed = runForm.botSuggestions(rows, "starter", { everyone: true });
  assert.equal(typed.length, 10);
  assert.equal(typed[0].name, "starter");
  assert.equal(typed.some((row) => row.name === "*"), false);

  const everyone = runForm.botSuggestions(rows, "eve", { everyone: true });
  assert.equal(everyone[0].name, "*");
  assert.equal(everyone[0].everyone, true);
});

test("suggestions deduplicate malformed catalogs and respect the hard limit", () => {
  const alpha = bot("alpha", 1, { broken: true });
  const rows = [null, {}, alpha, bot("alpha", 9), bot("beta", 2)];

  const suggestions = runForm.botSuggestions(rows, "", { limit: 1 });
  assert.equal(suggestions.length, 1);
  assert.equal(suggestions[0], rows[4]);
  assert.deepEqual(runForm.botSuggestions(rows, "", { limit: 0 }), []);
  assert.equal(
    runForm.botSuggestions(
      Array.from({ length: 12 }, (_, index) => bot(`limit_${index}`, index + 1)),
      "",
      { limit: 100 },
    ).length,
    10,
  );
});
