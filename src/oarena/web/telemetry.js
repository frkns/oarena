/** Machine-readable records embedded in the engine's captured output. */

const PROFILER_PREFIX = "[OARENA:ProfilerReport]";
const LEGACY_PREFIX = "OARENA_TELEMETRY ";
const TIME_FIELDS = ["total_us", "self_us", "max_total_us"];

function finiteNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : 0;
}

export function normaliseProfilerReport(payload, legacy = false) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null;
  if (legacy && payload.kind !== "profile") return null;
  if (!payload.spans || typeof payload.spans !== "object" || Array.isArray(payload.spans)) return null;

  const scale = legacy && Number(payload.schema) === 1 ? 1_000 : 1;
  const spans = {};
  for (const [name, raw] of Object.entries(payload.spans)) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) continue;
    const span = { calls: Math.trunc(finiteNumber(raw.calls)) };
    for (const field of TIME_FIELDS) span[field] = finiteNumber(raw[field]) * scale;
    spans[String(name)] = span;
  }
  if (!Object.keys(spans).length) return null;

  return {
    schema: legacy ? 1 : Number(payload.schema) || 2,
    clock: "cpu_us",
    team: String(payload.team || "").toLowerCase(),
    unit_id: payload.unit_id,
    unit_type: String(payload.unit_type || "unknown"),
    from_round: payload.from_round,
    to_round: payload.to_round,
    interrupted: Math.trunc(finiteNumber(payload.interrupted)),
    bad_nesting: Math.trunc(finiteNumber(payload.bad_nesting)),
    spans,
  };
}

export function normaliseProfilerRecords(records) {
  const reports = [];
  for (const record of Array.isArray(records) ? records : []) {
    const report = normaliseProfilerReport(record?.payload, Boolean(record?.legacy));
    if (report) reports.push(report);
  }
  return reports;
}

/**
 * Remove valid profiler records from captured output and return them decoded.
 * Unknown or malformed marker lines deliberately remain visible in the log.
 */
export function extractProfilerReports(text) {
  const reports = [];
  const kept = [];
  for (const line of String(text || "").split("\n")) {
    let raw = null;
    let legacy = false;
    if (line.startsWith(PROFILER_PREFIX)) {
      raw = line.slice(PROFILER_PREFIX.length).trimStart();
    } else if (line.startsWith(LEGACY_PREFIX)) {
      raw = line.slice(LEGACY_PREFIX.length);
      legacy = true;
    }
    if (raw === null) {
      kept.push(line);
      continue;
    }

    let report = null;
    try {
      report = normaliseProfilerReport(JSON.parse(raw), legacy);
    } catch (_err) {
      /* A partial or corrupt record is ordinary diagnostic output. */
    }
    if (report) reports.push(report);
    else kept.push(line);
  }
  return { text: kept.join("\n"), reports };
}
