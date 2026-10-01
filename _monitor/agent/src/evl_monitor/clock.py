"""Wall and monotonic time, injectable so tests can move time by hand."""

from __future__ import annotations

import threading
import time


class RealClock:
    def time(self) -> float:
        return time.time()

    def monotonic(self) -> float:
        return time.monotonic()

    def wait_until(self, wall: float, stop: threading.Event) -> bool:
        """Sleep until `wall` (epoch seconds). Returns False if `stop` was set."""
        delay = wall - time.time()
        if delay > 0:
            return not stop.wait(delay)
        return not stop.is_set()


class FakeClock:
    def __init__(self, start: float = 1_790_000_000.0):
        self._t = float(start)
        self._m = 1000.0

    def time(self) -> float:
        return self._t

    def monotonic(self) -> float:
        return self._m

    def advance(self, seconds: float) -> None:
        self._t += seconds
        self._m += seconds

    def set_wall(self, wall: float) -> None:
        """Jump the wall clock only (NTP step); monotonic keeps going."""
        self._t = float(wall)

    def wait_until(self, wall: float, stop: threading.Event) -> bool:
        if wall > self._t:
            self.advance(wall - self._t)
        return not stop.is_set()
