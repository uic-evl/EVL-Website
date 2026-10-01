"""Rollup maths, retention bounds, restart recovery and clock jumps."""

import os
import signal
import subprocess
import sys
import time

import pytest

from evl_monitor.engine import Engine
from evl_monitor.store import Acc, Store

T0 = 1_790_000_000  # a multiple of every tiny step


def rows(store, tier):
    return store.db.execute(
        "SELECT s.key, p.t, p.n, p.mean, p.mx, p.mn FROM pts p JOIN series s ON s.id = p.sid "
        "WHERE p.tier = ? ORDER BY s.key, p.t", (tier,)).fetchall()


def feed(engine, start, stop, value=lambda t: float(t % 100), key="host.cpu_pct"):
    for t in range(start, stop):
        engine.add(t, {key: value(t)})


def test_weighted_mean_max_min(store):
    a = Acc()
    for v in (10.0, 10.0):
        a.add(v)
    b = Acc()
    b.add(40.0)
    store.commit_bucket(T0, {"host.cpu_pct": a}, fine_end=T0 + 2)
    store.commit_bucket(T0 + 2, {"host.cpu_pct": b}, fine_end=T0 + 4)
    (key, t, n, mean, mx, mn), = rows(store, 1)
    assert (t, n, mean, mx, mn) == (T0, 3, 20.0, 40.0, 10.0)  # (2*10 + 1*40) / 3


def test_all_null_bucket_stores_no_row(store, tiny):
    eng = Engine(store, tiny)
    for t in range(T0, T0 + 6):
        eng.add(t, {"host.cpu_pct": None, "host.mem_pct": 50.0})
    keys = {r[0] for r in rows(store, 0)}
    assert keys == {"host.mem_pct"}


def test_buckets_align_to_step(store, tiny):
    eng = Engine(store, tiny)
    feed(eng, T0 + 1, T0 + 40)
    for tier in tiny:
        for _key, t, *_ in rows(store, tier.index):
            assert t % tier.step == 0


def test_unknown_series_keys_are_ignored(store, tiny):
    eng = Engine(store, tiny)
    for t in range(T0, T0 + 6):
        eng.add(t, {"host.cpu_pct": 1.0, "host.cmdline": 2.0, "gpu.99.util_pct": 3.0})
    assert {r[0] for r in rows(store, 0)} == {"host.cpu_pct"}


def test_retention_bounds_and_flat_size(store, tiny):
    eng = Engine(store, tiny)
    rotation = tiny[-1].step * tiny[-1].keep  # one full turn of the coarsest tier
    sizes = []
    for turn in range(10):
        feed(eng, T0 + turn * rotation, T0 + (turn + 1) * rotation)
        for tier in tiny:
            n = store.db.execute("SELECT COUNT(*) FROM pts WHERE tier = ?", (tier.index,)).fetchone()[0]
            assert n <= tier.keep, (tier.range, n)
        store.checkpoint()
        st = store.stats()
        sizes.append(st["page_count"])
        assert st["wal_bytes"] <= 4 * 1024 * 1024
    assert sizes[-1] == sizes[-3], sizes  # file stops growing once every tier is full


def test_coarse_tiers_match_a_direct_aggregate(store, tiny):
    eng = Engine(store, tiny)
    feed(eng, T0, T0 + 200, value=lambda t: float(t % 7))
    # tier 2 (8 s) bucket from raw samples: mean of t % 7 over 8 consecutive seconds
    for _key, t, n, mean, mx, mn in rows(store, 2):
        raw = [float(x % 7) for x in range(t, t + 8)]
        assert n == 8
        assert mean == pytest.approx(sum(raw) / 8)
        assert (mx, mn) == (max(raw), min(raw))


def _run(path, tiny, segments):
    """Feed samples over `segments`; a None segment drops the engine (a crash)."""
    store = Store(path, tiny)
    eng = Engine(store, tiny)
    for seg in segments:
        if seg is None:
            store.db.close()  # in-memory bucket is lost, like a SIGKILL
            store = Store(path, tiny)
            eng = Engine(store, tiny)
            continue
        feed(eng, *seg)
    return store


def test_restart_loses_at_most_one_fine_bucket(tmp_path, tiny):
    ref = _run(os.path.join(tmp_path, "ref.db"), tiny, [(T0, T0 + 300)])
    crash = _run(os.path.join(tmp_path, "crash.db"), tiny, [(T0, T0 + 151), None, (T0 + 151, T0 + 300)])
    a_ref, a_crash = rows(ref, 0), rows(crash, 0)
    lost = {r[1] for r in a_ref} - {r[1] for r in a_crash}
    assert lost <= {T0 + 150}  # the open bucket [150, 152) had one sample in memory
    for tier in tiny[1:]:
        r_ref = {r[1]: r for r in rows(ref, tier.index)}
        r_crash = {r[1]: r for r in rows(crash, tier.index)}
        assert r_ref.keys() == r_crash.keys()
        for t, row in r_ref.items():
            if t <= T0 + 150 < t + tier.step:
                assert r_crash[t][2] == row[2] - 1  # one sample fewer in that window
            else:
                assert r_crash[t] == row


def test_downtime_renders_as_null_gap(store, tiny):
    eng = Engine(store, tiny)
    feed(eng, T0, T0 + 40)
    feed(eng, T0 + 80, T0 + 120)  # down from 40 to 80
    tier = tiny[2]  # 8 s buckets, 6 kept
    start, data = store.window(tier, eng.open_t, tier.keep)
    assert start == T0 + 64  # closed windows end at 112
    means = data["host.cpu_pct"][0]
    assert means[:2] == [None, None]  # [64, 80) had no samples
    assert None not in means[2:]


def test_open_bucket_is_not_served(store, tiny):
    eng = Engine(store, tiny)
    feed(eng, T0, T0 + 21)  # [20, 22) is open
    start, data = store.window(tiny[0], T0 + 21, 5)
    assert start + 5 * 2 == T0 + 20
    assert data["host.cpu_pct"][0][-1] is not None


def test_gap_longer_than_retention(store, tiny):
    eng = Engine(store, tiny)
    feed(eng, T0, T0 + 40)
    feed(eng, T0 + 10_000, T0 + 10_040)
    for tier in tiny:
        ts = [r[1] for r in rows(store, tier.index)]
        assert all(t >= T0 + 10_040 - tier.keep * tier.step - tier.step for t in ts)


def test_catch_up_is_idempotent(db_path, tiny):
    s = _run(db_path, tiny, [(T0, T0 + 101)])
    s.catch_up(T0 + 500)
    first = [rows(s, t.index) for t in tiny]
    s.catch_up(T0 + 500)
    assert [rows(s, t.index) for t in tiny] == first


def test_clock_backwards_drops_samples(store, tiny):
    eng = Engine(store, tiny)
    feed(eng, T0, T0 + 20)
    before = rows(store, 0)
    feed(eng, T0 - 100, T0 + 10)  # NTP stepped back: these buckets are already written
    assert rows(store, 0) == before


def test_clock_forward_jump_is_bounded(store, tiny):
    eng = Engine(store, tiny)
    feed(eng, T0, T0 + 20)
    started = time.monotonic()
    feed(eng, T0 + 10 * 365 * 86400, T0 + 10 * 365 * 86400 + 4)
    assert time.monotonic() - started < 2


def test_tier_change_drops_only_changed_tiers(db_path, tiny):
    s = _run(db_path, tiny, [(T0, T0 + 200)])
    s.db.close()
    from evl_monitor import tiers as tiers_mod
    changed = tiers_mod.parse("2:6:5,4:6:5,8:6:5,16:6:5,64:6:5")
    s2 = Store(db_path, changed)
    assert rows(s2, 0) and rows(s2, 3)
    assert not rows(s2, 4)
    s2.db.close()


def test_corrupt_database_is_kept_aside(db_path, tiny):
    with open(db_path, "wb") as f:
        f.write(b"this is not a database" * 100)
    s = Store(db_path, tiny)
    assert os.path.exists(db_path + ".corrupt")
    assert s.last_bucket() is None
    s.db.close()


CHILD = r"""
import sys
from evl_monitor import tiers as T
from evl_monitor.engine import Engine
from evl_monitor.store import Store
tiny = T.parse("2:6:5,4:6:5,8:6:5,16:6:5,32:6:5")
eng = Engine(Store(sys.argv[1], tiny), tiny)
t = 1_790_000_000
print("ready", flush=True)
while True:
    eng.add(t, {"host.cpu_pct": float(t % 50)})
    t += 1
"""


def test_sigkill_mid_write_leaves_a_usable_database(db_path, tiny):
    p = subprocess.Popen([sys.executable, "-c", CHILD, db_path], stdout=subprocess.PIPE)
    assert p.stdout.readline().strip() == b"ready"
    time.sleep(1.0)
    p.send_signal(signal.SIGKILL)
    p.wait()
    s = Store(db_path, tiny)
    assert s.db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    last = s.last_bucket()
    assert last is not None
    s.catch_up(last + 2)
    eng = Engine(s, tiny)
    feed(eng, last + 2, last + 40)
    assert rows(s, 4)
    s.db.close()
