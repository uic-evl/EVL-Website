"""The set of prebuilt responses, swapped atomically as files are rebuilt.

Small files are built every time their data changes. The large series/<range>.json
files are registered lazily: built on the first request after a change, then served
from memory until the next change, so nobody pays for them unless someone reads them.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from .render import Entry


class _Lazy:
    def __init__(self, build: Callable[[], Entry | None]):
        self.build = build
        self.value: Entry | None = None
        self.lock = threading.Lock()
        self.done = False

    def get(self) -> Entry | None:
        if self.done:
            return self.value
        with self.lock:
            if not self.done:
                self.value = self.build()
                self.done = True
        return self.value


class Publisher:
    def __init__(self) -> None:
        self._entries: dict[str, Entry | _Lazy] = {}
        self._lock = threading.Lock()

    def _swap(self, path: str, item) -> None:
        with self._lock:
            entries = dict(self._entries)
            entries[path] = item
            self._entries = entries  # readers see the old or the new map, never a mix

    def put(self, path: str, entry: Entry) -> None:
        self._swap(path, entry)

    def put_lazy(self, path: str, build: Callable[[], Entry | None]) -> None:
        self._swap(path, _Lazy(build))

    def get(self, path: str) -> Entry | None:
        item = self._entries.get(path)
        if isinstance(item, _Lazy):
            return item.get()
        return item

    def paths(self) -> list[str]:
        return sorted(self._entries)
