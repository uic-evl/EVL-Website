import gzip
import http.client
import json
import socket
import threading
import time

import pytest

from evl_monitor import render, schema
from evl_monitor.publish import Publisher
from evl_monitor.server import accepts_gzip, make_server

from .test_schema import good_now


@pytest.fixture
def served():
    pub = Publisher()
    pub.put("/now.json", render.encode(good_now(), schema.NOW, "public, max-age=2"))
    health = {"ok": True}

    def h():
        return health["ok"], {"ok": health["ok"], "age_s": 1, "seq": 3}

    srv = make_server("127.0.0.1", 0, pub, h, cors_origins=("http://localhost:4000",), max_conn=4)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv.server_address[1], health, srv
    srv.shutdown()
    srv.server_close()


def get(port, path, method="GET", headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.request(method, path, headers=headers or {})
    r = c.getresponse()
    body = r.read()
    c.close()
    return r, body


def test_now_json_plain_and_gzip(served):
    port, _, _ = served
    r, body = get(port, "/now.json")
    assert r.status == 200 and json.loads(body)["id"] == "arcade"
    assert r.getheader("Cache-Control") == "public, max-age=2"
    assert r.getheader("Vary") == "Accept-Encoding"
    assert r.getheader("X-Content-Type-Options") == "nosniff"
    rg, bodyg = get(port, "/now.json", headers={"Accept-Encoding": "gzip"})
    assert rg.getheader("Content-Encoding") == "gzip"
    assert gzip.decompress(bodyg) == body
    assert rg.getheader("ETag") != r.getheader("ETag")


def test_etag_304(served):
    port, _, _ = served
    r, _ = get(port, "/now.json", headers={"Accept-Encoding": "gzip"})
    r2, body2 = get(port, "/now.json", headers={"Accept-Encoding": "gzip", "If-None-Match": r.getheader("ETag")})
    assert r2.status == 304 and body2 == b""


@pytest.mark.parametrize("path, status", [
    ("/etc/passwd", 404), ("/history/2y.json", 404), ("/../now.json", 404),
    ("/now.json?x=1", 200), ("/procs.json", 503), ("/healthz", 200),
])
def test_routes(served, path, status):
    port, _, _ = served
    r, _ = get(port, path)
    assert r.status == status


def test_head_has_no_body(served):
    port, _, _ = served
    r, body = get(port, "/now.json", method="HEAD")
    assert r.status == 200 and body == b"" and int(r.getheader("Content-Length")) > 0


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "OPTIONS"])
def test_other_methods_405(served, method):
    port, _, _ = served
    r, _ = get(port, "/now.json", method=method)
    assert r.status == 405 and r.getheader("Allow") == "GET, HEAD"


def test_cors_only_for_allowed_origin(served):
    port, _, _ = served
    r, _ = get(port, "/now.json", headers={"Origin": "http://localhost:4000"})
    assert r.getheader("Access-Control-Allow-Origin") == "http://localhost:4000"
    assert "Origin" in r.getheader("Vary")
    r2, _ = get(port, "/now.json", headers={"Origin": "https://evil.example"})
    assert r2.getheader("Access-Control-Allow-Origin") is None


def test_healthz_503_when_stale(served):
    port, health, _ = served
    health["ok"] = False
    r, body = get(port, "/healthz")
    assert r.status == 503 and json.loads(body)["ok"] is False


@pytest.mark.parametrize("header, ok", [
    ("gzip", True), ("gzip;q=0", False), ("br, gzip;q=0.5", True), ("identity", False),
    ("*", True), (None, False), ("GZIP", True),
])
def test_accepts_gzip(header, ok):
    assert accepts_gzip(header) is ok


def test_connection_cap(served):
    port, _, srv = served
    held = []
    for _ in range(4):  # max_conn=4, each held open without sending a request
        s = socket.create_connection(("127.0.0.1", port))
        held.append(s)
    time.sleep(0.2)
    extra = socket.create_connection(("127.0.0.1", port))
    extra.settimeout(2)
    extra.sendall(b"GET /now.json HTTP/1.1\r\nHost: x\r\n\r\n")
    try:
        data = extra.recv(100)
    except (ConnectionResetError, TimeoutError):
        data = b""
    assert data == b""  # refused: closed without an answer
    for s in held:
        s.close()
    extra.close()
    time.sleep(0.3)
    r, _ = get(port, "/now.json")
    assert r.status == 200  # slots come back
