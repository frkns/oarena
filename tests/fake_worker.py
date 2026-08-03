"""A deterministic stand-in for the fcode engine.

A real game costs 3–9 seconds, so nothing in the unit suite is allowed to play
one.  This module provides the two substitutes the rest of the tests need:

``FakeRunner``
    An in-process replacement for :func:`oarena.runner.run_one`.  It records
    every :class:`~oarena.runner.GameSpec` it is handed, writes real (tiny)
    replay/log files into the spec's temp directory so the league's file-moving
    and replay-budget code runs for real, and returns a deterministic
    :class:`~oarena.runner.GameOutcome`.

``main`` (script mode)
    A stand-in for ``python -m oarena._worker``.  ``tests/conftest.py`` rewrites
    the supervisor's argv to point at this file, which exercises the *real*
    :func:`oarena.runner.run_one` — subprocess spawning, fd redirection, result
    files, process-group kills — with no engine involved.

Both halves agree on one rule: **the alphabetically smaller bot name wins**, and
equal names draw.  Behaviour other than a clean game is requested through
markers in a bot's directory name (see :data:`MARKERS`), which is the only
channel the worker protocol gives a test.

The script half deliberately imports nothing from ``oarena``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
from uuid import uuid4

if TYPE_CHECKING:  # pragma: no cover - typing only
    from oarena.runner import GameOutcome, GameSpec

MARKERS = ("validation", "loadfail", "hang", "panic", "crash", "die", "raises")
"""Substrings of a bot directory name that make the *script* half misbehave."""

TRACEBACK_TEMPLATE = """Traceback (most recent call last):
  File "{entry}", line 194, in on_turn
    self.act()
  File "{entry}", line 12, in act
    return 1 / 0
ZeroDivisionError: division by zero
"""

FAKE_FCODE_VERSION = "test-fcode-1"
FAKE_FCODE_METADATA: dict[str, Any] = {
    "metadata_version": 1,
    "version": FAKE_FCODE_VERSION,
    "game_constants": {"MAX_TURNS": 1000},
    "enums": {},
    "direction_deltas": {},
}


# --------------------------------------------------------------------------- #
# shared rules
# --------------------------------------------------------------------------- #


def expected_winner(a: str, b: str) -> str:
    """``'a'``, ``'b'`` or ``'draw'`` — the alphabetically smaller name wins."""
    if a == b:
        return "draw"
    return "a" if a < b else "b"


def _marker(name: str) -> str:
    for marker in MARKERS:
        if marker in name:
            return marker
    return ""


# --------------------------------------------------------------------------- #
# in-process fake: replaces runner.run_one
# --------------------------------------------------------------------------- #


class FakeRunner:
    """A configurable, instant replacement for :func:`oarena.runner.run_one`.

    Every knob is a plain attribute so a test can flip it between games::

        fake.win_condition = "coinflip"
        fake.status_for["beta"] = "loadfail"
    """

    def __init__(self) -> None:
        self.calls: list[GameSpec] = []
        self.status_for: dict[str, str] = {}
        """Bot name → forced status. ``loadfail`` is turned into the right side."""
        self.errors_for: dict[str, int] = {}
        """Bot name → number of tracebacks to attribute to it."""
        self.scripted: deque[GameOutcome] = deque()
        """Outcomes returned (and consumed) before any other rule applies."""
        self.hook: Callable[[GameSpec], GameOutcome | None] | None = None
        self.winner: str | None = None
        self.win_condition: str = "core_destroyed"
        self.turns: int = 500
        self.duration_ms: int = 1234
        self.replay_bytes: int = 64
        self.write_replay: bool = True
        self.write_log: bool = True
        self.delay: float = 0.0

    # -- helpers ----------------------------------------------------------- #

    def _status(self, spec: GameSpec) -> str:
        for side, source in (("a", spec.a), ("b", spec.b)):
            forced = self.status_for.get(source.name)
            if forced:
                return f"loadfail_{side}" if forced == "loadfail" else forced
        return "ok"

    def _file(self, spec: GameSpec, suffix: str, payload: bytes) -> Path:
        spec.tmp_dir.mkdir(parents=True, exist_ok=True)
        path = spec.tmp_dir / f"{uuid4().hex}{suffix}"
        path.write_bytes(payload)
        return path

    # -- the call ---------------------------------------------------------- #

    def __call__(
        self, spec: GameSpec, *, cancelled: threading.Event | None = None
    ) -> GameOutcome:
        from oarena.runner import GameOutcome, PlayerResult

        self.calls.append(spec)
        if self.delay:
            if cancelled is not None and cancelled.wait(self.delay):
                return GameOutcome(status="killed", error="cancelled by test pool")
            time.sleep(0 if cancelled is not None else self.delay)
        if cancelled is not None and cancelled.is_set():
            return GameOutcome(status="killed", error="cancelled by test pool")
        if self.scripted:
            return self.scripted.popleft()
        if self.hook is not None:
            forced = self.hook(spec)
            if forced is not None:
                return forced

        status = self._status(spec)
        ok = status == "ok"
        winner: str | None
        if not ok:
            winner = None
        elif self.winner is not None:
            winner = self.winner
        else:
            winner = expected_winner(spec.a.name, spec.b.name)

        log_path: Path | None = None
        if self.write_log:
            log_path = self._file(spec, ".log", self._log_text(spec, status).encode())
        replay_path: Path | None = None
        if self.write_replay:
            replay_path = self._file(spec, ".replay26", b"R" * self.replay_bytes)

        outcome = GameOutcome(
            status=status,
            winner=winner,
            win_condition=self.win_condition if ok else "",
            turns=self.turns if ok else 0,
            error="" if ok else f"fake {status}",
            duration_ms=self.duration_ms,
            replay_path=replay_path,
            log_path=log_path,
            log_tail=self._log_text(spec, status)[-4000:],
            a=PlayerResult(
                titanium=100, mined=40, units=4, buildings=8,
                errors=self.errors_for.get(spec.a.name, 0),
            ),
            b=PlayerResult(
                titanium=90, mined=30, units=3, buildings=7,
                errors=self.errors_for.get(spec.b.name, 0),
            ),
            fcode_version=FAKE_FCODE_VERSION,
            fcode_metadata=FAKE_FCODE_METADATA,
        )
        return outcome

    def _log_text(self, spec: GameSpec, status: str) -> str:
        if status == "loadfail_a":
            return "Bot A failed to load: ImportError: No module named 'nope'\n"
        if status == "loadfail_b":
            return "Bot B failed to load: ImportError: No module named 'nope'\n"
        parts = [f"game {spec.a.name} vs {spec.b.name} on {spec.map.name}\n"]
        for side in (spec.a, spec.b):
            for _ in range(self.errors_for.get(side.name, 0)):
                parts.append(TRACEBACK_TEMPLATE.format(entry=side.entry))
        return "".join(parts)


# --------------------------------------------------------------------------- #
# script mode: replaces `python -m oarena._worker`
# --------------------------------------------------------------------------- #


def _engine_result(a_name: str, b_name: str) -> dict[str, Any]:
    """The shape ``fcode.fcode_engine.run_game`` returns."""
    verdict = expected_winner(a_name, b_name)
    return {
        "replay": "",
        "winner": {"a": "A", "b": "B"}.get(verdict),
        "turns": 640,
        "win_condition": "coinflip" if verdict == "draw" else "core_destroyed",
        "resign_message": None,
        "a_titanium": 7427,
        "a_titanium_collected": 4880,
        "a_units": 4,
        "a_buildings": 40,
        "b_titanium": 2198,
        "b_titanium_collected": 0,
        "b_units": 15,
        "b_buildings": 20,
    }


def _attach_log(path: str) -> None:
    sys.stdout.flush()
    sys.stderr.flush()
    handle = open(path, "wb")  # noqa: SIM115 - the fds outlive the object on purpose
    os.dup2(handle.fileno(), 1)
    os.dup2(handle.fileno(), 2)


def _emit(text: str) -> None:
    os.write(2, text.encode())


def main() -> int:
    """Play one fake game exactly the way the real worker does."""
    job = json.loads(sys.stdin.read())
    os.chdir(str(job["cwd"]))
    _attach_log(str(job["log"]))

    a_entry, b_entry = Path(job["a"]), Path(job["b"])
    a_name, b_name = a_entry.parent.name, b_entry.parent.name
    marker_a, marker_b = _marker(a_name), _marker(b_name)

    if "envcheck" in a_name or "envcheck" in b_name:
        _emit(
            "PYTHONDONTWRITEBYTECODE="
            f"{os.environ.get('PYTHONDONTWRITEBYTECODE', '<unset>')}\n"
        )

    for turn in (100, 200, 300):
        _emit(f"Completed turn {turn}\n")

    if marker_a == "validation" and marker_b == "validation":
        _emit(
            "Both bots failed validation: "
            "A=SyntaxError: invalid syntax on side A, "
            "B=SyntaxError: invalid syntax on side B\n"
        )
        os._exit(12)

    if marker_a == "validation" or marker_b == "validation":
        side = "A" if marker_a == "validation" else "B"
        _emit(f"Bot {side} failed validation: SyntaxError: invalid syntax\n")
        os._exit(10 if side == "A" else 11)

    if marker_a == "loadfail" or marker_b == "loadfail":
        side = "A" if marker_a == "loadfail" else "B"
        _emit(f"Bot {side} failed to load: ImportError: No module named 'nope'\n")
        os._exit(139)  # the engine dies with SIGSEGV; no result file is written

    if marker_a == "die" or marker_b == "die":
        _emit("something went very wrong inside the engine\n")
        os._exit(7)

    if marker_a == "hang" or marker_b == "hang":
        # A grandchild in the same session proves the supervisor kills the whole
        # process group rather than just the worker.
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
        Path(str(job["result"]) + ".pid").write_text(str(child.pid), encoding="utf-8")
        time.sleep(300)

    if marker_a == "panic" or marker_b == "panic":
        entry = a_entry if marker_a == "panic" else b_entry
        payload = {
            "ok": False,
            "error": "RuntimeError: bot escaped into the engine",
            "traceback": TRACEBACK_TEMPLATE.format(entry=entry),
        }
    elif marker_a == "crash" or marker_b == "crash":
        payload: dict[str, Any] = {
            "ok": False,
            "error": "RuntimeError: engine exploded",
            "traceback": "Traceback (most recent call last):\nRuntimeError: engine exploded\n",
        }
    else:
        for side, entry in (("a", a_entry), ("b", b_entry)):
            if _marker(a_name if side == "a" else b_name) == "raises":
                _emit(TRACEBACK_TEMPLATE.format(entry=entry))
                _emit(TRACEBACK_TEMPLATE.format(entry=entry))
        Path(str(job["replay"])).write_bytes(b"REPLAY26" * 8)
        payload = {
            "ok": True,
            "result": _engine_result(a_name, b_name),
            "fcode_version": FAKE_FCODE_VERSION,
            "fcode_metadata": FAKE_FCODE_METADATA,
        }

    with open(str(job["result"]), "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
        handle.flush()
        os.fsync(handle.fileno())
    return 0


if __name__ == "__main__":
    try:
        _code = main()
    except BaseException:  # noqa: BLE001 - mirror the real worker's contract
        _code = 4
    os._exit(_code)
