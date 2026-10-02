"""The hub: gentle polling, caching, validation, the overview, CORS and HTTPS."""

import gzip
import http.client
import json
import os
import shutil
import ssl
import subprocess
import threading
import time

import pytest

from evl_monitor import fake, render, schema
from evl_monitor.agent import Agent
from evl_monitor.clock import FakeClock
from evl_monitor.config import Config
from evl_monitor.hub import BACKGROUND, FetchError, HostEntry, Hub, load_hosts, make_hub_server
from evl_monitor.publish import Publisher
from evl_monitor.store import Store

from .conftest import env

# fake agents ---------------------------------------------------------------------


class Agents:
    """In-process fake agents answering like the HTTP fetcher, with request counts."""

    def __init__(self, tmp_path, ids, clock):
        self.clock = clock
        self.pubs = {}
        self.calls: dict[str, list[str]] = {i: [] for i in ids}
        self.down: set[str] = set()
        self.tamper = None
        for i in ids:
            cfg = Config.from_env(env(MONITOR_ID=i, MONITOR_FAKE="1", MONITOR_MOUNTS="root:/"))
            store = Store(str(tmp_path / f"{i}.db"), cfg.tiers)
            pub = Publisher()
            col = fake.FakeCollectors(cfg, clock)
            a = Agent(cfg, clock, col, store, pub)
            a.startup()
            col.start_services(a.publish_services, a.gpu_use)
            for _ in range(3):
                clock.advance(1)
                a.tick(int(clock.time()))
            self.pubs[i] = pub

    def __call__(self, host: HostEntry, file: str, etag):
        self.calls[host.id].append(file)
        if host.id in self.down:
            raise FetchError("unreachable")
        e = self.pubs[host.id].get("/" + file)
        if e is None:
            return 503, b"", {}
        if etag == e.etag_gz:
            return 304, b"", {"etag": e.etag_gz}
        body = e.raw
        if self.tamper:
            body = self.tamper(json.loads(body))
        return 200, body, {"etag": e.etag_gz, "cache-control": e.cache_control}


class Mono:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def make_hub(tmp_path, ids=("a", "b"), planned=("p",)):
    clock = FakeClock(1_790_000_000)
    agents = Agents(tmp_path, ids, clock)
    mono = Mono()
    entries = [HostEntry(i, i.upper(), "G", f"{i}.evl.uic.edu", "live") for i in ids]
    entries += [HostEntry(p, p.upper(), "G", f"{p}.evl.uic.edu", "planned") for p in planned]
    hub = Hub(lambda: entries, fetcher=agents, monotonic=mono, wall=clock.time)
    hub.refresh_hosts(force=True)
    return hub, agents, mono, clock


def overview(hub):
    return json.loads(hub.overview().raw)


# host list -----------------------------------------------------------------------


def test_load_hosts(tmp_path):
    p = tmp_path / "monitor.yml"
    p.write_text("""
groups:
  - {id: g1, name: "DOCC / ARCADE", hosts: [arcade, evil, bad_id]}
  - {id: g2, name: SAGE3, hosts: [sage200, later]}
hosts:
  arcade: {name: ARCADE, fqdn: arcade.evl.uic.edu, status: live}
  evil: {name: Evil, fqdn: evil.example.com, status: live}
  bad_id: {name: X, fqdn: x.evl.uic.edu, status: live}
  sage200: {name: SAGE200, fqdn: sage200.evl.uic.edu, status: live}
  later: {name: Later, fqdn: later.evl.uic.edu, status: planned}
""")
    hosts = load_hosts(str(p))
    assert [(h.id, h.status, h.group) for h in hosts] == [
        ("arcade", "live", "DOCC / ARCADE"), ("sage200", "live", "SAGE3"), ("later", "planned", "SAGE3")]


def test_host_list_reload_keeps_state(tmp_path):
    hub, agents, mono, _ = make_hub(tmp_path)
    hub.poll_once()
    before = hub.states["a"]
    mono.t += 31
    hub.refresh_hosts()
    assert hub.states["a"] is before  # unchanged entry keeps its cache


# schedule, backoff, validation -------------------------------------------------------


def test_first_round_fetches_background_files_once(tmp_path):
    hub, agents, mono, _ = make_hub(tmp_path)
    hub.poll_once()
    assert sorted(agents.calls["a"]) == sorted(BACKGROUND)
    assert "p" not in agents.calls  # planned hosts are never polled
    mono.t += 10
    hub.poll_once()
    assert len(agents.calls["a"]) == len(BACKGROUND)  # nothing due yet
    mono.t += 5
    hub.poll_once()
    assert agents.calls["a"][-1] == "now.json" and len(agents.calls["a"]) == len(BACKGROUND) + 1


def test_background_load_per_host_is_gentle_with_many_viewers(tmp_path):
    hub, agents, mono, clock = make_hub(tmp_path, ids=("a",), planned=())
    hub.poll_once()
    agents.calls["a"].clear()
    for _ in range(4 * 60):  # four minutes, one hub round per second
        mono.t += 1
        clock.advance(1)
        hub.poll_once()
        for _ in range(20):  # twenty open pages reading the overview
            hub.overview()
    per_minute = len(agents.calls["a"]) / 4
    assert per_minute <= 6, agents.calls["a"]


def test_backoff_and_recovery(tmp_path):
    hub, agents, mono, _ = make_hub(tmp_path)
    hub.poll_once()
    agents.down.add("a")
    mono.t += 15
    hub.poll_once()
    assert hub.states["a"].failures == 1 and hub.states["a"].error == "unreachable"
    n = len(agents.calls["a"])
    mono.t += 10
    hub.poll_once()
    assert len(agents.calls["a"]) == n  # still backing off (15 s)
    mono.t += 6
    hub.poll_once()
    assert hub.states["a"].failures == 2
    assert {h["id"]: h["status"] for h in overview(hub)["hosts"]}["a"] == "offline"
    for wait in (30, 60, 120, 300, 300):
        mono.t += wait + 1
        hub.poll_once()
    assert len(agents.calls["a"]) == n + 6  # one attempt per backoff step, never a burst
    agents.down.clear()
    mono.t += 301
    hub.poll_once()
    assert hub.states["a"].failures == 0
    assert {h["id"]: h["status"] for h in overview(hub)["hosts"]}["a"] == "live"


@pytest.mark.parametrize("tamper", [
    lambda p: dict(p, id="someone-else"),
    lambda p: dict(p, cmdline="python serve.py --key=SECRET"),
    lambda p: "not an object",
])
def test_payloads_failing_the_schema_are_rejected(tmp_path, tamper):
    hub, agents, mono, _ = make_hub(tmp_path, ids=("a",), planned=())
    agents.tamper = lambda p: json.dumps(tamper(p)).encode()
    hub.poll_once()
    st = hub.states["a"]
    assert st.error == "bad_payload" and not st.cache
    assert b"SECRET" not in hub.overview().raw


# on-demand files -----------------------------------------------------------------------


def test_on_demand_cache_and_floor(tmp_path):
    hub, agents, mono, _ = make_hub(tmp_path, ids=("a",), planned=())
    entry, stale = hub.get("a", "history/24h.json")
    assert entry is not None and not stale
    hub.get("a", "history/24h.json")
    assert agents.calls["a"].count("history/24h.json") == 1  # max-age 60 s
    mono.t += 61
    hub.get("a", "history/24h.json")
    assert agents.calls["a"].count("history/24h.json") == 2
    hub.get("a", "procs.json")
    mono.t += 5  # procs max-age is 2 s, but the hub's floor is 10 s
    hub.get("a", "procs.json")
    assert agents.calls["a"].count("procs.json") == 1


def test_concurrent_viewers_share_one_fetch(tmp_path):
    hub, agents, mono, _ = make_hub(tmp_path, ids=("a",), planned=())
    slow = agents.__call__

    def slow_fetch(host, file, etag):
        time.sleep(0.2)
        return slow(host, file, etag)
    hub.fetcher = slow_fetch
    threads = [threading.Thread(target=hub.get, args=("a", "series/7d.json")) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert agents.calls["a"].count("series/7d.json") == 1


def test_stale_copy_served_when_the_agent_dies(tmp_path):
    hub, agents, mono, _ = make_hub(tmp_path, ids=("a",), planned=())
    hub.get("a", "history/1h.json")
    agents.down.add("a")
    mono.t += 30
    entry, stale = hub.get("a", "history/1h.json")
    assert entry is not None and stale


def test_unknown_files_and_hosts(tmp_path):
    hub, *_ = make_hub(tmp_path)
    assert hub.get("nosuch", "now.json") == (None, False)
    assert hub.get("a", "../../etc/passwd") == (None, False)
    assert hub.get("p", "now.json") == (None, False)  # planned


# overview ----------------------------------------------------------------------------------


def test_overview_states(tmp_path):
    hub, agents, mono, clock = make_hub(tmp_path)
    o = overview(hub)
    schema.validate(schema.OVERVIEW, o)
    assert {h["id"]: h["status"] for h in o["hosts"]} == {"a": "connecting", "b": "connecting", "p": "planned"}
    hub.poll_once()
    o = overview(hub)
    schema.validate(schema.OVERVIEW, o)
    by = {h["id"]: h for h in o["hosts"]}
    assert by["a"]["status"] == "live" and by["a"]["now"]["id"] == "a" and by["a"]["daily"]["id"] == "a"
    assert by["p"]["now"] is None and by["p"]["status"] == "planned"
    clock.advance(120)  # the agent's sample gets old while the hub still reaches it
    hub.mark_dirty()
    assert {h["id"]: h["status"] for h in overview(hub)["hosts"]}["a"] == "stale"


# over HTTP and HTTPS ------------------------------------------------------------------------


def serve(hub, **kw):
    srv = make_hub_server(hub, "127.0.0.1", 0, ("https://www.evl.uic.edu",), **kw)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def get(port, path, headers=None, context=None):
    c = (http.client.HTTPSConnection("127.0.0.1", port, timeout=5, context=context) if context
         else http.client.HTTPConnection("127.0.0.1", port, timeout=5))
    c.request("GET", path, headers=headers or {})
    r = c.getresponse()
    body = r.read()
    c.close()
    return r, body


def test_http_routes_and_cors(tmp_path):
    hub, agents, mono, _ = make_hub(tmp_path)
    hub.poll_once()
    srv = serve(hub)
    port = srv.server_address[1]
    try:
        r, body = get(port, "/overview.json", {"Origin": "https://www.evl.uic.edu", "Accept-Encoding": "gzip"})
        assert r.status == 200 and r.getheader("Access-Control-Allow-Origin") == "https://www.evl.uic.edu"
        assert json.loads(gzip.decompress(body))["hosts"][0]["id"] == "a"
        r, _ = get(port, "/overview.json", {"Origin": "https://evil.example"})
        assert r.getheader("Access-Control-Allow-Origin") is None
        r, body = get(port, "/a/history/1h.json")
        assert r.status == 200 and json.loads(body)["range"] == "1h"
        assert get(port, "/nosuch/now.json")[0].status == 404
        assert get(port, "/p/now.json")[0].status == 404  # planned: nothing is broken
        assert get(port, "/a/etc/passwd.json")[0].status == 404
        agents.down.add("b")
        mono.t += 100
        assert get(port, "/b/series/1y.json")[0].status == 502
        assert get(port, "/healthz")[0].status == 503  # no poll round for 100 s
        hub.poll_once()
        assert get(port, "/healthz")[0].status == 200
    finally:
        srv.shutdown()
        srv.server_close()


def _cert(dirpath, cn):
    openssl = shutil.which("openssl")
    assert openssl, "the HTTPS tests need the openssl command"
    subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
                    "-keyout", str(dirpath / "key.pem"), "-out", str(dirpath / "cert.pem"),
                    "-subj", f"/CN={cn}", "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"],
                   check=True, capture_output=True)


def test_https_and_certificate_reload(tmp_path):
    _cert(tmp_path, "first")
    hub, *_ = make_hub(tmp_path)
    hub.poll_once()
    srv = serve(hub, cert=str(tmp_path / "cert.pem"), key=str(tmp_path / "key.pem"))
    port = srv.server_address[1]
    try:
        ctx = ssl.create_default_context(cafile=str(tmp_path / "cert.pem"))
        r, _ = get(port, "/overview.json", context=ctx)
        assert r.status == 200
        with pytest.raises((ssl.SSLError, ConnectionError, http.client.HTTPException, OSError)):
            get(port, "/overview.json")  # plain HTTP to the HTTPS port
        os.makedirs(tmp_path / "new")
        _cert(tmp_path / "new", "second")
        time.sleep(1.1)  # a new mtime
        os.replace(tmp_path / "new" / "cert.pem", tmp_path / "cert.pem")
        os.replace(tmp_path / "new" / "key.pem", tmp_path / "key.pem")
        ctx2 = ssl.create_default_context(cafile=str(tmp_path / "cert.pem"))
        c = http.client.HTTPSConnection("127.0.0.1", port, timeout=5, context=ctx2)
        c.request("GET", "/healthz")
        assert c.getresponse().status == 200
        subject = dict(x[0] for x in c.sock.getpeercert()["subject"])
        assert subject["commonName"] == "second"  # renewed certificate, no restart
        c.close()
    finally:
        srv.shutdown()
        srv.server_close()


def test_overview_entry_is_cacheable(tmp_path):
    hub, *_ = make_hub(tmp_path)
    hub.poll_once()
    e = hub.overview()
    assert isinstance(e, render.Entry) and e.cache_control == "public, max-age=5"
