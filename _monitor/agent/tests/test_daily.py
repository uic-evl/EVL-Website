"""daily.json: average load per local day for the past 30 days."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from evl_monitor import days, schema
from evl_monitor.render import daily_payload

TZ = "America/Chicago"
CHI = ZoneInfo(TZ)


def ts(y, mo, d, h=0):
    return int(datetime(y, mo, d, h, tzinfo=CHI).timestamp())


def hourly(start, hours, values):
    """Rows (key, t, n, mean) for `hours` consecutive 1 h buckets from `start`."""
    rows = []
    for k in range(hours):
        t = start + k * 3600
        for key, v in values.items():
            rows.append((key, t, 720, v(k) if callable(v) else v))
    return rows


def test_components_and_combined_load():
    rows = hourly(ts(2026, 9, 10), 24, {
        "host.cpu_pct": 40.0, "host.mem_pct": 50.0, "host.load1": 12.0,
        "gpu.0.util_pct": 90.0, "gpu.1.util_pct": 10.0,  # mean over GPUs: 50
        "gpu.0.mem_pct": 80.0, "gpu.1.mem_pct": 0.0,
    })
    p = daily_payload("arcade", ts(2026, 9, 11, 12), TZ, rows)
    schema.validate(schema.DAILY, p)
    (d,) = p["days"]
    assert d["date"] == "2026-09-10" and d["hours"] == 24 and d["day"] == ts(2026, 9, 10)
    assert (d["cpu_pct"], d["mem_pct"], d["gpu_util_pct"], d["gpu_mem_pct"], d["load1"]) == (40.0, 50.0, 50.0, 40.0, 12.0)
    assert d["load_pct"] == pytest.approx((40 + 50 + 50 + 40) / 4, abs=0.05)  # cpu, mem, gpu util, gpu mem


def test_no_gpu_host_uses_cpu_and_memory():
    rows = hourly(ts(2026, 9, 10), 2, {"host.cpu_pct": 20.0, "host.mem_pct": 60.0})
    (d,) = daily_payload("utk", ts(2026, 9, 10, 5), TZ, rows)["days"]
    assert d["gpu_util_pct"] is None and d["load_pct"] == 40.0


def test_weighted_by_samples():
    rows = [("host.cpu_pct", ts(2026, 9, 10, 1), 720, 10.0), ("host.cpu_pct", ts(2026, 9, 10, 2), 360, 70.0)]
    (d,) = daily_payload("x", ts(2026, 9, 11), TZ, rows)["days"]
    assert d["cpu_pct"] == 30.0  # (720*10 + 360*70) / 1080
    assert d["hours"] == 2  # a partial day says so


def test_local_days_and_the_25_hour_dst_day():
    start = ts(2026, 10, 31)  # DST ends Sunday 2026-11-01 at 2:00 in Chicago
    rows = hourly(start, 24 + 25 + 24, {"host.cpu_pct": 1.0})
    out = daily_payload("x", ts(2026, 11, 3), TZ, rows)["days"]
    assert [(d["date"], d["hours"]) for d in out] == [("2026-10-31", 24), ("2026-11-01", 25), ("2026-11-02", 24)]
    assert out[1]["day"] == ts(2026, 11, 1)


def test_keeps_the_last_30_days_and_today():
    rows = hourly(ts(2026, 8, 1), 24 * 40, {"host.cpu_pct": 5.0})
    out = daily_payload("x", ts(2026, 9, 10, 12), TZ, rows)["days"]
    assert len(out) == 31 and out[-1]["date"] == "2026-09-09"


def test_day_start_helpers():
    t = ts(2026, 3, 8, 15)  # DST starts that morning
    assert days.day_start(t, TZ) == ts(2026, 3, 8)
    assert days.date_of(t, TZ) == "2026-03-08"
