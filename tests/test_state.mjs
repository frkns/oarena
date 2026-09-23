import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const modulePath = path.join(here, "../src/oarena/web/state.js");
const source = fs.readFileSync(modulePath, "utf8");
const clientState = await import(
  `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`
);

test("a new process is detected even when its event counter is equal", () => {
  const changes = clientState.serverHelloChanges(
    { instance: "old", webRevision: "web-a", seq: 0 },
    { instance: "new", web_revision: "web-a", seq: 0 },
  );

  assert.deepEqual(changes, { webChanged: false, instanceChanged: true });
});

test("a browser-code revision is distinct from a process restart", () => {
  const changes = clientState.serverHelloChanges(
    { instance: "old", webRevision: "web-a" },
    { instance: "new", web_revision: "web-b" },
  );

  assert.deepEqual(changes, { webChanged: true, instanceChanged: true });
});

test("same and legacy hello identities retain sequence fallback behavior", () => {
  assert.deepEqual(
    clientState.serverHelloChanges(
      { instance: "same", webRevision: "web-a" },
      { instance: "same", web_revision: "web-a" },
    ),
    { webChanged: false, instanceChanged: false },
  );
  assert.deepEqual(
    clientState.serverHelloChanges(
      { instance: "same", webRevision: "web-a" },
      { seq: 0 },
    ),
    { webChanged: false, instanceChanged: false },
  );
});

test("state refresh never adopts a newer server revision as loaded code", async () => {
  const originalFetch = globalThis.fetch;
  const original = {
    webRevision: clientState.state.webRevision,
    serverWebRevision: clientState.state.serverWebRevision,
  };
  clientState.state.webRevision = "loaded-web-a";
  try {
    globalThis.fetch = async () => new Response(JSON.stringify({
      instance: "server-b",
      web_revision: "served-web-b",
      config: {},
      status: {},
      ladder: [],
      maps: [],
      counts: {},
      fcode: "test",
      seq: 0,
    }), { status: 200, headers: { "Content-Type": "application/json" } });

    await clientState.refresh();

    assert.equal(clientState.state.webRevision, "loaded-web-a");
    assert.equal(clientState.state.serverWebRevision, "served-web-b");
    assert.equal(
      clientState.serverHelloChanges(clientState.state, {
        instance: "server-b",
        web_revision: clientState.state.serverWebRevision,
      }).webChanged,
      true,
    );
  } finally {
    globalThis.fetch = originalFetch;
    clientState.state.webRevision = original.webRevision;
    clientState.state.serverWebRevision = original.serverWebRevision;
  }
});
