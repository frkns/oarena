"""oarena — a local bot league for the Florent Code League (fcode).

Deliberately free of imports: importing :mod:`oarena` must stay cheap so that
``python -m oarena._worker`` and ``oarena --version`` pay no startup cost.
"""

from __future__ import annotations

__version__ = "2.0.0"
