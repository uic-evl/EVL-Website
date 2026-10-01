"""A one-route Docker API proxy: python -m evl_monitor.dockerproxy

It holds docker.sock so the agent does not. It listens on a unix socket in a volume
shared only with the agent, accepts only `GET /containers/json` (optionally with an
API version prefix), always asks Docker for exactly `/containers/json?all=1`, and
replies with only the fields in FIELDS: id, names, image, state, status, created,
published ports and the compose project/service labels. Inspect, logs, exec, export
and archive are out of reach, and the agent never sees commands, mounts, other
labels or environment variables.

`--check` connects to the proxy socket and exits 0 if it answers (the healthcheck).
"""

from __future__ import annotations

import http.client
import json
import os
import re
import socket
import socketserver
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler

ALLOWED_PATH = re.compile(r"^(/v1\.\d{1,3})?/containers/json$")
DOCKER_SOCK = os.environ.get("DOCKER_SOCK", "/var/run/docker.sock")
LISTEN = os.environ.get("MONITOR_DOCKER_SOCK", "/run/evl-monitor/docker.sock")
CACHE_SECONDS = 5.0
MAX_UPSTREAM = 8 * 1024 * 1024


class _UnixConn(http.client.HTTPConnection):
    def __init__(self, path: str, timeout: float = 3.0):
        super().__init__("docker", timeout=timeout)
        self._path = path

    def connect(self) -> None:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        s.connect(self._path)
        self.sock = s


KEEP_LABELS = ("com.docker.compose.project", "com.docker.compose.service")
MAX_CONTAINERS = 500


def _ports(raw) -> list[dict]:
    out = []
    for p in raw if isinstance(raw, list) else []:
        if not isinstance(p, dict):
            continue
        entry = {k: p.get(k) for k in ("IP", "PrivatePort", "PublicPort", "Type")}
        if isinstance(entry["PrivatePort"], int):
            out.append(entry)
    return out[:32]


def project(items) -> list[dict]:
    out = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        cid = item.get("Id")
        names = item.get("Names")
        if not (isinstance(cid, str) and isinstance(names, list)):
            continue
        labels = item.get("Labels") if isinstance(item.get("Labels"), dict) else {}
        out.append({
            "Id": cid,
            "Names": [n for n in names if isinstance(n, str)][:4],
            "Image": item.get("Image") if isinstance(item.get("Image"), str) else None,
            "State": item.get("State") if isinstance(item.get("State"), str) else None,
            "Status": item.get("Status") if isinstance(item.get("Status"), str) else None,
            "Created": item.get("Created") if isinstance(item.get("Created"), int) else None,
            "Ports": _ports(item.get("Ports")),
            "Labels": {k: labels[k] for k in KEEP_LABELS if isinstance(labels.get(k), str)},
        })
    return out[:MAX_CONTAINERS]


class Upstream:
    def __init__(self, sock_path: str = DOCKER_SOCK, fetch=None):
        self.sock_path = sock_path
        self.fetch = fetch or self._fetch
        self._lock = threading.Lock()
        self._at = -1e9
        self._body = b"[]"

    def _fetch(self) -> list:
        conn = _UnixConn(self.sock_path)
        try:
            conn.request("GET", "/containers/json?all=1")  # fixed upstream path; client queries are dropped
            resp = conn.getresponse()
            raw = resp.read(MAX_UPSTREAM + 1)
            if resp.status != 200 or len(raw) > MAX_UPSTREAM:
                raise OSError(f"docker answered {resp.status}")
            return json.loads(raw)
        finally:
            conn.close()

    def body(self) -> bytes:
        with self._lock:
            if time.monotonic() - self._at > CACHE_SECONDS:
                self._body = json.dumps(project(self.fetch()), separators=(",", ":")).encode()
                self._at = time.monotonic()
            return self._body


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "evl-monitor-dockerproxy"
    sys_version = ""
    timeout = 5
    upstream: Upstream

    def log_message(self, format, *args):  # noqa: A002
        return

    def address_string(self):
        return "unix"

    def _reply(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        if not ALLOWED_PATH.match(path):
            self._reply(403, b'{"message":"forbidden"}')
            return
        try:
            self._reply(200, self.upstream.body())
        except Exception:  # noqa: BLE001
            self._reply(502, b'{"message":"docker unavailable"}')

    def _forbidden(self):
        self._reply(403, b'{"message":"forbidden"}')

    do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _forbidden  # noqa: N815


class UnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


def serve(listen: str = LISTEN, upstream: Upstream | None = None) -> UnixServer:
    if os.path.exists(listen):
        os.unlink(listen)
    handler = type("BoundProxyHandler", (ProxyHandler,), {"upstream": upstream or Upstream()})
    old = os.umask(0o177)
    try:
        srv = UnixServer(listen, handler)
    finally:
        os.umask(old)
    return srv


def check(listen: str = LISTEN) -> int:
    conn = _UnixConn(listen, timeout=3)
    try:
        conn.request("GET", "/containers/json")
        return 0 if conn.getresponse().status == 200 else 1
    except OSError:
        return 1
    finally:
        conn.close()


def main(argv: list[str]) -> int:
    if "--check" in argv:
        return check()
    srv = serve()
    try:
        srv.serve_forever()
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
