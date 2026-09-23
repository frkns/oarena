"""The child process that plays exactly one fcode game.

Invoked as ``python -m oarena._worker`` by :mod:`oarena.runner`; it is never
imported by the parent.  Isolation is not a luxury: a bot whose module fails to
import kills the interpreter with SIGSEGV before ``run_game`` ever returns, so
each game needs a disposable process and the *result file* named in the job is
the only channel back to the supervisor.

The job is a single JSON object on stdin::

    {"a": "/abs/a/main.py", "b": "/abs/b/main.py", "map": "/abs/m.map26",
     "replay": "/abs/tmp/g.replay26", "log": "/abs/tmp/g.log",
     "result": "/abs/tmp/g.json", "seed": 7, "tle_ms": 50, "cwd": "/abs/project"}

Two engine quirks shape the code below:

* the engine writes to file descriptors 1 and 2 straight from Rust, so the log
  is attached with :func:`os.dup2` at the fd level, *before*
  ``fcode.fcode_engine`` is imported — Python-level redirection captures
  nothing, and a load failure only ever announces itself on fd 2;
* the interpreter cannot be finalised normally after the engine has run
  sub-interpreters (CPython 3.12 aborts with "remaining subinterpreters"), so
  the module ends in :func:`os._exit`.  Nothing may be added after it.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

EXIT_OK = 0
EXIT_BAD_JOB = 3
"""stdin held no usable job, so there is no result file to write."""
EXIT_NO_RESULT = 4
"""The game finished but the result file could not be written."""


def _read_job() -> dict[str, Any]:
    """Read the one JSON job object the parent writes to stdin."""
    return json.loads(sys.stdin.read())


def _write_result(path: str, payload: dict[str, Any]) -> None:
    """Write the result document durably — it is the only channel to the parent."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, default=str)
        fh.flush()
        os.fsync(fh.fileno())


def _attach_log(path: str) -> None:
    """Point fds 1 and 2 at ``path`` so everything the engine emits is captured.

    Called before importing the engine: ``Bot A failed to load: ...`` is written
    to fd 2 by the Rust side moments before the process dies, and that line is
    how the supervisor tells a broken bot from a crashed arena.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    with open(path, "wb") as fh:
        os.dup2(fh.fileno(), 1)
        os.dup2(fh.fileno(), 2)


def _play(
    job: dict[str, Any],
) -> tuple[dict[str, Any], str, dict[str, Any] | None, dict[str, Any] | None]:
    """Run one game and return its result plus exact engine provenance.

    Metadata capture is deliberately best-effort: an older or unusual fcode
    package must still be allowed to play a rateable game.  The parent will
    discard a new replay when this snapshot is unavailable or invalid.
    """
    os.chdir(str(job["cwd"]))
    _attach_log(str(job["log"]))

    import fcode
    from oarena.config import fcode_metadata

    version = str(getattr(fcode, "__version__", None) or "unknown")
    try:
        metadata = fcode_metadata(fcode)
    except Exception:  # metadata must never stop the engine from playing
        metadata = None

    import fcode.fcode_engine as engine_module

    run_game = engine_module.run_game
    installed_ruleset = None
    raw_ruleset = job.get("ruleset")
    if raw_ruleset is not None:
        if not isinstance(raw_ruleset, dict) or raw_ruleset.get("name") != "flow_benchmark":
            raise ValueError("unsupported oarena worker ruleset")
        from problems.flow_benchmark.runtime import install

        installed_ruleset = install(
            raw_ruleset,
            fcode_module=fcode,
            engine_module=engine_module,
        )

    engine_root = str(Path(fcode.__file__).resolve().parent)
    result = run_game(
        str(job["a"]),
        str(job["b"]),
        engine_root,
        str(job["map"]),
        str(job["replay"]),
        int(job["seed"]),
        int(job["tle_ms"]),
    )
    ruleset_result = (
        installed_ruleset.finish(Path(job["replay"]))
        if installed_ruleset is not None
        else None
    )
    return result, version, metadata, ruleset_result


def main() -> int:
    """Play one game and record the outcome; return this process's exit code."""
    try:
        job = _read_job()
        result_path = str(job["result"])
    except Exception:
        # Nothing to write to and nothing safe to say on stderr: the parent will
        # classify this process by its exit code.
        return EXIT_BAD_JOB

    payload: dict[str, Any]
    try:
        result, fcode_version, fcode_metadata, ruleset_result = _play(job)
        payload = {
            "ok": True,
            "result": result,
            "fcode_version": fcode_version,
            "fcode_metadata": fcode_metadata,
            "ruleset_result": ruleset_result,
        }
    except BaseException as exc:  # noqa: BLE001 - the result file must always be written
        payload = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        }

    try:
        _write_result(result_path, payload)
    except Exception:
        return EXIT_NO_RESULT
    return EXIT_OK


if __name__ == "__main__":
    try:
        _code = main()
    except BaseException:  # noqa: BLE001 - never let the interpreter finalise
        _code = EXIT_NO_RESULT
    os._exit(_code)

    # Do not put code after this.
