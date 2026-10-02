"""The hub: polls every server's agent gently and serves what it cached.

    python -m evl_monitor.hub            (runs on arcade, port 6161, see _monitor/hub/)
    python -m evl_monitor.hub --check    (healthcheck: exit 0 while polling)

The page talks only to the hub, so the servers see a few small requests a minute from
one place, however many people have the page open:

- background: now.json every 15 s, services.json every 2 min, daily.json every 15 min,
  host.json and spark.json every 10 min;
- on demand (when someone opens a server): procs, history, series and usage files,
  cached for the agent's own max-age (at least 10 s);
- one request at a time per server, conditional (ETag) and gzip'ed, 3 s timeout;
- an unreachable server is retried after 15, 30, 60, 120, then every 300 s.

Every payload is checked against the agent's closed schema and its id before it is
cached, so the page only ever sees what the agent is allowed to publish.
"""

from __future__ import annotations

import gzip
import http.client
import json
import logging
import math
import os
import re
import socket
import ssl
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from . import __version__, render, schema
from .check import FILES
from .server import BoundedServer, Handler

log = logging.getLogger("evl_monitor.hub")

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
FQDN_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,252}$")

BACKGROUND = {"now.json": 15, "services.json": 120, "daily.json": 900, "host.json": 600, "spark.json": 600}
ON_DEMAND_FLOOR = 10
BACKOFF = (15, 30, 60, 120, 300)
TIMEOUT = 3.0
MAX_BYTES = 8 * 1024 * 1024
HOSTS_RELOAD = 30.0
# the site, plus a local Jekyll preview (the data is not secret, and nothing sends credentials)
DEFAULT_CORS = ("https://www.evl.uic.edu,https://www-new.evl.uic.edu,"
                "http://localhost:4000,http://127.0.0.1:4000,http://localhost:8080,http://127.0.0.1:8080")

MAX_AGE_RE = re.compile(r"max-age=(\d+)")


@dataclass
class HostEntry:
    id: str
    name: str
    group: str
    fqdn: str
    status: str  # live | planned
    port: int = 9877


@dataclass
class Cached:
    entry: render.Entry
    payload: dict
    etag: str | None  # the agent's ETag for its gzip variant
    fetched: float  # monotonic
    max_age: int


@dataclass
class HostState:
    entry: HostEntry
    cache: dict[str, Cached] = field(default_factory=dict)
    due: dict[str, float] = field(default_factory=dict)
    failures: int = 0
    retry_at: float = 0.0
    last_ok: int | None = None  # epoch seconds
    error: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)
    upstream_requests: int = 0


class FetchError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code  # one of schema.HUB_ERROR


# host list ---------------------------------------------------------------------


def load_hosts(path: str, allowed_suffix: str = ".evl.uic.edu", port: int = 9877) -> list[HostEntry]:
    """Hosts from the site's _data/monitor.yml, in page order (by group)."""
    import yaml

    with open(path) as f:
        data = yaml.safe_load(f) or {}
    hosts = data.get("hosts") or {}
    out = []
    for g in data.get("groups") or []:
        for hid in g.get("hosts") or []:
            h = hosts.get(hid) or {}
            fqdn = str(h.get("fqdn", "")).lower()
            if not ID_RE.match(str(hid)) or not FQDN_RE.match(fqdn):
                log.warning("skipping host %r: bad id or name", hid)
                continue
            if allowed_suffix and not fqdn.endswith(allowed_suffix):
                log.warning("skipping host %r: %s is not under %s", hid, fqdn, allowed_suffix)
                continue
            out.append(HostEntry(
                id=str(hid), name=render._printable(h.get("name") or hid, 64) or str(hid),
                group=render._printable(g.get("name") or "", 64) or "",
                fqdn=fqdn, status="live" if h.get("status") == "live" else "planned", port=port))
    return out


# upstream ------------------------------------------------------------------------


def fetch_http(host: HostEntry, file: str, etag: str | None) -> tuple[int, bytes, dict]:
    """GET http://<fqdn>:<port>/<file>; returns (status, body, headers). Raises FetchError."""
    conn = http.client.HTTPConnection(host.fqdn, host.port, timeout=TIMEOUT)
    headers = {"Accept-Encoding": "gzip", "User-Agent": f"evl-monitor-hub/{__version__}"}
    if etag:
        headers["If-None-Match"] = etag
    try:
        conn.request("GET", "/" + file, headers=headers)
        resp = conn.getresponse()
        body = resp.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise FetchError("bad_payload")
        if resp.getheader("Content-Encoding") == "gzip" and body:
            body = gzip.decompress(body)
        return resp.status, body, {k.lower(): v for k, v in resp.getheaders()}
    except socket.gaierror as exc:
        raise FetchError("dns") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise FetchError("timeout") from exc
    except (OSError, http.client.HTTPException) as exc:
        raise FetchError("unreachable") from exc
    finally:
        conn.close()


# the hub ---------------------------------------------------------------------------


class Hub:
    def __init__(self, hosts_provider, fetcher=fetch_http, monotonic=time.monotonic, wall=time.time,
                 now_seconds: int = BACKGROUND["now.json"], workers: int = 4):
        self.hosts_provider = hosts_provider
        self.fetcher = fetcher
        self.monotonic = monotonic
        self.wall = wall
        self.schedule = dict(BACKGROUND, **{"now.json": now_seconds})
        self.states: dict[str, HostState] = {}
        self.order: list[str] = []
        self._hosts_at = -math.inf
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="hub-fetch")
        self._overview: render.Entry | None = None
        self._dirty = True
        self.last_round: float | None = None

    # hosts -------------------------------------------------------------------

    def refresh_hosts(self, force: bool = False) -> None:
        now = self.monotonic()
        if not force and now - self._hosts_at < HOSTS_RELOAD:
            return
        self._hosts_at = now
        try:
            entries = self.hosts_provider()
        except Exception:  # noqa: BLE001 - keep the last good list
            log.exception("could not read the host list; keeping the previous one")
            return
        with self._lock:
            states = {}
            for e in entries:
                old = self.states.get(e.id)
                if old is not None and old.entry == e:
                    states[e.id] = old
                else:
                    states[e.id] = HostState(e)
            self.states = states
            self.order = [e.id for e in entries]
            self._dirty = True

    # fetching -------------------------------------------------------------------

    def _fetch(self, st: HostState, file: str) -> Cached:
        """One upstream request (caller holds st.lock). Updates health; raises FetchError."""
        old = st.cache.get(file)
        st.upstream_requests += 1
        try:
            status, body, headers = self.fetcher(st.entry, file, old.etag if old else None)
            if status == 304 and old is not None:
                old.fetched = self.monotonic()
                cached = old
            elif status != 200:
                raise FetchError("http_error")
            else:
                try:
                    payload = json.loads(body)
                except ValueError as exc:
                    raise FetchError("bad_payload") from exc
                if not isinstance(payload, dict) or payload.get("id") != st.entry.id:
                    raise FetchError("bad_payload")
                cc = headers.get("cache-control", "")
                m = MAX_AGE_RE.search(cc)
                max_age = int(m.group(1)) if m else ON_DEMAND_FLOOR
                try:
                    entry = render.encode(payload, FILES[file], f"public, max-age={max(2, min(max_age, 3600))}")
                except render.RenderError as exc:
                    raise FetchError("bad_payload") from exc
                cached = Cached(entry, payload, headers.get("etag"), self.monotonic(), max_age)
                st.cache[file] = cached
        except FetchError as exc:
            st.failures += 1
            st.error = exc.code
            st.retry_at = self.monotonic() + BACKOFF[min(st.failures - 1, len(BACKOFF) - 1)]
            self._dirty = True
            raise
        st.failures = 0
        st.error = None
        st.retry_at = 0.0
        st.last_ok = int(self.wall())
        if file in ("now.json", "daily.json"):
            self._dirty = True
        return cached

    def _poll_host(self, st: HostState) -> None:
        if not st.lock.acquire(blocking=False):
            return  # a viewer's request is already talking to this host
        try:
            now = self.monotonic()
            if now < st.retry_at:
                return
            for file, every in self.schedule.items():
                if now < st.due.get(file, 0.0):
                    continue
                try:
                    self._fetch(st, file)
                except FetchError:
                    return  # back off; try again later
                st.due[file] = self.monotonic() + every
        finally:
            st.lock.release()

    def poll_once(self, wait: bool = True) -> None:
        self.refresh_hosts()
        with self._lock:
            live = [self.states[i] for i in self.order if self.states[i].entry.status == "live"]
        futures = [self._pool.submit(self._poll_host, st) for st in live]
        if wait:
            for f in futures:
                f.result()
        self.last_round = self.monotonic()

    def get(self, host_id: str, file: str) -> tuple[render.Entry | None, bool]:
        """A cached file for a viewer: (entry or None, stale). Fetches on demand when needed."""
        with self._lock:
            st = self.states.get(host_id)
        if st is None or st.entry.status != "live" or file not in FILES:
            return None, False
        cached = st.cache.get(file)
        if file in self.schedule:  # background files are served as cached
            return (cached.entry if cached else None), bool(cached) and st.failures > 0

        def fresh(c: Cached | None) -> bool:
            return c is not None and self.monotonic() - c.fetched < max(c.max_age, ON_DEMAND_FLOOR)

        if fresh(cached):
            return cached.entry, False
        with st.lock:  # one request at a time per host; concurrent viewers wait here
            cached = st.cache.get(file)
            if fresh(cached):
                return cached.entry, False  # another viewer just fetched it
            if self.monotonic() < st.retry_at:
                return (cached.entry if cached else None), cached is not None
            try:
                return self._fetch(st, file).entry, False
            except FetchError:
                return (cached.entry if cached else None), cached is not None

    # overview --------------------------------------------------------------------

    def _status(self, st: HostState, now_payload: dict | None) -> tuple[str, int | None]:
        if st.entry.status != "live":
            return "planned", None
        age = None
        if now_payload is not None:
            age = max(0, int(self.wall() - now_payload["ts"]))
        if now_payload is None:
            return ("offline" if st.failures else "connecting"), age
        if st.failures >= 2:
            return "offline", age
        stale_after = 3 * max(self.schedule["now.json"], int(now_payload.get("interval", 5)))
        return ("stale" if age is not None and age > stale_after else "live"), age

    def overview(self) -> render.Entry:
        with self._lock:
            if self._overview is not None and not self._dirty:
                return self._overview
            hosts = []
            for hid in self.order:
                st = self.states[hid]
                now_c = st.cache.get("now.json")
                daily_c = st.cache.get("daily.json")
                now_p = now_c.payload if now_c else None
                status, age = self._status(st, now_p)
                hosts.append({
                    "id": hid, "name": st.entry.name, "group": st.entry.group, "status": status,
                    "age_s": age, "last_ok": st.last_ok, "error": st.error if st.entry.status == "live" else None,
                    "now": now_p, "daily": daily_c.payload if daily_c else None,
                })
            payload = {"v": 1, "ts": int(self.wall()), "hub": __version__,
                       "now_seconds": self.schedule["now.json"], "hosts": hosts}
            self._overview = render.encode(payload, schema.OVERVIEW, "public, max-age=5")
            self._dirty = False
            return self._overview

    def mark_dirty(self) -> None:
        self._dirty = True

    def health(self) -> tuple[bool, dict]:
        age = None if self.last_round is None else self.monotonic() - self.last_round
        ok = age is not None and age < 60
        with self._lock:
            hosts = len(self.order)
        return ok, {"ok": ok, "age_s": None if age is None else int(age), "hosts": hosts}

    def run(self, stop: threading.Event) -> None:
        while not stop.is_set():
            try:
                self.poll_once()
                self.mark_dirty()  # ages move on even without new data
            except Exception:  # noqa: BLE001
                log.exception("poll round failed")
            stop.wait(1.0)


# HTTP / HTTPS ---------------------------------------------------------------------

PATH_RE = re.compile(r"^/(?P<id>[a-z0-9][a-z0-9-]{0,31})/(?P<file>[a-z0-9/]{1,24}\.json)$")


class HubHandler(Handler):
    hub: Hub

    def _serve(self, head: bool) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            ok, body = self.hub.health()
            self._send(200 if ok else 503, json.dumps(body, separators=(",", ":")).encode(), "no-store", head)
            return
        if path == "/overview.json":
            self.serve_entry(self.hub.overview(), head)
            return
        m = PATH_RE.match(path)
        if not m or m["file"] not in FILES:
            self._send(404, b'{"error":"not found"}', "no-store", head)
            return
        entry, stale = self.hub.get(m["id"], m["file"])
        if entry is None:
            st = self.hub.states.get(m["id"])
            if st is not None and st.entry.status == "live":
                self._send(502, b'{"error":"not available"}', "no-store", head)
            else:
                self._send(404, b'{"error":"not found"}', "no-store", head)  # unknown or planned
            return
        self.serve_entry(entry, head, {"X-Monitor-Stale": "1"} if stale else None)


class TLSServer(BoundedServer):
    """HTTPS with the handshake in the worker thread and the certificate reloaded on renewal."""

    def __init__(self, addr, handler, max_conn: int, cert: str, key: str):
        self.cert, self.key = cert, key
        self._ctx: ssl.SSLContext | None = None
        self._ctx_stamp: tuple | None = None
        self._ctx_lock = threading.Lock()
        self.context()  # fail fast on a bad certificate
        super().__init__(addr, handler, max_conn)

    def context(self) -> ssl.SSLContext:
        try:
            stamp = (os.stat(self.cert).st_mtime, os.stat(self.key).st_mtime)
        except OSError:
            if self._ctx is None:
                raise
            return self._ctx  # files briefly missing during a renewal: keep serving
        with self._ctx_lock:
            if self._ctx is None or stamp != self._ctx_stamp:
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                ctx.minimum_version = ssl.TLSVersion.TLSv1_2
                try:
                    ctx.load_cert_chain(self.cert, self.key)
                except (ssl.SSLError, OSError):
                    if self._ctx is None:
                        raise  # no certificate at all: fail at start
                    # a half-written renewal (new certificate, old key): keep the working pair
                    log.warning("could not load the renewed certificate yet; keeping the previous one")
                    return self._ctx
                self._ctx, self._ctx_stamp = ctx, stamp
            return self._ctx

    def finish_request(self, request, client_address):
        request.settimeout(10)
        try:
            tls = self.context().wrap_socket(request, server_side=True)
        except (ssl.SSLError, OSError):
            return
        try:
            self.RequestHandlerClass(tls, client_address, self)
        finally:
            try:
                tls.close()
            except OSError:
                pass


def make_hub_server(hub: Hub, bind: str, port: int, cors_origins=(), cert: str = "", key: str = "",
                    max_conn: int = 64):
    handler = type("BoundHubHandler", (HubHandler,), {"hub": hub, "cors_origins": frozenset(cors_origins)})
    if cert and key:
        return TLSServer((bind, port), handler, max_conn, cert, key)
    return BoundedServer((bind, port), handler, max_conn)


# entry point ------------------------------------------------------------------------


def _env(name: str, default: str = "") -> str:
    """A setting; empty counts as unset (compose passes `${X:-}` as an empty string)."""
    return (os.environ.get(name, "").strip() or default).strip()


def check() -> int:
    port = int(_env("HUB_PORT", "6161"))
    scheme = "https" if _env("HUB_TLS_CERT") else "http"
    ctx = ssl.create_default_context()
    ctx.check_hostname = False  # local healthcheck; the certificate names the public host
    ctx.verify_mode = ssl.CERT_NONE
    conn = (http.client.HTTPSConnection("127.0.0.1", port, timeout=5, context=ctx) if scheme == "https"
            else http.client.HTTPConnection("127.0.0.1", port, timeout=5))
    try:
        conn.request("GET", "/healthz")
        return 0 if conn.getresponse().status == 200 else 1
    except OSError:
        return 1
    finally:
        conn.close()


def main(argv: list[str]) -> int:
    if "--check" in argv:
        return check()
    logging.basicConfig(level=_env("HUB_LOG_LEVEL", "WARNING").upper(),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    hosts_file = _env("HUB_HOSTS", "/config/monitor.yml")
    suffix = "" if _env("HUB_DEV") in ("1", "true") else ".evl.uic.edu"
    agent_port = int(_env("HUB_AGENT_PORT", "9877"))
    hub = Hub(lambda: load_hosts(hosts_file, suffix, agent_port), now_seconds=int(_env("HUB_NOW_SECONDS", "15")))
    hub.refresh_hosts(force=True)
    # compose passes an empty value when unset: empty means the default list
    cors = [o for o in (_env("HUB_CORS_ORIGINS") or DEFAULT_CORS).split(",") if o]
    server = make_hub_server(hub, _env("HUB_BIND", "0.0.0.0"), int(_env("HUB_PORT", "6161")), cors,
                             _env("HUB_TLS_CERT"), _env("HUB_TLS_KEY"))
    threading.Thread(target=server.serve_forever, name="http", daemon=True).start()
    stop = threading.Event()
    import signal

    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    hub.run(stop)
    server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
