"""A small fixed-size pool of supervised games.

Each pooled thread spends essentially all of its life blocked in
``subprocess.wait``, so a :class:`~concurrent.futures.ThreadPoolExecutor` is the
right shape here despite the GIL: the work happens in the worker processes that
:func:`oarena.runner.run_one` spawns.
"""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor

from .runner import GameOutcome, GameSpec, cancel_active, run_one

__all__ = ["Pool"]


class Pool:
    """N games in flight, each a supervised subprocess.

    ``in_flight`` counts jobs that have been submitted but not yet finished —
    including those still queued inside the executor — so callers can use it to
    decide when to hand over more work.
    """

    def __init__(self, workers: int) -> None:
        self._workers = max(1, int(workers))
        self._lock = threading.Lock()
        self._cancelled = threading.Event()
        self._in_flight = 0
        self._executor = ThreadPoolExecutor(
            max_workers=self._workers, thread_name_prefix="oarena-game"
        )

    @property
    def workers(self) -> int:
        return self._workers

    @property
    def in_flight(self) -> int:
        with self._lock:
            return self._in_flight

    def submit(self, spec: GameSpec) -> Future[GameOutcome]:
        """Queue a game; the returned future never carries an exception."""
        with self._lock:
            self._in_flight += 1
        try:
            future = self._executor.submit(run_one, spec, cancelled=self._cancelled)
        except BaseException:
            # RuntimeError after shutdown, or the thread could not be started.
            self._release()
            raise
        future.add_done_callback(self._on_done)
        return future

    def shutdown(self, *, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)

    def force_stop(self) -> int:
        """Abort real engine workers now, rather than waiting for their timeout.

        The league stops submitting before it calls this. Benchmark mode may
        have additional futures queued inside the executor, so cancel those
        before they can start after Ctrl-C.
        """
        self._cancelled.set()
        self._executor.shutdown(wait=False, cancel_futures=True)
        return cancel_active()

    def __enter__(self) -> Pool:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.shutdown()

    def _on_done(self, _future: Future[GameOutcome]) -> None:
        self._release()

    def _release(self) -> None:
        with self._lock:
            self._in_flight -= 1
