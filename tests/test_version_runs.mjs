import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(
  path.join(here, "../src/oarena/web/version-runs.js"),
  "utf8",
);
const { playedRunOrdinal } = await import(
  `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`
);

const run = (ordinal, version, from, to) => ({
  ordinal,
  version,
  first_seen_at: from,
  last_seen_at: to,
  transition_known: true,
});

// v5 was activated, replaced by v6, then brought back -- so the version alone
// does not say which run a match belongs to.
const reactivated = [
  run(2, 5, "2026-08-01T02:00:00Z", "2026-08-01T03:00:00Z"),
  run(1, 6, "2026-08-01T01:00:00Z", "2026-08-01T01:30:00Z"),
  run(0, 5, "2026-08-01T00:00:00Z", "2026-08-01T00:30:00Z"),
];

test("a match is placed in the run whose span contains it", () => {
  assert.equal(
    playedRunOrdinal({ runs: reactivated, version: 5, at: "2026-08-01T00:15:00Z" }),
    0,
  );
  assert.equal(
    playedRunOrdinal({ runs: reactivated, version: 5, at: "2026-08-01T02:30:00Z" }),
    2,
  );
  assert.equal(
    playedRunOrdinal({ runs: reactivated, version: 6, at: "2026-08-01T01:10:00Z" }),
    1,
  );
});

test("the boundaries of a run are inside it", () => {
  assert.equal(
    playedRunOrdinal({ runs: reactivated, version: 5, at: "2026-08-01T00:00:00Z" }),
    0,
  );
  assert.equal(
    playedRunOrdinal({ runs: reactivated, version: 5, at: "2026-08-01T00:30:00Z" }),
    0,
  );
});

test("an unobserved match still resolves when only one run could hold it", () => {
  // Outside every span -- a pinned side, or older than the collected window.
  assert.equal(
    playedRunOrdinal({ runs: reactivated, version: 6, at: "2026-07-01T00:00:00Z" }),
    1,
  );
});

test("an unobserved match with several candidate runs is not guessed at", () => {
  assert.equal(
    playedRunOrdinal({ runs: reactivated, version: 5, at: "2026-07-01T00:00:00Z" }),
    null,
  );
});

test("a version that was never observed has no run", () => {
  assert.equal(
    playedRunOrdinal({ runs: reactivated, version: 9, at: "2026-08-01T00:15:00Z" }),
    null,
  );
});

test("missing or malformed input never invents a run", () => {
  assert.equal(playedRunOrdinal(), null);
  assert.equal(playedRunOrdinal({ runs: reactivated, version: null, at: "x" }), null);
  assert.equal(playedRunOrdinal({ runs: null, version: 5, at: "x" }), null);
  // An unparseable timestamp falls back to the unambiguous-candidate rule.
  assert.equal(playedRunOrdinal({ runs: reactivated, version: 6, at: "nope" }), 1);
  assert.equal(playedRunOrdinal({ runs: reactivated, version: 5, at: "nope" }), null);
  // A run without a stored ordinal cannot be addressed.
  assert.equal(
    playedRunOrdinal({ runs: [{ version: 5 }], version: 5, at: "2026-08-01T00:00:00Z" }),
    null,
  );
});
