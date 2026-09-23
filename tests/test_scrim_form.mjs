import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const modulePath = path.join(here, "../src/oarena/web/scrim-form.js");
const source = fs.readFileSync(modulePath, "utf8");
const form = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);

const OWN = "11111111-1111-4111-8111-111111111111";
const OTHER = "22222222-2222-4222-8222-222222222222";
const SOURCE = "33333333-3333-4333-8333-333333333333";
const REQUEST = "44444444-4444-4444-8444-444444444444";

test("canonicalizes UUIDs without pinning their version", () => {
  assert.equal(form.canonicalScrimUuid(OTHER.toUpperCase()), OTHER);
  assert.equal(form.canonicalScrimUuid("not-a-team"), "");
  assert.equal(form.isScrimUuid(SOURCE), true);
});

test("manual request is narrow, deduplicates maps, and pins an optional version", () => {
  assert.deepEqual(
    form.buildScrimRequest({
      requestKey: REQUEST,
      opponentTeamId: OTHER.toUpperCase(),
      opponentTeamName: "Other team",
      sourceMatchId: SOURCE,
      mapNames: ["atoll", "atoll", "sprint"],
      ownTeamId: OWN,
    }),
    {
      request_key: REQUEST,
      opponent_team_id: OTHER,
      opponent_team_name: "Other team",
      source_match_id: SOURCE,
      map_names: ["atoll", "sprint"],
    },
  );
});

test("manual request rejects self-play, invalid source IDs, and more than five maps", () => {
  assert.throws(
    () => form.buildScrimRequest({ requestKey: REQUEST, opponentTeamId: OWN, ownTeamId: OWN }),
    /another team/,
  );
  assert.throws(
    () => form.buildScrimRequest({ requestKey: REQUEST, opponentTeamId: OTHER, sourceMatchId: "bad" }),
    /Source match must be a UUID/,
  );
  assert.throws(
    () => form.buildScrimRequest({
      requestKey: REQUEST,
      opponentTeamId: OTHER,
      mapNames: ["a", "b", "c", "d", "e", "f"],
    }),
    /at most 5 maps/,
  );
});

test("autoscrim config keeps an explicit, named, deduplicated target set", () => {
  assert.deepEqual(
    form.buildAutoscrimConfig({
      enabled: true,
      ownTeamId: OWN,
      targetTeams: [
        { id: OTHER, name: "Other team" },
        { id: OTHER, name: "duplicate" },
        { id: SOURCE, name: "Third team" },
      ],
      targetMatchesPerVersion: "4",
      mapNames: ["atoll"],
    }),
    {
      enabled: true,
      target_team_ids: [OTHER, SOURCE],
      target_team_names: { [OTHER]: "Other team", [SOURCE]: "Third team" },
      target_matches_per_version: 4,
      map_names: ["atoll"],
    },
  );
  assert.deepEqual(
    form.buildAutoscrimConfig({
      enabled: true,
      ownTeamId: OWN,
      targetTeams: [{ id: OTHER, name: "Other team" }],
      mapNames: [],
    }),
    {
      enabled: true,
      target_team_ids: [OTHER],
      target_matches_per_version: 0,
      target_team_names: { [OTHER]: "Other team" },
      map_names: [],
    },
  );
  assert.throws(
    () => form.buildAutoscrimConfig({ enabled: true, targetTeams: [] }),
    /at least one autoscrim target/,
  );
});

test("request IDs use randomUUID when available and secure bytes otherwise", () => {
  assert.equal(form.newScrimRequestKey({ randomUUID: () => REQUEST }), REQUEST);
  const fallback = form.newScrimRequestKey({
    getRandomValues(bytes) {
      bytes.fill(0xab);
      return bytes;
    },
  });
  assert.equal(form.isScrimUuid(fallback), true);
  assert.equal(fallback[14], "4");
  assert.match(fallback[19], /[89ab]/);
});
