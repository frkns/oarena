/**
 * Bootstrap, router, shell chrome, live event stream and dialogs.
 *
 * `app.js` owns everything outside `#view`: the topbar, the rail, the activity
 * log, the overlays and the `EventSource`. Everything inside `#view` belongs to
 * `views.js`, which this module calls into and never imports state from
 * directly (`state.js` is the only shared mutable surface, so there is no
 * import cycle).
 *
 * Two rules run through the whole file:
 *
 * 1. **Nothing from the server is ever interpolated into HTML.** Every node is
 *    built with `el()`, and every server-supplied string lands in a text node.
 *    Bot names, notes, log lines and tracebacks are attacker-ish input as far
 *    as this file is concerned.
 * 2. **A single game never triggers a refetch.** `game_finished` is folded into
 *    client state by `state.applyGame`; only a detected gap in the event
 *    sequence, a bot appearing/disappearing, or an explicit sync goes back to
 *    `/api/state`.
 */

import {
  api,
  applyGame,
  emit,
  fmt,
  refresh,
  serverHelloChanges,
  state,
} from "./state.js";
import { createMapPreview } from "./map-preview.js";
import {
  botSuggestions,
  completedRunHash,
  customSeedFitsRounds,
  loadRunDialogDraft,
  MAX_CUSTOM_SEED,
  MIN_CUSTOM_SEED,
  newWebMatchBatchTag,
  normalizeCustomSeed,
  normalizeRunDialogDraft,
  optimisticRunStatus,
  runActivityLabel,
  saveRunDialogDraft,
  WebMatchCompletionTracker,
} from "./run-form.js";
import { preloadGames, refreshView, views } from "./views.js";

// --------------------------------------------------------------------------
// DOM helpers
// --------------------------------------------------------------------------

/** `document.getElementById`, shortened — every id here comes from index.html. */
function $(id) {
  return document.getElementById(id);
}

function appendChildren(node, children) {
  for (const child of children) {
    if (child === null || child === undefined || child === false || child === true) continue;
    if (Array.isArray(child)) {
      appendChildren(node, child);
      continue;
    }
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

/**
 * Build an element.
 *
 * `attrs` understands `class`, `text`, `style` (string or object), `dataset`,
 * `onclick`-style function props and plain attributes; `true` sets a bare
 * attribute and `null`/`undefined`/`false` skips it. Children may be nodes,
 * arrays or primitives — primitives always become **text nodes**, which is
 * what makes this helper injection-proof. There is deliberately no
 * `innerHTML` escape hatch anywhere in this file.
 */
export function el(tag, attrs = null, ...children) {
  const node = document.createElement(tag);
  if (attrs) {
    for (const [key, value] of Object.entries(attrs)) {
      if (value === null || value === undefined || value === false) continue;
      if (key === "class" || key === "className") {
        node.className = String(value);
      } else if (key === "text") {
        node.textContent = String(value);
      } else if (key === "style") {
        if (typeof value === "string") node.setAttribute("style", value);
        else Object.assign(node.style, value);
      } else if (key === "dataset") {
        Object.assign(node.dataset, value);
      } else if (key.startsWith("on") && typeof value === "function") {
        node.addEventListener(key.slice(2).toLowerCase(), value);
      } else if (value === true) {
        node.setAttribute(key, "");
      } else {
        node.setAttribute(key, String(value));
      }
    }
  }
  appendChildren(node, children);
  return node;
}

/**
 * Replace a node's contents, dropping nullish children.
 *
 * Use this instead of the native `replaceChildren`: that one stringifies its
 * arguments, so the very common `cond ? el(...) : null` idiom silently renders
 * the literal text "null" into the page.
 */
export function mount(node, ...children) {
  node.textContent = "";
  appendChildren(node, children);
  return node;
}

/** An `.empty` block — the fallback every view and overlay falls back to. */
export function emptyState(title, hint, ...actions) {
  return el(
    "div",
    { class: "empty" },
    el("div", { class: "empty-title" }, title),
    hint ? el("div", { class: "empty-hint" }, hint) : null,
    actions.length ? el("div", { class: "empty-actions" }, ...actions) : null,
  );
}

// --------------------------------------------------------------------------
// shell references
// --------------------------------------------------------------------------

const dom = {
  root: document.documentElement,
  projectName: $("project-name"),
  projectMeta: $("project-meta"),
  statusPill: $("status-pill"),
  statusText: $("status-text"),
  statusSub: $("status-sub"),
  statusProgress: $("status-progress"),
  statusProgressFill: $("status-progress-fill"),
  statusCount: $("status-count"),
  btnRun: $("btn-run"),
  btnStop: $("btn-stop"),
  btnSync: $("btn-sync"),
  btnTheme: $("btn-theme"),
  btnShortcuts: $("btn-shortcuts"),
  rail: $("rail"),
  countBots: $("count-bots"),
  countGames: $("count-games"),
  countMaps: $("count-maps"),
  railVersion: $("rail-version"),
  view: $("view"),
  drawerHost: $("drawer-host"),
  logStrip: $("log-strip"),
  logToggle: $("log-toggle"),
  logPeek: $("log-peek"),
  logLines: $("log-lines"),
  logClear: $("log-clear"),
  connDot: $("conn-dot"),
  modalHost: $("modal-host"),
  toastHost: $("toast-host"),
  tooltip: $("tooltip"),
  offline: $("offline-banner"),
  offlineText: $("offline-text"),
  offlineRetry: $("offline-retry"),
  srStatus: $("sr-status"),
  squareViewerHost: $("square-viewer-host"),
  squareViewerFrame: $("square-viewer-frame"),
  squareViewerStatusText: $("square-viewer-status-text"),
};

// --------------------------------------------------------------------------
// persistent Square replay viewer
// --------------------------------------------------------------------------

const SQUARE_LAST_GAME_KEY = "oarena.square.last-game";
const SQUARE_PREPARE_LIMIT = 4;

function squareViewerManager() {
  const host = dom.squareViewerHost;
  const frame = dom.squareViewerFrame;
  const statusText = dom.squareViewerStatusText;
  if (!host || !frame) {
    return {
      show() {},
      showReplay() {},
      prepareGames() {},
      hide() {},
      setTheme() {},
      getGame: (id) => api(`/api/games/${encodeURIComponent(String(id))}`),
      getProfiler: () => [],
      onProfiler: () => () => {},
      requestFullscreen: async () => {},
    };
  }

  const detailCache = new Map();
  const detailInflight = new Map();
  const profilerCache = new Map();
  const profilerListeners = new Set();

  let requestSeq = 0;
  let ready = false;
  let activeSlot = null;
  let activeSource = null;
  let activeKey = null;
  let loadedKey = null;
  let currentLoad = null;
  let pendingLoad = null;
  let positionFrame = null;
  let revealFrame = null;
  let sentVisibility = null;
  let currentTheme = dom.root.dataset.theme === "light" ? "light" : "dark";
  let primeBusy = false;
  let primeDone = false;
  let temporaryWake = false;
  let prepareGeneration = 0;
  let prepareQueue = [];
  let currentPrepare = null;
  let prepareIdle = null;

  const resizeObserver = typeof ResizeObserver === "function"
    ? new ResizeObserver(() => schedulePosition())
    : null;

  function nextRequestId(kind, key) {
    requestSeq += 1;
    return `${kind}:${requestSeq}:${key}`;
  }

  function post(message) {
    const target = frame.contentWindow;
    if (!target) return false;
    target.postMessage(message, location.origin);
    return true;
  }

  function setStatus(kind, text) {
    host.dataset.state = kind;
    if (statusText) statusText.textContent = text;
    if (activeSlot) activeSlot.setAttribute("aria-busy", kind === "loading" ? "true" : "false");
  }

  function sendVisibility(visible) {
    if (sentVisibility === visible || !ready) return;
    sentVisibility = visible;
    post({ type: "oarena:square:visibility", visible });
  }

  function setHostVisible(visible) {
    const next = Boolean(visible && activeSlot && activeSlot.isConnected);
    host.dataset.active = next ? "true" : "false";
    host.setAttribute("aria-hidden", next ? "false" : "true");
    frame.setAttribute("aria-hidden", next ? "false" : "true");
    frame.tabIndex = next ? 0 : -1;
    sendVisibility(next || temporaryWake);
  }

  function positionHost() {
    positionFrame = null;
    if (!activeSlot || !activeSlot.isConnected) {
      sizeParkedHost();
      setHostVisible(false);
      return;
    }
    if (document.fullscreenElement === host) {
      setHostVisible(true);
      return;
    }

    const rect = activeSlot.getBoundingClientRect();
    const viewport = dom.view?.getBoundingClientRect() || {
      top: 0,
      right: window.innerWidth,
      bottom: window.innerHeight,
      left: 0,
    };
    const width = Math.max(1, rect.width);
    const height = Math.max(1, rect.height);
    const topClip = Math.max(0, viewport.top - rect.top);
    const rightClip = Math.max(0, rect.right - viewport.right);
    const bottomClip = Math.max(0, rect.bottom - viewport.bottom);
    const leftClip = Math.max(0, viewport.left - rect.left);
    const intersects = width - leftClip - rightClip > 1 && height - topClip - bottomClip > 1;

    host.style.top = `${rect.top}px`;
    host.style.left = `${rect.left}px`;
    host.style.width = `${width}px`;
    host.style.height = `${height}px`;
    host.style.clipPath = `inset(${topClip}px ${rightClip}px ${bottomClip}px ${leftClip}px round var(--radius))`;
    setHostVisible(intersects);
  }

  function schedulePosition() {
    if (positionFrame !== null) return;
    positionFrame = requestAnimationFrame(positionHost);
  }

  function parkedDimensions() {
    const width = Math.max(320, (dom.view?.clientWidth || window.innerWidth) - 32);
    let height = Math.min(960, Math.max(420, window.innerHeight - 105));
    if (window.innerWidth <= 720) {
      height = Math.min(620, Math.max(300, window.innerHeight - 105));
    }
    if (window.innerHeight <= 600) height = Math.max(280, window.innerHeight - 105);
    return { width, height };
  }

  function sizeParkedHost() {
    const { width, height } = parkedDimensions();
    host.style.width = `${width}px`;
    host.style.height = `${height}px`;
  }

  function park() {
    if (revealFrame !== null) {
      cancelAnimationFrame(revealFrame);
      revealFrame = null;
    }
    setHostVisible(false);
    host.style.top = "-10000px";
    host.style.left = "-10000px";
    sizeParkedHost();
    host.style.clipPath = "none";
  }

  function rememberGame(game) {
    if (!game || !Number.isFinite(Number(game.id))) return game;
    const key = String(game.id);
    detailCache.delete(key);
    detailCache.set(key, game);
    while (detailCache.size > SQUARE_PREPARE_LIMIT + 2) {
      detailCache.delete(detailCache.keys().next().value);
    }
    return game;
  }

  async function getGame(id) {
    const key = String(id);
    if (detailCache.has(key)) {
      const cached = detailCache.get(key);
      detailCache.delete(key);
      detailCache.set(key, cached);
      return cached;
    }
    if (detailInflight.has(key)) return detailInflight.get(key);
    const promise = api(`/api/games/${encodeURIComponent(key)}`)
      .then(rememberGame)
      .finally(() => detailInflight.delete(key));
    detailInflight.set(key, promise);
    return promise;
  }

  function rememberProfiler(key, records) {
    const value = Array.isArray(records) ? records : [];
    profilerCache.delete(key);
    profilerCache.set(key, value);
    while (profilerCache.size > 4) profilerCache.delete(profilerCache.keys().next().value);
    for (const listener of [...profilerListeners]) {
      try {
        listener({ key, records: value });
      } catch (error) {
        console.error("oarena: profiler listener failed", error);
      }
    }
  }

  function getProfiler(key) {
    return profilerCache.get(String(key)) || [];
  }

  function onProfiler(listener) {
    if (typeof listener !== "function") return () => {};
    profilerListeners.add(listener);
    return () => profilerListeners.delete(listener);
  }

  function gamePayload(game) {
    return {
      id: game.id,
      a: game.a,
      b: game.b,
      map: game.map,
      fcode_metadata: game.fcode_metadata ?? null,
    };
  }

  function localSource(game) {
    const key = String(game.id);
    return {
      key,
      replayUrl: `/api/games/${encodeURIComponent(key)}/replay`,
      game: gamePayload(game),
      localGameId: key,
    };
  }

  function normalizeReplaySource(source) {
    if (!source || typeof source !== "object") throw new TypeError("Replay source is required");
    const key = String(source.key || "");
    const replayUrl = String(source.replayUrl || "");
    if (!key || !replayUrl || !source.game) throw new TypeError("Replay source is incomplete");
    return {
      key,
      replayUrl,
      game: gamePayload(source.game),
      localGameId: source.localGameId === null || source.localGameId === undefined
        ? null
        : String(source.localGameId),
    };
  }

  function cancelPrepareIdle() {
    if (prepareIdle === null) return;
    if (typeof cancelIdleCallback === "function") cancelIdleCallback(prepareIdle);
    else clearTimeout(prepareIdle);
    prepareIdle = null;
  }

  function schedulePrepare() {
    if (
      prepareIdle !== null ||
      !ready ||
      currentLoad ||
      currentPrepare ||
      prepareQueue.length === 0
    ) {
      return;
    }
    const run = () => {
      prepareIdle = null;
      if (!ready || currentLoad || currentPrepare) return;
      const queued = prepareQueue.shift();
      if (!queued || queued.generation !== prepareGeneration) {
        schedulePrepare();
        return;
      }
      const { source, retainKeys, warmTimeSeries } = queued;
      const requestId = nextRequestId("prepare", source.key);
      currentPrepare = { requestId, key: source.key, generation: queued.generation };
      post({
        type: "oarena:square:prepare",
        requestId,
        key: source.key,
        replayUrl: source.replayUrl,
        game: source.game,
        retainKeys,
        warmTimeSeries,
      });
    };
    prepareIdle = typeof requestIdleCallback === "function"
      ? requestIdleCallback(run)
      : setTimeout(run, 250);
  }

  function cancelPrepares() {
    prepareGeneration += 1;
    prepareQueue = [];
    currentPrepare = null;
    cancelPrepareIdle();
    if (ready) post({ type: "oarena:square:cancel-prepare" });
  }

  function prepareGames(rows, selectedId) {
    cancelPrepares();
    if (!Array.isArray(rows)) return;
    const current = rows.find((row) => String(row?.id) === String(selectedId));
    if (!current || !Number.isInteger(current.batch_ordinal)) return;
    const candidates = rows
      .filter((row) =>
        row &&
        Number.isSafeInteger(Number(row.id)) &&
        Number(row.id) > 0 &&
        row.has_replay === true &&
        Number.isInteger(row.batch_ordinal) &&
        row.batch_ordinal > current.batch_ordinal
      )
      .sort((left, right) =>
        left.batch_ordinal - right.batch_ordinal || Number(left.id) - Number(right.id)
      )
      .slice(0, SQUARE_PREPARE_LIMIT);
    if (candidates.length === 0) return;

    const generation = prepareGeneration;
    const retainKeys = [String(selectedId), ...candidates.map((row) => String(row.id))];
    void (async () => {
      for (let index = 0; index < candidates.length; index += 1) {
        if (generation !== prepareGeneration) return;
        try {
          const game = await getGame(candidates[index].id);
          if (generation !== prepareGeneration) return;
          if (!game?.has_replay) continue;
          prepareQueue.push({
            generation,
            source: localSource(game),
            retainKeys,
            warmTimeSeries: index === 0,
          });
          schedulePrepare();
        } catch {
          // A failed speculative detail request is retried normally on selection.
        }
      }
    })();
  }

  function sendLoad(source, { backgroundPrime = false } = {}) {
    if (!ready) {
      if (!backgroundPrime) pendingLoad = source;
      return;
    }
    if (!backgroundPrime) cancelPrepares();
    pendingLoad = null;
    const { key, game } = source;
    temporaryWake = backgroundPrime && !activeSlot;
    if (temporaryWake) {
      // A sleeping Phaser scene cannot commit the first replay. Wake it only
      // for this one offscreen load, then put it back to sleep.
      sentVisibility = null;
      sendVisibility(true);
    }
    const requestId = nextRequestId("load", key);
    // Once a replacement starts, the old key no longer reliably describes
    // the canvas: decoding can partially mutate the scene before failing.
    loadedKey = null;
    currentLoad = { requestId, key, source, backgroundPrime };
    if (!backgroundPrime && activeKey === key) {
      setStatus("loading", `Loading ${game.a} vs ${game.b}…`);
    }
    post({
      type: "oarena:square:load",
      requestId,
      key,
      replayUrl: source.replayUrl,
      game,
      theme: currentTheme,
    });
  }

  function showReplay(slot, replaySource, theme) {
    const source = normalizeReplaySource(replaySource);
    const { key, game } = source;
    // `loadedKey` describes what is on canvas, while `currentLoad` describes
    // what will replace it.  If A is loaded, B is in flight and the user picks
    // A again, A is not settled: supersede B with a fresh A request.
    const alreadyLoaded = loadedKey === key && currentLoad === null;
    if (activeSlot && activeSlot !== slot) resizeObserver?.unobserve(activeSlot);
    activeSlot = slot;
    activeSource = source;
    activeKey = key;
    primeDone = true;
    currentTheme = theme === "light" ? "light" : "dark";
    resizeObserver?.observe(slot);
    slot.setAttribute("aria-owns", frame.id);
    slot.setAttribute("aria-label", `Square 2D replay: ${game.a} versus ${game.b}`);
    frame.title = `Square 2D replay: ${game.a} versus ${game.b}`;
    setStatus(alreadyLoaded ? "loaded" : "loading", alreadyLoaded
      ? `Loaded ${game.a} vs ${game.b}`
      : "Loading replay…");
    positionHost();
    if (revealFrame !== null) cancelAnimationFrame(revealFrame);
    revealFrame = requestAnimationFrame(() => {
      revealFrame = null;
      if (activeSlot === slot) positionHost();
    });
    if (ready) {
      post({ type: "oarena:square:theme", theme: currentTheme });
      sentVisibility = null;
      sendVisibility(true);
    }
    if (alreadyLoaded) {
      if (source.localGameId !== null) rememberLastGame(source.localGameId);
      return;
    }
    if (currentLoad?.key === key) {
      currentLoad.backgroundPrime = false;
      temporaryWake = false;
      return;
    }
    sendLoad(source);
  }

  function show(slot, game, theme) {
    rememberGame(game);
    showReplay(slot, localSource(game), theme);
  }

  function hide(slot = null) {
    if (slot && activeSlot !== slot) return;
    const oldSlot = activeSlot;
    if (oldSlot) {
      resizeObserver?.unobserve(oldSlot);
      oldSlot.removeAttribute("aria-owns");
      oldSlot.removeAttribute("aria-label");
      oldSlot.removeAttribute("aria-busy");
    }
    activeSlot = null;
    activeSource = null;
    activeKey = null;
    if (document.activeElement === frame) dom.view?.focus({ preventScroll: true });
    if (document.fullscreenElement === host) {
      document.exitFullscreen?.().catch(() => {});
    }
    park();
  }

  function setTheme(theme) {
    currentTheme = theme === "light" ? "light" : "dark";
    if (ready) post({ type: "oarena:square:theme", theme: currentTheme });
  }

  async function requestFullscreen() {
    if (!activeSlot || typeof host.requestFullscreen !== "function") {
      throw new Error("Fullscreen is not supported by this browser");
    }
    await host.requestFullscreen();
  }

  function lastGameId() {
    try {
      const value = localStorage.getItem(SQUARE_LAST_GAME_KEY);
      return /^\d+$/.test(value || "") ? value : null;
    } catch {
      return null;
    }
  }

  function rememberLastGame(key) {
    try {
      localStorage.setItem(SQUARE_LAST_GAME_KEY, key);
    } catch {
      /* A blocked storage policy only disables cross-load warming. */
    }
  }

  async function primeLikelyReplay() {
    if (!ready || primeBusy || primeDone || activeSlot || currentLoad) return;
    primeBusy = true;
    try {
      const tryPrime = async (key) => {
        if (!key || primeDone || activeSlot || currentLoad || !ready) return false;
        try {
          const game = await getGame(key);
          if (!game?.has_replay) return false;
          if (primeDone || activeSlot || currentLoad || !ready) return false;
          primeDone = true;
          sendLoad(localSource(game), { backgroundPrime: true });
          return true;
        } catch {
          return false;
        }
      };

      const last = lastGameId();
      if (last && (await tryPrime(last))) return;

      let candidate = null;
      try {
        const page = await preloadGames();
        for (const game of page?.games || []) {
          if (game?.status === "ok" && game?.has_replay) {
            candidate = String(game.id);
            break;
          }
        }
      } catch {
        /* The normal game route remains authoritative if eager discovery fails. */
      }
      if (candidate && (await tryPrime(candidate))) return;
      primeDone = true;
    } finally {
      primeBusy = false;
    }
  }

  function handleMessage(event) {
    if (event.origin !== location.origin || event.source !== frame.contentWindow) return;
    const message = event.data;
    if (!message || typeof message !== "object") return;

    if (message.type === "oarena:square:ready") {
      ready = true;
      sentVisibility = null;
      post({ type: "oarena:square:theme", theme: currentTheme });
      sendVisibility(Boolean(activeSlot && activeSlot.isConnected));
      if (pendingLoad) sendLoad(pendingLoad);
      else void primeLikelyReplay();
      return;
    }

    if (message.type === "oarena:square:loading") {
      if (currentLoad?.requestId !== message.requestId) return;
      if (activeKey === currentLoad.key) setStatus("loading", "Decoding replay…");
      return;
    }

    if (message.type === "oarena:square:loaded") {
      if (currentLoad?.requestId !== message.requestId) return;
      loadedKey = currentLoad.key;
      rememberProfiler(loadedKey, message.profilerRecords);
      if (!currentLoad.backgroundPrime && currentLoad.source.localGameId !== null) {
        rememberLastGame(currentLoad.source.localGameId);
      }
      temporaryWake = false;
      currentLoad = null;
      if (!activeSlot || activeKey === loadedKey) setStatus("loaded", "Replay loaded");
      sentVisibility = null;
      sendVisibility(host.dataset.active === "true");
      schedulePrepare();
      return;
    }

    if (
      message.type === "oarena:square:prepared" ||
      message.type === "oarena:square:prepare-error"
    ) {
      if (currentPrepare?.requestId !== message.requestId) return;
      if (message.type === "oarena:square:prepared") {
        rememberProfiler(currentPrepare.key, message.profilerRecords);
      }
      currentPrepare = null;
      schedulePrepare();
      return;
    }

    if (message.type === "oarena:square:error") {
      if (currentLoad?.requestId !== message.requestId) return;
      const failedKey = currentLoad.key;
      const backgroundPrime = currentLoad.backgroundPrime;
      temporaryWake = false;
      currentLoad = null;
      if (activeKey === failedKey) setStatus("error", message.error || "Could not load replay");
      sentVisibility = null;
      sendVisibility(host.dataset.active === "true");
      if (backgroundPrime) primeDone = true;
    }
  }

  window.addEventListener("message", handleMessage);
  window.addEventListener("resize", schedulePosition);
  window.addEventListener("scroll", schedulePosition, true);
  window.visualViewport?.addEventListener("resize", schedulePosition);
  window.visualViewport?.addEventListener("scroll", schedulePosition);
  document.addEventListener("fullscreenchange", schedulePosition);
  // Content inserted above the viewer can move its slot without changing the
  // slot's own dimensions, which ResizeObserver alone cannot see.
  const layoutObserver = typeof MutationObserver === "function"
    ? new MutationObserver(() => schedulePosition())
    : null;
  if (dom.view) layoutObserver?.observe(dom.view, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["class", "hidden", "style"],
  });
  frame.addEventListener("load", () => {
    if (activeSource) pendingLoad = activeSource;
    ready = false;
    loadedKey = null;
    currentLoad = null;
    cancelPrepares();
    primeDone = Boolean(activeSource);
    temporaryWake = false;
    sentVisibility = null;
    post({ type: "oarena:square:hello" });
  });
  post({ type: "oarena:square:hello" });
  park();

  return {
    show,
    showReplay,
    prepareGames,
    hide,
    setTheme,
    getGame,
    getProfiler,
    onProfiler,
    requestFullscreen,
  };
}

const squareViewer = squareViewerManager();

// --------------------------------------------------------------------------
// theme
// --------------------------------------------------------------------------

const THEME_STORAGE_KEY = "oarena-theme";

/**
 * Switch the theme everywhere: the `<html>` attribute the CSS keys off, the
 * browser-persisted preference, and a `themechange` event. Square updates its
 * persistent scene in place; the optional Official viewer still takes theme
 * through its iframe query string.
 */
export function setTheme(theme, { rerender = true, persist = true } = {}) {
  const next = theme === "light" ? "light" : "dark";
  state.theme = next;
  dom.root.dataset.theme = next;
  squareViewer.setTheme(next);
  if (persist) {
    try {
      globalThis.localStorage?.setItem(THEME_STORAGE_KEY, next);
    } catch (err) {
      toast(`theme changed for this page, but could not remember it: ${err?.message || err}`, "error");
    }
  }
  const label = next === "dark" ? "Switch to the light theme" : "Switch to the dark theme";
  dom.btnTheme?.setAttribute("aria-label", label);
  dom.btnTheme?.setAttribute("title", label);
  document.dispatchEvent(new CustomEvent("themechange", { detail: { theme: next } }));
  if (rerender) safeRefreshView();
}

// --------------------------------------------------------------------------
// toasts
// --------------------------------------------------------------------------

const TOAST_MS = 5000;

/** A transient, dismissible notice. Form failures go inline instead. */
export function toast(message, level = "info", timeout = TOAST_MS) {
  if (!dom.toastHost) return () => {};
  const node = el(
    "div",
    { class: "toast", "data-level": level },
    el("span", { class: "toast-msg" }, String(message)),
    el("button", { class: "toast-close", type: "button", "aria-label": "Dismiss" }, "✕"),
  );
  let timer = null;
  const dismiss = () => {
    if (timer) clearTimeout(timer);
    if (!node.isConnected) return;
    node.classList.add("is-leaving");
    setTimeout(() => node.remove(), 140);
  };
  node.querySelector(".toast-close").addEventListener("click", dismiss);
  dom.toastHost.append(node);
  if (timeout > 0) timer = setTimeout(dismiss, timeout);
  return dismiss;
}

// --------------------------------------------------------------------------
// tooltip (one shared node, positioned by JS)
// --------------------------------------------------------------------------

/** Show the shared tooltip near a viewport point. Text only — never markup. */
export function showTooltip(text, x, y) {
  const tip = dom.tooltip;
  if (!tip || !text) return;
  tip.textContent = String(text);
  tip.hidden = false;
  const rect = tip.getBoundingClientRect();
  const left = Math.min(Math.max(6, x), window.innerWidth - rect.width - 6);
  let top = y + 14;
  if (top + rect.height > window.innerHeight - 6) top = y - rect.height - 10;
  tip.style.left = `${Math.round(left)}px`;
  tip.style.top = `${Math.round(Math.max(6, top))}px`;
}

export function hideTooltip() {
  if (dom.tooltip) dom.tooltip.hidden = true;
}

/** Anchor the tooltip under an element (used by the delegated `data-tip` hook). */
function tooltipFor(target) {
  const text = target.getAttribute("data-tip");
  if (!text) return;
  const box = target.getBoundingClientRect();
  showTooltip(text, box.left + box.width / 2, box.bottom - 2);
}

function wireTooltips() {
  const enter = (event) => {
    const target = event.target instanceof Element ? event.target.closest("[data-tip]") : null;
    if (target) tooltipFor(target);
    else hideTooltip();
  };
  document.addEventListener("mouseover", enter);
  document.addEventListener("focusin", enter);
  document.addEventListener("mouseout", (event) => {
    if (event.target instanceof Element && event.target.closest("[data-tip]")) hideTooltip();
  });
  document.addEventListener("focusout", hideTooltip);
  window.addEventListener("scroll", hideTooltip, true);
}

// --------------------------------------------------------------------------
// modal + drawer
// --------------------------------------------------------------------------

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), ' +
  'textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function focusableIn(root) {
  return [...root.querySelectorAll(FOCUSABLE)].filter(
    (node) => !node.hidden && node.offsetParent !== null,
  );
}

let modalReturn = null;
let modalOnClose = null;

/** Put one `.modal` into `#modal-host`, trap focus in it and reveal the scrim. */
export function openModal(node, { onClose = null } = {}) {
  closeModal();
  modalReturn = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  modalOnClose = onClose;
  mount(dom.modalHost, node);
  dom.modalHost.hidden = false;
  const first = focusableIn(node)[0];
  (first || node).focus?.({ preventScroll: true });
  return node;
}

export function closeModal() {
  if (!dom.modalHost || dom.modalHost.hidden) return;
  dom.modalHost.hidden = true;
  mount(dom.modalHost);
  const callback = modalOnClose;
  modalOnClose = null;
  const back = modalReturn;
  modalReturn = null;
  try {
    callback?.();
  } catch (err) {
    console.error("oarena: modal close handler threw", err);
  }
  back?.focus?.({ preventScroll: true });
}

/** Slide a `.drawer` in from the right. The host doubles as its own scrim. */
export function openDrawer(node) {
  mount(dom.drawerHost, node);
  dom.drawerHost.hidden = false;
  const first = focusableIn(node)[0];
  (first || node).focus?.({ preventScroll: true });
  return node;
}

export function closeDrawer() {
  if (!dom.drawerHost || dom.drawerHost.hidden) return;
  dom.drawerHost.hidden = true;
  mount(dom.drawerHost);
}

function wireOverlays() {
  dom.modalHost.addEventListener("click", (event) => {
    if (event.target === dom.modalHost) closeModal();
  });
  dom.modalHost.addEventListener("keydown", (event) => {
    if (event.key !== "Tab") return;
    const items = focusableIn(dom.modalHost);
    if (items.length === 0) return;
    const first = items[0];
    const last = items[items.length - 1];
    const active = document.activeElement;
    if (event.shiftKey && (active === first || !dom.modalHost.contains(active))) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  });
  dom.drawerHost.addEventListener("click", (event) => {
    if (event.target === dom.drawerHost) closeDrawer();
  });
}

// --------------------------------------------------------------------------
// activity log
// --------------------------------------------------------------------------

const LOG_CAP = 500;
const LOG_OPEN_KEY = "oarena-log-open";

function setLogOpen(open) {
  dom.logStrip.dataset.open = open ? "true" : "false";
  dom.logToggle.setAttribute("aria-expanded", open ? "true" : "false");
  try {
    localStorage.setItem(LOG_OPEN_KEY, open ? "1" : "0");
  } catch {
    /* ignore */
  }
  if (open) dom.logLines.scrollTop = dom.logLines.scrollHeight;
}

function logIsOpen() {
  return dom.logStrip.dataset.open === "true";
}

/**
 * Append one activity line, capped at `LOG_CAP` nodes.
 *
 * Auto-scroll only happens when the user was already parked at the bottom, so
 * reading back through a run is not yanked away by the next arriving game.
 */
export function appendLog(level, message, atMs = Date.now()) {
  const box = dom.logLines;
  if (!box) return;
  const text = String(message ?? "");
  const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 24;
  box.append(
    el(
      "div",
      { class: "log-line", "data-level": level || "info" },
      el("span", { class: "log-time" }, fmt.time(new Date(atMs).toISOString())),
      el("span", { class: "log-msg" }, text),
    ),
  );
  while (box.childElementCount > LOG_CAP) box.firstElementChild.remove();
  if (atBottom) box.scrollTop = box.scrollHeight;
  dom.logPeek.textContent = text;
  dom.logPeek.dataset.level = level || "info";
}

function wireLog() {
  let open = false;
  try {
    open = localStorage.getItem(LOG_OPEN_KEY) === "1";
  } catch {
    /* ignore */
  }
  setLogOpen(open);
  dom.logToggle.addEventListener("click", () => setLogOpen(!logIsOpen()));
  dom.logClear.addEventListener("click", () => {
    mount(dom.logLines);
    dom.logPeek.textContent = "";
  });
}

// --------------------------------------------------------------------------
// topbar chrome
// --------------------------------------------------------------------------

function updateCounts() {
  const counts = state.counts || {};
  dom.countBots.textContent = Number.isFinite(counts.bots) ? fmt.int(counts.bots) : "–";
  dom.countGames.textContent = Number.isFinite(counts.games) ? fmt.int(counts.games) : "–";
  dom.countMaps.textContent = Number.isFinite(counts.maps) ? fmt.int(counts.maps) : "–";
}

/** Project name, engine version, worker count and the rail counters. */
function renderShell() {
  const cfg = state.config || {};
  dom.projectName.textContent = cfg.name || "oarena";
  if (cfg.root) dom.projectName.title = cfg.root;
  const meta = [];
  if (state.fcode) meta.push(`fcode ${state.fcode}`);
  if (Number.isFinite(cfg.workers)) {
    meta.push(`${cfg.workers} worker${cfg.workers === 1 ? "" : "s"}`);
  }
  dom.projectMeta.textContent = meta.join(" · ");
  dom.railVersion.textContent = cfg.version ? `oarena v${cfg.version}` : "oarena";
  updateCounts();
}

/**
 * The run-state pill: mode word, in-flight count, games/min and a determinate
 * bar for finite runs. An arena has no total, so it shows a bare game counter.
 */
function renderStatus() {
  const status = state.status || {};
  const running = Boolean(status.running);
  const stopping = Boolean(status.stopping);

  dom.statusPill.dataset.state = stopping ? "stopping" : running ? "running" : "idle";
  dom.statusText.textContent = stopping
    ? "stopping"
    : running
      ? status.mode || "running"
      : "idle";

  const bits = [];
  if (running) {
    const activity = runActivityLabel(status);
    if (activity) bits.push(activity);
    if (Number.isFinite(status.rate) && status.rate > 0) {
      bits.push(`${Math.round(status.rate)}/min`);
    }
    if (status.idle_reason) bits.push(status.idle_reason);
  } else if (status.label) {
    bits.push(status.label);
  }
  dom.statusSub.textContent = bits.join(" · ");
  dom.statusPill.title = status.label || "Arena status";

  const total = Number.isFinite(status.total) && status.total > 0 ? status.total : null;
  const done = Number.isFinite(status.done) ? status.done : 0;
  if (total) {
    const pct = Math.max(0, Math.min(100, (done / total) * 100));
    dom.statusProgress.hidden = false;
    dom.statusProgress.setAttribute("aria-valuenow", String(Math.round(pct)));
    dom.statusProgressFill.style.width = `${pct.toFixed(1)}%`;
    dom.statusCount.textContent = `${done}/${total}`;
  } else {
    dom.statusProgress.hidden = true;
    dom.statusProgress.setAttribute("aria-valuenow", "0");
    dom.statusProgressFill.style.width = "0%";
    dom.statusCount.textContent = done > 0 ? fmt.int(done) : "";
  }

  const stopLabel = dom.btnStop.querySelector("span");
  dom.btnStop.disabled = !running;
  if (stopping) {
    if (stopLabel) stopLabel.textContent = "Force stop";
    dom.btnStop.title = "Abort in-flight games now  (s)";
  } else {
    if (stopLabel) stopLabel.textContent = "Stop";
    dom.btnStop.title = "Stop after in-flight games finish  (s)";
  }
}

// --------------------------------------------------------------------------
// router
// --------------------------------------------------------------------------

/** route name -> { nav id, rail key, document-title label }. */
const ROUTES = {
  ladder: { nav: "nav-ladder", label: "Ladder" },
  matrix: { nav: "nav-matrix", label: "Matrix" },
  games: { nav: "nav-games", label: "Games" },
  game: { nav: "nav-games", label: "Game" },
  bots: { nav: "nav-bots", label: "Bots" },
  bot: { nav: "nav-bots", label: "Bot" },
  maps: { nav: "nav-maps", label: "Maps" },
  storage: { nav: "nav-storage", label: "Storage" },
  fcode: { nav: "nav-fcode", label: "FCode" },
  "test-runs": { nav: "nav-test-runs", label: "Test runs" },
  scrims: { nav: "nav-scrims", label: "Scrims" },
};

const NAV_HASHES = [
  "#/ladder",
  "#/matrix",
  "#/games",
  "#/bots",
  "#/maps",
  "#/storage",
  "#/fcode",
  "#/test-runs",
  "#/scrims",
];

function decodeSegment(text) {
  try {
    return decodeURIComponent(text);
  } catch {
    return text;
  }
}

/**
 * `#/games/412?bot=starter` -> `{view: "game", params: {id: 412, bot: "starter"}}`.
 * Returns `null` for anything unrecognised, which the router redirects.
 */
export function parseRoute(raw) {
  const hash = String(raw || "").replace(/^#/, "");
  const [pathPart, queryPart] = hash.split("?");
  const segments = pathPart.split("/").filter(Boolean).map(decodeSegment);
  const params = {};
  if (queryPart) {
    for (const [key, value] of new URLSearchParams(queryPart)) params[key] = value;
  }

  const head = segments[0] || "ladder";
  const tail = segments[1];
  const route = (view, extra = {}) => ({
    view,
    params: { ...params, ...extra },
    hash: `#${pathPart || "/ladder"}${queryPart ? `?${queryPart}` : ""}`,
  });

  switch (head) {
    case "ladder":
      return route("ladder");
    case "matrix":
      return route("matrix");
    case "games":
      if (tail === undefined) return route("games");
      return /^\d+$/.test(tail) ? route("game", { id: Number(tail) }) : null;
    case "bots":
      return tail === undefined ? route("bots") : route("bot", { name: tail });
    case "maps":
      return route("maps");
    case "storage":
      return route("storage");
    case "fcode":
      return tail === undefined ? route("fcode") : null;
    case "test-runs":
      return tail === undefined ? route("test-runs") : null;
    case "scrims":
      return tail === undefined ? route("scrims") : null;
    default:
      return null;
  }
}

function setActiveNav(view) {
  const active = ROUTES[view]?.nav;
  for (const meta of Object.values(ROUTES)) {
    const node = $(meta.nav);
    if (!node) continue;
    if (meta.nav === active) node.setAttribute("aria-current", "page");
    else node.removeAttribute("aria-current");
  }
}

function routeTitle(route) {
  const project = state.config?.name;
  const suffix = project ? ` · ${project} · oarena` : " · oarena";
  if (route.view === "game") return `Game #${route.params.id}${suffix}`;
  if (route.view === "bot") return `${route.params.name}${suffix}`;
  return `${ROUTES[route.view].label}${suffix}`;
}

function announce(text) {
  if (dom.srStatus) dom.srStatus.textContent = text;
}

let cleanup = null;
let renderToken = 0;

function runCleanup() {
  const fn = cleanup;
  cleanup = null;
  if (typeof fn !== "function") return;
  try {
    fn();
  } catch (err) {
    console.error("oarena: view cleanup threw", err);
  }
}

/** Re-render the current view without touching the route (theme, resync). */
function safeRefreshView() {
  try {
    refreshView();
  } catch (err) {
    console.error("oarena: refreshView threw", err);
  }
}

/**
 * Render the view named by `location.hash`.
 *
 * Renderers may be async; a route change while one is in flight bumps
 * `renderToken`, and the stale result is discarded (and its cleanup run
 * immediately) rather than being written over the newer view.
 */
async function render() {
  const route = parseRoute(location.hash);
  if (!route) {
    location.replace("#/ladder");
    return;
  }
  const token = ++renderToken;

  runCleanup();
  closeDrawer();
  hideTooltip();

  state.route = route;
  dom.view.dataset.view = route.view;
  mount(dom.view);
  setActiveNav(route.view);
  document.title = routeTitle(route);
  announce(`${ROUTES[route.view].label} view`);
  dom.view.focus({ preventScroll: true });
  emit("route", route);

  const renderer = views?.[route.view];
  if (typeof renderer !== "function") {
    dom.view.append(emptyState("Unknown view", `No renderer for "${route.view}".`));
    return;
  }

  try {
    const result = await renderer(dom.view, route.params);
    if (token !== renderToken) {
      if (typeof result === "function") result();
      return;
    }
    cleanup = typeof result === "function" ? result : null;
  } catch (err) {
    if (token !== renderToken) return;
    console.error("oarena: view render failed", err);
    mount(dom.view, 
      emptyState(
        "This view failed to render",
        err?.message || String(err),
        el("button", { class: "btn btn-primary btn-sm", type: "button", onclick: render }, "Retry"),
      ),
    );
  }
}

/** Navigate by hash (history entry), which re-enters the router. */
export function navigate(hash) {
  const next = hash.startsWith("#") ? hash : `#${hash}`;
  if (location.hash === next) render();
  else location.hash = next;
}

// --------------------------------------------------------------------------
// live event stream
// --------------------------------------------------------------------------

const SSE_TYPES = [
  "hello",
  "log",
  "bot_added",
  "bot_changed",
  "bot_broken",
  "bot_fixed",
  "game_started",
  "game_finished",
  "status",
  "run_started",
  "run_finished",
  "platform_scrim",
];

const BACKOFF_MIN = 500;
const BACKOFF_MAX = 10000;
/** More missed events than the server will replay in one go: resync instead. */
const GAP_LIMIT = 400;

let source = null;
let backoff = BACKOFF_MIN;
let reconnectTimer = null;
let refreshTimer = null;
/** The sequence number the next live event should carry. */
let expectedSeq = null;

/**
 * Finite Match runs are handed off to Games only after both sides agree:
 * the POST accepted our exact immutable tag and the live feed finished it.
 */
const webMatchCompletions = new WebMatchCompletionTracker();
const webMatchReconciliations = new Map();
const webMatchReconcileTimers = new Map();
const webMatchReconcileAttempts = new Map();
const webMatchReconcileWarned = new Set();
const WEB_MATCH_RECONCILE_MIN_MS = 1000;
const WEB_MATCH_RECONCILE_MAX_MS = 5000;

function isAcceptedWebMatch(tag) {
  return webMatchCompletions.acceptedTags().includes(tag);
}

function stopWebMatchReconciliation(tag) {
  const timer = webMatchReconcileTimers.get(tag);
  if (timer !== undefined) clearTimeout(timer);
  webMatchReconcileTimers.delete(tag);
  webMatchReconcileAttempts.delete(tag);
  webMatchReconcileWarned.delete(tag);
}

function scheduleWebMatchReconciliation(tag, { immediate = false } = {}) {
  if (!isAcceptedWebMatch(tag)) {
    stopWebMatchReconciliation(tag);
    return;
  }
  if (webMatchReconciliations.has(tag)) return;
  const pending = webMatchReconcileTimers.get(tag);
  if (pending !== undefined) {
    if (!immediate) return;
    clearTimeout(pending);
    webMatchReconcileTimers.delete(tag);
  }
  const attempt = webMatchReconcileAttempts.get(tag) || 0;
  const delay = immediate
    ? 0
    : Math.min(WEB_MATCH_RECONCILE_MAX_MS, WEB_MATCH_RECONCILE_MIN_MS * (2 ** attempt));
  if (!immediate) webMatchReconcileAttempts.set(tag, attempt + 1);
  const timer = setTimeout(() => {
    webMatchReconcileTimers.delete(tag);
    void reconcileWebMatch(tag);
  }, delay);
  webMatchReconcileTimers.set(tag, timer);
}

function fetchWebMatchBatch(tag) {
  const query = new URLSearchParams({ tag, limit: "500" });
  return api(`/api/batch?${query}`);
}

function openCompletedWebMatch(hash) {
  // A user may have dismissed Run and opened a different overlay while the
  // match was running. Never close an unrelated modal on completion.
  if (dom.modalHost?.querySelector("#run-dialog")) closeModal();
  navigate(hash);
  dom.view.scrollTop = 0;
  requestAnimationFrame(() => {
    dom.view.scrollTop = 0;
  });
}

function consumeCompletedWebMatch(completion, recoveredGames = null) {
  if (!completion) return;
  stopWebMatchReconciliation(completion.tag);

  // Normally the ordinal-zero game_finished precedes run_finished, so this is
  // the immediate path. If a reconnect missed even part of the game stream,
  // recover the planned first game from the immutable batch before opening it.
  if (completion.firstGame?.batch_ordinal === 0) {
    openCompletedWebMatch(completion.hash);
    return;
  }
  if (Array.isArray(recoveredGames)) {
    openCompletedWebMatch(completedRunHash(completion.tag, recoveredGames));
    return;
  }

  void (async () => {
    let hash = completion.hash;
    try {
      const batch = await fetchWebMatchBatch(completion.tag);
      hash = completedRunHash(completion.tag, batch?.games);
    } catch (err) {
      appendLog("warn", `could not resolve completed match games: ${err?.message || err}`);
    }
    openCompletedWebMatch(hash);
  })();
}

function reconcileWebMatch(tag) {
  if (!isAcceptedWebMatch(tag)) {
    stopWebMatchReconciliation(tag);
    return null;
  }
  if (webMatchReconciliations.has(tag)) return webMatchReconciliations.get(tag);
  const timer = webMatchReconcileTimers.get(tag);
  if (timer !== undefined) clearTimeout(timer);
  webMatchReconcileTimers.delete(tag);
  let retry = false;
  const reconciliation = (async () => {
    try {
      const batch = await fetchWebMatchBatch(tag);
      webMatchReconcileWarned.delete(tag);
      if (batch?.mode !== "match") {
        webMatchCompletions.reject(tag);
        stopWebMatchReconciliation(tag);
        return;
      }
      if (batch.status === "running") {
        retry = true;
        return;
      }
      const games = Array.isArray(batch.games) ? batch.games : [];
      if (games[0]) webMatchCompletions.captureGame(games[0]);
      settleOptimisticWebMatch(tag, {
        played: batch.played_games,
        total: batch.requested_games,
      });
      consumeCompletedWebMatch(
        webMatchCompletions.captureRunFinished({ mode: "match", batch_tag: tag }),
        games,
      );
    } catch (err) {
      if (err?.status === 404) {
        webMatchCompletions.reject(tag);
        stopWebMatchReconciliation(tag);
        return;
      }
      retry = true;
      if (!webMatchReconcileWarned.has(tag)) {
        webMatchReconcileWarned.add(tag);
        appendLog("warn", `could not reconcile Match run: ${err?.message || err}`);
      }
    }
  })().finally(() => {
    webMatchReconciliations.delete(tag);
    if (retry) scheduleWebMatchReconciliation(tag);
  });
  webMatchReconciliations.set(tag, reconciliation);
  return reconciliation;
}

function reconcileCompletedWebMatches() {
  for (const tag of webMatchCompletions.acceptedTags()) {
    scheduleWebMatchReconciliation(tag, { immediate: true });
  }
}

function settleOptimisticWebMatch(tag, { played = null, total = null } = {}) {
  if (state.status?.web_match_tag !== tag) return;
  const finished = Number.isSafeInteger(played) && played >= 0
    ? played
    : state.status.done;
  const planned = Number.isSafeInteger(total) && total >= 0
    ? total
    : state.status.total;
  state.status = {
    ...state.status,
    running: false,
    stopping: false,
    queued: 0,
    in_flight: 0,
    done: finished,
    total: planned,
    web_match_tag: null,
  };
  renderStatus();
}

function setConnection(status) {
  if (dom.connDot) dom.connDot.dataset.state = status;
}

function goOnline() {
  const changed = !state.online;
  state.online = true;
  setConnection("live");
  dom.offline.hidden = true;
  if (changed) {
    emit("online", true);
    reconcileCompletedWebMatches();
  }
}

function goOffline(message) {
  const changed = state.online;
  state.online = false;
  setConnection("down");
  dom.offlineText.textContent = message;
  dom.offline.hidden = false;
  if (changed) emit("online", false);
}

function disconnect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (source) {
    const dying = source;
    source = null;
    try {
      dying.close();
    } catch {
      /* already closed */
    }
  }
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  const wait = backoff;
  backoff = Math.min(BACKOFF_MAX, Math.round(backoff * 1.8));
  goOffline(`Disconnected from the arena — retrying in ${(wait / 1000).toFixed(1)}s…`);
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connect();
  }, wait);
}

/**
 * Pull a fresh `/api/state` and re-render, coalescing bursts.
 *
 * Used only when patching cannot be trusted: an event-sequence gap, a bot
 * appearing or disappearing, or an explicit resync.
 */
function requestFullRefresh(reason) {
  if (refreshTimer) return;
  refreshTimer = setTimeout(async () => {
    refreshTimer = null;
    try {
      await refresh();
      if (reloadForWebRevisionChange()) return;
      expectedSeq = state.seq + 1;
      renderShell();
      renderStatus();
      safeRefreshView();
      refreshOpenRunCatalog?.();
      reconcileCompletedWebMatches();
    } catch (err) {
      appendLog("error", `resync failed (${reason}): ${err.message}`);
    }
  }, 250);
}

function reloadForWebRevisionChange() {
  const loaded = state.webRevision;
  const served = state.serverWebRevision;
  if (!loaded || !served || loaded === served) return false;
  location.reload();
  return true;
}

function onHello(data) {
  backoff = BACKOFF_MIN;
  goOnline();
  const identity = serverHelloChanges(state, data);
  if (identity.webChanged) {
    location.reload();
    return;
  }
  const head = Number(data?.seq);
  if (identity.instanceChanged) {
    if (Number.isFinite(head)) {
      state.seq = head;
      expectedSeq = head + 1;
    }
    requestFullRefresh("the arena restarted");
    return;
  }
  if (!Number.isFinite(head)) return;
  if (head < state.seq) {
    // The bus counter went backwards: the server was restarted under us.
    state.seq = head;
    expectedSeq = head + 1;
    requestFullRefresh("the arena restarted");
  } else if (state.seq > 0 && head - state.seq > GAP_LIMIT) {
    // Further behind than the server will replay — patching would leave holes.
    requestFullRefresh("the event stream fell too far behind");
  }
}

function dispatch(type, data, atMs) {
  switch (type) {
    case "log":
      appendLog(data.level || "info", data.msg || "", atMs);
      break;

    case "status":
      state.status = data;
      renderStatus();
      break;

    case "game_finished": {
      const game = data.game;
      const delta = data.delta || {};
      if (game) {
        const known = (name) => state.ladder.some((row) => row.name === name);
        if (!known(game.a) || !known(game.b)) requestFullRefresh("an unknown bot played");
        applyGame(game, delta);
        updateCounts();
        emit("game", { game, delta });
        emit("ladder", state.ladder);
        consumeCompletedWebMatch(webMatchCompletions.captureGame(game));
      }
      break;
    }

    case "bot_added":
      appendLog("ok", `${data.name} discovered`, atMs);
      requestFullRefresh("a bot was added");
      emit("bot", { event: type, ...data });
      break;

    case "bot_changed":
      appendLog("info", `${data.name} changed on disk — sigma re-inflated`, atMs);
      requestFullRefresh("a bot changed");
      emit("bot", { event: type, ...data });
      break;

    case "bot_broken":
      appendLog("error", `${data.name} is broken: ${data.reason || "failed to load"}`, atMs);
      requestFullRefresh("a bot broke");
      emit("bot", { event: type, ...data });
      break;

    case "bot_fixed":
      appendLog("ok", `${data.name} loads again`, atMs);
      requestFullRefresh("a bot was fixed");
      emit("bot", { event: type, ...data });
      break;

    case "bot_active": {
      const row = state.ladder.find((candidate) => candidate.name === data.name);
      if (row) row.active = data.active !== false;
      else requestFullRefresh("an unknown bot changed activity");
      if (state.bots?.[data.name]?.bot) {
        state.bots[data.name].bot.active = data.active !== false;
      }
      state.matrix = null;
      refreshOpenRunCatalog?.();
      emit("bot", { event: type, ...data });
      emit("ladder", state.ladder);
      break;
    }

    case "run_started": {
      const total = Number.isFinite(data.total) ? ` (${data.total} games)` : "";
      appendLog("info", `${data.mode} started — ${data.label || "unnamed"}${total}`, atMs);
      break;
    }

    case "run_finished":
      appendLog(
        data.stopped ? "warn" : "ok",
        `${data.mode} finished — ${fmt.int(data.played)} games${data.stopped ? " (stopped)" : ""}`,
        atMs,
      );
      settleOptimisticWebMatch(data.batch_tag, { played: data.played });
      consumeCompletedWebMatch(webMatchCompletions.captureRunFinished(data));
      break;

    default:
      break;
  }
  // Raw pass-through so a view can listen for one specific server event.
  emit(type, data);
}

function handleFrame(type, event) {
  let envelope;
  try {
    envelope = JSON.parse(event.data);
  } catch {
    return;
  }
  const data = envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
  const atMs = Number.isFinite(envelope?.ts) ? envelope.ts * 1000 : Date.now();

  if (type === "hello") {
    onHello(data);
    return;
  }

  const seq = Number(envelope?.seq);
  if (Number.isFinite(seq)) {
    if (expectedSeq !== null && seq > expectedSeq) {
      requestFullRefresh("the event stream skipped ahead");
    }
    expectedSeq = seq + 1;
    if (seq > state.seq) state.seq = seq;
  }
  goOnline();
  dispatch(type, data, atMs);
}

/** Open (or reopen) the single `EventSource`, resuming from `state.seq`. */
function connect() {
  disconnect();
  setConnection("connecting");
  expectedSeq = state.seq + 1;

  let es;
  try {
    es = new EventSource(`/api/events?since=${encodeURIComponent(state.seq)}`);
  } catch (err) {
    console.error("oarena: cannot open the event stream", err);
    scheduleReconnect();
    return;
  }
  source = es;

  for (const type of SSE_TYPES) {
    es.addEventListener(type, (event) => {
      if (source !== es) return;
      handleFrame(type, event);
    });
  }
  es.addEventListener("error", () => {
    if (source !== es) return;
    // Take reconnection into our own hands so the backoff is ours, not the
    // browser's fixed `retry:` interval.
    disconnect();
    scheduleReconnect();
  });
}

function forceReconnect() {
  backoff = BACKOFF_MIN;
  disconnect();
  connect();
}

// --------------------------------------------------------------------------
// run dialog
// --------------------------------------------------------------------------

let runStartInFlight = false;
let refreshOpenRunCatalog = null;

function clampInt(value, min, max, fallback) {
  const n = Number.parseInt(value, 10);
  if (!Number.isFinite(n)) return fallback;
  return Math.min(max, Math.max(min, n));
}

function plural(n, word) {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

function runDialogStorage() {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/** Bind one accessible, recency-aware bot picker without constraining free text. */
function createBotCombobox(input, list, { everyone = false, includeInactive = false } = {}) {
  let choices = [];
  let active = -1;
  let blurTimer = 0;

  function setActive(index) {
    const options = [...list.querySelectorAll('[role="option"]')];
    active = options.length && index >= 0
      ? Math.max(0, Math.min(options.length - 1, index))
      : -1;
    for (const [i, option] of options.entries()) {
      const selected = i === active;
      option.setAttribute("aria-selected", selected ? "true" : "false");
      if (selected) option.scrollIntoView({ block: "nearest" });
    }
    if (active >= 0) input.setAttribute("aria-activedescendant", options[active].id);
    else input.removeAttribute("aria-activedescendant");
  }

  function close() {
    list.hidden = true;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
    active = -1;
  }

  function select(index) {
    const choice = choices[index];
    if (!choice) return;
    window.clearTimeout(blurTimer);
    input.value = choice.name;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    close();
    input.focus({ preventScroll: true });
  }

  function render({ resetActive = true } = {}) {
    choices = botSuggestions(state.ladder, input.value, {
      everyone,
      includeInactive,
      limit: 10,
    });
    const options = choices.map((row, index) => {
      const tags = [];
      if (row.everyone) tags.push("everyone");
      else if (row.broken) tags.push("broken");
      else if (!row.active) tags.push("off");
      const option = el(
        "div",
        {
          class: "bot-combobox-option",
          id: `${input.id}-option-${index}`,
          role: "option",
          "aria-selected": "false",
        },
        el("span", { class: "bot-combobox-name" }, row.name),
        tags.length ? el("span", { class: "bot-combobox-tag" }, tags.join(", ")) : null,
      );
      option.addEventListener("pointerdown", (event) => {
        if (event.pointerType === "mouse" && event.button !== 0) return;
        event.preventDefault();
        select(index);
      });
      // Assistive technologies may synthesize click without a pointer event.
      option.addEventListener("click", () => {
        if (!list.hidden) select(index);
      });
      option.addEventListener("mousemove", () => setActive(index));
      return option;
    });
    mount(list, ...options);
    list.hidden = options.length === 0;
    input.setAttribute("aria-expanded", options.length ? "true" : "false");
    if (resetActive) setActive(-1);
    else if (active >= 0) setActive(active);
  }

  input.addEventListener("focus", () => {
    window.clearTimeout(blurTimer);
    render();
  });
  input.addEventListener("click", () => {
    if (list.hidden) render();
  });
  input.addEventListener("input", () => render());
  input.addEventListener("blur", () => {
    blurTimer = window.setTimeout(close, 0);
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (list.hidden) render();
      if (!choices.length) return;
      if (active < 0) setActive(event.key === "ArrowDown" ? 0 : choices.length - 1);
      else setActive(Math.max(0, active + (event.key === "ArrowDown" ? 1 : -1)));
    } else if (event.key === "Enter" && !list.hidden && active >= 0) {
      event.preventDefault();
      select(active);
    } else if (event.key === "Escape" && !list.hidden) {
      event.preventDefault();
      event.stopPropagation();
      close();
    }
  });

  function refreshPicker() {
    if (document.activeElement === input || !list.hidden) {
      render({ resetActive: false });
    }
  }

  return { close, refresh: refreshPicker };
}

/**
 * The Run modal: a Match tab (explicit pairing over chosen maps) and an Arena
 * tab (a matchmaker that runs until stopped).
 *
 * Bot B's `everyone` option is not a match at all — it is posted to
 * `/api/arena` as `{kind: "vs", target: A}`, which is what "vs everyone" means
 * on the server.
 */
export function openRunDialog(initialTab = null) {
  if (runStartInFlight) {
    toast("a run is already being started", "warn");
    return;
  }
  const template = $("tpl-run-dialog");
  if (!template) return;
  const node = template.content.cloneNode(true).firstElementChild;
  const q = (id) => node.querySelector(`#${id}`);

  const tabMatch = q("run-tab-match");
  const tabArena = q("run-tab-arena");
  const panelMatch = q("run-panel-match");
  const panelArena = q("run-panel-arena");
  const botA = q("run-bot-a");
  const botB = q("run-bot-b");
  const botAOptions = q("run-bot-a-options");
  const botBOptions = q("run-bot-b-options");
  const swap = q("run-swap");
  const officialMapSet = q("run-maps-official");
  const extraMapSet = q("run-maps-extra");
  const repeat = q("run-repeat");
  const seedPolicyField = q("run-seed-policy-field");
  const seedPolicy = q("run-seed-policy");
  const seedField = q("run-seed-field");
  const seed = q("run-seed");
  const seedHelp = q("run-seed-help");
  const mirror = q("run-mirror");
  const rated = q("run-rated");
  const countLine = q("run-count");
  const arenaKind = q("arena-kind");
  const arenaTopField = q("arena-top-field");
  const arenaTop = q("arena-top");
  const arenaTargetField = q("arena-target-field");
  const arenaTarget = q("arena-target");
  const arenaTargetOptions = q("arena-target-options");
  const arenaWorkers = q("arena-workers");
  const arenaRated = q("arena-rated");
  const errorLine = q("run-error");
  const cancel = q("run-cancel");
  const submit = q("run-submit");
  const mapPreview = createMapPreview(node);
  const noBotsMessage = "No bots on disk — add a directory containing main.py and press Sync.";

  const storage = runDialogStorage();
  const project = state.config?.root || state.config?.name || "default";
  const availableBots = state.ladder.filter((row) => row.source_present !== false);
  const activeNames = availableBots
    .filter((row) => row.active !== false)
    .map((row) => row.name);
  const names = availableBots.map((row) => row.name);
  const preferredNames = activeNames.length ? activeNames : names;
  const mapNames = state.maps.map((map) => map.name);
  const configured = new Set(state.config?.maps || []);
  const defaultMaps = mapNames.filter((name) => configured.size === 0 || configured.has(name));
  const restored = normalizeRunDialogDraft(loadRunDialogDraft(storage, project), {
    botNames: names,
    arenaBotNames: activeNames,
    mapNames,
    defaults: {
      tab: "match",
      match: {
        a: preferredNames[0] ?? "",
        b: preferredNames[1] ?? (preferredNames.length ? "*" : ""),
        maps: defaultMaps,
        repeat: 1,
        mirror: state.config?.mirror !== false,
        rated: true,
        seedPolicy: state.config?.seed_policy === "fixed" ? "fixed" : "random",
        seed: normalizeCustomSeed(state.config?.seed_exact ?? state.config?.seed) ?? "1",
      },
      arena: { kind: "ladder", top: 8, target: activeNames[0] ?? "", rated: true },
    },
  });
  const matchDraft = restored.match;
  const arenaDraft = restored.arena;
  let tab = initialTab === "match" || initialTab === "arena"
    ? initialTab
    : restored.tab;

  // --- bots ---
  botA.value = matchDraft.a;
  botB.value = matchDraft.b;
  arenaTarget.value = arenaDraft.target;
  const botPickers = [
    createBotCombobox(botA, botAOptions, { includeInactive: true }),
    createBotCombobox(botB, botBOptions, { everyone: true, includeInactive: true }),
    createBotCombobox(arenaTarget, arenaTargetOptions),
  ];
  const currentAvailableBots = () => state.ladder.filter(
    (row) => row.source_present !== false,
  );
  const currentActiveNames = () => currentAvailableBots()
    .filter((row) => row.active !== false)
    .map((row) => row.name);
  const refreshBotCatalog = () => {
    for (const picker of botPickers) picker.refresh();
    const hasBots = currentAvailableBots().length > 0;
    if (!runStartInFlight) submit.disabled = !hasBots;
    if (!hasBots) fail(noBotsMessage);
    else if (errorLine.textContent === noBotsMessage) {
      errorLine.textContent = "";
      errorLine.hidden = true;
    }
  };

  // --- maps ---
  const restoredMaps = new Set(matchDraft.maps);
  const makeMapChip = (map) => {
    const on = restoredMaps.has(map.name);
    const chip = el(
      "button",
      {
        class: "chip chip-toggle",
        type: "button",
        "aria-pressed": on ? "true" : "false",
        "data-map": map.name,
      },
      map.name,
      " ",
      el("span", { class: "chip-dim" }, `${map.width}×${map.height}`),
    );
    chip.addEventListener("click", () => {
      chip.setAttribute("aria-pressed", chip.getAttribute("aria-pressed") === "true" ? "false" : "true");
      updateCount();
      persistDraft();
    });
    mapPreview.bind(chip, map);
    return chip;
  };
  const officialChips = state.maps
    .filter((map) => map.source !== "extra")
    .map(makeMapChip);
  const extraChips = state.maps
    .filter((map) => map.source === "extra")
    .map(makeMapChip);
  const chips = [...officialChips, ...extraChips];
  mount(
    officialMapSet,
    ...(officialChips.length
      ? officialChips
      : [el("span", { class: "map-picker-empty", text: "No official maps found" })]),
  );
  mount(
    extraMapSet,
    ...(extraChips.length
      ? extraChips
      : [el("span", { class: "map-picker-empty", text: "No extra maps found" })]),
  );

  const selectedMaps = () =>
    chips.filter((c) => c.getAttribute("aria-pressed") === "true").map((c) => c.dataset.map);

  const setAll = (subset, fn) => {
    for (const chip of subset) {
      chip.setAttribute("aria-pressed", fn(chip.getAttribute("aria-pressed") === "true") ? "true" : "false");
    }
    updateCount();
    persistDraft();
  };
  q("run-maps-all").addEventListener("click", () => setAll(chips, () => true));
  q("run-maps-none").addEventListener("click", () => setAll(chips, () => false));
  q("run-maps-invert").addEventListener("click", () => setAll(chips, (on) => !on));
  q("run-extra-maps-all").addEventListener("click", () => setAll(extraChips, () => true));
  q("run-extra-maps-none").addEventListener("click", () => setAll(extraChips, () => false));

  // --- restored values, falling back to project/template defaults ---
  repeat.value = String(matchDraft.repeat);
  seedPolicy.value = matchDraft.seedPolicy;
  seed.value = String(matchDraft.seed);
  let lastValidSeed = matchDraft.seed;
  mirror.checked = matchDraft.mirror;
  rated.checked = matchDraft.rated;
  arenaKind.value = arenaDraft.kind;
  arenaTop.value = String(arenaDraft.top);
  arenaRated.checked = arenaDraft.rated;
  arenaWorkers.value = String(state.config?.workers ?? "");

  function customSeedValue() {
    return normalizeCustomSeed(seed.value);
  }

  function syncSeedFields() {
    const applies = botB.value.trim() !== "*";
    seedPolicyField.hidden = !applies;
    seedField.hidden = !applies || seedPolicy.value !== "fixed";
    seedHelp.hidden = !applies;
  }

  function rememberedCustomSeed() {
    const value = customSeedValue();
    if (value !== null) lastValidSeed = value;
    return lastValidSeed;
  }

  function persistDraft() {
    saveRunDialogDraft(storage, project, {
      tab,
      match: {
        a: botA.value,
        b: botB.value,
        maps: selectedMaps(),
        repeat: clampInt(repeat.value, 1, 500, 1),
        mirror: mirror.checked,
        rated: rated.checked,
        seedPolicy: seedPolicy.value,
        seed: rememberedCustomSeed(),
      },
      arena: {
        kind: arenaKind.value,
        top: clampInt(arenaTop.value, 2, 64, 8),
        target: arenaTarget.value,
        rated: arenaRated.checked,
      },
    });
  }

  /** "15 maps × 2 rounds × 2 sides = **60 games**", live. */
  function updateCount() {
    syncSeedFields();
    if (botB.value.trim() === "*") {
      mount(countLine, 
        `${botA.value || "this bot"} against every other bot — runs as an arena until you press `,
        el("b", null, "Stop"),
        ".",
      );
      return;
    }
    const maps = selectedMaps().length;
    const rounds = clampInt(repeat.value, 1, 500, 1);
    const sides = mirror.checked ? 2 : 1;
    const total = maps * rounds * sides;
    mount(countLine, 
      `${plural(maps, "map")} × ${plural(rounds, "round")} × ${plural(sides, "side")} = `,
      el("b", null, plural(total, "game")),
    );
  }

  function setTab(next, { persist = true } = {}) {
    tab = next;
    const onMatch = next === "match";
    tabMatch.setAttribute("aria-selected", onMatch ? "true" : "false");
    tabArena.setAttribute("aria-selected", onMatch ? "false" : "true");
    panelMatch.hidden = !onMatch;
    panelArena.hidden = onMatch;
    for (const picker of botPickers) picker.close();
    submit.textContent = onMatch ? "Start match" : "Start arena";
    if (persist) persistDraft();
  }

  function syncArenaFields() {
    arenaTopField.hidden = arenaKind.value !== "top";
    arenaTargetField.hidden = arenaKind.value !== "vs";
  }

  function fail(message) {
    errorLine.textContent = message;
    errorLine.hidden = false;
  }

  async function start() {
    if (runStartInFlight || submit.disabled) return;
    runStartInFlight = true;
    errorLine.hidden = true;
    errorLine.textContent = "";
    submit.disabled = true;
    // A tiny invalid match can start and finish while its POST response is
    // still in flight. Remember the live-feed position so the optimistic
    // "running" state below cannot overwrite a newer completed status.
    const eventSeqAtSubmit = state.seq;
    let optimisticRun = null;
    try {
      botA.value = botA.value.trim();
      botB.value = botB.value.trim();
      arenaTarget.value = arenaTarget.value.trim();
      persistDraft();
      if (tab === "arena") {
        const kind = arenaKind.value;
        if (kind === "vs" && !arenaTarget.value) throw new Error("pick a target bot");
        if (kind === "vs" && !currentActiveNames().includes(arenaTarget.value)) {
          throw new Error("Arena targets must be enabled in Bots");
        }
        await api("/api/arena", {
          method: "POST",
          body: {
            kind,
            top: kind === "top" ? clampInt(arenaTop.value, 2, 64, 8) : 0,
            target: kind === "vs" ? arenaTarget.value : null,
            rated: arenaRated.checked,
          },
        });
        optimisticRun = {
          mode: kind === "vs" ? "vs" : "arena",
          label: kind === "vs" ? `${arenaTarget.value} vs field` : `${kind} arena`,
          total: null,
        };
        toast(`arena started (${kind})`, "ok");
      } else if (botB.value === "*") {
        if (!botA.value) throw new Error("pick a bot");
        if (!currentActiveNames().includes(botA.value)) {
          throw new Error("enable this bot in Bots before running it against everyone");
        }
        await api("/api/arena", {
          method: "POST",
          body: { kind: "vs", target: botA.value, rated: rated.checked },
        });
        optimisticRun = {
          mode: "vs",
          label: `${botA.value} vs everyone`,
          total: null,
        };
        toast(`arena started — ${botA.value} vs everyone`, "ok");
      } else {
        const maps = selectedMaps();
        const rounds = clampInt(repeat.value, 1, 500, 1);
        const customSeed = seedPolicy.value === "fixed" ? customSeedValue() : null;
        if (!botA.value || !botB.value) throw new Error("pick both bots");
        if (maps.length === 0) throw new Error("pick at least one map");
        if (seedPolicy.value === "fixed" && customSeed === null) {
          throw new Error(
            `custom seed must be a whole number from ${MIN_CUSTOM_SEED} to ${MAX_CUSTOM_SEED}`,
          );
        }
        if (customSeed !== null && !customSeedFitsRounds(customSeed, rounds)) {
          throw new Error(`custom seed plus ${rounds} rounds exceeds ${MAX_CUSTOM_SEED}`);
        }
        const batchTag = newWebMatchBatchTag();
        if (!webMatchCompletions.arm(batchTag)) {
          throw new Error("could not reserve this Match run; please try again");
        }
        let result;
        try {
          result = await api("/api/match", {
            method: "POST",
            body: {
              a: botA.value,
              b: botB.value,
              maps,
              repeat: rounds,
              mirror: mirror.checked,
              rated: rated.checked,
              seed_policy: seedPolicy.value,
              seed: customSeed,
              tag: batchTag,
            },
          });
        } catch (err) {
          webMatchCompletions.reject(batchTag);
          throw err;
        }
        if (result?.tag !== batchTag) {
          webMatchCompletions.reject(batchTag);
          throw new Error("the server did not confirm this Match run");
        }
        const completion = webMatchCompletions.accept(batchTag);
        consumeCompletedWebMatch(completion);
        if (!completion) scheduleWebMatchReconciliation(batchTag);
        optimisticRun = {
          mode: "match",
          label: `${botA.value} vs ${botB.value}`,
          total: result?.total,
          batchTag,
        };
        toast(`match queued — ${plural(result?.total ?? 0, "game")}`, "ok");
      }
      if (dom.modalHost?.contains(node)) closeModal();
      // The server's own status event follows within 500 ms; this keeps the
      // pill from reading "idle" in the meantime. If any server event arrived
      // during the request, its state is authoritative (the whole run may
      // already have finished), so leave it alone.
      if (state.seq === eventSeqAtSubmit) {
        state.status = optimisticRunStatus(state.status, optimisticRun);
        renderStatus();
      }
    } catch (err) {
      fail(err?.message || String(err));
    } finally {
      runStartInFlight = false;
      submit.disabled = false;
    }
  }

  tabMatch.addEventListener("click", () => setTab("match"));
  tabArena.addEventListener("click", () => setTab("arena"));
  botA.addEventListener("input", () => { updateCount(); persistDraft(); });
  botB.addEventListener("input", () => { updateCount(); persistDraft(); });
  repeat.addEventListener("input", () => { updateCount(); persistDraft(); });
  seedPolicy.addEventListener("change", () => { syncSeedFields(); persistDraft(); });
  seed.addEventListener("input", persistDraft);
  mirror.addEventListener("change", () => { updateCount(); persistDraft(); });
  rated.addEventListener("change", persistDraft);
  swap.addEventListener("click", () => {
    if (botB.value === "*") return;
    const a = botA.value;
    botA.value = botB.value;
    botB.value = a;
    updateCount();
    persistDraft();
  });
  arenaKind.addEventListener("change", () => { syncArenaFields(); persistDraft(); });
  arenaTop.addEventListener("input", persistDraft);
  arenaTarget.addEventListener("input", persistDraft);
  arenaRated.addEventListener("change", persistDraft);
  q("run-close").addEventListener("click", () => { persistDraft(); closeModal(); });
  cancel.addEventListener("click", () => { persistDraft(); closeModal(); });
  submit.addEventListener("click", start);
  // Enter submits from text/number fields, but not selects or buttons. Native
  // select Enter must only choose the seed policy; Cancel and Close stay inert.
  node.addEventListener("keydown", (event) => {
    const field = event.target instanceof HTMLInputElement;
    if (!event.defaultPrevented && event.key === "Enter" && field) {
      event.preventDefault();
      start();
    }
  });

  // Merely opening (and toggling closed) must not change the saved mode.
  // Starting or explicitly choosing a tab still persists it.
  setTab(tab, { persist: false });
  syncArenaFields();
  updateCount();

  if (availableBots.length === 0) {
    fail(noBotsMessage);
    submit.disabled = true;
  }

  openModal(node, {
    onClose: () => {
      if (refreshOpenRunCatalog === refreshBotCatalog) refreshOpenRunCatalog = null;
      mapPreview.destroy();
    },
  });
  refreshOpenRunCatalog = refreshBotCatalog;
  // Make the keyboard path `r`, Enter exactly equivalent to opening Match and
  // pressing its primary action. Disabled submits leave focus on Close.
  if (!submit.disabled) submit.focus({ preventScroll: true });
}

/** The `?` sheet, straight out of its template. */
export function openShortcuts() {
  const template = $("tpl-shortcuts");
  if (!template) return;
  const node = template.content.cloneNode(true).firstElementChild;
  node.querySelector("#shortcut-close").addEventListener("click", closeModal);
  openModal(node);
}

// --------------------------------------------------------------------------
// topbar actions
// --------------------------------------------------------------------------

async function stopRun() {
  if (dom.btnStop.disabled) return;
  dom.btnStop.disabled = true;
  const force = Boolean(state.status && state.status.stopping);
  try {
    await api("/api/stop", { method: "POST", body: force ? { force: true } : null });
    state.status = { ...(state.status || {}), stopping: true };
    renderStatus();
    if (force) toast("force stop requested — aborting in-flight games", "warn");
  } catch (err) {
    toast(`stop failed: ${err.message}`, "error");
    renderStatus();
  }
}

function describeSync(report) {
  const bits = [];
  for (const key of ["added", "changed", "missing", "unbroken"]) {
    const list = report?.[key];
    if (Array.isArray(list) && list.length) bits.push(`${key} ${list.join(", ")}`);
  }
  return bits.length ? bits.join(" · ") : "nothing changed";
}

async function syncNow() {
  dom.btnSync.disabled = true;
  try {
    const report = await api("/api/sync", { method: "POST" });
    const summary = describeSync(report);
    toast(`sync: ${summary}`, summary === "nothing changed" ? "info" : "ok");
    appendLog("info", `sync — ${summary}`);
    await refresh();
    if (reloadForWebRevisionChange()) return;
    expectedSeq = state.seq + 1;
    renderShell();
    renderStatus();
    safeRefreshView();
    refreshOpenRunCatalog?.();
  } catch (err) {
    toast(`sync failed: ${err.message}`, "error");
  } finally {
    dom.btnSync.disabled = false;
  }
}

/** A deliberate confirmation flow; the server refuses it while games run. */
export function openResetDialog() {
  const scope = el(
    "select",
    { class: "select", "aria-label": "What should be reset" },
    el("option", { value: "history", text: "Ladder only — games + ratings" }),
    el("option", { value: "clean", text: "Everything — ladder + replays + logs + bot history" })
  );
  const warning = el("p", { class: "field-hint" });
  const error = el("p", { class: "form-error", hidden: true });
  const cancel = el("button", { class: "btn btn-ghost", type: "button", text: "Cancel", onclick: closeModal });
  const submit = el("button", { class: "btn btn-danger", type: "button", text: "Confirm reset" });
  const node = el(
    "div",
    { class: "modal", role: "dialog", "aria-modal": "true", "aria-labelledby": "reset-title" },
    el("header", { class: "modal-head" },
      el("h2", { class: "modal-title", id: "reset-title", text: "Reset arena data" }),
      el("button", { class: "btn btn-ghost btn-icon modal-close", type: "button", "aria-label": "Close", text: "✕", onclick: closeModal })
    ),
    el("div", { class: "modal-body" },
      el("label", { class: "field" }, el("span", { class: "field-label", text: "What should be reset?" }), scope),
      warning,
      error
    ),
    el("footer", { class: "modal-foot" }, cancel, submit)
  );
  const describe = () => {
    const clean = scope.value === "clean";
    warning.textContent = clean
      ? "Deletes the complete arena database state: games, ratings, replays, logs, temporary files and tracked source-version history. Your bots/ and maps/ directories stay on disk."
      : "Deletes every game and returns each bot to its default rating and uncertainty. Bot notes and source-version history stay; existing replay and log files stay on disk.";
    submit.textContent = clean ? "Delete all arena data" : "Reset ladder";
  };
  scope.addEventListener("change", describe);
  submit.addEventListener("click", async () => {
    const clean = scope.value === "clean";
    submit.disabled = true;
    error.hidden = true;
    try {
      await api("/api/reset", { method: "POST", body: clean ? { all: true, clean: true } : {} });
      closeModal();
      await refresh();
      if (reloadForWebRevisionChange()) return;
      expectedSeq = state.seq + 1;
      renderShell();
      renderStatus();
      safeRefreshView();
      toast(clean ? "clean arena reset" : "history reset", "ok");
    } catch (err) {
      error.textContent = err?.message || String(err);
      error.hidden = false;
      describe();
    }
  });
  describe();
  openModal(node);
  phrase.focus();
}

function wireChrome() {
  dom.btnRun.addEventListener("click", () => openRunDialog());
  dom.btnStop.addEventListener("click", stopRun);
  dom.btnSync.addEventListener("click", syncNow);
  dom.btnTheme.addEventListener("click", () =>
    setTheme(state.theme === "dark" ? "light" : "dark"),
  );
  dom.btnShortcuts.addEventListener("click", openShortcuts);
  dom.offlineRetry.addEventListener("click", forceReconnect);
}

// --------------------------------------------------------------------------
// keyboard
// --------------------------------------------------------------------------

function isTyping(target) {
  // Check both the event target and the focused element.  Some browsers retarget
  // key events around number-input spinner controls, and a global `1`–`6`
  // shortcut must never steal a character from an active form control.
  const candidates = [target, document.activeElement];
  return candidates.some((node) => {
    if (!(node instanceof Element)) return false;
    return node.matches("input, textarea, select, [contenteditable='true']")
      || Boolean(node.closest("input, textarea, select, [contenteditable='true']"));
  });
}

/** `/` — focus whatever the current view offers as its filter box. */
function focusFilter() {
  const input =
    dom.view.querySelector(".search input") ||
    dom.view.querySelector('input[type="search"]') ||
    dom.view.querySelector("input.input");
  if (!input) return false;
  input.focus();
  input.select?.();
  return true;
}

/** Toggle only the Run dialog; never replace a different open modal. */
function toggleRunDialog() {
  if (dom.modalHost?.querySelector("#run-dialog")) {
    closeModal();
    return true;
  }
  if (!dom.modalHost?.hidden) return false;
  openRunDialog("match");
  return true;
}

function onKeydown(event) {
  if (event.defaultPrevented) return;

  if (event.key === "Escape") {
    if (!dom.modalHost.hidden) {
      event.preventDefault();
      closeModal();
    } else if (!dom.drawerHost.hidden) {
      event.preventDefault();
      closeDrawer();
    } else if (isTyping(event.target)) {
      event.target.blur();
    } else {
      hideTooltip();
    }
    return;
  }

  if (isTyping(event.target)) return;
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  if (event.key === "r" && !event.repeat && toggleRunDialog()) {
    event.preventDefault();
    return;
  }
  // Every modal other than Run owns the keyboard while it is up; number
  // shortcuts must not navigate the view hidden behind it.
  if (!dom.modalHost.hidden) return;

  const index = "123456789".indexOf(event.key);
  if (index >= 0) {
    event.preventDefault();
    navigate(NAV_HASHES[index]);
    return;
  }

  switch (event.key) {
    case "s":
      event.preventDefault();
      stopRun();
      break;
    case "/":
      if (focusFilter()) event.preventDefault();
      break;
    case "l":
      event.preventDefault();
      setLogOpen(!logIsOpen());
      break;
    case "t":
      event.preventDefault();
      setTheme(state.theme === "dark" ? "light" : "dark");
      break;
    case "?":
      event.preventDefault();
      openShortcuts();
      break;
    default:
      break;
  }
}

// --------------------------------------------------------------------------
// boot
// --------------------------------------------------------------------------

/**
 * Anything `views.js` needs from the shell without importing this module —
 * importing `app.js` from `views.js` would close an import cycle.
 */
const bridge = {
  el,
  emptyState,
  toast,
  navigate,
  openModal,
  closeModal,
  openDrawer,
  closeDrawer,
  openRunDialog,
  openResetDialog,
  showTooltip,
  hideTooltip,
  setTheme,
  appendLog,
  squareViewer,
};

async function boot() {
  globalThis.oarena = bridge;

  if (!location.hash) history.replaceState(null, "", "#/ladder");
  setTheme(dom.root.dataset.theme || "dark", { rerender: false, persist: false });

  wireChrome();
  wireOverlays();
  wireLog();
  wireTooltips();
  document.addEventListener("keydown", onKeydown);
  window.addEventListener("hashchange", render);
  window.addEventListener("beforeunload", disconnect);

  // Games is the only primary route whose first page is not part of /api/state.
  // Fetch its compact summary in parallel with boot so the tab is data-ready.
  void preloadGames();
  renderStatus();

  try {
    await refresh();
    if (reloadForWebRevisionChange()) return;
    renderShell();
    renderStatus();
  } catch (err) {
    appendLog("error", `could not read /api/state: ${err.message}`);
    toast(`could not reach the arena: ${err.message}`, "error");
  }

  connect();
  await render();
}

boot();
