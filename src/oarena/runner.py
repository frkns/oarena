"""Supervision of a single fcode game.

Every game is played by a throwaway ``python -m oarena._worker`` subprocess in
its own session, because the engine is hostile to its host:

* a bot that fails to import segfaults the interpreter before ``run_game``
  returns, so a *dead child with no result file* is a normal, expected outcome
  and is classified by scanning the captured log for ``Bot A failed to load:``;
* ``tle_ms`` bounds a bot's per-turn budget but not wall-clock time, so the
  supervisor enforces its own deadline and kills the whole process group;
* the engine writes to fds 1 and 2 from Rust, so the child re-points those
  descriptors at a log file that this module then cleans, tails and hands back.

:func:`run_one` never raises: every failure path produces a :class:`GameOutcome`.
The parent process must never import ``fcode.fcode_engine`` — importing plain
``fcode`` (pure Python, for the version and the bundled asset paths) is safe.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from .bots import BotSource
from .maps import GameMap

__all__ = [
    "GameOutcome",
    "GameSpec",
    "PlayerResult",
    "canonical_fcode_metadata_json",
    "check_fcode",
    "fcode_engine_root",
    "run_one",
    "cancel_active",
    "visualiser_dist",
]

LOG_TAIL_CHARS = 4000
"""How much of the cleaned log :attr:`GameOutcome.log_tail` carries."""

_REAP_TIMEOUT_S = 5.0

_TIMED_OUT = object()
"""Sentinel: the worker blew its wall-clock deadline (see :func:`_talk_to_child`)."""

_ACTIVE_LOCK = threading.Lock()
_ACTIVE: set[subprocess.Popen[bytes]] = set()
"""Live engine worker process groups, for an explicit user-requested abort."""

_TURN_NOISE = re.compile(r"^Completed turn \d+[ \t]*\r?\n?", re.MULTILINE)
_TRACEBACK_START = re.compile(r"^Traceback \(most recent call last\):", re.MULTILINE)
_LOAD_FAIL_BOTH = re.compile(
    r"^Both bots failed (?:to load|validation):[ \t]*A=(.*?),[ \t]*B=(.*)$",
    re.MULTILINE,
)
_LOAD_FAIL = (
    (
        "loadfail_a",
        re.compile(r"^Bot A failed (?:to load|validation):[ \t]*(.*)$", re.MULTILINE),
    ),
    (
        "loadfail_b",
        re.compile(r"^Bot B failed (?:to load|validation):[ \t]*(.*)$", re.MULTILINE),
    ),
)


# --------------------------------------------------------------------------- #
# locating fcode
# --------------------------------------------------------------------------- #


def fcode_engine_root() -> Path:
    """Directory the engine wants as its ``engine_root`` (the ``fcode`` package)."""
    module = importlib.import_module("fcode")
    origin = getattr(module, "__file__", None)
    if not origin:
        raise RuntimeError("the installed 'fcode' package has no file location")
    return Path(origin).resolve().parent


def visualiser_dist() -> Path | None:
    """Path of the bundled Vite visualiser build, or ``None`` if unavailable."""
    try:
        root = fcode_engine_root()
    except Exception:
        return None
    dist = root / "data" / "visualiser"
    return dist if (dist / "index.html").is_file() else None


def check_fcode() -> str:
    """Return the installed fcode version, or raise with an actionable message."""
    try:
        module = importlib.import_module("fcode")
    except Exception as exc:
        raise RuntimeError(
            f"fcode is not importable from {sys.executable}: {exc}. "
            "Install it with `pip install fcode` (oarena runs the official engine)."
        ) from exc
    return str(getattr(module, "__version__", "unknown"))


# --------------------------------------------------------------------------- #
# data
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class GameSpec:
    """Everything needed to play one game: who, where, and how long it may take."""

    a: BotSource
    b: BotSource
    map: GameMap
    seed: int
    tle_ms: int
    timeout_s: float
    cwd: Path
    tmp_dir: Path
    python_dont_write_bytecode: bool = False


@dataclass
class PlayerResult:
    """One side's numbers; ``errors`` counts attributed bot failures."""

    titanium: int = 0
    mined: int = 0
    units: int = 0
    buildings: int = 0
    errors: int = 0


@dataclass
class GameOutcome:
    """The result of one supervised game — the only thing :func:`run_one` returns."""

    # ok | timeout | loadfail_a | loadfail_b | loadfail_both | engine_error | killed
    status: str
    winner: str | None = None  # 'a' | 'b' | 'draw' | None
    win_condition: str = ""
    turns: int = 0
    resign_message: str = ""
    error: str = ""
    a: PlayerResult = field(default_factory=PlayerResult)
    b: PlayerResult = field(default_factory=PlayerResult)
    duration_ms: int = 0
    replay_path: Path | None = None
    log_path: Path | None = None
    log_tail: str = ""
    fcode_version: str = ""
    fcode_metadata: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


_FCODE_METADATA_KEYS = frozenset(
    {"metadata_version", "version", "game_constants", "enums", "direction_deltas"}
)


def canonical_fcode_metadata_json(
    fcode_version: str, metadata: dict[str, Any] | None
) -> str:
    """Return a stable JSON snapshot, or ``""`` for invalid provenance.

    The top-level version is intentionally independent of the metadata object
    in the worker protocol.  Requiring them to agree catches partially written,
    stale, or hand-built worker responses before a replay depends on them.
    ``allow_nan=False`` also prevents non-portable JSON from reaching SQLite.
    """

    if not isinstance(fcode_version, str) or not fcode_version:
        return ""
    if not isinstance(metadata, dict) or set(metadata) != _FCODE_METADATA_KEYS:
        return ""
    if type(metadata.get("metadata_version")) is not int or metadata["metadata_version"] != 1:
        return ""
    if metadata.get("version") != fcode_version:
        return ""
    if not all(
        isinstance(metadata.get(name), dict)
        for name in ("game_constants", "enums", "direction_deltas")
    ):
        return ""
    try:
        return json.dumps(
            metadata,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError):
        return ""


def _worker_fcode_provenance(
    payload: dict[str, Any] | None,
) -> tuple[str, dict[str, Any] | None]:
    """Validate and detach the provenance portion of a worker response."""

    if payload is None:
        return "", None
    raw_version = payload.get("fcode_version")
    version = raw_version if isinstance(raw_version, str) else ""
    raw_metadata = payload.get("fcode_metadata")
    metadata = raw_metadata if isinstance(raw_metadata, dict) else None
    encoded = canonical_fcode_metadata_json(version, metadata)
    if not encoded:
        return version, None
    decoded = json.loads(encoded)
    return version, decoded if isinstance(decoded, dict) else None


# --------------------------------------------------------------------------- #
# the supervisor
# --------------------------------------------------------------------------- #


def run_one(
    spec: GameSpec, *, cancelled: threading.Event | None = None
) -> GameOutcome:
    """Play one game in a subprocess and describe what happened.

    Never raises.  The replay and log files it names in the outcome are left on
    disk for the caller to move or delete; the job/result scratch files are
    always cleaned up here. ``cancelled`` belongs to the submitting pool and
    closes the race between a force-stop snapshot and subprocess registration.
    """
    started = time.monotonic()
    if cancelled is not None and cancelled.is_set():
        return GameOutcome(
            status="killed",
            error="cancelled before worker start",
            duration_ms=_elapsed_ms(started),
        )
    token = uuid4().hex
    replay_path = spec.tmp_dir / f"{token}.replay26"
    log_path = spec.tmp_dir / f"{token}.log"
    result_path = spec.tmp_dir / f"{token}.json"

    try:
        spec.tmp_dir.mkdir(parents=True, exist_ok=True)
        return _supervise(
            spec,
            started,
            replay_path,
            log_path,
            result_path,
            cancelled=cancelled,
        )
    except Exception as exc:  # noqa: BLE001 - run_one must never raise
        log_text = _clean_log(log_path)
        return GameOutcome(
            status="engine_error",
            winner=None,
            error=f"{type(exc).__name__}: {exc}",
            duration_ms=_elapsed_ms(started),
            replay_path=replay_path if replay_path.exists() else None,
            log_path=log_path if log_text else None,
            log_tail=log_text[-LOG_TAIL_CHARS:],
        )
    finally:
        _unlink(result_path)


def cancel_active() -> int:
    """Immediately kill every currently supervised engine process group.

    This is deliberately separate from the normal wall-clock timeout: explicit
    force-stop paths (including CLI Ctrl-C) use it. Each worker is its own
    session, so killing the group also kills anything the Rust engine spawned.
    """
    with _ACTIVE_LOCK:
        processes = list(_ACTIVE)
    for proc in processes:
        _kill_group(proc)
    return len(processes)


def _supervise(
    spec: GameSpec,
    started: float,
    replay_path: Path,
    log_path: Path,
    result_path: Path,
    *,
    cancelled: threading.Event | None = None,
) -> GameOutcome:
    """Spawn the worker, wait for it (or kill it), and classify the aftermath."""
    job = {
        "a": str(spec.a.entry),
        "b": str(spec.b.entry),
        "map": str(spec.map.path),
        "replay": str(replay_path),
        "log": str(log_path),
        "result": str(result_path),
        "seed": int(spec.seed),
        "tle_ms": int(spec.tle_ms),
        "cwd": str(spec.cwd),
    }

    proc = subprocess.Popen(
        [sys.executable, "-m", "oarena._worker"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        # Only the child's *bootstrap* output can land here: it re-points fd 2 at
        # the log file before it touches the engine. Keeping the pipe means an
        # `ImportError: oarena` surfaces as a reason instead of a bare exit code.
        stderr=subprocess.PIPE,
        start_new_session=True,
        cwd=str(spec.cwd),
        env=_child_env(spec.python_dont_write_bytecode),
    )

    with _ACTIVE_LOCK:
        _ACTIVE.add(proc)
        abort_now = cancelled is not None and cancelled.is_set()

    try:
        if abort_now:
            _kill_group(proc)
        timed_out = False
        bootstrap_err = _talk_to_child(proc, job, spec.timeout_s)
        if bootstrap_err is _TIMED_OUT:
            timed_out = True
            _kill_group(proc)
            bootstrap_err = _drain(proc)

        duration_ms = _elapsed_ms(started)
        log_text = _clean_log(log_path)
        payload = _read_result(result_path)
        log_text = _merge_payload_traceback(log_path, log_text, payload)
        fcode_version, fcode_metadata = _worker_fcode_provenance(payload)

        engine: dict[str, Any] | None = None
        if timed_out:
            # A killed worker may have left a partial or even complete result file;
            # a game that blew the wall clock is a timeout regardless.
            status = "timeout"
            error = f"exceeded {spec.timeout_s:g}s wall clock"
        elif payload is None:
            status, error = _classify_dead_child(log_text, proc.returncode, str(bootstrap_err))
        elif payload.get("ok"):
            result = payload.get("result")
            if isinstance(result, dict):
                status, error, engine = "ok", "", result
            else:
                status = "engine_error"
                error = "worker returned no result document"
        else:
            status = "engine_error"
            error = str(payload.get("error") or "worker reported an unspecified failure")

        a_errors, b_errors = _attribute_tracebacks(log_text, spec)
        # Import/validation failures happen before a turn traceback can exist,
        # but they are still bot errors and must appear in the same per-side
        # counters used by the ladder, batch summaries and bot detail pages.
        if status in ("loadfail_a", "loadfail_both"):
            a_errors = max(1, a_errors)
        if status == "loadfail_b" or (
            status == "loadfail_both" and spec.a.dir != spec.b.dir
        ):
            b_errors = max(1, b_errors)
        outcome = GameOutcome(
            status=status,
            winner=None,
            error=error,
            duration_ms=duration_ms,
            replay_path=replay_path if replay_path.exists() else None,
            log_path=log_path if log_text else None,
            log_tail=log_text[-LOG_TAIL_CHARS:],
            a=PlayerResult(errors=a_errors),
            b=PlayerResult(errors=b_errors),
            fcode_version=fcode_version,
            fcode_metadata=fcode_metadata,
        )
        if engine is not None:
            _apply_engine_result(outcome, engine)
        return outcome
    finally:
        with _ACTIVE_LOCK:
            _ACTIVE.discard(proc)


def _apply_engine_result(outcome: GameOutcome, engine: dict[str, Any]) -> None:
    """Fold the engine's result dict into ``outcome`` (error counts survive)."""
    outcome.winner = {"A": "a", "B": "b"}.get(str(engine.get("winner")), "draw")
    outcome.win_condition = str(engine.get("win_condition") or "")
    outcome.turns = _as_int(engine.get("turns"))
    outcome.resign_message = str(engine.get("resign_message") or "")
    outcome.a.titanium = _as_int(engine.get("a_titanium"))
    outcome.a.mined = _as_int(engine.get("a_titanium_collected"))
    outcome.a.units = _as_int(engine.get("a_units"))
    outcome.a.buildings = _as_int(engine.get("a_buildings"))
    outcome.b.titanium = _as_int(engine.get("b_titanium"))
    outcome.b.mined = _as_int(engine.get("b_titanium_collected"))
    outcome.b.units = _as_int(engine.get("b_units"))
    outcome.b.buildings = _as_int(engine.get("b_buildings"))


def _classify_dead_child(
    log_text: str, returncode: int | None, bootstrap_err: str = ""
) -> tuple[str, str]:
    """No result file: decide whether a bot failed to import or the child crashed.

    An import failure inside the engine prints one line to fd 2 and then takes
    the process down with SIGSEGV, so the log is the only evidence. Anything the
    worker managed to say before it attached that log (a missing ``oarena`` or
    ``fcode`` on the child's path) is the next best clue.
    """
    both = _LOAD_FAIL_BOTH.search(log_text)
    if both:
        a_reason = both.group(1).strip() or "bot A failed to load"
        b_reason = both.group(2).strip() or "bot B failed to load"
        return "loadfail_both", f"A={a_reason}; B={b_reason}"
    for status, pattern in _LOAD_FAIL:
        match = pattern.search(log_text)
        if match:
            return status, match.group(1).strip() or "bot failed to load"
    reason = f"worker died (exit {returncode})"
    tail = bootstrap_err.strip().splitlines()
    if tail:
        reason = f"{reason}: {tail[-1].strip()}"
    return "killed", reason


def _child_env(python_dont_write_bytecode: bool = False) -> dict[str, str]:
    """Environment for the worker, with this package importable by absolute path.

    The worker chdirs into the project root before doing anything else, which
    silently invalidates every *relative* entry on its path — a source checkout
    started with ``PYTHONPATH=src`` would fail to import ``oarena`` and report
    nothing but an exit code. Pinning the package's own parent directory keeps
    the worker importable however oarena itself was launched.
    """
    env = dict(os.environ)
    pkg_parent = str(Path(__file__).resolve().parent.parent)
    parts = [p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p]
    if pkg_parent not in parts:
        parts.insert(0, pkg_parent)
    env["PYTHONPATH"] = os.pathsep.join(parts)
    if python_dont_write_bytecode:
        env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _talk_to_child(
    proc: subprocess.Popen[bytes], job: dict[str, Any], timeout_s: float
) -> str | object:
    """Send the job, drain stderr and wait; return ``_TIMED_OUT`` past the deadline.

    ``communicate`` is what keeps the stderr pipe from filling while we block on
    a game that can legitimately run for minutes.
    """
    payload = json.dumps(job).encode("utf-8")
    try:
        _, err = proc.communicate(input=payload, timeout=timeout_s if timeout_s > 0 else None)
    except subprocess.TimeoutExpired:
        return _TIMED_OUT
    except (OSError, ValueError):
        return _drain(proc)
    return (err or b"").decode("utf-8", "replace")


def _drain(proc: subprocess.Popen[bytes]) -> str:
    """Collect whatever the child left on stderr after it was killed."""
    try:
        _, err = proc.communicate(timeout=_REAP_TIMEOUT_S)
    except Exception:  # noqa: BLE001 - best effort on an already-dead child
        return ""
    return (err or b"").decode("utf-8", "replace")


def _kill_group(proc: subprocess.Popen[bytes]) -> None:
    """SIGKILL the worker's whole process group, then reap it.

    The worker runs with ``start_new_session=True``, so its pid is its process
    group id and anything the engine spawned dies with it.
    """
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except OSError:
            pass
    try:
        proc.wait(timeout=_REAP_TIMEOUT_S)
    except subprocess.TimeoutExpired:  # pragma: no cover - SIGKILL is not refusable
        pass


def _read_result(path: Path) -> dict[str, Any] | None:
    """Load the worker's result document, or ``None`` if absent or truncated."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        payload = json.loads(raw)
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


# --------------------------------------------------------------------------- #
# log handling
# --------------------------------------------------------------------------- #


def _clean_log(path: Path) -> str:
    """Strip the engine's ``Completed turn N`` chatter and rewrite the log file.

    Returns the cleaned text ("" when there is nothing left, in which case the
    file is removed so no empty scratch files leak).
    """
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""

    cleaned = _TURN_NOISE.sub("", raw)
    if not cleaned.strip():
        _unlink(path)
        return ""
    if cleaned != raw:
        try:
            path.write_text(cleaned, encoding="utf-8")
        except OSError:
            pass
    return cleaned


def _merge_payload_traceback(
    log_path: Path, log_text: str, payload: dict[str, Any] | None
) -> str:
    """Keep a worker-reported traceback with the fd-level engine log.

    Exceptions propagated out of ``run_game`` are serialized in the result
    document rather than printed. Merging that traceback before attribution
    lets a bot frame still turn an engine panic into the responsible bot's
    error/loss. Tracebacks containing no bot path remain unattributed.
    """
    if not isinstance(payload, dict) or payload.get("ok"):
        return log_text
    raw = payload.get("traceback")
    traceback_text = raw.strip() if isinstance(raw, str) else ""
    if not traceback_text or traceback_text in log_text:
        return log_text
    merged = f"{log_text.rstrip()}\n{traceback_text}\n" if log_text else f"{traceback_text}\n"
    try:
        log_path.write_text(merged, encoding="utf-8")
    except OSError:
        pass
    return merged


def _attribute_tracebacks(log_text: str, spec: GameSpec) -> tuple[int, int]:
    """Count each bot's runtime failures as *tracebacks*, not stack frames.

    One bad turn produces a five-frame traceback; counting ``File "..."`` lines
    would report five errors for one mistake.  The log is split into blocks that
    start at a ``Traceback (most recent call last):`` line and each block is
    attributed to whichever bot's directory is named inside it (both → both,
    neither → ignored).  A bot playing itself gets every block counted once, on
    side A.
    """
    if not log_text:
        return 0, 0

    starts = [m.start() for m in _TRACEBACK_START.finditer(log_text)]
    if not starts:
        return 0, 0

    a_prefix = _dir_prefix(spec.a.dir)
    b_prefix = _dir_prefix(spec.b.dir)
    self_match = a_prefix == b_prefix

    a_errors = b_errors = 0
    bounds = starts + [len(log_text)]
    for index, start in enumerate(starts):
        block = log_text[start : bounds[index + 1]]
        in_a = a_prefix in block
        in_b = (not self_match) and b_prefix in block
        if in_a:
            a_errors += 1
        if in_b:
            b_errors += 1
    return a_errors, b_errors


def _dir_prefix(directory: Path) -> str:
    """``/bots/starter`` → ``/bots/starter/`` so it cannot match ``starter2``."""
    return str(directory).rstrip(os.sep) + os.sep


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _unlink(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass
