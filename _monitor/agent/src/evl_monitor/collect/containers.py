"""Containers on the host, asked of the docker-proxy over a unix socket.

The agent never sees docker.sock. The proxy answers only GET /containers/json and
returns only the fields dockerproxy.FIELDS keeps (see dockerproxy.py).
"""

from __future__ import annotations

import http.client
import json
import re
import socket
import threading
import time

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
REFRESH = 30.0
MIN_GAP = 5.0


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path: str, timeout: float = 2.0):
        super().__init__("localhost", timeout=timeout)
        self.path = path

    def connect(self) -> None:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        s.connect(self.path)
        self.sock = s


def fetch(path: str, timeout: float = 2.0) -> list[dict]:
    conn = UnixHTTPConnection(path, timeout)
    try:
        conn.request("GET", "/containers/json")
        resp = conn.getresponse()
        body = resp.read(8 * 1024 * 1024)
        if resp.status != 200:
            raise OSError(f"docker-proxy answered {resp.status}")
        return json.loads(body)
    finally:
        conn.close()


class ContainerNames:
    """Cached container list; thread-safe (the sampler and the services thread share it)."""

    def __init__(self, sock_path: str, monotonic=time.monotonic, fetcher=fetch):
        self.sock_path = sock_path
        self.monotonic = monotonic
        self.fetcher = fetcher
        self._items: list[dict] = []
        self._names: dict[str, str] = {}
        self._at = -1e9
        self._lock = threading.Lock()
        self.status = "off" if not sock_path else "unavailable"

    def _refresh(self) -> None:
        self._at = self.monotonic()
        try:
            items = self.fetcher(self.sock_path)
        except Exception:  # noqa: BLE001
            self.status = "unavailable"
            return
        items = [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []
        names = {}
        for item in items:
            cid = item.get("Id")
            raw = (item.get("Names") or [None])[0]
            if isinstance(cid, str) and isinstance(raw, str):
                names[cid] = raw.lstrip("/")
        self._items = items
        self._names = names
        self.status = "ok"

    def _due(self, force_gap: float | None = None) -> None:
        age = self.monotonic() - self._at
        if age > REFRESH or (force_gap is not None and age > force_gap):
            self._refresh()

    def items(self) -> list[dict]:
        if not self.sock_path:
            return []
        with self._lock:
            self._due()
            return list(self._items)

    def count(self) -> int | None:
        """Running containers on the host (None when the proxy is off or down)."""
        if not self.sock_path:
            return None
        with self._lock:
            self._due()
            if self.status != "ok":
                return None
            return sum(1 for i in self._items if i.get("State", "running") == "running")

    def name(self, cid: str | None) -> str | None:
        if cid is None or not self.sock_path:
            return None
        with self._lock:
            self._due(None if cid in self._names else MIN_GAP)
            name = self._names.get(cid)
        if name and NAME_RE.match(name):
            return name
        return cid[:12]  # not a Docker container (e.g. containerd) or not listed yet
