"""HTTP server for the prebuilt JSON files.

Exact routes only, GET and HEAD only, no filesystem access, no request logging (so
no client addresses are kept). Bytes are built ahead of time by the sampler, so a
request is a dictionary lookup.
"""

from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .publish import Publisher
from .tiers import RANGES

ROUTES = frozenset(
    ["/now.json", "/procs.json", "/host.json", "/spark.json", "/usage.json", "/services.json", "/daily.json"]
    + [f"/history/{r}.json" for r in RANGES]
    + [f"/series/{r}.json" for r in RANGES]
)


def accepts_gzip(header: str | None) -> bool:
    if not header:
        return False
    for part in header.split(","):
        name, _, params = part.strip().partition(";")
        if name.strip().lower() not in ("gzip", "*"):
            continue
        q = 1.0
        for p in params.split(";"):
            k, _, v = p.strip().partition("=")
            if k.strip().lower() == "q":
                try:
                    q = float(v)
                except ValueError:
                    q = 0.0
        return q > 0
    return False


class Handler(BaseHTTPRequestHandler):
    server_version = "evl-monitor"
    sys_version = ""
    protocol_version = "HTTP/1.1"
    timeout = 10

    # set on the subclass by make_server
    publisher: Publisher
    health = None
    cors_origins: frozenset = frozenset()

    def log_message(self, format, *args):  # noqa: A002 - no access log, no client IPs
        return

    def _common(self, cache_control: str) -> None:
        self.send_header("Cache-Control", cache_control)
        self.send_header("X-Content-Type-Options", "nosniff")
        origin = self.headers.get("Origin")
        if origin and origin in self.cors_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Expose-Headers", "Date, ETag")
            self.send_header("Vary", "Origin, Accept-Encoding")
        else:
            self.send_header("Vary", "Accept-Encoding")

    def _send(self, status: int, body: bytes, cache_control: str, head: bool,
              ctype: str = "application/json", extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self._common(cache_control)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def resolve(self, path: str):
        """(publisher, health, file path) for a request path; fakegw overrides this."""
        return self.publisher, self.health, path

    def _serve(self, head: bool) -> None:
        publisher, health, path = self.resolve(self.path.split("?", 1)[0])
        if publisher is None:
            self._send(502, b'{"error":"bad gateway"}', "no-store", head)
            return
        if path == "/healthz":
            ok, body = health()
            self._send(200 if ok else 503, json.dumps(body, separators=(",", ":")).encode(),
                       "no-store", head)
            return
        if path not in ROUTES:
            self._send(404, b'{"error":"not found"}', "no-store", head)
            return
        entry = publisher.get(path)
        if entry is None:
            self._send(503, b'{"error":"starting"}', "no-store", head, extra={"Retry-After": "5"})
            return
        gz = accepts_gzip(self.headers.get("Accept-Encoding"))
        etag = entry.etag_gz if gz else entry.etag
        inm = self.headers.get("If-None-Match")
        if inm and etag in [t.strip() for t in inm.split(",")]:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Content-Length", "0")
            self._common(entry.cache_control)
            self.end_headers()
            return
        extra = {"ETag": etag}
        if gz:
            extra["Content-Encoding"] = "gzip"
        self._send(200, entry.gz if gz else entry.raw, entry.cache_control, head, extra=extra)

    def do_GET(self):  # noqa: N802
        self._serve(head=False)

    def do_HEAD(self):  # noqa: N802
        self._serve(head=True)

    def _not_allowed(self):
        self._send(405, b'{"error":"method not allowed"}', "no-store", False, extra={"Allow": "GET, HEAD"})

    do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _not_allowed  # noqa: N815


class BoundedServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, handler, max_conn: int):
        self._slots = threading.BoundedSemaphore(max_conn)
        super().__init__(addr, handler)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            try:
                request.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


def make_server(bind: str, port: int, publisher: Publisher, health, cors_origins=(), max_conn: int = 32):
    handler = type("BoundHandler", (Handler,), {
        "publisher": publisher,
        "health": staticmethod(health),
        "cors_origins": frozenset(cors_origins),
    })
    return BoundedServer((bind, port), handler, max_conn)
