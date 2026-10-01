"""Build, validate and encode the public JSON payloads."""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import math
from dataclasses import dataclass

from . import __version__, registry, schema
from . import days as days_mod
from .tiers import RANGES, SPARK_POINTS, Tier

log = logging.getLogger(__name__)

HOST_DP = {**registry.HOST_METRICS, "cores": 0, "mem_total_gib": 1, "swap_used_gib": 1, "swap_total_gib": 1}
GPU_DP = {**{k: v for k, v in registry.GPU_METRICS.items() if k != "procs"},
          "mem_total_gib": 1, "power_limit_w": 0}
MOUNT_DP = {"used_pct": 1, "used_gib": 1, "total_gib": 1}

# every file the agent serves (host.json lists them so clients can discover new ones)
FILES = (["now.json", "procs.json", "host.json", "spark.json", "usage.json", "services.json", "daily.json"]
         + [f"history/{r}.json" for r in RANGES] + [f"series/{r}.json" for r in RANGES])


def r(x, dp: int):
    """Round for publishing; non-finite or missing values become null."""
    if x is None or isinstance(x, bool):
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x):
        return None
    if dp == 0:
        return int(round(x))
    return round(x, dp)


@dataclass(frozen=True)
class Entry:
    raw: bytes
    gz: bytes
    etag: str
    etag_gz: str
    cache_control: str


class RenderError(ValueError):
    pass


def encode(payload: dict, node: schema.Node, cache_control: str) -> Entry:
    try:
        schema.validate(node, payload)
    except schema.SchemaError as exc:
        # log the path only: the value may be exactly what must not be published
        log.error("payload failed its schema at %s; not published", exc.path)
        raise RenderError(exc.path) from None
    raw = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode()
    gz = gzip.compress(raw, compresslevel=6, mtime=0)
    h = hashlib.blake2b(raw, digest_size=8).hexdigest()
    return Entry(raw, gz, f'"{h}"', f'"{h}-gz"', cache_control)


# payloads ----------------------------------------------------------------------


def now_payload(ident: str, ts: int, seq: int, interval: int, boot_ts, sample, gpu_status: str,
                procs_status: str, gpus: list[dict]) -> dict:
    host = sample["host"]
    return {
        "v": 1, "id": ident, "agent": __version__, "ts": int(ts), "seq": int(seq),
        "interval": int(interval), "boot_ts": boot_ts,
        "host": {k: r(host.get(k), dp) for k, dp in HOST_DP.items()},
        "cpu_cores_pct": [r(x, 0) for x in sample.get("per_core") or []],
        "mounts": {label: {"path": m.get("path", "/"), **{k: r(m.get(k), dp) for k, dp in MOUNT_DP.items()}}
                   for label, m in sample["mounts"].items()},
        "nics": {name: {k: r(m.get(k), dp) for k, dp in registry.NIC_METRICS.items()}
                 for name, m in (sample.get("nics") or {}).items()},
        "disks": {name: {k: r(m.get(k), dp) for k, dp in registry.DISK_METRICS.items()}
                  for name, m in (sample.get("disks") or {}).items()},
        "gpu_status": gpu_status,
        "procs_status": procs_status,
        "gpus": [
            {
                "i": g["i"],
                **{k: r(g.get(k), dp) for k, dp in GPU_DP.items()},
                "procs": g.get("procs"),
                "mig": g.get("mig"),
                "throttle": list(g.get("throttle") or []),
            }
            for g in gpus
        ],
    }


def procs_payload(ident: str, ts: int, procs_status: str, containers_status: str,
                  per_gpu: list[dict]) -> dict:
    return {
        "v": 1, "id": ident, "ts": int(ts),
        "procs_status": procs_status, "containers_status": containers_status,
        "gpus": per_gpu,
    }


def host_payload(ident: str, ts: int, interval: int, facts: dict, sample, gpu_status: str,
                 gpu_facts: dict, tiers: tuple[Tier, ...]) -> dict:
    cpu = facts.get("cpu") or {}
    host = sample["host"]
    return {
        "v": 1, "id": ident, "agent": __version__, "ts": int(ts), "interval": int(interval),
        "boot_ts": facts.get("boot_ts"),
        "gpu_status": gpu_status,
        "facts": {
            "os": _printable(facts.get("os"), 128),
            "kernel": _printable(facts.get("kernel"), 128),
            "cpu_model": _printable(cpu.get("model"), 128),
            "gpu_driver": gpu_facts.get("driver"),
            "cuda": gpu_facts.get("cuda"),
        },
        "cpu": {k: cpu.get(k) for k in ("sockets", "cores", "threads", "max_mhz")},
        "mem": {"total_gib": r(host.get("mem_total_gib"), 1), "swap_total_gib": r(host.get("swap_total_gib"), 1)},
        "mounts": {label: {"path": m.get("path", "/"), "total_gib": r(m.get("total_gib"), 1)}
                   for label, m in sample["mounts"].items()},
        "nics": sorted(sample.get("nics") or {}),
        "disks": sorted(sample.get("disks") or {}),
        "gpus": [
            {
                "i": d["i"],
                "name": _printable(d.get("name"), 96),
                "mem_total_gib": r(d.get("mem_total_gib"), 1),
                "power_limit_w": r(d.get("power_limit_w"), 0),
                "mig": d.get("mig"),
            }
            for d in gpu_facts.get("devices") or []
        ],
        "ranges": [{"range": t.range, "step": t.step, "n": t.serve} for t in tiers],
        "files": list(FILES),
    }


def _printable(s, maxlen: int):
    if s is None:
        return None
    s = "".join(ch if 0x20 <= ord(ch) <= 0x7E else " " for ch in str(s)).strip()
    return s[:maxlen] or None


def _round_list(xs: list, dp: int) -> list:
    return [r(x, dp) for x in xs]


def history_payload(ident: str, tier: Tier, start: int, data: dict[str, tuple]) -> dict:
    """The page's history file: the CORE series only, mean and max."""
    host: dict = {}
    mounts: dict = {}
    gpus: dict[int, dict] = {}
    for key, (means, maxes, _mins) in sorted(data.items()):
        p = registry.parse(key)
        if p is None or not registry.is_core(key):
            continue
        kind, name, metric = p
        dp = registry.decimals(key)
        if kind == "host":
            host[metric] = {"mean": _round_list(means, dp), "max": _round_list(maxes, dp)}
        elif kind == "mount":
            mounts[name] = {"used_pct": {"mean": _round_list(means, dp)}}
        elif kind == "gpu":
            g = gpus.setdefault(int(name), {"i": int(name)})
            g[metric] = {"mean": _round_list(means, dp), "max": _round_list(maxes, dp)}
    return {
        "v": 1, "id": ident, "range": tier.range, "start": int(start), "step": tier.step,
        "n": tier.serve, "host": host, "mounts": mounts,
        "gpus": [gpus[i] for i in sorted(gpus)],
    }


def full_payload(ident: str, tier: Tier, start: int, data: dict[str, tuple]) -> dict:
    """series/<range>.json: every stored series, mean, max and min."""
    series = {}
    for key, (means, maxes, mins) in sorted(data.items()):
        if not registry.is_valid_key(key):
            continue
        dp = registry.decimals(key)
        series[key] = {"mean": _round_list(means, dp), "max": _round_list(maxes, dp),
                       "min": _round_list(mins, dp)}
    return {"v": 1, "id": ident, "range": tier.range, "start": int(start), "step": tier.step,
            "n": tier.serve, "series": series}


def spark_payload(ident: str, tier: Tier, start: int, data: dict[str, tuple]) -> dict:
    n = SPARK_POINTS
    empty = [None] * n
    gpu_means = [v[0] for k, v in data.items() if k.startswith("gpu.") and k.endswith(".util_pct")]
    gpu = []
    for i in range(n):
        vals = [s[i] for s in gpu_means if s[i] is not None]
        gpu.append(sum(vals) / len(vals) if vals else None)
    return {
        "v": 1, "id": ident, "start": int(start), "step": tier.step, "n": n,
        "cpu_pct": _round_list(data.get("host.cpu_pct", (empty,))[0], 1),
        "mem_pct": _round_list(data.get("host.mem_pct", (empty,))[0], 1),
        "gpu_util_pct": _round_list(gpu, 1),
    }


def services_payload(ident: str, ts: int, parts: dict) -> dict:
    return {"v": 1, "id": ident, "ts": int(ts), **parts}


def usage_payload(ident: str, ts: int, tz: str, rows: list[tuple[int, str, str, float, float]]) -> dict:
    days: dict[int, list] = {}
    for day, user, container, gpu_s, mem_s in rows:
        days.setdefault(day, []).append({
            "user": user, "container": container or None,
            "gpu_h": r(gpu_s / 3600, 3), "mem_gib_h": r(mem_s / 3600, 2),
        })
    return {"v": 1, "id": ident, "ts": int(ts), "tz": tz,
            "days": [{"day": d, "date": days_mod.date_of(d, tz), "rows": days[d]} for d in sorted(days)]}


DAILY_DAYS = 30


def daily_payload(ident: str, ts: int, tz: str, rows: list[tuple[str, int, int, float]]) -> dict:
    """Average load per local day: CPU, memory and GPU, and their mean as one load figure.

    load_pct is the mean of cpu_pct, mem_pct, gpu_util_pct and gpu_mem_pct (cpu_pct and mem_pct on
    hosts without GPUs). GPU figures are averaged over the host's GPUs. Days carry `hours`, the
    number of hours with data, so a partial day (today, or a day with downtime) is visible.
    """
    acc: dict[str, dict[str, list[float]]] = {}  # date -> key -> [weighted sum, weight]
    hours: dict[str, set[int]] = {}
    starts: dict[str, int] = {}
    for key, t, n, mean in rows:
        d = days_mod.date_of(t, tz)
        a = acc.setdefault(d, {}).setdefault(key, [0.0, 0.0])
        a[0] += mean * n
        a[1] += n
        if key == "host.cpu_pct":
            hours.setdefault(d, set()).add(t)
        starts.setdefault(d, days_mod.day_start(t, tz))

    def avg(series: dict[str, list[float]], key: str):
        a = series.get(key)
        return a[0] / a[1] if a and a[1] else None

    def gpu_avg(series: dict[str, list[float]], metric: str):
        vals = [avg(series, k) for k in series if k.startswith("gpu.") and k.endswith("." + metric)]
        vals = [v for v in vals if v is not None]
        return sum(vals) / len(vals) if vals else None

    out = []
    for d in sorted(acc)[-(DAILY_DAYS + 1):]:
        s = acc[d]
        cpu, mem = avg(s, "host.cpu_pct"), avg(s, "host.mem_pct")
        gpu_util, gpu_mem = gpu_avg(s, "util_pct"), gpu_avg(s, "mem_pct")
        parts = [v for v in (cpu, mem, gpu_util, gpu_mem) if v is not None]
        out.append({
            "date": d, "day": starts[d], "hours": len(hours.get(d, ())),
            "cpu_pct": r(cpu, 1), "mem_pct": r(mem, 1),
            "gpu_util_pct": r(gpu_util, 1), "gpu_mem_pct": r(gpu_mem, 1),
            "load1": r(avg(s, "host.load1"), 2),
            "load_pct": r(sum(parts) / len(parts), 1) if parts else None,
        })
    return {"v": 1, "id": ident, "ts": int(ts), "tz": tz, "days": out}
