import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(
  path.join(here, "../src/oarena/square_visualiser/square-only.js"),
  "utf8",
);

function abortError() {
  return Object.assign(new Error("aborted"), { name: "AbortError" });
}

async function waitFor(predicate, label) {
  const deadline = Date.now() + 1000;
  while (!predicate()) {
    if (Date.now() > deadline) throw new Error(`timeout: ${label}`);
    await new Promise((resolve) => setTimeout(resolve, 2));
  }
}

test("prepare is isolated, cache hits skip replay bytes, and loads cancel stale work", async () => {
  const origin = "https://oarena.test";
  const listeners = new Map();
  const posted = [];
  const calls = [];
  const fetches = [];
  const delays = new Map();
  const decoded = new Set();
  let vanishingChecks = 0;
  const parent = {
    postMessage(message, targetOrigin) {
      posted.push({ message, targetOrigin });
    },
  };
  const context = vm.createContext({
    URL,
    AbortController,
    TextEncoder,
    setTimeout,
    clearTimeout,
    console,
    document: {
      currentScript: {
        src: `${origin}/viz/assets/square-only.js`,
        dataset: {},
      },
      title: "",
    },
    location: new URL(`${origin}/viz/`),
    history: { state: null, replaceState() {} },
    parent,
    addEventListener(type, listener) {
      listeners.set(type, listener);
    },
    fetch(url, { signal } = {}) {
      fetches.push(String(url));
      return new Promise((resolve, reject) => {
        if (signal?.aborted) {
          reject(abortError());
          return;
        }
        const timer = setTimeout(
          () => resolve({
            ok: true,
            status: 200,
            async arrayBuffer() {
              return new TextEncoder().encode(String(url)).buffer;
            },
            async json() {
              return { game_constants: { marker: String(url) } };
            },
          }),
          delays.get(String(url)) ?? 0,
        );
        signal?.addEventListener("abort", () => {
          clearTimeout(timer);
          reject(abortError());
        }, { once: true });
      });
    },
  });
  context.window = context;
  context.window.location = context.location;
  context.window.history = context.history;
  context.window.parent = parent;
  vm.runInContext(source, context, { filename: "square-only.js" });
  await context.__OARENA_FCODE_METADATA_READY__;

  context.__OARENA_SQUARE_BRIDGE__.connect(
    async (input) => {
      calls.push({ kind: "load", ...input });
      decoded.delete(input.key);
      return { profilerRecords: [{ key: input.key }] };
    },
    () => {},
    () => {},
    async (input) => {
      calls.push({
        kind: "prepare",
        ...input,
        globalMetadata: context.__OARENA_FCODE_METADATA__,
      });
      decoded.add(input.key);
      return { prepared: true, profilerRecords: [{ key: input.key }] };
    },
    (key) => {
      if (key === "vanishing") {
        vanishingChecks += 1;
        return vanishingChecks === 1;
      }
      return decoded.has(key);
    },
  );
  assert.equal(posted.at(-1).message.type, "oarena:square:ready");

  const dispatch = (data) => listeners.get("message")({
    origin,
    source: parent,
    data,
  });
  const buffer = () => vm.runInContext("new ArrayBuffer(8)", context);
  const metadata = (marker) => ({ game_constants: { marker } });
  const hasMessage = (type, requestId) => posted.some(
    (entry) => entry.message.type === type && entry.message.requestId === requestId,
  );

  context.__OARENA_FCODE_METADATA__ = metadata("visible");
  const oldTitle = context.document.title;
  dispatch({
    type: "oarena:square:prepare",
    requestId: "p2",
    key: "2",
    replay: buffer(),
    game: { id: 2, a: "Alpha", b: "Beta", fcode_metadata: metadata("game-2") },
    retainKeys: ["2", "3"],
    warmTimeSeries: true,
  });
  await waitFor(() => hasMessage("oarena:square:prepared", "p2"), "prepare 2");
  const prepared = calls.find((entry) => entry.kind === "prepare" && entry.key === "2");
  assert.equal(prepared.metadata.game_constants.marker, "game-2");
  assert.equal(prepared.globalMetadata.game_constants.marker, "visible");
  assert.equal(context.__OARENA_FCODE_METADATA__.game_constants.marker, "visible");
  assert.equal(context.document.title, oldTitle);
  assert.deepEqual([...prepared.retainKeys], ["2", "3"]);
  assert.equal(prepared.warmTimeSeries, true);

  const avoidedUrl = `${origin}/must-not-fetch-2`;
  dispatch({
    type: "oarena:square:load",
    requestId: "l2",
    key: "2",
    replayUrl: "/must-not-fetch-2",
    theme: "dark",
    game: { id: 2, a: "Alpha", b: "Beta", fcode_metadata: metadata("game-2") },
  });
  await waitFor(() => hasMessage("oarena:square:loaded", "l2"), "load 2");
  const loaded = calls.find((entry) => entry.kind === "load" && entry.key === "2");
  assert.equal(loaded.replay, null);
  assert.equal(fetches.includes(avoidedUrl), false);
  assert.equal(loaded.metadata.game_constants.marker, "game-2");
  assert.equal(context.__OARENA_FCODE_METADATA__.game_constants.marker, "game-2");
  assert.equal(context.document.title, "Alpha vs Beta · Replay");

  const fallbackUrl = `${origin}/fallback-vanishing`;
  dispatch({
    type: "oarena:square:load",
    requestId: "l-vanishing",
    key: "vanishing",
    replayUrl: "/fallback-vanishing",
    game: {
      id: 7,
      a: "Fallback A",
      b: "Fallback B",
      fcode_metadata: metadata("fallback"),
    },
  });
  await waitFor(
    () => hasMessage("oarena:square:loaded", "l-vanishing"),
    "fallback load",
  );
  const fallback = calls.find(
    (entry) => entry.kind === "load" && entry.key === "vanishing",
  );
  assert.equal(fallback.replay?.byteLength > 0, true);
  assert.equal(fetches.includes(fallbackUrl), true);

  const slow3 = `${origin}/slow-3`;
  delays.set(slow3, 80);
  dispatch({
    type: "oarena:square:prepare",
    requestId: "p3",
    key: "3",
    replayUrl: "/slow-3",
    game: { id: 3, fcode_metadata: metadata("game-3") },
  });
  dispatch({ type: "oarena:square:cancel-prepare" });
  await new Promise((resolve) => setTimeout(resolve, 100));
  assert.equal(calls.some((entry) => entry.kind === "prepare" && entry.key === "3"), false);
  assert.equal(
    hasMessage("oarena:square:prepared", "p3") ||
      hasMessage("oarena:square:prepare-error", "p3"),
    false,
  );

  const slow4 = `${origin}/slow-4`;
  delays.set(slow4, 80);
  dispatch({
    type: "oarena:square:prepare",
    requestId: "p4",
    key: "4",
    replayUrl: "/slow-4",
    game: { id: 4, fcode_metadata: metadata("game-4") },
  });
  dispatch({
    type: "oarena:square:load",
    requestId: "l5",
    key: "5",
    replay: buffer(),
    game: { id: 5, a: "Five A", b: "Five B", fcode_metadata: metadata("game-5") },
  });
  await waitFor(() => hasMessage("oarena:square:loaded", "l5"), "load 5");
  await new Promise((resolve) => setTimeout(resolve, 100));
  assert.equal(calls.some((entry) => entry.kind === "prepare" && entry.key === "4"), false);
  assert.equal(context.__OARENA_FCODE_METADATA__.game_constants.marker, "game-5");
  assert.equal(context.document.title, "Five A vs Five B · Replay");
});
