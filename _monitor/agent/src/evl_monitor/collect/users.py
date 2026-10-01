"""uid to user name, as the host sees it.

1. The host's /etc/passwd, read through the read-only /hostfs mount and re-read when
   its mtime changes (a single-file bind mount would go stale when useradd replaces it).
2. For directory accounts (UIC AD through SSSD), pwd.getpwuid inside the container,
   whose nsswitch says `passwd: sss` and talks to the host's sssd socket. That lookup
   runs on a worker thread with a time budget; until it answers, the uid shows as
   "uid N", and the answer is cached.
3. Otherwise "uid N".
"""

from __future__ import annotations

import os
import pwd
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,32}$")
OK_TTL = 600.0
FAIL_TTL = 60.0


def _fallback(uid: int) -> str:
    return f"uid {uid}"


class UserResolver:
    def __init__(self, hostfs: str, nss: bool = True, strip_domain: bool = True,
                 budget: float = 2.0, lookup=None):
        self.passwd_path = os.path.join(hostfs, "etc/passwd")
        self.nss = nss
        self.strip_domain = strip_domain
        self.budget = budget
        self.lookup = lookup or (lambda uid: pwd.getpwuid(uid).pw_name)
        self._mtime: float | None = None
        self._local: dict[int, str] = {}
        self._cache: dict[int, tuple[float, str | None]] = {}
        self._pending: dict[int, object] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nss")

    def _reload_local(self) -> None:
        try:
            mtime = os.stat(self.passwd_path).st_mtime
        except OSError:
            self._local = {}
            self._mtime = None
            return
        if mtime == self._mtime:
            return
        local: dict[int, str] = {}
        with open(self.passwd_path) as f:
            for line in f:
                parts = line.split(":")
                if len(parts) >= 3 and parts[2].isdigit():
                    local.setdefault(int(parts[2]), parts[0])
        self._local = local
        self._mtime = mtime

    def _clean(self, name: str | None, uid: int) -> str:
        if not name:
            return _fallback(uid)
        if self.strip_domain and "@" in name:
            name = name.split("@", 1)[0]
        return name if NAME_RE.match(name) else _fallback(uid)

    def name(self, uid: int) -> str:
        try:
            self._reload_local()
        except OSError:
            pass
        if uid in self._local:
            return self._clean(self._local[uid], uid)
        if not self.nss:
            return _fallback(uid)
        now = time.monotonic()
        with self._lock:
            hit = self._cache.get(uid)
            if hit and hit[0] > now:
                return self._clean(hit[1], uid)
            fut = self._pending.get(uid)
            if fut is not None:
                return _fallback(uid)  # still resolving: never wait twice for one uid
            fut = self._pool.submit(self._resolve, uid)
            self._pending[uid] = fut
        try:
            return self._clean(fut.result(timeout=self.budget), uid)
        except Exception:  # noqa: BLE001 - timeout or lookup error
            return _fallback(uid)

    def _resolve(self, uid: int) -> str | None:
        try:
            name = self.lookup(uid)
            ttl = OK_TTL
        except Exception:  # noqa: BLE001
            name, ttl = None, FAIL_TTL
        with self._lock:
            self._cache[uid] = (time.monotonic() + ttl, name)
            self._pending.pop(uid, None)
        return name
