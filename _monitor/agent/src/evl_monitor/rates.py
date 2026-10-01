"""Counter-to-rate conversion over monotonic time."""

from __future__ import annotations


class Rates:
    def __init__(self) -> None:
        self._prev: dict[str, tuple[float, float]] = {}

    def rate(self, key: str, value: float | None, now: float) -> float | None:
        """Per-second rate of a monotonically increasing counter.

        The first reading, a counter that went backwards (reset, wrap, a device that
        vanished and came back) and a zero time step all give None.
        """
        if value is None:
            self._prev.pop(key, None)
            return None
        prev = self._prev.get(key)
        self._prev[key] = (value, now)
        if prev is None:
            return None
        pv, pt = prev
        dt = now - pt
        if dt <= 0 or value < pv:
            return None
        return (value - pv) / dt

    def total_rate(self, prefix: str, counters: dict[str, float], now: float) -> float | None:
        """Sum of per-counter rates; None if no counter has a rate yet."""
        seen = set()
        total = None
        for name, value in counters.items():
            key = f"{prefix}:{name}"
            seen.add(key)
            r = self.rate(key, value, now)
            if r is not None:
                total = (total or 0.0) + r
        for key in [k for k in self._prev if k.startswith(prefix + ":") and k not in seen]:
            del self._prev[key]
        return total
