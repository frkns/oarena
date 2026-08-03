"""In-process event bus: the arena's single live feed.

`League` (and anything else holding the bus) calls :meth:`EventBus.emit`; the HTTP
layer turns subscribers into SSE streams and uses :meth:`EventBus.since` to replay
what a reconnecting client missed.

Two properties matter and both are enforced here:

* **Thread safety.** Emission happens on the league's run thread while HTTP
  handler threads subscribe and unsubscribe; one lock guards the sequence
  counter, the ring buffer and the subscriber set.
* **A slow reader can never stall the arena.** Subscriber queues are bounded and
  drop their oldest event on overflow, counting the drop, so `emit()` is always
  non-blocking. A client that sees a gap resyncs with `since()`.

Event types and their payloads are fixed by the web UI; see the contract's
event table (`hello`, `log`, `bot_added`, `bot_changed`, `bot_broken`,
`bot_fixed`, `game_started`, `game_finished`, `status`, `run_started`,
`run_finished`).
"""

from __future__ import annotations

import queue
import threading
import time
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

__all__ = ["Event", "EventBus"]

# How many times emit() retries a full subscriber queue before giving up on the
# new event. Only one emitter runs at a time (the bus lock), so one eviction is
# normally enough; the retries only cover a reader racing us for the slot.
_OFFER_RETRIES = 4


@dataclass(frozen=True)
class Event:
    """One broadcast fact. `seq` is unique and strictly increasing per bus."""

    seq: int
    ts: float
    type: str
    data: dict = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        """Wire form used by the SSE stream and `/api/events`."""
        return {"seq": self.seq, "ts": self.ts, "type": self.type, "data": self.data}


class _SubscriberQueue(queue.Queue):
    """Bounded event queue that evicts its oldest item instead of blocking.

    `dropped` counts events this subscriber lost. A non-zero value (or a gap in
    the `seq` numbers it reads) means the reader fell behind and should resync
    through :meth:`EventBus.since`.
    """

    def __init__(self, maxsize: int) -> None:
        super().__init__(maxsize)
        self.dropped = 0

    def offer(self, event: Event) -> bool:
        """Enqueue without blocking. Returns False if anything had to be dropped."""
        for _ in range(_OFFER_RETRIES):
            try:
                self.put_nowait(event)
                return True
            except queue.Full:
                try:
                    self.get_nowait()
                except queue.Empty:  # a reader drained it first; the slot is free
                    pass
                self.dropped += 1
        self.dropped += 1
        return False


class EventBus:
    """Fan-out of :class:`Event` objects to any number of live subscribers.

    The last `capacity` events are retained so a client can catch up after a
    reconnect. Subscribers receive events published *after* they subscribed;
    everything older comes from `since()`.
    """

    def __init__(self, capacity: int = 2000) -> None:
        self._capacity = max(1, int(capacity))
        self._lock = threading.Lock()
        self._ring: deque[Event] = deque(maxlen=self._capacity)
        self._subs: set[_SubscriberQueue] = set()
        self._seq = 0

    # --- introspection ---------------------------------------------------

    @property
    def last_seq(self) -> int:
        """Sequence number of the most recent event (0 before anything is emitted)."""
        with self._lock:
            return self._seq

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def subscribers(self) -> int:
        with self._lock:
            return len(self._subs)

    # --- publishing ------------------------------------------------------

    def emit(self, type: str, **data: Any) -> Event:
        """Publish an event to the ring buffer and every subscriber. Never blocks."""
        with self._lock:
            self._seq += 1
            event = Event(seq=self._seq, ts=time.time(), type=type, data=data)
            self._ring.append(event)
            for sub in self._subs:
                sub.offer(event)
        return event

    # --- consuming -------------------------------------------------------

    def since(self, seq: int, limit: int = 500) -> list[Event]:
        """Retained events with `seq` strictly greater than the given one.

        Oldest first, at most `limit`. A caller that finds the first returned
        event is not exactly `seq + 1` has fallen off the ring buffer and should
        refetch the full state instead of patching.
        """
        if limit <= 0:
            return []
        with self._lock:
            out: list[Event] = []
            for event in self._ring:
                if event.seq > seq:
                    out.append(event)
                    if len(out) >= limit:
                        break
        return out

    @contextmanager
    def subscribe(self, maxsize: int | None = None) -> Iterator[queue.Queue[Event]]:
        """Yield a queue fed with every event emitted while the block is open.

        The queue is bounded (`maxsize`, defaulting to the bus capacity) and
        drops its oldest entry when a reader falls behind, so a stalled consumer
        slows nobody down. The yielded object exposes a `dropped` counter for
        exactly that case. Unsubscription is automatic on exit.
        """
        size = self._capacity if maxsize is None else max(1, int(maxsize))
        sub = _SubscriberQueue(size)
        with self._lock:
            self._subs.add(sub)
        try:
            yield sub
        finally:
            with self._lock:
                self._subs.discard(sub)
