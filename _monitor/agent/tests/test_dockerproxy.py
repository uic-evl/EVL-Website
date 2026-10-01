import json
import os
import shutil
import tempfile
import threading

import pytest

from evl_monitor import dockerproxy
from evl_monitor.collect.containers import UnixHTTPConnection

DOCKER_REPLY = [{
    "Id": "a" * 64, "Names": ["/nim-gemma4"], "Image": "nvcr.io/nim/google/gemma",
    "State": "running", "Status": "Up 3 hours (healthy)", "Created": 1789000000,
    "Ports": [{"IP": "127.0.0.1", "PrivatePort": 8000, "PublicPort": 8000, "Type": "tcp"}],
    "Command": "serve --api-key=SECRET",
    "Labels": {"token": "SECRET", "com.docker.compose.project": "llm", "com.docker.compose.service": "nim"},
    "Mounts": [{"Source": "/home/alice"}], "Env": ["HF_TOKEN=SECRET"],
}]

PROJECTED = [{
    "Id": "a" * 64, "Names": ["/nim-gemma4"], "Image": "nvcr.io/nim/google/gemma",
    "State": "running", "Status": "Up 3 hours (healthy)", "Created": 1789000000,
    "Ports": [{"IP": "127.0.0.1", "PrivatePort": 8000, "PublicPort": 8000, "Type": "tcp"}],
    "Labels": {"com.docker.compose.project": "llm", "com.docker.compose.service": "nim"},
}]


@pytest.fixture
def proxy():
    # AF_UNIX paths are capped near 104 bytes on macOS; pytest's tmp_path is longer
    d = tempfile.mkdtemp(prefix="evlm")
    path = os.path.join(d, "p.sock")
    calls = []

    def fetch():
        calls.append(1)
        return DOCKER_REPLY
    srv = dockerproxy.serve(path, dockerproxy.Upstream(fetch=fetch))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield path, calls
    srv.shutdown()
    srv.server_close()
    shutil.rmtree(d, ignore_errors=True)


def ask(path, method, url):
    c = UnixHTTPConnection(path)
    c.request(method, url)
    r = c.getresponse()
    body = r.read()
    c.close()
    return r.status, body


@pytest.mark.parametrize("url", ["/containers/json", "/v1.45/containers/json", "/containers/json?all=1"])
def test_allowed_and_projected(proxy, url):
    path, _ = proxy
    status, body = ask(path, "GET", url)
    assert status == 200
    assert json.loads(body) == PROJECTED
    assert b"SECRET" not in body and b"alice" not in body


@pytest.mark.parametrize("method, url", [
    ("GET", "/containers/" + "a" * 64 + "/json"),
    ("GET", "/containers/abc/logs"),
    ("GET", "/info"),
    ("POST", "/containers/json"),
    ("DELETE", "/containers/abc"),
    ("GET", "/v1.45/containers/json/../abc/json"),
])
def test_everything_else_forbidden(proxy, method, url):
    path, _ = proxy
    status, _ = ask(path, method, url)
    assert status == 403


def test_upstream_is_cached(proxy):
    path, calls = proxy
    for _ in range(5):
        ask(path, "GET", "/containers/json")
    assert len(calls) == 1


def test_socket_is_private(proxy):
    path, _ = proxy
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"


def test_projection_drops_junk():
    out = dockerproxy.project([{"Id": 1}, "x", {"Id": "b", "Names": ["/n", 3], "Ports": ["junk", {"PrivatePort": "x"}]}])
    assert out == [{"Id": "b", "Names": ["/n"], "Image": None, "State": None, "Status": None,
                    "Created": None, "Ports": [], "Labels": {}}]
    assert dockerproxy.project({"message": "err"}) == []
