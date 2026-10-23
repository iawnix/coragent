"""A bounded observation shares one deadline across its subprocess requests."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import math
import signal
import time


_DEADLINE = ContextVar("job_observation_deadline", default=None)


class ObservationTimeout(Exception):
    """Observation failed; this says nothing about the scientific Job outcome."""


@contextmanager
def observation_deadline(seconds):
    seconds = float(seconds)
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("observation timeout must be positive and finite")
    deadline = time.monotonic() + seconds
    existing = _DEADLINE.get()
    token = _DEADLINE.set(min(existing, deadline) if existing is not None else deadline)
    try:
        yield
    finally:
        _DEADLINE.reset(token)


def remaining_timeout(command, timeout):
    deadline = _DEADLINE.get()
    if deadline is None:
        return timeout
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ObservationTimeout("job_observation_timed_out")
    return min(timeout, remaining)


def observation_timeout(error):
    if _DEADLINE.get() is not None:
        return ObservationTimeout("job_observation_timed_out")
    return error


@contextmanager
def cancel_observation_on_signal():
    """Unwind subprocess cleanup when the supervising worker stops the CLI."""
    def cancel(signum, _frame):
        # Suppress repeated termination while subprocess groups are reaped.
        for watched in previous:
            signal.signal(watched, signal.SIG_IGN)
        raise SystemExit(128 + signum)

    previous = {watched: signal.getsignal(watched)
                for watched in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
    for watched in previous:
        signal.signal(watched, cancel)
    try:
        yield
    finally:
        for watched, handler in previous.items():
            signal.signal(watched, handler)
