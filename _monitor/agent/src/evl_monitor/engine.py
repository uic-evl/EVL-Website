"""Turns 5 s samples into finest-tier buckets and hands closed buckets to the store."""

from __future__ import annotations

import logging
import math

from .store import Acc, Store
from .tiers import Tier

log = logging.getLogger(__name__)


class Engine:
    def __init__(self, store: Store, tiers: tuple[Tier, ...]):
        self.store = store
        self.step = tiers[0].step
        self.open_t: int | None = None
        self.accs: dict[str, Acc] = {}
        last = store.last_bucket()
        # buckets at or before this were written by a previous run
        self.floor = last if last is not None else None

    def add(self, ts: int, values: dict[str, float | None]) -> set[int]:
        """Add one sample. Returns the tiers whose history changed (empty if none)."""
        b = (ts // self.step) * self.step
        if self.floor is not None and b <= self.floor:
            return set()  # clock went back past stored data: drop until it catches up
        changed: set[int] = set()
        if self.open_t is not None and b < self.open_t:
            return changed  # clock stepped back inside this run
        if self.open_t is not None and b > self.open_t:
            changed = self._close(fine_end=b)
        if self.open_t is None or b > self.open_t:
            self.open_t = b
            self.accs = {}
        for key, v in values.items():
            if v is None or isinstance(v, bool) or not math.isfinite(v):
                continue
            acc = self.accs.get(key)
            if acc is None:
                acc = self.accs[key] = Acc()
            acc.add(float(v))
        return changed

    def _close(self, fine_end: int) -> set[int]:
        t = self.open_t
        assert t is not None
        changed = self.store.commit_bucket(t, self.accs, fine_end)
        self.floor = t
        return changed
