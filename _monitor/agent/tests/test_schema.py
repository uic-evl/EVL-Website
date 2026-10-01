"""The closed schema: undeclared keys and strings never reach a public payload."""

import gzip
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from evl_monitor import render, schema
from evl_monitor.agent import Agent, RealCollectors
from evl_monitor.clock import RealClock
from evl_monitor.collect.gpu import GpuSnapshot
from evl_monitor.config import Config
from evl_monitor.publish import Publisher
from evl_monitor.store import Store

from .conftest import env


def good_now():
    sample = {
        "host": {"cpu_pct": 37.44, "load1": 1.234, "mem_pct": 40.0, "mem_used_gib": 1.0, "mem_total_gib": 2.0},
        "per_core": [10.0, 90.0],
        "mounts": {"root": {"path": "/", "used_pct": 43.6, "used_gib": 812.4, "total_gib": 1862.0}},
        "nics": {"eno1": {"rx_mbs": 1.0, "tx_mbs": 2.0}},
        "disks": {"nvme0n1": {"r_mbs": 1.0, "w_mbs": 2.0, "busy_pct": 3.0}},
    }
    return render.now_payload(
        "arcade", 1_790_000_005, 3, 5, 1_789_000_000, sample, "ok", "ok",
        [{"i": 0, "util_pct": 98, "mem_pct": 89.6, "procs": 1, "mig": False, "throttle": ["sw_power_cap"]}],
    )


def test_good_now_payload_validates_and_rounds():
    p = good_now()
    schema.validate(schema.NOW, p)
    assert p["host"]["cpu_pct"] == 37.4 and p["host"]["load1"] == 1.23


@pytest.mark.parametrize("mutate", [
    lambda p: p["host"].__setitem__("cmdline", "python serve.py --token=x"),
    lambda p: p.__setitem__("hostname", "arcade"),
    lambda p: p.__setitem__("gpu_status", "on fire"),
    lambda p: p["gpus"][0]["throttle"].append("because"),
    lambda p: p.__setitem__("id", "Arcade!"),
    lambda p: p["host"].__setitem__("cpu_pct", float("nan")),
    lambda p: p["mounts"].__setitem__("../etc", {"path": "/", "used_pct": 1, "used_gib": 1, "total_gib": 1}),
    lambda p: p["mounts"]["root"].__setitem__("path", "/home/alice; rm -rf"),
    lambda p: p["nics"].__setitem__("eth0 secret", {"rx_mbs": 1, "tx_mbs": 1}),
    lambda p: p["host"].__setitem__("hostname_hint", 1.0),
])
def test_now_payload_rejects(mutate):
    p = good_now()
    mutate(p)
    with pytest.raises(schema.SchemaError):
        schema.validate(schema.NOW, p)


def test_encode_refuses_and_logs_only_the_path(caplog):
    p = good_now()
    p["host"]["environ"] = "SECRET=hunter2"
    with pytest.raises(render.RenderError):
        render.encode(p, schema.NOW, "no-store")
    assert "hunter2" not in caplog.text
    assert "$.host.environ" in caplog.text


@pytest.mark.parametrize("field, value", [
    ("user", "alice; rm -rf /"),
    ("user", "x" * 40),
    ("container", "/etc/passwd"),
    ("name", "a" * 16),
])
def test_procs_free_text_is_narrow(field, value):
    row = {"user": "alice", "container": "nim", "name": "python3", "kind": "compute", "mem_gib": 1.0}
    row[field] = value
    p = render.procs_payload("arcade", 1, "ok", "ok", [{"i": 0, "more": 0, "procs": [row]}])
    with pytest.raises(schema.SchemaError):
        schema.validate(schema.PROCS, p)


def test_no_schema_declares_a_forbidden_key():
    def walk(node):
        if isinstance(node, schema.Obj):
            for k, v in node.fields.items():
                assert k not in schema.FORBIDDEN_KEYS
                walk(v)
        elif isinstance(node, schema.List):
            walk(node.item)
        elif isinstance(node, schema.Map):
            walk(node.value)
    for n in (schema.NOW, schema.PROCS, schema.HOST, schema.HISTORY, schema.SPARK):
        walk(n)


def test_package_never_reads_cmdline_or_environ():
    """No string literal or path in the package names /proc/<pid>/cmdline or environ."""
    import re
    literal = re.compile(r"""['"/](cmdline|environ)['"]""")
    src = Path(__file__).resolve().parents[1] / "src" / "evl_monitor"
    for path in src.rglob("*.py"):
        if path.name == "schema.py":
            continue  # FORBIDDEN_KEYS lists these names to reject them
        for n, line in enumerate(path.read_text().splitlines(), 1):
            assert not literal.search(line), f"{path.name}:{n}: {line.strip()}"


CANARY_CHILD = r"""
import ctypes, sys, time
libc = ctypes.CDLL(None)
libc.prctl(15, b"canaryproc", 0, 0, 0)  # PR_SET_NAME
print("ready", flush=True)
time.sleep(30)
"""


class FakeGpu:
    def __init__(self, pid):
        self.pid = pid

    def latest(self, max_age):
        gpus = [{"i": 0, "util_pct": 50, "mem_pct": 10.0, "procs": 1, "mig": False, "throttle": []}]
        return GpuSnapshot("ok", gpus, {0: [(self.pid, 2 * 1024**3, "compute")]},
                           {"driver": "570.1", "cuda": "12.8", "devices": []})

    def start(self):
        pass

    def stop(self):
        pass


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="reads /proc and prctl")
def test_canary_argv_and_env_never_appear(tmp_path):
    proc = subprocess.Popen(
        [sys.executable, "-c", CANARY_CHILD, "--token=CANARY_ARG"],
        env={**os.environ, "SECRET": "CANARY_ENV"}, stdout=subprocess.PIPE)
    try:
        assert proc.stdout.readline().strip() == b"ready"
        cfg = Config.from_env(env(MONITOR_HOSTFS="/", MONITOR_DOCKER_SOCK=""))
        clock = RealClock()
        collectors = RealCollectors(cfg, clock)
        collectors.gpu = FakeGpu(proc.pid)
        pub = Publisher()
        store = Store(str(tmp_path / "db"), cfg.tiers)
        agent = Agent(cfg, clock, collectors, store, pub)
        agent.startup()
        for k in range(3):
            agent.tick(int(time.time()) + k)
        blob = b"".join(gzip.decompress(pub.get(p).gz) for p in pub.paths())
        assert b"CANARY_ARG" not in blob and b"CANARY_ENV" not in blob
        procs = json.loads(pub.get("/procs.json").raw)
        assert procs["gpus"][0]["procs"][0]["name"] == "canaryproc"
    finally:
        proc.kill()
