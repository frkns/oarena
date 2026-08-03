"""`oarena.runner`: supervising one game.

Most of these run the *real* :func:`oarena.runner.run_one` — subprocess, job on
stdin, result file, wall-clock deadline, process-group kill — with the argv
rewritten to ``tests/fake_worker.py`` (the ``worker_script`` fixture).  The
engine is never involved, so the whole file finishes in about a second.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

from fake_worker import FAKE_FCODE_METADATA, FAKE_FCODE_VERSION
from oarena import pool as poolmod
from oarena import runner
from oarena.pool import Pool
from oarena.runner import GameOutcome, GameSpec, PlayerResult


def test_child_env_forces_no_bytecode_for_game_worker(monkeypatch) -> None:
    monkeypatch.delenv("PYTHONDONTWRITEBYTECODE", raising=False)
    assert "PYTHONDONTWRITEBYTECODE" not in runner._child_env(False)
    assert runner._child_env(True)["PYTHONDONTWRITEBYTECODE"] == "1"


@pytest.mark.usefixtures("worker_script")
def test_no_bytecode_setting_reaches_worker_that_imports_fcode(spec_factory) -> None:
    spec = replace(
        spec_factory("envcheck", "beta"),
        python_dont_write_bytecode=True,
    )
    outcome = runner.run_one(spec)
    try:
        assert outcome.status == "ok"
        assert outcome.log_path is not None
        assert "PYTHONDONTWRITEBYTECODE=1" in outcome.log_path.read_text()
    finally:
        _cleanup(outcome)


# --------------------------------------------------------------------------- #
# outcome mapping, end to end
# --------------------------------------------------------------------------- #


@pytest.mark.usefixtures("worker_script")
def test_a_clean_game_maps_the_engine_result(spec_factory) -> None:
    spec = spec_factory("alpha", "beta")
    outcome = run_and_clean(spec)

    assert outcome.status == "ok"
    assert outcome.ok is True
    assert outcome.winner == "a"  # "A" -> "a"
    assert outcome.win_condition == "core_destroyed"
    assert outcome.turns == 640
    assert outcome.error == ""
    assert outcome.duration_ms > 0
    assert outcome.fcode_version == FAKE_FCODE_VERSION
    assert outcome.fcode_metadata == FAKE_FCODE_METADATA
    assert outcome.a == PlayerResult(titanium=7427, mined=4880, units=4, buildings=40)
    assert outcome.b == PlayerResult(titanium=2198, mined=0, units=15, buildings=20)


@pytest.mark.usefixtures("worker_script")
def test_slot_b_winner_maps_to_b(spec_factory) -> None:
    outcome = run_and_clean(spec_factory("zulu", "alpha"))
    assert outcome.winner == "b"


@pytest.mark.usefixtures("worker_script")
def test_a_null_winner_maps_to_draw(spec_factory) -> None:
    outcome = run_and_clean(spec_factory("twin", "twin"))
    assert outcome.winner == "draw"
    assert outcome.win_condition == "coinflip"


@pytest.mark.usefixtures("worker_script")
def test_the_replay_is_handed_back_for_the_caller_to_move(spec_factory) -> None:
    spec = spec_factory("alpha", "beta")
    outcome = runner.run_one(spec)
    try:
        assert outcome.replay_path is not None
        assert outcome.replay_path.is_file()
        assert outcome.replay_path.read_bytes().startswith(b"REPLAY26")
    finally:
        _cleanup(outcome)


@pytest.mark.usefixtures("worker_script")
def test_a_log_of_pure_turn_noise_is_thrown_away(spec_factory) -> None:
    spec = spec_factory("alpha", "beta")
    outcome = runner.run_one(spec)
    try:
        assert outcome.log_path is None
        assert outcome.log_tail == ""
        assert list(spec.tmp_dir.glob("*.log")) == []
    finally:
        _cleanup(outcome)


@pytest.mark.usefixtures("worker_script")
def test_turn_noise_is_stripped_from_a_log_worth_keeping(spec_factory) -> None:
    spec = spec_factory("raises-a-lot", "beta")
    outcome = runner.run_one(spec)
    try:
        assert outcome.log_path is not None
        text = outcome.log_path.read_text()
        assert "Completed turn" not in text
        assert "Completed turn" not in outcome.log_tail
        assert "ZeroDivisionError" in text
        assert text.endswith(outcome.log_tail[-40:])
    finally:
        _cleanup(outcome)


@pytest.mark.usefixtures("worker_script")
def test_a_load_failure_on_side_a_is_detected(spec_factory) -> None:
    outcome = run_and_clean(spec_factory("loadfail-one", "beta"))

    assert outcome.status == "loadfail_a"
    assert outcome.winner is None
    assert "ImportError" in outcome.error


@pytest.mark.usefixtures("worker_script")
def test_a_load_failure_on_side_b_is_detected(spec_factory) -> None:
    outcome = run_and_clean(spec_factory("alpha", "loadfail-two"))
    assert outcome.status == "loadfail_b"


@pytest.mark.usefixtures("worker_script")
def test_a_validation_failure_on_side_a_is_an_attributed_error(spec_factory) -> None:
    outcome = run_and_clean(spec_factory("validation-one", "beta"))

    assert outcome.status == "loadfail_a"
    assert outcome.error == "SyntaxError: invalid syntax"
    assert (outcome.a.errors, outcome.b.errors) == (1, 0)


@pytest.mark.usefixtures("worker_script")
def test_both_validation_failures_finish_and_count_both_sides(spec_factory) -> None:
    outcome = run_and_clean(
        spec_factory("validation-one", "validation-two")
    )

    assert outcome.status == "loadfail_both"
    assert "A=SyntaxError: invalid syntax on side A" in outcome.error
    assert "B=SyntaxError: invalid syntax on side B" in outcome.error
    assert (outcome.a.errors, outcome.b.errors) == (1, 1)


@pytest.mark.usefixtures("worker_script")
def test_self_match_with_two_validation_failures_finishes(spec_factory) -> None:
    outcome = run_and_clean(
        spec_factory("validation-syntax", "validation-syntax")
    )

    assert outcome.status == "loadfail_both"
    assert outcome.winner is None
    assert (outcome.a.errors, outcome.b.errors) == (1, 0)


@pytest.mark.usefixtures("worker_script")
def test_a_worker_exception_becomes_engine_error(spec_factory) -> None:
    outcome = run_and_clean(spec_factory("crashy", "beta"))

    assert outcome.status == "engine_error"
    assert outcome.error == "RuntimeError: engine exploded"


@pytest.mark.usefixtures("worker_script")
def test_a_worker_payload_traceback_is_kept_and_attributed(spec_factory) -> None:
    outcome = run_and_clean(spec_factory("panic-alpha", "beta"))

    assert outcome.status == "engine_error"
    assert outcome.error == "RuntimeError: bot escaped into the engine"
    assert (outcome.a.errors, outcome.b.errors) == (1, 0)
    assert "ZeroDivisionError" in outcome.log_tail


@pytest.mark.usefixtures("worker_script")
def test_a_dead_worker_without_a_loadfail_line_is_killed(spec_factory) -> None:
    outcome = run_and_clean(spec_factory("die-here", "beta"))

    assert outcome.status == "killed"
    assert "exit 7" in outcome.error


@pytest.mark.usefixtures("worker_script")
def test_a_timeout_kills_the_whole_process_group(spec_factory, tmp_path: Path) -> None:
    spec = spec_factory("hang-forever", "beta", timeout_s=1.0)
    started = time.monotonic()
    outcome = runner.run_one(spec)
    elapsed = time.monotonic() - started

    try:
        assert outcome.status == "timeout"
        assert "wall clock" in outcome.error
        assert elapsed < 20.0

        pid_files = list(spec.tmp_dir.glob("*.json.pid"))
        assert pid_files, "the fake worker never recorded its grandchild"
        pid = int(pid_files[0].read_text())
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and _alive(pid):
            time.sleep(0.05)
        assert not _alive(pid), "the grandchild survived the process-group kill"
    finally:
        _cleanup(outcome)


@pytest.mark.usefixtures("worker_script")
def test_cancel_active_aborts_a_live_worker_immediately(spec_factory) -> None:
    """The dashboard force-stop path kills a real worker, not just its future."""
    spec = spec_factory("hang-forever", "beta", timeout_s=60.0)
    outcomes: list[GameOutcome] = []
    thread = threading.Thread(target=lambda: outcomes.append(runner.run_one(spec)))
    thread.start()
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and not runner._ACTIVE:
        time.sleep(0.01)
    assert runner._ACTIVE, "worker never reached the supervisor"

    assert runner.cancel_active() == 1
    thread.join(timeout=5.0)
    assert not thread.is_alive(), "force-stop did not reap the game worker"
    assert outcomes and outcomes[0].status == "killed"
    _cleanup(outcomes[0])


@pytest.mark.usefixtures("worker_script")
def test_pool_abort_during_spawn_kills_the_new_worker(
    spec_factory, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancellation between Popen and registration cannot miss the child."""
    cancelled = threading.Event()
    worker_popen = runner.subprocess.Popen

    def cancel_after_spawn(*args, **kwargs):
        proc = worker_popen(*args, **kwargs)
        cancelled.set()
        return proc

    monkeypatch.setattr(runner.subprocess, "Popen", cancel_after_spawn)
    started = time.monotonic()
    outcome = runner.run_one(
        spec_factory("hang-forever", "beta", timeout_s=60.0),
        cancelled=cancelled,
    )
    try:
        assert outcome.status == "killed"
        assert time.monotonic() - started < 5.0
        assert not runner._ACTIVE
    finally:
        _cleanup(outcome)


def test_pool_force_stop_cancels_queued_games(monkeypatch: pytest.MonkeyPatch) -> None:
    """Benchmark jobs queued behind a worker must not start after Ctrl-C."""
    started = threading.Event()
    release = threading.Event()

    def blocking_run(
        _spec: object, *, cancelled: threading.Event | None = None
    ) -> GameOutcome:
        started.set()
        if cancelled is not None and cancelled.wait(timeout=2.0):
            return GameOutcome(status="killed")
        assert release.is_set()
        return GameOutcome(status="killed")

    monkeypatch.setattr(poolmod, "run_one", blocking_run)
    monkeypatch.setattr(poolmod, "cancel_active", lambda: 1)
    pool = Pool(1)
    first = pool.submit(object())  # type: ignore[arg-type]
    queued = [pool.submit(object()) for _ in range(3)]  # type: ignore[arg-type]
    try:
        assert started.wait(timeout=1.0)
        assert pool.force_stop() == 1
        assert all(future.cancelled() for future in queued)
    finally:
        release.set()
        pool.shutdown()

    assert first.result(timeout=1.0).status == "killed"


@pytest.mark.usefixtures("worker_script")
def test_runtime_tracebacks_are_attributed_per_bot(spec_factory) -> None:
    outcome = run_and_clean(spec_factory("raises-a-lot", "beta"))

    assert outcome.status == "ok"
    assert outcome.a.errors == 2  # two tracebacks, not eight frames
    assert outcome.b.errors == 0


def test_run_one_never_raises_on_a_hopeless_spec(spec_factory, monkeypatch) -> None:
    def explode(*_args: object, **_kwargs: object) -> None:
        raise OSError("no processes left")

    monkeypatch.setattr(runner.subprocess, "Popen", explode)
    outcome = runner.run_one(spec_factory("alpha", "beta"))

    assert outcome.status == "engine_error"
    assert "no processes left" in outcome.error


# --------------------------------------------------------------------------- #
# traceback attribution in isolation
# --------------------------------------------------------------------------- #


TRACEBACK = """Traceback (most recent call last):
  File "{entry}", line 194, in on_turn
    self.act()
  File "{entry}", line 12, in act
    raise ValueError("nope")
ValueError: nope
"""


def test_attribution_counts_tracebacks_not_frames(spec_factory) -> None:
    spec = spec_factory("alpha", "beta")
    log = TRACEBACK.format(entry=spec.a.entry)

    assert runner._attribute_tracebacks(log, spec) == (1, 0)


def test_attribution_separates_the_two_bots(spec_factory) -> None:
    spec = spec_factory("alpha", "beta")
    log = (
        TRACEBACK.format(entry=spec.a.entry)
        + TRACEBACK.format(entry=spec.b.entry)
        + TRACEBACK.format(entry=spec.b.entry)
    )
    assert runner._attribute_tracebacks(log, spec) == (1, 2)


def test_attribution_of_a_self_match_counts_side_a_only(spec_factory) -> None:
    spec = spec_factory("twin", "twin")
    log = TRACEBACK.format(entry=spec.a.entry) * 3

    assert runner._attribute_tracebacks(log, spec) == (3, 0)


def test_attribution_ignores_frames_from_neither_bot(spec_factory) -> None:
    spec = spec_factory("alpha", "beta")
    log = TRACEBACK.format(entry="/usr/lib/python3.12/json/decoder.py")

    assert runner._attribute_tracebacks(log, spec) == (0, 0)


def test_attribution_does_not_match_a_prefix_directory(spec_factory) -> None:
    spec = spec_factory("alpha", "beta")
    sibling = str(spec.a.dir) + "2/main.py"
    assert runner._attribute_tracebacks(TRACEBACK.format(entry=sibling), spec) == (0, 0)


def test_attribution_of_an_empty_log(spec_factory) -> None:
    assert runner._attribute_tracebacks("", spec_factory("alpha", "beta")) == (0, 0)


# --------------------------------------------------------------------------- #
# log cleaning and dead-child classification
# --------------------------------------------------------------------------- #


def test_clean_log_strips_turn_noise_and_rewrites_the_file(tmp_path: Path) -> None:
    path = tmp_path / "game.log"
    path.write_text("Completed turn 1\nreal output\nCompleted turn 2\n", encoding="utf-8")

    cleaned = runner._clean_log(path)

    assert cleaned == "real output\n"
    assert path.read_text() == "real output\n"


def test_clean_log_removes_a_log_with_nothing_but_noise(tmp_path: Path) -> None:
    path = tmp_path / "game.log"
    path.write_text("Completed turn 1\nCompleted turn 2\n", encoding="utf-8")

    assert runner._clean_log(path) == ""
    assert not path.exists()


def test_clean_log_of_a_missing_file(tmp_path: Path) -> None:
    assert runner._clean_log(tmp_path / "absent.log") == ""


@pytest.mark.parametrize(
    ("log", "expected_status", "expected_fragment"),
    [
        ("Bot A failed to load: ImportError: boom\n", "loadfail_a", "ImportError: boom"),
        ("Bot B failed to load: SyntaxError: bad\n", "loadfail_b", "SyntaxError: bad"),
        (
            "Bot A failed validation: IndentationError: bad indent\n",
            "loadfail_a",
            "IndentationError: bad indent",
        ),
        (
            "Bot B failed validation: SyntaxError: bad\n",
            "loadfail_b",
            "SyntaxError: bad",
        ),
        (
            "Both bots failed validation: A=SyntaxError: bad A, B=ImportError: bad B\n",
            "loadfail_both",
            "A=SyntaxError: bad A; B=ImportError: bad B",
        ),
        (
            "Both bots failed to load: A=ImportError: bad A, B=SyntaxError: bad B\n",
            "loadfail_both",
            "A=ImportError: bad A; B=SyntaxError: bad B",
        ),
        ("nothing useful here\n", "killed", "worker died"),
        ("", "killed", "worker died"),
    ],
)
def test_classify_dead_child(log: str, expected_status: str, expected_fragment: str) -> None:
    status, error = runner._classify_dead_child(log, -11)
    assert status == expected_status
    assert expected_fragment in error


def test_classify_dead_child_reports_the_bootstrap_error() -> None:
    status, error = runner._classify_dead_child("", 1, "ModuleNotFoundError: no oarena")
    assert status == "killed"
    assert "ModuleNotFoundError" in error


# --------------------------------------------------------------------------- #
# engine dict mapping in isolation
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("raw", "expected"), [("A", "a"), ("B", "b"), (None, "draw"), ("weird", "draw")]
)
def test_winner_mapping(raw: str | None, expected: str) -> None:
    outcome = GameOutcome(status="ok")
    runner._apply_engine_result(outcome, {"winner": raw})
    assert outcome.winner == expected


def test_apply_engine_result_tolerates_missing_keys() -> None:
    outcome = GameOutcome(status="ok")
    runner._apply_engine_result(outcome, {})

    assert outcome.turns == 0
    assert outcome.win_condition == ""
    assert outcome.resign_message == ""
    assert outcome.a == PlayerResult()


def test_apply_engine_result_keeps_the_error_counts() -> None:
    outcome = GameOutcome(status="ok", a=PlayerResult(errors=3), b=PlayerResult(errors=1))
    runner._apply_engine_result(outcome, {"winner": "A", "a_titanium": 10})

    assert outcome.a.errors == 3
    assert outcome.b.errors == 1
    assert outcome.a.titanium == 10


def test_worker_fcode_provenance_rejects_a_version_mismatch() -> None:
    metadata = {**FAKE_FCODE_METADATA, "version": "some-other-engine"}

    version, accepted = runner._worker_fcode_provenance(
        {
            "fcode_version": FAKE_FCODE_VERSION,
            "fcode_metadata": metadata,
        }
    )

    assert version == FAKE_FCODE_VERSION
    assert accepted is None


def test_fcode_metadata_json_is_canonical_and_rejects_nan() -> None:
    encoded = runner.canonical_fcode_metadata_json(
        FAKE_FCODE_VERSION, FAKE_FCODE_METADATA
    )
    assert encoded == (
        '{"direction_deltas":{},"enums":{},"game_constants":{"MAX_TURNS":1000},'
        '"metadata_version":1,"version":"test-fcode-1"}'
    )

    invalid = {
        **FAKE_FCODE_METADATA,
        "game_constants": {"BROKEN": float("nan")},
    }
    assert runner.canonical_fcode_metadata_json(FAKE_FCODE_VERSION, invalid) == ""


# --------------------------------------------------------------------------- #
# fcode helpers
# --------------------------------------------------------------------------- #


def test_check_fcode_returns_a_version_or_says_how_to_install() -> None:
    try:
        assert isinstance(runner.check_fcode(), str)
    except RuntimeError as exc:
        assert "pip install fcode" in str(exc)


def test_visualiser_dist_is_a_real_bundle_or_none() -> None:
    dist = runner.visualiser_dist()
    assert dist is None or (dist / "index.html").is_file()


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _cleanup(outcome: GameOutcome) -> None:
    for path in (outcome.replay_path, outcome.log_path):
        if path is not None:
            try:
                path.unlink()
            except OSError:
                pass


def run_and_clean(spec: GameSpec) -> GameOutcome:
    """Run a game and delete its scratch files, keeping the outcome."""
    outcome = runner.run_one(spec)
    _cleanup(outcome)
    return outcome
