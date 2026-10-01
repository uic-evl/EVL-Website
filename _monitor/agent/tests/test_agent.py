"""End to end in process: fake collectors, fake clock, every published file valid."""

import gzip
import json

from evl_monitor import days, fake, schema
from evl_monitor.agent import Agent
from evl_monitor.check import FILES
from evl_monitor.clock import FakeClock
from evl_monitor.config import Config
from evl_monitor.publish import Publisher
from evl_monitor.store import Store

from .conftest import env


def make(tmp_path, clock, **kw):
    cfg = Config.from_env(env(MONITOR_FAKE="1", MONITOR_MOUNTS="root:/,data:/data", **kw))
    store = Store(str(tmp_path / "m.db"), cfg.tiers)
    pub = Publisher()
    collectors = fake.FakeCollectors(cfg, clock)
    agent = Agent(cfg, clock, collectors, store, pub)
    collectors.start_services(agent.publish_services, agent.gpu_use)
    return cfg, store, pub, agent


def payload(pub, path):
    return json.loads(gzip.decompress(pub.get(path).gz))


def run_ticks(agent, clock, n):
    for _ in range(n):
        clock.advance(1)
        agent.tick(int(clock.time()))


def test_all_files_published_and_valid(tmp_path):
    clock = FakeClock(1_790_000_000)
    cfg, store, pub, agent = make(tmp_path, clock)
    agent.startup()
    run_ticks(agent, clock, 200)
    for name, node in FILES.items():
        p = payload(pub, "/" + name)
        schema.validate(node, p)
        assert not schema.forbidden_keys(p)
        assert p["id"] == "test"
    now = payload(pub, "/now.json")
    assert now["seq"] == 199 and len(now["gpus"]) == 4
    procs = payload(pub, "/procs.json")
    assert procs["gpus"][0]["procs"][0]["container"] == "nim-gemma4"
    h1 = payload(pub, "/history/1h.json")
    assert len(h1["host"]["cpu_pct"]["mean"]) == h1["n"] == cfg.tiers[0].serve
    assert h1["gpus"][3].get("util_pct") is None or all(v is None for v in h1["gpus"][3]["util_pct"]["mean"])


def test_history_is_core_and_series_has_everything(tmp_path):
    clock = FakeClock(1_790_000_000)
    _, _, pub, agent = make(tmp_path, clock)
    agent.startup()
    run_ticks(agent, clock, 60)
    hist = payload(pub, "/history/1h.json")
    assert set(hist["host"]) <= {"cpu_pct", "load1", "mem_pct", "net_rx_mbs", "net_tx_mbs", "disk_r_mbs", "disk_w_mbs"}
    full = payload(pub, "/series/1h.json")
    keys = set(full["series"])
    for k in ("host.cpu_iowait_pct", "host.procs", "nic.ib0.rx_mbs", "disk.nvme1n1.busy_pct",
              "gpu.0.pcie_rx_mbs", "gpu.0.throttle_power", "mount.data.used_gib"):
        assert k in keys, k
    assert set(full["series"]["host.cpu_pct"]) == {"mean", "max", "min"}


def test_gpu_usage_is_accounted_per_user_and_container(tmp_path):
    clock = FakeClock(1_790_000_000)  # GPU 2's bursty job is on at this time
    _, store, pub, agent = make(tmp_path, clock)
    agent.startup()
    run_ticks(agent, clock, 101)  # the first tick is a baseline and is not accounted
    agent._flush_usage()
    usage = payload(pub, "/usage.json")
    (day,) = usage["days"]
    assert usage["tz"] == "America/Chicago"
    assert day["day"] == days.day_start(clock.time(), "America/Chicago")
    assert day["date"] == days.date_of(clock.time(), "America/Chicago")
    rows = {(r["user"], r["container"]): r for r in day["rows"]}
    assert rows[("alice", "nim-gemma4")]["gpu_h"] == round(100 / 3600, 3)  # GPU 0, 100 s
    assert rows[("alice", "train-xyz")]["gpu_h"] == round(100 / 3600, 3)  # GPU 2's job
    assert rows[("alice", "nim-gemma4")]["mem_gib_h"] > 0
    assert set(rows) == {("alice", "nim-gemma4"), ("alice", "train-xyz")}  # bob's GPU 1 idle, GPU 3 MIG
    agent._flush_usage()  # flushing twice must not double count
    again = {(r["user"], r["container"]): r for r in payload(pub, "/usage.json")["days"][0]["rows"]}
    assert again == rows


def test_first_sample_is_baseline_only(tmp_path):
    clock = FakeClock(1_790_000_000)
    _, store, pub, agent = make(tmp_path, clock)
    agent.startup()
    agent.tick(int(clock.time()))
    assert store.db.execute("SELECT COUNT(*) FROM pts").fetchone()[0] == 0
    assert payload(pub, "/now.json")["seq"] == 0


def test_health_goes_stale(tmp_path):
    clock = FakeClock(1_790_000_000)
    _, _, _, agent = make(tmp_path, clock)
    assert agent.health()[0] is False
    agent.startup()
    run_ticks(agent, clock, 2)
    assert agent.health()[0] is True
    clock.advance(10)  # interval 1, so 3 s is stale
    assert agent.health()[0] is False


def test_backfill_fills_every_range(tmp_path):
    clock = FakeClock(1_790_000_000)
    cfg, store, pub, agent = make(tmp_path, clock)
    fake.backfill(store, cfg, clock.time())
    agent = Agent(cfg, clock, fake.FakeCollectors(cfg, clock), store, pub)
    agent.startup()
    for t in cfg.tiers:
        p = payload(pub, f"/history/{t.range}.json")
        assert all(v is not None for v in p["host"]["cpu_pct"]["mean"]), t.range


def test_daily_covers_30_days_with_the_real_tiers(tmp_path):
    clock = FakeClock(1_790_000_000)
    cfg = Config.from_env({"MONITOR_ID": "real", "MONITOR_FAKE": "1"})  # default tiers, 5 s
    store = Store(str(tmp_path / "r.db"), cfg.tiers)
    fake.backfill(store, cfg, clock.time())
    pub = Publisher()
    Agent(cfg, clock, fake.FakeCollectors(cfg, clock), store, pub).startup()
    daily = payload(pub, "/daily.json")
    schema.validate(schema.DAILY, daily)
    assert len(daily["days"]) == 31  # 30 days and today
    full = daily["days"][1:-1]
    assert all(d["hours"] in (23, 24, 25) for d in full)
    assert all(d["load_pct"] is not None and d["gpu_util_pct"] is not None for d in daily["days"])


def test_restart_keeps_history(tmp_path):
    clock = FakeClock(1_790_000_000)
    cfg, store, pub, agent = make(tmp_path, clock)
    agent.startup()
    run_ticks(agent, clock, 100)
    before = payload(pub, "/history/24h.json")["host"]["cpu_pct"]["mean"]
    store.db.close()
    cfg, store, pub, agent = make(tmp_path, clock)
    agent.startup()
    after = payload(pub, "/history/24h.json")["host"]["cpu_pct"]["mean"]
    assert after == before  # rendered from disk before the first new sample
