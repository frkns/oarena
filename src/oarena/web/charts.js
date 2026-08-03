/**
 * charts.js — dependency-free SVG/canvas builders for the oarena dashboard.
 *
 * Every builder returns a detached element the caller inserts wherever it likes.
 * Nothing here imports anything, touches global state, or hard-codes a colour:
 * strokes and fills come from the design system's custom properties (or from
 * `currentColor`), so a chart follows the theme without being re-rendered. The
 * one exception is `mapThumb`, which paints into a canvas and therefore has to
 * resolve those properties to concrete values at draw time.
 *
 * All builders are total: empty, missing or malformed input produces a valid
 * (usually placeholder) element rather than an exception.
 */

const SVG_NS = "http://www.w3.org/2000/svg";

/**
 * Standard-normal quantile for a two-sided 95% interval.
 *
 * Every band and every LCB95 value in the UI uses this one number, and it
 * matches `oarena.ratings.CI` on the server. LCB95 is exactly the lower edge of
 * the band.
 */
export const CI = 1.959963984540054;
export const CI_LABEL = "\u03bc \u2212 1.96\u03c3";


/* -------------------------------------------------------------------------- */
/* tiny helpers                                                               */
/* -------------------------------------------------------------------------- */

/** Create an SVG element with attributes (numbers are stringified, null skipped). */
function s(tag, attrs) {
  const node = document.createElementNS(SVG_NS, tag);
  if (attrs) {
    for (const key of Object.keys(attrs)) {
      const value = attrs[key];
      if (value === null || value === undefined || value === false) continue;
      node.setAttribute(key, String(value));
    }
  }
  return node;
}

/** A `<title>` child — the zero-cost native tooltip for a chart element. */
function titled(node, text) {
  if (text) {
    const t = s("title");
    t.textContent = text;
    node.appendChild(t);
  }
  return node;
}

function num(value, fallback = 0) {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function clamp(value, lo, hi) {
  return value < lo ? lo : value > hi ? hi : value;
}

function round(value, digits = 2) {
  return num(value).toFixed(digits);
}

/** Keep both identity and distinguishing suffix when a mono chart label is too long. */
function middleEllipsis(value, maxChars) {
  const text = String(value ?? "");
  const limit = Math.max(5, Math.floor(num(maxChars, text.length)));
  if (text.length <= limit) return text;
  const room = limit - 1;
  const left = Math.max(2, Math.floor(room * 0.38));
  return `${text.slice(0, left)}…${text.slice(-(room - left))}`;
}

/**
 * Tick positions on a "nice" 1/2/2.5/5 × 10ⁿ grid covering [lo, hi].
 *
 * Returns at most `count + 2` values; an empty or degenerate range yields the
 * two endpoints so callers never have to special-case it.
 */
function niceTicks(lo, hi, count = 6) {
  if (!Number.isFinite(lo) || !Number.isFinite(hi) || hi <= lo) return [lo, hi];
  const raw = (hi - lo) / Math.max(1, count);
  const magnitude = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / magnitude;
  const step = (norm >= 5 ? 10 : norm >= 2.5 ? 5 : norm >= 2 ? 2.5 : norm >= 1 ? 2 : 1) * magnitude;
  const ticks = [];
  for (let t = Math.ceil(lo / step) * step; t <= hi + step * 1e-9; t += step) {
    ticks.push(Math.abs(t) < step * 1e-9 ? 0 : t);
  }
  return ticks.length ? ticks : [lo, hi];
}

/** Format a tick label without trailing noise ("25", "27.5", "-3"). */
function tickLabel(value) {
  const rounded = Math.round(value * 100) / 100;
  return Number.isInteger(rounded) ? String(rounded) : String(rounded);
}

/** A centred placeholder used whenever there is nothing to draw. */
function placeholder(width, height, message) {
  const root = s("svg", {
    class: "chart-svg",
    viewBox: `0 0 ${width} ${height}`,
    role: "img",
    "aria-label": message,
  });
  const text = s("text", {
    class: "axis-text",
    x: width / 2,
    y: height / 2,
    "text-anchor": "middle",
    "dominant-baseline": "middle",
  });
  text.textContent = message;
  root.appendChild(text);
  return root;
}

/* -------------------------------------------------------------------------- */
/* rating interval chart                                                      */
/* -------------------------------------------------------------------------- */

/**
 * Horizontal 95% credible intervals (μ ± 1.96σ), one row per bot, on a single
 * shared x-scale. The left edge of a band is exactly that bot's LCB95.
 *
 * This is the honest picture of a TrueSkill ladder: the bar is the whole
 * plausible range of a bot's skill and the tick is its mean, so two bands that
 * do not overlap are a real ordering while two that do are still a coin toss.
 * Rows are drawn in the order given (the caller normally sorts by μ) and the
 * row height shrinks as the field grows so 40 bots still fit.
 *
 * @param {Array<{name:string,mu:number,sigma:number,lcb95?:number,score?:number,rank?:number,
 *                broken?:boolean,inactive?:boolean,active?:boolean}>} rows
 * @param {{width?:number,rowHeight?:number,labelWidth?:number,valueWidth?:number,
 *          maxLabelWidth?:number,minPlotWidth?:number,highlight?:string,onSelect?:Function}} [opts]
 * @returns {SVGElement}
 */
export function intervalChart(rows, opts = {}) {
  const list = (Array.isArray(rows) ? rows : []).filter(Boolean);
  const width = num(opts.width, 720);
  if (!list.length) return placeholder(width, 90, "No rated bots yet");

  const valueW = num(opts.valueWidth, 52);
  const labelText = (row) => row.rank ? `${row.rank}. ${String(row.name ?? "")}` : String(row.name ?? "");
  // Mono labels average a little over six logical SVG units per glyph. Grow
  // the gutter for real bot names, while always reserving a useful interval
  // plot. Anything beyond the bound is middle-ellipsised so suffix variants
  // remain distinguishable.
  const longestLabel = list.reduce((longest, row) => Math.max(longest, labelText(row).length), 0);
  const minPlotW = Math.max(240, num(opts.minPlotWidth, 300));
  const maxLabelW = Math.max(124, Math.min(num(opts.maxLabelWidth, 310), width - valueW - minPlotW));
  const wantedLabelW = 18 + longestLabel * 6.35;
  const labelW = opts.labelWidth === undefined
    ? clamp(wantedLabelW, 124, maxLabelW)
    : clamp(num(opts.labelWidth, 124), 80, Math.max(80, width - valueW - 40));
  const maxLabelChars = Math.max(5, Math.floor((labelW - 14) / 6.35));
  const rowH = num(opts.rowHeight, list.length > 26 ? 13 : list.length > 14 ? 16 : 19);
  const padTop = 6;
  const axisH = 18;
  const plotL = labelW;
  const plotR = width - valueW;
  const plotW = Math.max(40, plotR - plotL);
  const bodyH = list.length * rowH;
  const height = padTop + bodyH + axisH;

  let lo = Infinity;
  let hi = -Infinity;
  for (const row of list) {
    const mu = num(row.mu, 25);
    const sigma = Math.abs(num(row.sigma, 0));
    lo = Math.min(lo, mu - CI * sigma);
    hi = Math.max(hi, mu + CI * sigma);
  }
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) {
    lo = 0;
    hi = 50;
  }
  if (hi - lo < 1e-6) {
    lo -= 1;
    hi += 1;
  }
  const margin = (hi - lo) * 0.04;
  lo -= margin;
  hi += margin;
  const x = (value) => plotL + ((num(value) - lo) / (hi - lo)) * plotW;

  const interactive = typeof opts.onSelect === "function";
  const root = s("svg", {
    class: "bandchart",
    viewBox: `0 0 ${width} ${height}`,
    role: interactive ? "group" : "img",
    "aria-label": `Rating intervals for ${list.length} bots`,
  });

  for (const tick of niceTicks(lo, hi, 6)) {
    const tx = x(tick);
    if (tx < plotL - 0.5 || tx > plotR + 0.5) continue;
    root.appendChild(s("line", { class: "grid-line", x1: tx, x2: tx, y1: padTop, y2: padTop + bodyH }));
    const label = s("text", { class: "axis-text", x: tx, y: height - 5, "text-anchor": "middle" });
    label.textContent = tickLabel(tick);
    root.appendChild(label);
  }
  root.appendChild(
    s("line", { class: "axis-line", x1: plotL, x2: plotR, y1: padTop + bodyH, y2: padTop + bodyH })
  );

  const bandH = Math.max(5, Math.min(9, rowH - 5));
  list.forEach((row, index) => {
    const name = String(row.name ?? "");
    const mu = num(row.mu, 25);
    const sigma = Math.abs(num(row.sigma, 0));
    const lcb95 = row.lcb95 === undefined || row.lcb95 === null
      ? (row.score === undefined || row.score === null ? mu - CI * sigma : num(row.score))
      : num(row.lcb95);
    const inactive = row.inactive === true || row.active === false;
    const y = padTop + index * rowH;
    const bandY = y + (rowH - bandH) / 2;

    const description =
      `${name}. LCB95 ${round(lcb95)}; mean ${round(mu)}; sigma ${round(sigma)}; ` +
      `95 percent interval ${round(mu - CI * sigma)} to ${round(mu + CI * sigma)}`;
    const group = titled(s("g", { "data-name": name, "aria-label": description }), description);
    if (interactive) {
      group.setAttribute("role", "link");
      group.setAttribute("tabindex", "0");
      group.style.cursor = "pointer";
      const select = () => opts.onSelect(name);
      group.addEventListener("click", select);
      group.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          select();
        }
      });
    }
    const hit = s("rect", {
      class: "band-row-hit",
      x: 0,
      y,
      width,
      height: rowH,
      "data-name": name,
    });
    group.appendChild(hit);

    const label = s("text", {
      class: "band-label",
      x: labelW - 8,
      y: y + rowH / 2,
      "text-anchor": "end",
      "dominant-baseline": "middle",
    });
    label.textContent = middleEllipsis(labelText(row), maxLabelChars);
    group.appendChild(label);

    const left = x(mu - CI * sigma);
    const right = x(mu + CI * sigma);
    const band = s("rect", {
      class: "band",
      x: left,
      y: bandY,
      width: Math.max(2, right - left),
      height: bandH,
      "data-broken": row.broken ? "true" : "false",
      "data-inactive": inactive ? "true" : "false",
    });
    band.setAttribute("rx", "2");
    group.appendChild(band);

    const tick = x(mu);
    group.appendChild(
      s("line", { class: "band-mu", x1: tick, x2: tick, y1: y + 1.5, y2: y + rowH - 1.5 })
    );

    const value = s("text", {
      class: "band-value",
      x: width - 4,
      y: y + rowH / 2,
      "text-anchor": "end",
      "dominant-baseline": "middle",
    });
    value.textContent = round(lcb95);
    group.appendChild(value);

    if (opts.highlight && opts.highlight === name) {
      group.appendChild(
        s("rect", {
          class: "band-row-hit",
          x: 0,
          y,
          width,
          height: rowH,
          style: "fill: var(--accent-soft)",
        })
      );
    }
    root.appendChild(group);
  });

  return root;
}

/* -------------------------------------------------------------------------- */
/* line chart with an optional confidence band                                */
/* -------------------------------------------------------------------------- */

/**
 * A single series with an optional σ ribbon and a hover crosshair.
 *
 * The crosshair is wired inside the returned SVG (pointer events on a full-plot
 * overlay), so the caller only has to insert the node. Client coordinates are
 * converted through the element's own bounding box, which keeps the readout
 * correct however the chart is scaled by CSS.
 *
 * @param {Array<{x:number,y:number}>} series
 * @param {{band?:Array<{x:number,lo:number,hi:number}>,markers?:Array<{x:number,label?:string,title?:string}>,
 *          height?:number,width?:number,label?:string,xLabel?:string,digits?:number,dots?:boolean}} [opts]
 * @returns {SVGElement}
 */
export function lineChart(series, opts = {}) {
  const points = (Array.isArray(series) ? series : [])
    .filter((p) => p && Number.isFinite(num(p.x, NaN)) && Number.isFinite(num(p.y, NaN)))
    .map((p) => ({ x: num(p.x), y: num(p.y) }));
  const width = num(opts.width, 640);
  const height = num(opts.height, 170);
  if (points.length === 0) return placeholder(width, height, "No history yet");

  const band = (Array.isArray(opts.band) ? opts.band : []).filter(
    (p) => p && Number.isFinite(num(p.x, NaN)) && Number.isFinite(num(p.lo, NaN)) && Number.isFinite(num(p.hi, NaN))
  );
  const digits = opts.digits === undefined ? 2 : num(opts.digits, 2);
  const left = 46;
  const right = width - 10;
  const top = 10;
  const bottom = height - 20;

  let xLo = Infinity;
  let xHi = -Infinity;
  let yLo = Infinity;
  let yHi = -Infinity;
  for (const p of points) {
    xLo = Math.min(xLo, p.x);
    xHi = Math.max(xHi, p.x);
    yLo = Math.min(yLo, p.y);
    yHi = Math.max(yHi, p.y);
  }
  for (const p of band) {
    xLo = Math.min(xLo, num(p.x));
    xHi = Math.max(xHi, num(p.x));
    yLo = Math.min(yLo, num(p.lo));
    yHi = Math.max(yHi, num(p.hi));
  }
  if (xHi - xLo < 1e-9) {
    xLo -= 0.5;
    xHi += 0.5;
  }
  if (yHi - yLo < 1e-9) {
    yLo -= 1;
    yHi += 1;
  }
  const pad = (yHi - yLo) * 0.08;
  yLo -= pad;
  yHi += pad;

  const px = (v) => left + ((num(v) - xLo) / (xHi - xLo)) * (right - left);
  const py = (v) => bottom - ((num(v) - yLo) / (yHi - yLo)) * (bottom - top);

  const root = s("svg", {
    class: "chart-svg",
    viewBox: `0 0 ${width} ${height}`,
    role: "img",
    "aria-label": opts.label || "Rating over games",
  });

  for (const tick of niceTicks(yLo, yHi, 4)) {
    const y = py(tick);
    if (y < top - 0.5 || y > bottom + 0.5) continue;
    root.appendChild(s("line", { class: "grid-line", x1: left, x2: right, y1: y, y2: y }));
    const label = s("text", {
      class: "axis-text",
      x: left - 6,
      y,
      "text-anchor": "end",
      "dominant-baseline": "middle",
    });
    label.textContent = tickLabel(tick);
    root.appendChild(label);
  }
  root.appendChild(s("line", { class: "axis-line", x1: left, x2: right, y1: bottom, y2: bottom }));

  for (const tick of niceTicks(xLo, xHi, 4)) {
    const x = px(tick);
    if (x < left - 0.5 || x > right + 0.5) continue;
    const label = s("text", { class: "axis-text", x, y: height - 5, "text-anchor": "middle" });
    label.textContent = tickLabel(Math.round(tick));
    root.appendChild(label);
  }

  if (band.length > 1) {
    const forward = band.map((p) => `${px(p.x)},${py(p.hi)}`);
    const backward = band
      .slice()
      .reverse()
      .map((p) => `${px(p.x)},${py(p.lo)}`);
    root.appendChild(
      s("path", { class: "series-band", d: `M${forward.join("L")}L${backward.join("L")}Z` })
    );
  }

  // A source change happens between games, so callers anchor a marker to the
  // first rating point made with that version. It is deliberately behind the
  // series so the dashed rule describes history without hiding the data.
  const markers = (Array.isArray(opts.markers) ? opts.markers : []).filter(
    (marker) => marker && Number.isFinite(num(marker.x, NaN))
  );
  for (const marker of markers) {
    const mx = num(marker.x);
    if (mx < xLo || mx > xHi) continue;
    const line = s("line", {
      class: "series-version-marker",
      x1: px(mx),
      x2: px(mx),
      y1: top,
      y2: bottom,
    });
    root.appendChild(titled(line, String(marker.title || marker.label || "Source changed")));
  }

  root.appendChild(
    s("polyline", {
      class: "series-line",
      points: points.map((p) => `${px(p.x)},${py(p.y)}`).join(" "),
      "vector-effect": "non-scaling-stroke",
    })
  );

  const showDots = opts.dots !== false && points.length <= 60;
  if (showDots) {
    for (const p of points) {
      root.appendChild(s("circle", { class: "series-dot", cx: px(p.x), cy: py(p.y), r: 1.7 }));
    }
  }

  // -- crosshair ----------------------------------------------------------
  const cross = s("g", { "pointer-events": "none", hidden: "hidden" });
  const rule = s("line", { class: "grid-line", y1: top, y2: bottom, style: "stroke: var(--accent)" });
  const dot = s("circle", { class: "series-dot", r: 3 });
  const readout = s("text", { class: "axis-text", y: top + 2, style: "fill: var(--fg)" });
  cross.append(rule, dot, readout);
  root.appendChild(cross);

  const overlay = s("rect", {
    x: left,
    y: top,
    width: Math.max(1, right - left),
    height: Math.max(1, bottom - top),
    fill: "transparent",
    "pointer-events": "all",
  });
  const move = (event) => {
    const box = root.getBoundingClientRect();
    if (!box.width) return;
    const vx = ((event.clientX - box.left) / box.width) * width;
    let best = points[0];
    let bestDistance = Infinity;
    for (const p of points) {
      const d = Math.abs(px(p.x) - vx);
      if (d < bestDistance) {
        bestDistance = d;
        best = p;
      }
    }
    const cx = px(best.x);
    const cy = py(best.y);
    rule.setAttribute("x1", String(cx));
    rule.setAttribute("x2", String(cx));
    dot.setAttribute("cx", String(cx));
    dot.setAttribute("cy", String(cy));
    readout.textContent = `#${Math.round(best.x)} · ${round(best.y, digits)}`;
    readout.setAttribute("x", String(cx > (left + right) / 2 ? cx - 6 : cx + 6));
    readout.setAttribute("text-anchor", cx > (left + right) / 2 ? "end" : "start");
    cross.removeAttribute("hidden");
  };
  overlay.addEventListener("pointermove", move);
  overlay.addEventListener("pointerleave", () => cross.setAttribute("hidden", "hidden"));
  root.appendChild(overlay);

  return root;
}

/* -------------------------------------------------------------------------- */
/* multi-bot rating history                                                    */
/* -------------------------------------------------------------------------- */

const TIMELINE_COLOURS = [
  "var(--accent)", "var(--b)", "var(--win)", "var(--warn)",
  "#cf8cff", "#64d7d2", "#ff778d", "#a9c15e",
];

function timelineTick(ms) {
  const date = new Date(ms);
  if (Number.isNaN(date.getTime())) return "–";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/**
 * Multiple TrueSkill histories on either a per-bot game-count or time axis.
 *
 * Each series is ``{name, points: [{x, y, sigma}], markers: [{x, y, title}]}``.
 * The translucent ribbon is its 95% interval (μ ± 1.96σ); a small outlined dot
 * marks the first game played after a source hash changed.
 */
export function multiRatingChart(series, opts = {}) {
  const requested = opts.xDomain || {};
  const requestedLo = num(requested.lo, NaN);
  const requestedHi = num(requested.hi, NaN);
  const hasRequestedDomain = Number.isFinite(requestedLo) && Number.isFinite(requestedHi)
    && requestedHi > requestedLo;
  const list = (Array.isArray(series) ? series : [])
    .map((row, index) => ({
      ...row,
      colour: row.colour || TIMELINE_COLOURS[index % TIMELINE_COLOURS.length],
      points: (Array.isArray(row.points) ? row.points : []).filter(
        (p) => p && Number.isFinite(num(p.x, NaN)) && Number.isFinite(num(p.y, NaN))
          && (!hasRequestedDomain || (num(p.x) >= requestedLo && num(p.x) <= requestedHi))
      ),
    }))
    .filter((row) => row.points.length);
  const width = num(opts.width, 760);
  const height = num(opts.height, 270);
  const timeAxis = opts.xMode === "time";
  if (!list.length) return placeholder(width, height, "No rated history yet");

  const left = 48, right = width - 10, top = 12, bottom = height - 24;
  // A zoom/range control specifies the x domain, not merely a filter.  Keeping
  // that exact domain is what makes the global-game axis honest: if no selected
  // bot played for a stretch, the chart shows a gap instead of silently pulling
  // its left edge right to the first remaining point.
  let xLo = hasRequestedDomain ? requestedLo : Infinity;
  let xHi = hasRequestedDomain ? requestedHi : -Infinity;
  let yLo = Infinity, yHi = -Infinity;
  for (const row of list) for (const point of row.points) {
    const sigma = Math.abs(num(point.sigma, 0));
    if (!hasRequestedDomain) {
      xLo = Math.min(xLo, num(point.x));
      xHi = Math.max(xHi, num(point.x));
    }
    yLo = Math.min(yLo, num(point.y) - CI * sigma);
    yHi = Math.max(yHi, num(point.y) + CI * sigma);
  }
  if (xHi - xLo < 1) {
    if (timeAxis) { xLo -= 43_200_000; xHi += 43_200_000; }
    else { xLo -= 0.5; xHi += 0.5; }
  }
  if (yHi - yLo < 1e-9) { yLo -= 1; yHi += 1; }
  const yPad = (yHi - yLo) * 0.08;
  yLo -= yPad; yHi += yPad;
  const px = (x) => left + ((num(x) - xLo) / (xHi - xLo)) * (right - left);
  const py = (y) => bottom - ((num(y) - yLo) / (yHi - yLo)) * (bottom - top);

  const interactive = typeof opts.onZoom === "function" || typeof opts.onReset === "function";
  const root = s("svg", {
    class: `chart-svg multi-rating-chart${interactive ? " is-zoomable" : ""}`,
    viewBox: `0 0 ${width} ${height}`,
    role: "img",
    "aria-label": `${opts.label || `Top bot ratings by ${timeAxis ? "time" : "games played"}, with 95% intervals`}${interactive ? "; drag across the plot to zoom the x-axis, double-click to reset" : ""}`,
  });
  for (const tick of niceTicks(yLo, yHi, 4)) {
    const y = py(tick);
    root.appendChild(s("line", { class: "grid-line", x1: left, x2: right, y1: y, y2: y }));
    const text = s("text", { class: "axis-text", x: left - 6, y, "text-anchor": "end", "dominant-baseline": "middle" });
    text.textContent = tickLabel(tick);
    root.appendChild(text);
  }
  for (let i = 0; i <= 4; i += 1) {
    const x = left + ((right - left) * i) / 4;
    const value = xLo + ((xHi - xLo) * i) / 4;
    root.appendChild(s("line", { class: "grid-line", x1: x, x2: x, y1: top, y2: bottom }));
    const text = s("text", { class: "axis-text", x, y: height - 5, "text-anchor": "middle" });
    text.textContent = timeAxis ? timelineTick(value) : String(Math.max(0, Math.round(value)));
    root.appendChild(text);
  }
  root.appendChild(s("line", { class: "axis-line", x1: left, x2: right, y1: bottom, y2: bottom }));

  for (const row of list) {
    const points = row.points;
    if (points.length > 1) {
      const upper = points.map((p) => `${px(p.x)},${py(num(p.y) + CI * Math.abs(num(p.sigma, 0)))}`);
      const lower = points.slice().reverse().map((p) => `${px(p.x)},${py(num(p.y) - CI * Math.abs(num(p.sigma, 0)))}`);
      root.appendChild(s("path", { class: "multi-series-band", d: `M${upper.join("L")}L${lower.join("L")}Z`, style: `fill:${row.colour}` }));
      root.appendChild(s("polyline", { class: "multi-series-line", points: points.map((p) => `${px(p.x)},${py(p.y)}`).join(" "), style: `stroke:${row.colour}` }));
    } else {
      root.appendChild(s("circle", { class: "multi-series-point", cx: px(points[0].x), cy: py(points[0].y), r: 2.5, style: `fill:${row.colour}` }));
    }
    for (const marker of Array.isArray(row.markers) ? row.markers : []) {
      if (!Number.isFinite(num(marker.x, NaN)) || !Number.isFinite(num(marker.y, NaN))) continue;
      if (num(marker.x) < xLo || num(marker.x) > xHi) continue;
      const dot = s("circle", { class: "source-change-dot", cx: px(marker.x), cy: py(marker.y), r: 2.1, style: `stroke:${row.colour}` });
      root.appendChild(titled(dot, String(marker.title || `${row.name}: source changed`)));
    }
  }

  if (interactive) {
    const brush = s("rect", { class: "chart-zoom-select", x: left, y: top, width: 0, height: bottom - top, hidden: true });
    root.appendChild(brush);
    let dragStart = null;
    let dragEnd = null;
    let dragRect = null;
    let paintFrame = 0;
    const svgX = (event, rect = root.getBoundingClientRect()) => {
      if (!rect.width) return left;
      return clamp(((event.clientX - rect.left) / rect.width) * width, left, right);
    };
    const drawBrush = (from, to) => {
      const x = Math.min(from, to);
      brush.setAttribute("x", String(x));
      brush.setAttribute("width", String(Math.abs(to - from)));
      brush.removeAttribute("hidden");
    };
    root.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      dragRect = root.getBoundingClientRect();
      const x = svgX(event, dragRect);
      const y = ((event.clientY - dragRect.top) / dragRect.height) * height;
      if (y < top || y > bottom) return;
      dragStart = x;
      dragEnd = x;
      root.setPointerCapture?.(event.pointerId);
      drawBrush(x, x);
      event.preventDefault();
    });
    root.addEventListener("pointermove", (event) => {
      if (dragStart === null) return;
      dragEnd = svgX(event, dragRect || undefined);
      // Pointer events can arrive much faster than the browser can repaint an
      // SVG. Paint one brush per animation frame; the final pointer position
      // is still used exactly when the drag ends.
      if (!paintFrame) paintFrame = requestAnimationFrame(() => {
        paintFrame = 0;
        if (dragStart !== null && dragEnd !== null) drawBrush(dragStart, dragEnd);
      });
    });
    const finishDrag = (event) => {
      if (dragStart === null) return;
      const end = svgX(event, dragRect || undefined);
      const start = dragStart;
      dragStart = null;
      dragEnd = null;
      dragRect = null;
      if (paintFrame) cancelAnimationFrame(paintFrame);
      paintFrame = 0;
      brush.setAttribute("hidden", "");
      try { root.releasePointerCapture?.(event.pointerId); } catch { /* already released */ }
      if (Math.abs(end - start) < 8 || typeof opts.onZoom !== "function") return;
      const lo = xLo + ((Math.min(start, end) - left) / (right - left)) * (xHi - xLo);
      const hi = xLo + ((Math.max(start, end) - left) / (right - left)) * (xHi - xLo);
      opts.onZoom({ lo, hi });
    };
    root.addEventListener("pointerup", finishDrag);
    root.addEventListener("pointercancel", finishDrag);
    root.addEventListener("dblclick", (event) => {
      if (typeof opts.onReset === "function") {
        event.preventDefault();
        opts.onReset();
      }
    });
  }
  return root;
}

/* -------------------------------------------------------------------------- */
/* horizontal bar chart                                                       */
/* -------------------------------------------------------------------------- */

/**
 * Horizontal bars for rates in 0..1 (per-map win rate, per-opponent share…).
 *
 * A dashed reference line marks 50 %, bars are tinted win-green above it and
 * loss-red below, and the sample size fades a bar out so a 1-game map does not
 * shout as loudly as a 40-game one. Items with no games render as a track and
 * an en dash.
 *
 * @param {Array<{label:string,value:number|null,n?:number}>} items
 * @param {{width?:number,rowHeight?:number,labelWidth?:number,valueWidth?:number,
 *          reference?:number|null,max?:number}} [opts]
 * @returns {SVGElement}
 */
export function barChart(items, opts = {}) {
  const list = (Array.isArray(items) ? items : []).filter(Boolean);
  const width = num(opts.width, 640);
  if (!list.length) return placeholder(width, 80, "Nothing played yet");

  const rowH = num(opts.rowHeight, 20);
  const labelW = num(opts.labelWidth, 104);
  const valueW = num(opts.valueWidth, 78);
  const top = 4;
  const height = top + list.length * rowH + 6;
  const plotL = labelW;
  const plotR = width - valueW;
  const plotW = Math.max(30, plotR - plotL);
  const max = num(opts.max, 1) || 1;
  const reference = opts.reference === undefined ? 0.5 : opts.reference;

  const root = s("svg", {
    class: "chart-svg",
    viewBox: `0 0 ${width} ${height}`,
    role: "img",
    "aria-label": "Win rate per map",
  });

  const barH = Math.max(6, Math.min(10, rowH - 8));
  list.forEach((item, index) => {
    const y = top + index * rowH;
    const barY = y + (rowH - barH) / 2;
    const value = item.value === null || item.value === undefined ? null : num(item.value);
    const n = Math.max(0, num(item.n, 0));

    const label = s("text", {
      class: "axis-text",
      x: labelW - 8,
      y: y + rowH / 2,
      "text-anchor": "end",
      "dominant-baseline": "middle",
      style: "fill: var(--fg-dim)",
    });
    label.textContent = String(item.label ?? "");
    root.appendChild(titled(label, String(item.label ?? "")));

    const track = s("rect", { x: plotL, y: barY, width: plotW, height: barH, rx: 2 });
    track.style.fill = "var(--bg-2)";
    root.appendChild(track);

    if (value !== null) {
      const fraction = clamp(value / max, 0, 1);
      const bar = s("rect", {
        x: plotL,
        y: barY,
        width: Math.max(1.5, fraction * plotW),
        height: barH,
        rx: 2,
      });
      bar.style.fill =
        reference === null || Math.abs(value - reference) < 1e-9
          ? "var(--accent)"
          : value > reference
            ? "var(--win)"
            : "var(--loss)";
      bar.style.opacity = String(clamp(0.45 + n / 12, 0.45, 1));
      root.appendChild(
        titled(bar, `${item.label}: ${Math.round(value * 100)}% over ${n} game${n === 1 ? "" : "s"}`)
      );
    }

    if (reference !== null) {
      const rx = plotL + clamp(reference / max, 0, 1) * plotW;
      root.appendChild(
        s("line", {
          class: "grid-line",
          x1: rx,
          x2: rx,
          y1: barY - 2,
          y2: barY + barH + 2,
          "stroke-dasharray": "2 2",
        })
      );
    }

    const readout = s("text", {
      class: "axis-text",
      x: width - 4,
      y: y + rowH / 2,
      "text-anchor": "end",
      "dominant-baseline": "middle",
    });
    readout.textContent = value === null ? `– (${n})` : `${Math.round(value * 100)}% (${n})`;
    root.appendChild(readout);
  });

  return root;
}

/* -------------------------------------------------------------------------- */
/* sparkline                                                                  */
/* -------------------------------------------------------------------------- */

/**
 * A ~100×26 trend line for a bot card. Fewer than two points draws a flat
 * baseline instead of nothing, so the card keeps its height either way.
 *
 * @param {number[]} values
 * @param {{width?:number,height?:number,area?:boolean}} [opts]
 * @returns {SVGElement}
 */
export function sparkline(values, opts = {}) {
  const list = (Array.isArray(values) ? values : []).map((v) => num(v, NaN)).filter(Number.isFinite);
  const width = num(opts.width, 100);
  const height = num(opts.height, 26);
  const root = s("svg", {
    class: "spark-svg",
    viewBox: `0 0 ${width} ${height}`,
    preserveAspectRatio: "none",
    "aria-hidden": "true",
  });

  if (list.length < 2) {
    root.appendChild(
      s("line", {
        class: "grid-line",
        x1: 0,
        x2: width,
        y1: height / 2,
        y2: height / 2,
        "stroke-dasharray": "3 3",
        "vector-effect": "non-scaling-stroke",
      })
    );
    return root;
  }

  let lo = Infinity;
  let hi = -Infinity;
  for (const v of list) {
    lo = Math.min(lo, v);
    hi = Math.max(hi, v);
  }
  if (hi - lo < 1e-9) {
    lo -= 1;
    hi += 1;
  }
  const inset = 2;
  const px = (i) => (i / (list.length - 1)) * width;
  const py = (v) => inset + (1 - (v - lo) / (hi - lo)) * (height - inset * 2);
  const line = list.map((v, i) => `${px(i).toFixed(2)},${py(v).toFixed(2)}`);

  if (opts.area !== false) {
    root.appendChild(
      s("polygon", {
        class: "spark-area",
        points: `0,${height} ${line.join(" ")} ${width},${height}`,
      })
    );
  }
  root.appendChild(
    s("polyline", {
      class: "spark-line",
      points: line.join(" "),
      "vector-effect": "non-scaling-stroke",
    })
  );
  return root;
}

/* -------------------------------------------------------------------------- */
/* map thumbnail                                                              */
/* -------------------------------------------------------------------------- */

/** Resolve a CSS custom property to a concrete colour for canvas painting. */
function cssColor(name, fallback) {
  try {
    const value = getComputedStyle(document.documentElement).getPropertyValue(name);
    return value && value.trim() ? value.trim() : fallback;
  } catch (err) {
    return fallback;
  }
}

/** Decode base64 tile bytes; anything unparsable comes back empty. */
function decodeTiles(encoded) {
  if (typeof encoded !== "string" || !encoded) return new Uint8Array(0);
  try {
    const binary = atob(encoded);
    const out = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) out[i] = binary.charCodeAt(i);
    return out;
  } catch (err) {
    return new Uint8Array(0);
  }
}

/**
 * Paint a `.map26` grid onto a canvas: floor, wall and ore tiles plus a ringed
 * marker on each team's spawn in the slot-A / slot-B colours.
 *
 * The backing store is sized in whole tiles at device-pixel resolution, so the
 * result stays crisp on HiDPI displays while the CSS (`width: 100%`,
 * `image-rendering: pixelated`) scales it to the card. A map that failed to
 * parse (0×0) yields a small "unreadable" placeholder rather than a broken
 * canvas.
 *
 * @param {{name?:string,width:number,height:number,tiles:string,spawns?:Array<number[]>}} map
 * @param {{size?:number,grid?:boolean}} [opts]
 * @returns {HTMLCanvasElement}
 */
export function mapThumb(map, opts = {}) {
  const canvas = document.createElement("canvas");
  canvas.className = "map-canvas";
  const source = /** @type {any} */ (map || {});
  const w = Math.max(0, Math.floor(num(source.width, 0)));
  const h = Math.max(0, Math.floor(num(source.height, 0)));
  const tiles = decodeTiles(source.tiles);
  const ctx = canvas.getContext("2d");

  const bg = cssColor("--bg", "#0d0f13");
  const floor = cssColor("--bg-2", "#1b2029");
  const wall = cssColor("--line-strong", "#384254");
  const ore = cssColor("--warn", "#ffc44d");
  const line = cssColor("--line-soft", "#1e2430");

  if (!w || !h || tiles.length < w * h) {
    canvas.width = 120;
    canvas.height = 120;
    canvas.setAttribute("role", "img");
    canvas.setAttribute("aria-label", `${source.name || "map"}: unreadable`);
    if (ctx) {
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, 120, 120);
      ctx.strokeStyle = wall;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(30, 30);
      ctx.lineTo(90, 90);
      ctx.moveTo(90, 30);
      ctx.lineTo(30, 90);
      ctx.stroke();
    }
    return canvas;
  }

  const dpr = clamp(num(window.devicePixelRatio, 1), 1, 3);
  const target = num(opts.size, 240) * dpr;
  const cell = Math.max(2, Math.floor(target / Math.max(w, h)));
  canvas.width = w * cell;
  canvas.height = h * cell;
  canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", `${source.name || "map"} ${w}×${h}`);
  if (!ctx) return canvas;

  ctx.fillStyle = floor;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  for (let y = 0; y < h; y += 1) {
    for (let x = 0; x < w; x += 1) {
      const tile = tiles[y * w + x];
      if (tile === 0) continue;
      ctx.fillStyle = tile === 1 ? wall : ore;
      ctx.fillRect(x * cell, y * cell, cell, cell);
    }
  }

  if (opts.grid !== false && cell >= 8) {
    ctx.strokeStyle = line;
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let x = 1; x < w; x += 1) {
      ctx.moveTo(x * cell + 0.5, 0);
      ctx.lineTo(x * cell + 0.5, canvas.height);
    }
    for (let y = 1; y < h; y += 1) {
      ctx.moveTo(0, y * cell + 0.5);
      ctx.lineTo(canvas.width, y * cell + 0.5);
    }
    ctx.stroke();
  }

  const spawnColors = [cssColor("--a", "#ffb454"), cssColor("--b", "#8fc7ff")];
  const spawns = Array.isArray(source.spawns) ? source.spawns : [];
  spawns.forEach((spawn, index) => {
    if (!spawn || spawn.length < 2) return;
    const sx = num(spawn[0], -1);
    const sy = num(spawn[1], -1);
    if (sx < 0 || sy < 0 || sx >= w || sy >= h) return;
    const cx = sx * cell + cell / 2;
    const cy = sy * cell + cell / 2;
    const radius = Math.max(1.5, cell * 0.42);
    ctx.fillStyle = spawnColors[index % spawnColors.length];
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = bg;
    ctx.lineWidth = Math.max(1, cell * 0.12);
    ctx.stroke();
  });

  return canvas;
}

/* -------------------------------------------------------------------------- */
/* heat cell                                                                  */
/* -------------------------------------------------------------------------- */

/**
 * Diverging colour for a win-rate cell: loss-red below 0.5, neutral at 0.5,
 * win-green above, with the sample size driving how strongly the tint reads.
 *
 * `opacity` is the tint strength (0 = untinted), meant to be composed by the
 * caller — typically `color-mix(in srgb, <bg> <opacity*100>%, transparent)` —
 * so the cell text stays fully opaque. Eight games is treated as "enough to
 * believe", which matches the confidence the matrix view feeds to CSS.
 *
 * @param {number|null} winrate 0..1, or null when nothing was played
 * @param {number} n number of games behind that rate
 * @returns {{bg:string,fg:string,opacity:number}}
 */
export function heatCell(winrate, n) {
  const games = Math.max(0, num(n, 0));
  if (winrate === null || winrate === undefined || !games) {
    return { bg: "var(--bg-2)", fg: "var(--fg-mute)", opacity: 0 };
  }
  const rate = clamp(num(winrate, 0.5), 0, 1);
  const lean = rate - 0.5;
  const confidence = clamp(games / 8, 0, 1);
  const opacity = clamp(Math.abs(lean) * 2 * confidence * 0.82, 0, 1);
  const bg = Math.abs(lean) < 1e-9 ? "var(--draw)" : lean > 0 ? "var(--win)" : "var(--loss)";
  return { bg, fg: opacity > 0.3 ? "var(--fg)" : "var(--fg-dim)", opacity };
}
