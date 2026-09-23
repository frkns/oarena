(function () {
  "use strict";

  const pageUrl = new URL(window.location.href);
  // The no-store entry document loads this shim from oarena's current
  // content-fingerprinted asset prefix. Deriving the sprite base from the
  // executing script gives Phaser the same immutable URLs without hardcoding
  // an installation path or cache revision in the dashboard.
  const executingScript = document.currentScript,
    prefixBaseUrl = new URL("./", executingScript?.src || pageUrl);
  let configuredSpriteBaseUrl = null;
  try {
    const configured = executingScript?.dataset.oarenaSpriteBase;
    configuredSpriteBaseUrl = configured ? new URL(configured, pageUrl) : null;
  } catch (_error) {
    configuredSpriteBaseUrl = null;
  }

  function normaliseName(value) {
    const name = typeof value === "string" ? value.trim() : "";
    return name ? name.slice(0, 200) : null;
  }

  function sameOriginUrl(value) {
    if (!value) return null;
    try {
      const resolved = new URL(value, pageUrl);
      return resolved.origin === pageUrl.origin ? resolved : null;
    } catch (_error) {
      return null;
    }
  }

  function safeAssetBaseUrl(value) {
    try {
      const resolved = new URL(value || prefixBaseUrl.href, prefixBaseUrl);
      if (resolved.origin !== pageUrl.origin) return prefixBaseUrl.href;
      resolved.search = "";
      resolved.hash = "";
      if (!resolved.pathname.endsWith("/")) resolved.pathname += "/";
      return resolved.href;
    } catch (_error) {
      return prefixBaseUrl.href;
    }
  }

  // Keep all sprite requests underneath the viewer's actual URL prefix, even
  // when oarena itself is reverse-proxied. The fork itself is square-only.
  pageUrl.searchParams.set(
    "assetBaseUrl",
    safeAssetBaseUrl(
      configuredSpriteBaseUrl?.href ||
        pageUrl.searchParams.get("assetBaseUrl") ||
        prefixBaseUrl.href,
    ),
  );
  try {
    window.history.replaceState(window.history.state, "", pageUrl);
  } catch (_error) {
    // The viewer still works with its original URL in restrictive embeds.
  }

  let teamA = normaliseName(pageUrl.searchParams.get("teamA"));
  let teamB = normaliseName(pageUrl.searchParams.get("teamB"));

  function updateTitle() {
    document.title =
      teamA && teamB ? `${teamA} vs ${teamB} · Replay` : "Replay";
  }
  updateTitle();

  function isMetadata(value) {
    return Boolean(
      value &&
        typeof value === "object" &&
        !Array.isArray(value) &&
        value.game_constants &&
        typeof value.game_constants === "object",
    );
  }

  async function fetchJson(url) {
    const response = await fetch(url.href, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  // This promise exists synchronously, before the upstream module executes.
  // The forked reducer can therefore await one source of truth for constants.
  // Installed metadata is also retained separately so a later local upload
  // never inherits constants recorded for the initially opened league game.
  window.__OARENA_FCODE_METADATA_READY__ = (async function resolveMetadata() {
    const gameUrl = sameOriginUrl(pageUrl.searchParams.get("gameUrl"));
    const metadataUrl = sameOriginUrl(pageUrl.searchParams.get("metadataUrl"));
    let game = null;

    if (gameUrl) {
      try {
        game = await fetchJson(gameUrl);
        teamA = teamA || normaliseName(game && game.a);
        teamB = teamB || normaliseName(game && game.b);
        updateTitle();
      } catch (_error) {
        // A failed optional detail request must not prevent replay playback.
      }
    }

    const recorded = isMetadata(game && game.fcode_metadata)
      ? game.fcode_metadata
      : null;
    if (recorded) window.__OARENA_FCODE_METADATA__ = recorded;

    const livePromise = metadataUrl
      ? fetchJson(metadataUrl)
          .then((metadata) => {
            if (!isMetadata(metadata)) return null;
            window.__OARENA_LIVE_FCODE_METADATA__ = metadata;
            return metadata;
          })
          .catch(() => null)
      : Promise.resolve(null);
    window.__OARENA_LIVE_FCODE_METADATA_READY__ = livePromise;

    if (recorded) {
      // Do not delay the replay on live-package metadata when exact recorded
      // metadata is already available. Keep warming it for local file uploads.
      void livePromise;
      return recorded;
    }

    const live = await livePromise;
    if (live) window.__OARENA_FCODE_METADATA__ = live;
    return live;
  })();

  const bridgeState = {
    loadHandler: null,
    prepareHandler: null,
    hasPreparedHandler: null,
    themeHandler: null,
    visibilityHandler: null,
    pendingLoad: null,
    loadSerial: 0,
    loadController: null,
    prepareSerial: 0,
    prepareController: null,
    applyChain: Promise.resolve(),
    readySent: false,
    visible: true,
  };

  function postParent(type, requestId, error, extra) {
    const message = { type, ...(extra || {}) };
    if (requestId !== undefined) message.requestId = requestId;
    if (error) message.error = String(error).slice(0, 500);
    window.parent.postMessage(message, window.location.origin);
  }

  function validRequestId(value) {
    return (
      (typeof value === "string" && value.length > 0 && value.length <= 200) ||
      (typeof value === "number" && Number.isFinite(value))
    );
  }

  function validTheme(value) {
    return value === "light" || value === "dark" ? value : null;
  }

  async function metadataForGame(game) {
    const recorded = isMetadata(game.fcode_metadata)
      ? game.fcode_metadata
      : null;
    if (recorded) return recorded;

    await Promise.resolve(window.__OARENA_FCODE_METADATA_READY__);
    await Promise.resolve(window.__OARENA_LIVE_FCODE_METADATA_READY__);
    return isMetadata(window.__OARENA_LIVE_FCODE_METADATA__)
      ? window.__OARENA_LIVE_FCODE_METADATA__
      : null;
  }

  async function replayBytes(message, signal) {
    if (message.replay instanceof ArrayBuffer) return message.replay;
    const replayUrl = sameOriginUrl(message.replayUrl);
    if (!replayUrl) throw new Error("Invalid replay URL");
    const response = await fetch(replayUrl.href, {
      credentials: "same-origin",
      headers: { Accept: "application/octet-stream" },
      cache: "force-cache",
      signal,
    });
    if (!response.ok) {
      throw new Error(`Replay download failed (HTTP ${response.status})`);
    }
    return response.arrayBuffer();
  }

  async function runBridgeLoad(message, serial, signal) {
    const { requestId, game, key } = message;
    postParent("oarena:square:loading", requestId);
    try {
      const hasPrepared = bridgeState.hasPreparedHandler?.(key) === true;
      const [initialReplay, metadata] = await Promise.all([
        hasPrepared ? null : replayBytes(message, signal),
        metadataForGame(game),
      ]);
      let replay = initialReplay;
      if (serial !== bridgeState.loadSerial) return;

      const apply = async () => {
        if (serial !== bridgeState.loadSerial) return;
        const loadHandler = bridgeState.loadHandler;
        if (!loadHandler) {
          bridgeState.pendingLoad = { message, serial, signal };
          return;
        }
        if (
          replay === null &&
          bridgeState.hasPreparedHandler?.(key) !== true
        ) {
          replay = await replayBytes(message, signal);
          if (serial !== bridgeState.loadSerial || signal.aborted) return;
        }
        // Never allow a replay without provenance to inherit the previous
        // game's recorded constants. Install metadata only in the serialized
        // scene-application phase so an older request cannot win this race.
        window.__OARENA_FCODE_METADATA__ = metadata;
        teamA = normaliseName(game.a);
        teamB = normaliseName(game.b);
        updateTitle();

        const theme = validTheme(message.theme);
        if (theme) bridgeState.themeHandler?.(theme);
        const loaded = await loadHandler({
          requestId,
          replay,
          game,
          metadata,
          theme,
          key,
        });
        if (serial === bridgeState.loadSerial) {
          postParent("oarena:square:loaded", requestId, null, {
            profilerRecords: Array.isArray(loaded?.profilerRecords)
              ? loaded.profilerRecords
              : [],
          });
        }
      };
      const applied = bridgeState.applyChain.then(apply, apply);
      bridgeState.applyChain = applied.catch(() => {});
      await applied;
    } catch (error) {
      if (serial === bridgeState.loadSerial && error?.name !== "AbortError") {
        const detail = error instanceof Error ? error.message : String(error);
        postParent(
          "oarena:square:error",
          requestId,
          detail || "Replay load failed",
        );
      }
    }
  }

  function queueBridgeLoad(message) {
    const serial = ++bridgeState.loadSerial;
    bridgeState.loadController?.abort();
    cancelBridgePrepare();
    const controller = new AbortController();
    bridgeState.loadController = controller;
    if (bridgeState.loadHandler) {
      void runBridgeLoad(message, serial, controller.signal);
    } else {
      bridgeState.pendingLoad = { message, serial, signal: controller.signal };
    }
  }

  function cancelBridgePrepare() {
    bridgeState.prepareSerial += 1;
    bridgeState.prepareController?.abort();
    bridgeState.prepareController = null;
  }

  async function runBridgePrepare(message, serial, signal) {
    const { requestId, game, key } = message;
    try {
      const [replay, metadata] = await Promise.all([
        replayBytes(message, signal),
        metadataForGame(game),
      ]);
      if (serial !== bridgeState.prepareSerial || signal.aborted) return;
      const prepareHandler = bridgeState.prepareHandler;
      if (!prepareHandler) throw new Error("Square viewer prepare handler is unavailable");
      const prepared = await prepareHandler({
        requestId,
        replay,
        game,
        metadata,
        key,
        retainKeys: Array.isArray(message.retainKeys)
          ? message.retainKeys
              .filter((value) => typeof value === "string" && value.length <= 200)
              .slice(0, 5)
          : [],
        warmTimeSeries: message.warmTimeSeries === true,
      });
      if (serial === bridgeState.prepareSerial && !signal.aborted) {
        postParent("oarena:square:prepared", requestId, null, {
          key,
          prepared: prepared?.prepared === true,
          profilerRecords: Array.isArray(prepared?.profilerRecords)
            ? prepared.profilerRecords
            : [],
        });
      }
    } catch (error) {
      if (
        serial === bridgeState.prepareSerial &&
        !signal.aborted &&
        error?.name !== "AbortError"
      ) {
        const detail = error instanceof Error ? error.message : String(error);
        postParent(
          "oarena:square:prepare-error",
          requestId,
          detail || "Replay preparation failed",
          { key },
        );
      }
    } finally {
      if (serial === bridgeState.prepareSerial) bridgeState.prepareController = null;
    }
  }

  function queueBridgePrepare(message) {
    const serial = ++bridgeState.prepareSerial;
    bridgeState.prepareController?.abort();
    const controller = new AbortController();
    bridgeState.prepareController = controller;
    void runBridgePrepare(message, serial, controller.signal);
  }

  function extractProfilerReports(text) {
    const reports = [];
    const kept = [];
    for (const line of String(text || "").split("\n")) {
      const modernPrefix = "[OARENA:ProfilerReport]";
      const legacyPrefix = "OARENA_TELEMETRY ";
      let raw = null;
      let legacy = false;
      if (line.startsWith(modernPrefix)) {
        raw = line.slice(modernPrefix.length).trimStart();
      } else if (line.startsWith(legacyPrefix)) {
        raw = line.slice(legacyPrefix.length);
        legacy = true;
      }
      if (raw === null) {
        kept.push(line);
        continue;
      }
      try {
        const payload = JSON.parse(raw);
        if (
          payload &&
          typeof payload === "object" &&
          !Array.isArray(payload) &&
          payload.spans &&
          typeof payload.spans === "object" &&
          !Array.isArray(payload.spans) &&
          (!legacy || payload.kind === "profile")
        ) {
          reports.push({ payload, legacy });
          continue;
        }
      } catch (_error) {
        // Partial or malformed records remain ordinary visible stdout.
      }
      kept.push(line);
    }
    return { text: kept.join("\n"), reports };
  }

  const squareBridge = Object.freeze({
    extractProfilerReports,
    connect(
      loadHandler,
      themeHandler,
      visibilityHandler,
      prepareHandler,
      hasPreparedHandler,
    ) {
      if (typeof loadHandler !== "function") {
        throw new TypeError("Square viewer load handler must be a function");
      }
      bridgeState.loadHandler = loadHandler;
      bridgeState.themeHandler =
        typeof themeHandler === "function" ? themeHandler : null;
      bridgeState.visibilityHandler =
        typeof visibilityHandler === "function" ? visibilityHandler : null;
      bridgeState.prepareHandler =
        typeof prepareHandler === "function" ? prepareHandler : null;
      bridgeState.hasPreparedHandler =
        typeof hasPreparedHandler === "function" ? hasPreparedHandler : null;
      bridgeState.visibilityHandler?.(bridgeState.visible);
      if (!bridgeState.readySent) {
        bridgeState.readySent = true;
        postParent("oarena:square:ready");
      }
      const pending = bridgeState.pendingLoad;
      bridgeState.pendingLoad = null;
      if (pending) void runBridgeLoad(pending.message, pending.serial, pending.signal);
      return () => {
        if (bridgeState.loadHandler === loadHandler) {
          bridgeState.loadHandler = null;
          bridgeState.prepareHandler = null;
          bridgeState.hasPreparedHandler = null;
          bridgeState.themeHandler = null;
          bridgeState.visibilityHandler = null;
        }
      };
    },
  });
  Object.defineProperty(window, "__OARENA_SQUARE_BRIDGE__", {
    value: squareBridge,
    configurable: false,
    enumerable: false,
    writable: false,
  });

  window.addEventListener("message", (event) => {
    if (
      event.origin !== window.location.origin ||
      event.source !== window.parent ||
      !event.data ||
      typeof event.data !== "object"
    ) {
      return;
    }
    const message = event.data;
    if (message.type === "oarena:square:hello") {
      if (bridgeState.loadHandler) postParent("oarena:square:ready");
      return;
    }
    if (message.type === "oarena:square:theme") {
      const theme = validTheme(message.theme);
      if (theme) bridgeState.themeHandler?.(theme);
      return;
    }
    if (message.type === "oarena:square:visibility") {
      if (typeof message.visible === "boolean") {
        bridgeState.visible = message.visible;
        bridgeState.visibilityHandler?.(message.visible);
      }
      return;
    }
    if (message.type === "oarena:square:cancel-prepare") {
      cancelBridgePrepare();
      return;
    }
    const loadMessage = message.type === "oarena:square:load";
    const prepareMessage = message.type === "oarena:square:prepare";
    if (!loadMessage && !prepareMessage) return;
    if (!validRequestId(message.requestId)) return;
    const key =
      typeof message.key === "string" &&
      message.key.length > 0 &&
      message.key.length <= 200
        ? message.key
        : null;
    if (
      !key ||
      (message.replay !== undefined &&
        (!(message.replay instanceof ArrayBuffer) ||
          message.replay.byteLength === 0)) ||
      (!(message.replay instanceof ArrayBuffer) &&
        !sameOriginUrl(message.replayUrl)) ||
      !message.game ||
      typeof message.game !== "object" ||
      Array.isArray(message.game)
    ) {
      postParent(
        prepareMessage ? "oarena:square:prepare-error" : "oarena:square:error",
        message.requestId,
        prepareMessage
          ? "Invalid Square replay prepare message"
          : "Invalid Square replay load message",
      );
      return;
    }
    if (prepareMessage) queueBridgePrepare(message);
    else queueBridgeLoad(message);
  });

})();
