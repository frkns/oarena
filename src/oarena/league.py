"""The league orchestrator — what to play, and what a result means.

Everything else in oarena is a component: the store persists, the runner plays
one game, the matchmaker suggests a pairing. This module is the only thing that
*decides*, and it is deliberately the only writer of game history.

Concurrency contract
--------------------
* A run owns exactly one background thread and one cross-process writer lease.
  Every result commits its game row and both rating updates atomically. Games
  land in completion order, while tagged batches retain planned order in their
  explicit ``batch_ordinal``.
* Callers (the CLI, HTTP handlers) only ever read: :attr:`League.status`,
  :attr:`League.running`, and the event bus. The two mutating entry points from
  outside — :meth:`stop` and :meth:`sync` — are safe at any time; ``stop`` only
  flips a flag and ``sync`` only touches bot rows.
* One run at a time across every updated oarena process sharing the state
  directory. :meth:`start_match` and :meth:`start_arena` fail fast rather than
  interleave two runs over one ladder.

Rating policy
-------------
:meth:`League.finish` is the single source of truth for what counts as a rated
game: unrated runs, self-matches, crashes and load failures never move the
ladder, and the engine's ``coinflip`` tiebreak is recorded as a draw (it carries
no skill signal). ``store.recompute`` replays exactly the rows this method
writes, so a rebuild reproduces the live ratings.
"""

from __future__ import annotations

import os
import random
import shutil
import threading
import time
from collections import deque
from collections.abc import Sequence
from concurrent.futures import FIRST_COMPLETED, CancelledError, Future
from concurrent.futures import wait as wait_futures
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .bots import BotError, BotSource
from .bots import discover as discover_bots
from .bots import resolve as resolve_bot
from .config import Config, ensure_dirs
from .events import EventBus
from .maps import GameMap, MapError
from .maps import resolve as resolve_map
from .maps import select as select_maps
from .matchmaking import Matchmaker, NoMatch
from .matchmaking import make as make_matchmaker
from .pool import Pool
from .ratings import Rater
from .reporting import game_json
from .runner import GameOutcome, GameSpec, canonical_fcode_metadata_json
from .store import Game, Store

__all__ = ["Job", "League", "SyncReport"]

TICK_S = 0.25
"""Loop granularity: how long the run thread blocks waiting for a finished game."""

ARENA_IDLE_S = 1.0
"""How long an arena waits before re-checking after finding no legal pairing."""

STATUS_INTERVAL_S = 0.5
"""``status`` events are coalesced to at most 2 Hz."""

RATE_WINDOW_S = 60.0
"""Width of the sliding window behind ``status["rate"]``."""

GC_EVERY = 20
"""Finished games between replay-budget sweeps (summing a directory is not free)."""

_MIN_RATE_WINDOW_S = 5.0
"""Floor on the rate window so the first seconds of a run cannot report a wild number."""


# --------------------------------------------------------------------------- #
# plan objects
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Job:
    """One scheduled game. ``a`` plays engine slot A, ``b`` slot B."""

    a: str
    b: str
    map: str
    seed: int
    rated: bool = True
    tag: str = "match"
    batch_ordinal: int | None = None
    # ``match -m`` accepts a path outside the configured maps directory.  Keep
    # the stable display/database name in ``map`` while carrying the resolved
    # source path through the asynchronous run boundary.
    map_path: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "a": self.a,
            "b": self.b,
            "map": self.map,
            "seed": self.seed,
            "rated": self.rated,
            "tag": self.tag,
            "batch_ordinal": self.batch_ordinal,
            "map_path": self.map_path,
        }


@dataclass
class SyncReport:
    """What one :meth:`League.sync` changed. Every list is a *delta*, not a census."""

    added: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    unbroken: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.added or self.changed or self.missing or self.unbroken)

    def to_json(self) -> dict[str, list[str]]:
        return {
            "added": list(self.added),
            "changed": list(self.changed),
            "missing": list(self.missing),
            "unbroken": list(self.unbroken),
        }


# --------------------------------------------------------------------------- #
# the league
# --------------------------------------------------------------------------- #


class League:
    """Discovery, scheduling, execution and rating for one oarena project."""

    def __init__(
        self,
        cfg: Config,
        store: Store,
        bus: EventBus,
        rater: Rater | None = None,
    ) -> None:
        self.cfg = cfg
        self.store = store
        self.bus = bus
        self.rater = rater if rater is not None else Rater(cfg.trueskill)

        self._rng = random.Random()
        self._lock = threading.RLock()
        self._sync_lock = threading.Lock()

        # --- run state (guarded by _lock) --------------------------------- #
        self._thread: threading.Thread | None = None
        self._pool: Pool | None = None
        self._queue: deque[Job] = deque()
        self._live: dict[Future[GameOutcome], tuple[Job, float]] = {}
        self._running = False
        self._stopping = False
        self._mode = ""
        self._label = ""
        self._total: int | None = None
        self._limit = 0
        self._done = 0
        self._started: float | None = None
        self._started_mono: float | None = None
        self._workers = cfg.n_workers
        self._finishes: deque[float] = deque()
        self._last_status = 0.0
        self._batch_tag: str | None = None
        self._run_writer_held = False
        self._writer_adopted = threading.Event()
        self._next_batch_ordinal = 0
        self._discard_cancelled = False

        # --- run-thread-only state ---------------------------------------- #
        self._matchmaker: Matchmaker | None = None
        self._arena_rated = True
        self._arena_maps: list[GameMap] = []
        self._idle_until = 0.0
        self._idle_reason = ""
        self._idle_logged = 0.0
        self._seed_n = 0
        self._since_gc = 0
        self._bot_cache: dict[str, BotSource] = {}
        self._map_cache: dict[str, GameMap] = {}

        ensure_dirs(cfg)

    # ---------------------------------------------------------------- #
    # discovery
    # ---------------------------------------------------------------- #

    def sync(self) -> SyncReport:
        """Reconcile the bot table with what is on disk.

        New directories are inserted at the initial rating; a live bot whose
        sources changed keeps its mean but has sigma re-inflated so the ladder
        re-tests it (and is un-broken, since the edit may well be the fix); a
        bot whose directory vanished is deactivated.

        Only bot rows are touched, so this is safe to call while a run is in
        flight. Deactivation is never undone automatically — that would fight
        ``oarena bot disable``, which every command would otherwise reverse.
        """
        cfg = self.cfg
        report = SyncReport()
        with self.store.writer_lock.hold("bot catalog sync"), self._sync_lock:
            found = discover_bots(cfg.bots_dir)
            known = {b.name: b for b in self.store.bots()}

            for src in found:
                row = known.get(src.name)
                if cfg.bot_sync_mode == "verify-only":
                    if row is None:
                        raise BotError(
                            f"{src.name}: verify-only bot sync requires an existing "
                            "shared-league bot row"
                        )
                    if row.src_hash != src.src_hash:
                        raise BotError(
                            f"{src.name}: frozen source hash {src.src_hash} does not match "
                            f"shared-league hash {row.src_hash}"
                        )
                    # The frozen path is execution input, not catalog identity:
                    # never rewrite dir/entry, source versions or uncertainty.
                    continue
                if row is None:
                    self.store.upsert_bot(src, self.rater.initial())
                    self.store.set_hash(src.name, src.src_hash)
                    report.added.append(src.name)
                    self.bus.emit("bot_added", name=src.name)
                    continue

                if row.dir != str(src.dir) or row.entry != str(src.entry):
                    self.store.set_paths(src.name, str(src.dir), str(src.entry))

                if row.src_hash == src.src_hash:
                    continue

                self.store.set_hash(src.name, src.src_hash)
                self.store.set_rating(
                    src.name, self.rater.reinflate(row.rating, cfg.sigma_reinflate)
                )
                report.changed.append(src.name)
                self.bus.emit("bot_changed", name=src.name, hash=src.src_hash)
                if row.broken:
                    self.store.set_broken(src.name, False)
                    report.unbroken.append(src.name)
                    self.bus.emit("bot_fixed", name=src.name)

            if cfg.deactivate_missing_bots and cfg.bot_sync_mode != "verify-only":
                names = {src.name for src in found}
                for name, row in known.items():
                    if name in names or not row.active:
                        continue
                    self.store.set_active(name, False)
                    report.missing.append(name)
                    self.bus.emit(
                        "log", level="warn", msg=f"{name}: source directory is gone — deactivated"
                    )

        return report

    def resolve(self, name: str) -> BotSource:
        """Resolve a bot spec, syncing on a miss so the store knows it too."""
        cfg = self.cfg
        try:
            src = resolve_bot(cfg.bots_dir, name)
        except BotError:
            self.sync()
            src = resolve_bot(cfg.bots_dir, name)
        if self.store.get_bot(src.name) is None:
            self.sync()
        return src

    # ---------------------------------------------------------------- #
    # planning
    # ---------------------------------------------------------------- #

    def plan_match(
        self,
        a: str,
        b: str,
        *,
        maps: Sequence[str] | None = None,
        repeat: int = 1,
        mirror: bool | None = None,
        rated: bool = True,
        tag: str = "match",
    ) -> list[Job]:
        """Build the finite job list for ``a`` vs ``b``.

        One round covers every selected map before the next round starts, so a
        run stopped half way through still says something about every map. With
        ``mirror`` each pairing is played twice on the same map *and seed* with
        the sides swapped, which cancels turn-order bias. A bot matched against
        itself is always unrated.
        """
        cfg = self.cfg
        src_a, src_b = self.resolve(a), self.resolve(b)
        chosen = select_maps(cfg.maps_dir, maps, cfg.maps, cfg.extra_maps_dir)
        use_mirror = cfg.mirror if mirror is None else bool(mirror)
        rounds = max(1, int(repeat))
        if src_a.name == src_b.name:
            rated = False

        jobs: list[Job] = []
        for rnd in range(rounds):
            for game_map in chosen:
                seed = cfg.seed + rnd if cfg.seed_policy == "fixed" else self._random_seed()
                map_path = str(game_map.path.resolve())
                jobs.append(
                    Job(
                        src_a.name,
                        src_b.name,
                        game_map.name,
                        seed,
                        rated,
                        tag,
                        map_path=map_path,
                    )
                )
                if use_mirror:
                    jobs.append(
                        Job(
                            src_b.name,
                            src_a.name,
                            game_map.name,
                            seed,
                            rated,
                            tag,
                            map_path=map_path,
                        )
                    )
        return jobs

    # ---------------------------------------------------------------- #
    # execution
    # ---------------------------------------------------------------- #

    def start_match(
        self,
        jobs: list[Job],
        *,
        label: str = "",
        workers: int | None = None,
        batch_tag: str | None = None,
    ) -> None:
        """Run a finite job list. Raises ``RuntimeError`` if a run is already active."""
        if self.running:  # cheap pre-check; _begin re-checks under the lock
            raise RuntimeError("a run is already in progress")
        # A package directory is the source of truth.  Rehash immediately
        # before a run, so an edit made since the dashboard was opened gets its
        # own version marker and uncertainty before the first new game lands.
        planned = list(jobs)
        if batch_tag is not None:
            planned = [
                replace(job, tag=batch_tag, batch_ordinal=ordinal)
                for ordinal, job in enumerate(planned)
            ]
        self.store.writer_lock.acquire(
            f"rated run match{f' tag={batch_tag}' if batch_tag else ''}",
            exclusive=True,
        )
        reserved = False
        try:
            if batch_tag is not None:
                self.store.reserve_batch(
                    batch_tag, mode="match", requested_games=len(planned)
                )
                reserved = True
            self.sync()
            with self._lock:
                self._batch_tag = batch_tag
                self._run_writer_held = True
                self._begin(
                    mode="match",
                    label=label or _match_label(planned),
                    total=len(planned),
                    workers=workers,
                )
                self._queue.extend(planned)
                self._launch()
        except BaseException:
            if reserved:
                self.store.finish_batch(batch_tag or "", status="aborted")
            with self._lock:
                self._run_writer_held = False
                self._batch_tag = None
            self.store.writer_lock.release()
            raise

    def start_arena(
        self,
        kind: str = "ladder",
        *,
        top: int = 0,
        target: str | None = None,
        rated: bool = True,
        limit: int = 0,
        workers: int | None = None,
        batch_tag: str | None = None,
    ) -> None:
        """Run until stopped, letting ``kind`` choose each pairing.

        ``kind`` is one of ``ladder``/``top``/``vs``/``rr``. ``limit`` stops the
        run after that many games (0 = endless). Every pairing is queued twice,
        swapped, on one map and seed. Invalid arguments (unknown matchmaker,
        missing target, no maps) raise before the run thread starts.
        """
        cfg = self.cfg
        if self.running:  # cheap pre-check; _begin re-checks under the lock
            raise RuntimeError("a run is already in progress")
        if kind not in {"ladder", "top", "vs", "rr"}:
            raise ValueError(f"unknown matchmaker {kind!r}")
        total = int(limit) if limit > 0 else None
        planned_mode = "vs" if kind == "vs" else "arena"
        self.store.writer_lock.acquire(
            f"rated run arena{f' tag={batch_tag}' if batch_tag else ''}",
            exclusive=True,
        )
        reserved = False
        try:
            if batch_tag is not None:
                self.store.reserve_batch(
                    batch_tag, mode=planned_mode, requested_games=total
                )
                reserved = True
            self.sync()
            matchmaker = make_matchmaker(
                kind, self.store, self.rater, target=target, top=top, rng=self._rng
            )
            mode = "vs" if matchmaker.name == "vs" else "arena"
            if mode == "vs" and target:
                self.resolve(target)  # fail now on a typo, not once per idle second
            arena_maps = select_maps(cfg.maps_dir, None, cfg.maps, cfg.extra_maps_dir)
            with self._lock:
                self._batch_tag = batch_tag
                self._run_writer_held = True
                self._begin(
                    mode=mode,
                    label=_arena_label(matchmaker, top, target),
                    total=total,
                    workers=workers,
                )
                self._matchmaker = matchmaker
                self._arena_maps = arena_maps
                self._arena_rated = bool(rated)
                self._limit = max(0, int(limit))
                self._launch()
        except BaseException:
            if reserved:
                self.store.finish_batch(batch_tag or "", status="aborted")
            with self._lock:
                self._run_writer_held = False
                self._batch_tag = None
            self.store.writer_lock.release()
            raise

    def stop(self) -> None:
        """Stop scheduling new games and let the in-flight ones finish.

        Idempotent, and a no-op when nothing is running.
        """
        with self._lock:
            if not self._running or self._stopping:
                return
            self._stopping = True
        self.bus.emit("log", level="info", msg="stopping — waiting for in-flight games")

    def force_stop(self, *, discard_cancelled: bool = False) -> int:
        """Abort a run; optionally omit shutdown-cancelled games from history."""
        with self._lock:
            if not self._running:
                return 0
            self._stopping = True
            if discard_cancelled:
                self._discard_cancelled = True
            self._queue.clear()
            pool = self._pool
            # Ctrl-C can land after _begin() marks the run active but before
            # _launch() creates its thread. There is then no run loop available
            # to clear `_running`; finalize that pre-launch state here so CLI
            # cleanup cannot wait forever.
            if self._thread is None:
                self._running = False
                self._stopping = False
                self._pool = None
        killed = pool.force_stop() if pool is not None else 0
        self.bus.emit(
            "log", level="warn", msg=f"force stop — aborted {killed} in-flight game(s)"
        )
        self._emit_status(force=True)
        return killed

    def wait(self, timeout: float | None = None) -> bool:
        """Block until the run thread has fully exited. ``True`` if it has."""
        with self._lock:
            thread = self._thread
        if thread is None:
            return not self.running
        thread.join(timeout)
        return not thread.is_alive()

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    @property
    def workers(self) -> int:
        """Parallelism of the current run, or the configured default when idle."""
        with self._lock:
            return self._workers

    @property
    def status(self) -> dict[str, Any]:
        """A snapshot of the run for the topbar, the CLI footer and the SSE feed.

        ``since`` inside ``live`` and the ``now`` key are both ``time.monotonic``
        readings, so ``now - since`` is a game's age in seconds. ``started`` is
        wall-clock (epoch seconds) for display. Counters from the last run are
        kept after it ends, so a finished match still reads ``60/60``.
        """
        now = time.monotonic()
        with self._lock:
            live = [
                {"a": job.a, "b": job.b, "map": job.map, "seed": job.seed, "since": since}
                for job, since in sorted(self._live.values(), key=lambda item: item[1])
            ]
            elapsed = 0.0 if self._started_mono is None else now - self._started_mono
            return {
                "running": self._running,
                "mode": self._mode,
                "label": self._label,
                "queued": len(self._queue),
                "in_flight": len(self._live),
                "done": self._done,
                "total": self._total,
                "started": self._started,
                "elapsed": elapsed,
                "rate": self._rate(now),
                "workers": self._workers,
                "stopping": self._stopping,
                "now": now,
                # Only while the back-off is actually in force: an arena that
                # cannot find a matchup waits for one instead of exiting, and a
                # UI showing a still ladder needs to say why.
                "idle_reason": self._idle_reason if self._idle_until > now else "",
                "live": live,
            }

    # ---------------------------------------------------------------- #
    # run lifecycle
    # ---------------------------------------------------------------- #

    def _begin(self, *, mode: str, label: str, total: int | None, workers: int | None) -> None:
        """Reset run state for a new run. Caller holds the lock."""
        if self._running:
            raise RuntimeError("a run is already in progress")
        ensure_dirs(self.cfg)
        self._thread = None
        self._running = True
        self._stopping = False
        self._mode = mode
        self._label = label
        self._total = total
        self._limit = 0
        self._done = 0
        self._queue.clear()
        self._live.clear()
        self._finishes.clear()
        self._started = time.time()
        self._started_mono = time.monotonic()
        self._last_status = 0.0
        self._workers = max(1, int(workers)) if workers else self.cfg.n_workers
        self._matchmaker = None
        self._arena_maps = []
        self._idle_until = 0.0
        self._idle_reason = ""
        self._idle_logged = 0.0
        self._since_gc = 0
        self._seed_n = 0
        self._next_batch_ordinal = 0
        self._discard_cancelled = False
        self._writer_adopted.clear()
        self._bot_cache.clear()
        self._map_cache.clear()
        self._pool = Pool(self._workers)

    def _launch(self) -> None:
        """Start the run thread. Caller holds the lock."""
        self._thread = threading.Thread(target=self._run, name="oarena-league", daemon=True)
        try:
            self._thread.start()
            if not self._writer_adopted.wait(timeout=5.0):
                raise RuntimeError("run thread did not inherit the writer lease")
            self.store.writer_lock.disallow_current_thread()
        except BaseException:  # the OS refused a thread: leave the league idle, not wedged
            self._running = False
            if self._pool is not None:
                self._pool.shutdown(wait=False)
                self._pool = None
            raise

    def _run(self) -> None:
        """The run thread: schedule, collect, rate, repeat."""
        self.store.writer_lock.authorize_current_thread()
        self._writer_adopted.set()
        with self._lock:
            mode, label, total, pool, batch_tag = (
                self._mode,
                self._label,
                self._total,
                self._pool,
                self._batch_tag,
            )
        self.bus.emit(
            "run_started",
            mode=mode,
            total=total,
            label=label,
            batch_tag=batch_tag,
        )
        self._emit_status(force=True)

        aborted = False
        try:
            if pool is not None:
                self._drive(pool)
        except BaseException as exc:  # noqa: BLE001 - a run must not die silently
            aborted = True
            self.bus.emit(
                "log", level="error", msg=f"run aborted: {type(exc).__name__}: {exc}"
            )
        finally:
            try:
                if pool is not None:
                    pool.shutdown(wait=True)
            except BaseException as exc:  # noqa: BLE001 - still seal and unlock the run
                aborted = True
                self.bus.emit(
                    "log", level="error", msg=f"pool shutdown failed: {type(exc).__name__}: {exc}"
                )
            with self._lock:
                played, stopped = self._done, self._stopping
                self._queue.clear()
                self._live.clear()
                self._running = False
                self._stopping = False
                self._pool = None
            try:
                if batch_tag is not None:
                    terminal = "aborted" if aborted else ("stopped" if stopped else "completed")
                    self.store.finish_batch(batch_tag, status=terminal)
            finally:
                with self._lock:
                    release_writer = self._run_writer_held
                    self._run_writer_held = False
                    self._batch_tag = None
                if release_writer:
                    self.store.writer_lock.release()
            self._emit_status(force=True)
            self.bus.emit(
                "run_finished",
                mode=mode,
                played=played,
                stopped=stopped,
                batch_tag=batch_tag,
            )

    def _drive(self, pool: Pool) -> None:
        """The scheduling loop. Never busy-spins: it blocks on futures or sleeps."""
        while True:
            exhausted = False
            if not self._stopping:
                exhausted = self._fill(pool)

            with self._lock:
                pending = list(self._live)
            if not pending:
                if self._stopping or exhausted:
                    break
                # An arena with nothing to play: idle briefly and try again.
                time.sleep(TICK_S)
                continue

            done, _ = wait_futures(pending, timeout=TICK_S, return_when=FIRST_COMPLETED)
            for future in done:
                with self._lock:
                    entry = self._live.pop(future, None)
                    discard_cancelled = self._discard_cancelled
                if entry is None:  # pragma: no cover - a future is popped once
                    continue
                outcome = _outcome_of(future)
                if discard_cancelled and outcome.status == "killed":
                    if outcome.replay_path is not None:
                        _unlink(outcome.replay_path)
                    if outcome.log_path is not None:
                        _unlink(outcome.log_path)
                    continue
                self.finish(entry[0], outcome)
            self._emit_status()

    def _fill(self, pool: Pool) -> bool:
        """Submit until the pool is full. ``True`` when no more work can be scheduled.

        "No more work" ends the run once the in-flight games drain: a match has
        emptied its queue, or a capped arena has reached its game limit. An
        arena that merely has no legal pairing right now returns ``False`` and
        the loop idles instead.
        """
        while True:
            with self._lock:
                if len(self._live) >= self._workers:
                    return False
            job = self._next_job()
            if job is None:
                with self._lock:
                    if self._mode == "match":
                        return True
                    scheduled = self._done + len(self._live) + len(self._queue)
                    return self._limit > 0 and scheduled >= self._limit
            self._submit(pool, job)

    def _next_job(self) -> Job | None:
        """The next game to play, or ``None`` for "nothing right now".

        In match mode that means the finite queue is empty and the run is over;
        in arena mode it means the matchmaker had no legal pairing (or the game
        limit is reached) and the loop should idle rather than exit.
        """
        with self._lock:
            if self._queue:
                return self._queue.popleft()
            if self._mode == "match":
                return None
        return self._arena_pair()

    def _arena_pair(self) -> Job | None:
        """Queue one mirrored pairing and hand back the first half of it."""
        now = time.monotonic()
        if now < self._idle_until:
            return None

        remaining = self._remaining()
        if remaining <= 0:
            return None

        bots = sorted(
            self.store.bots(active_only=True), key=lambda b: (-b.mu, b.name)
        )
        matchmaker = self._matchmaker
        if matchmaker is None:  # pragma: no cover - set before the thread starts
            return None
        try:
            a, b = matchmaker.pick(bots)
        except NoMatch as exc:
            self._idle(str(exc))
            return None

        game_map = self._rng.choice(self._arena_maps)
        seed = self._next_seed()
        with self._lock:
            tag = self._batch_tag or self._mode
            first_ordinal = (
                self._next_batch_ordinal if self._batch_tag is not None else None
            )
            if self._batch_tag is not None:
                self._next_batch_ordinal += 1
            mirror_ordinal = (
                self._next_batch_ordinal
                if self._batch_tag is not None and remaining > 1
                else None
            )
            if mirror_ordinal is not None:
                self._next_batch_ordinal += 1
            first = Job(
                a,
                b,
                game_map.name,
                seed,
                self._arena_rated,
                tag,
                first_ordinal,
            )
            mirror = Job(
                b,
                a,
                game_map.name,
                seed,
                self._arena_rated,
                tag,
                mirror_ordinal,
            )
            if remaining > 1:
                self._queue.append(mirror)
        return first

    def _remaining(self) -> int:
        """Games an arena may still schedule (a huge number when uncapped)."""
        with self._lock:
            if self._limit <= 0:
                return 1 << 30
            return self._limit - (self._done + len(self._live) + len(self._queue))

    def _idle(self, reason: str) -> None:
        """Back off for a second without changing source identity mid-run."""
        now = time.monotonic()
        self._idle_until = now + ARENA_IDLE_S
        if reason != self._idle_reason or now - self._idle_logged > 30.0:
            self._idle_reason = reason
            self._idle_logged = now
            self.bus.emit("log", level="warn", msg=f"idle: {reason}")

    def _submit(self, pool: Pool, job: Job) -> None:
        """Turn a job into a running game, or drop it with a loud log line."""
        try:
            spec = self._spec(job)
        except (BotError, MapError) as exc:
            self.bus.emit(
                "log",
                level="error",
                msg=f"skipped {job.a} vs {job.b} on {job.map}: {exc}",
            )
            with self._lock:
                self._done += 1
            return

        future = pool.submit(spec)
        with self._lock:
            self._live[future] = (job, time.monotonic())
        self.bus.emit(
            "game_started", a=job.a, b=job.b, map=job.map, seed=job.seed, rated=job.rated
        )

    def _spec(self, job: Job) -> GameSpec:
        cfg = self.cfg
        return GameSpec(
            a=self._bot(job.a),
            b=self._bot(job.b),
            map=self._map(job.map_path or job.map),
            seed=job.seed,
            tle_ms=cfg.tle_ms,
            timeout_s=cfg.game_timeout_s,
            cwd=cfg.root,
            tmp_dir=cfg.tmp_dir,
            python_dont_write_bytecode=cfg.python_dont_write_bytecode,
        )

    def _bot(self, name: str) -> BotSource:
        """Resolve (and cache) a bot for the duration of a run.

        Hashing a bot's sources is not free and the paths cannot usefully change
        mid-run, so each name is resolved once. A bot that is not in the store
        yet is inserted here, on the run thread, so its rating row exists before
        the first result lands.
        """
        cached = self._bot_cache.get(name)
        if cached is not None:
            return cached
        src = resolve_bot(self.cfg.bots_dir, name)
        row = self.store.get_bot(src.name)
        if row is None:
            if self.cfg.bot_sync_mode == "verify-only":
                raise BotError(
                    f"{src.name}: verify-only bot sync requires an existing "
                    "shared-league bot row"
                )
            self.store.upsert_bot(src, self.rater.initial())
            self.store.set_hash(src.name, src.src_hash)
            self.bus.emit("bot_added", name=src.name)
        elif row.src_hash != src.src_hash:
            if self.cfg.bot_sync_mode == "verify-only":
                raise BotError(
                    f"{src.name}: frozen source hash {src.src_hash} does not match "
                    f"shared-league hash {row.src_hash}"
                )
            self.store.set_hash(src.name, src.src_hash)
            self.store.set_rating(
                src.name, self.rater.reinflate(row.rating, self.cfg.sigma_reinflate)
            )
            self.bus.emit("bot_changed", name=src.name, hash=src.src_hash)
        self._bot_cache[name] = src
        return src

    def _map(self, name: str) -> GameMap:
        cached = self._map_cache.get(name)
        if cached is None:
            cached = resolve_map(self.cfg.maps_dir, name, self.cfg.extra_maps_dir)
            self._map_cache[name] = cached
        return cached

    # ---------------------------------------------------------------- #
    # results
    # ---------------------------------------------------------------- #

    def finish(self, job: Job, outcome: GameOutcome) -> Game:
        """Record one finished game and apply its consequences.

        This is the single source of truth for rating policy:

        1. the log is kept whenever the game produced one; a newly generated
           replay is kept only for a completed game with valid per-game fcode
           provenance;
        2. a one-sided, bot-attributed failure is that bot's loss, including a
           validation failure that takes down the engine; failures on both
           sides and unattributed engine failures remain unrated;
        3. a bot that failed validation/import is marked broken even when the
           failure is rated, and a bot that later loads is un-broken again;
        4. a ``coinflip`` finish stays rated but is recorded as a draw — the
           engine's tiebreak carries no skill signal.
        """
        cfg = self.cfg
        winner = outcome.winner
        win_condition = outcome.win_condition
        rated = bool(job.rated) and job.a != job.b
        a_errors = max(0, outcome.a.errors)
        b_errors = max(0, outcome.b.errors)
        if outcome.status in ("loadfail_a", "loadfail_both"):
            a_errors = max(1, a_errors)
        if outcome.status == "loadfail_b" or (
            outcome.status == "loadfail_both" and job.a != job.b
        ):
            b_errors = max(1, b_errors)
        if outcome.status == "loadfail_both" and job.a == job.b:
            b_errors = 0

        if outcome.status == "loadfail_both":
            winner = None
            win_condition = "bot_error_both"
            rated = False
            reason = outcome.error or "both bots failed to load"
            self._break(job.a, reason)
            if job.b != job.a:
                self._break(job.b, reason)
        elif outcome.status in ("loadfail_a", "loadfail_b"):
            side_a = outcome.status.endswith("_a")
            culprit = job.a if side_a else job.b
            reason = outcome.error or "bot failed to load"
            winner = None if job.a == job.b else ("b" if side_a else "a")
            win_condition = "bot_error"
            self._break(culprit, reason)
        elif a_errors or b_errors:
            a_failed = a_errors > 0
            b_failed = b_errors > 0
            if job.a == job.b or a_failed == b_failed:
                winner = None
                win_condition = "bot_error_both"
                rated = False
            else:
                winner = "b" if a_failed else "a"
                win_condition = "bot_error"
        elif not outcome.ok:
            rated = False
            self.bus.emit(
                "log",
                level="warn",
                msg=f"{job.a} vs {job.b} on {job.map}: {outcome.status}"
                + (f" — {outcome.error}" if outcome.error else ""),
            )
        elif outcome.win_condition == "coinflip" and cfg.coinflip_is_draw:
            winner = "draw"

        fcode_metadata_json = canonical_fcode_metadata_json(
            outcome.fcode_version, outcome.fcode_metadata
        )
        game = Game(
            a=job.a,
            b=job.b,
            a_src_hash=self._bot(job.a).src_hash,
            b_src_hash=self._bot(job.b).src_hash,
            fcode_version=outcome.fcode_version,
            fcode_metadata_json=fcode_metadata_json,
            map=job.map,
            seed=job.seed,
            rated=rated,
            status=outcome.status,
            winner=winner,
            win_condition=win_condition,
            turns=outcome.turns,
            duration_ms=outcome.duration_ms,
            resign_message=outcome.resign_message,
            error=outcome.error,
            a_titanium=outcome.a.titanium,
            a_mined=outcome.a.mined,
            a_units=outcome.a.units,
            a_buildings=outcome.a.buildings,
            a_errors=a_errors,
            b_titanium=outcome.b.titanium,
            b_mined=outcome.b.mined,
            b_units=outcome.b.units,
            b_buildings=outcome.b.buildings,
            b_errors=b_errors,
            tag=job.tag,
            batch_ordinal=job.batch_ordinal,
        )

        delta = self.store.record_game(game, self.rater)
        self._persist_files(game, outcome)
        if outcome.ok and a_errors == 0:
            self._unbreak(job.a)
        if outcome.ok and b_errors == 0 and job.b != job.a:
            self._unbreak(job.b)

        with self._lock:
            self._done += 1
            self._finishes.append(time.monotonic())
            self._since_gc += 1
            sweep = self._since_gc >= GC_EVERY
            if sweep:
                self._since_gc = 0

        self.bus.emit("game_finished", game=game_json(game), delta=delta)
        if sweep:
            self.enforce_replay_budget()
        return game

    def _persist_files(self, game: Game, outcome: GameOutcome) -> None:
        """Move the run's temp replay/log under the game id, or throw them away.

        The id only exists once the row is inserted, hence the second write:
        insert, move, ``set_files``.
        """
        cfg = self.cfg
        replay = ""
        if outcome.replay_path is not None:
            if (
                outcome.ok
                and game.fcode_metadata_json
                and _move(outcome.replay_path, cfg.replay_dir / f"{game.id}.replay26")
            ):
                replay = f"{game.id}.replay26"
            else:
                _unlink(outcome.replay_path)
                if outcome.ok and not game.fcode_metadata_json:
                    self.bus.emit(
                        "log",
                        level="warn",
                        msg=(
                            f"discarded replay for game {game.id} ({game.a} vs {game.b}): "
                            "valid per-game fcode metadata was unavailable"
                        ),
                    )

        log = ""
        if outcome.log_path is not None and _move(outcome.log_path, cfg.log_dir / f"{game.id}.log"):
            log = f"{game.id}.log"

        game.replay, game.log = replay, log
        if replay or log:
            self.store.set_files(game.id, replay, log)

    def _break(self, name: str, reason: str) -> None:
        """Record a bot's latest load failure without excluding it from play."""
        bot = self.store.get_bot(name)
        if bot is None or not bot.broken or bot.broken_reason != reason:
            self.store.set_broken(name, True, reason)
            self.bus.emit("bot_broken", name=name, reason=reason)

    def _unbreak(self, name: str) -> None:
        """A bot that just played a clean game is not broken any more."""
        bot = self.store.get_bot(name)
        if bot is None or not bot.broken:
            return
        self.store.set_broken(name, False)
        self.bus.emit("bot_fixed", name=name)

    def enforce_replay_budget(self) -> int:
        """Delete the oldest replays until the directory fits the budget.

        Returns how many were pruned. A budget of 0 means "keep no replays".
        Only replays the store knows about are considered; stray files are the
        business of ``oarena gc``.
        """
        budget = self.cfg.replay_budget_bytes
        if budget is None:
            return 0
        entries = self.store.replay_files()  # newest first
        sized: list[tuple[int, Path, int]] = []
        total = 0
        for gid, name in entries:
            path = self.cfg.replay_dir / name
            try:
                size = path.stat().st_size
            except OSError:
                self.store.clear_replay(gid)  # the file is gone; stop advertising it
                continue
            sized.append((gid, path, size))
            total += size

        pruned = 0
        for gid, path, size in reversed(sized):  # oldest first
            if total <= budget:
                break
            _unlink(path)
            self.store.clear_replay(gid)
            total -= size
            pruned += 1
        if pruned:
            self.bus.emit(
                "log",
                level="info",
                msg=f"pruned {pruned} replay(s) to stay under {self.cfg.replay_budget_mb} MB",
            )
        return pruned

    # ---------------------------------------------------------------- #
    # small helpers
    # ---------------------------------------------------------------- #

    def _random_seed(self) -> int:
        # random.Random is not thread-safe, and this is genuinely cross-thread:
        # the run thread draws arena seeds while plan_match can be called from an
        # HTTP handler at the same time.
        with self._lock:
            return self._rng.randrange(1, 2**31)

    def _next_seed(self) -> int:
        """Seed for the next arena pairing, honouring ``seed_policy``."""
        with self._lock:
            if self.cfg.seed_policy == "fixed":
                seed = self.cfg.seed + self._seed_n
                self._seed_n += 1
                return seed
        return self._random_seed()

    def _rate(self, now: float) -> float:
        """Finished games per minute. Caller holds the lock."""
        cutoff = now - RATE_WINDOW_S
        while self._finishes and self._finishes[0] < cutoff:
            self._finishes.popleft()
        if not self._finishes:
            return 0.0
        elapsed = RATE_WINDOW_S if self._started_mono is None else now - self._started_mono
        window = max(_MIN_RATE_WINDOW_S, min(RATE_WINDOW_S, elapsed))
        return len(self._finishes) * 60.0 / window

    def _emit_status(self, force: bool = False) -> None:
        """Publish a ``status`` event, coalesced to :data:`STATUS_INTERVAL_S`."""
        now = time.monotonic()
        with self._lock:
            if not force and now - self._last_status < STATUS_INTERVAL_S:
                return
            self._last_status = now
        self.bus.emit("status", **self.status)


# --------------------------------------------------------------------------- #
# module helpers
# --------------------------------------------------------------------------- #


def _outcome_of(future: Future[GameOutcome]) -> GameOutcome:
    """The future's result; a raising future becomes an ``engine_error`` outcome."""
    try:
        return future.result()
    except CancelledError:
        return GameOutcome(status="killed", error="cancelled before collection")
    except BaseException as exc:  # noqa: BLE001 - run_one should never raise, but
        return GameOutcome(status="engine_error", error=f"{type(exc).__name__}: {exc}")


def _match_label(jobs: Sequence[Job]) -> str:
    """A short human label for a finite run, e.g. ``starter vs greedy · 30 games``."""
    if not jobs:
        return "match"
    names = {frozenset((job.a, job.b)) for job in jobs}
    if len(names) == 1:
        first = jobs[0]
        pair = first.a if first.a == first.b else f"{first.a} vs {first.b}"
    else:
        pair = "match"
    return f"{pair} · {len(jobs)} game{'s' if len(jobs) != 1 else ''}"


def _arena_label(matchmaker: Matchmaker, top: int, target: str | None) -> str:
    kind = matchmaker.name
    if kind == "vs" and target:
        return f"vs {target}"
    if kind == "top":
        return f"top {top}" if top else "top"
    if kind == "rr":
        return "round robin"
    return "ladder"


def _move(src: Path, dst: Path) -> bool:
    """Move ``src`` onto ``dst``, creating the parent. ``False`` if it could not be done."""
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.replace(src, dst)
        return True
    except OSError:
        try:  # a different filesystem under .oarena/ is unusual but survivable
            shutil.move(str(src), str(dst))
            return True
        except (OSError, shutil.Error):
            return False


def _unlink(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass
