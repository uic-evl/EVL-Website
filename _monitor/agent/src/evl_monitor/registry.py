"""Metrics kept in history: series keys, rounding, and which ones the page's files carry.

A series key is `<kind>.<metric>` for the host and `<kind>.<name>.<metric>` for a mount,
NIC, disk or GPU, e.g. `host.cpu_pct`, `mount.data.used_pct`, `nic.eno1.rx_mbs`,
`disk.nvme0n1.busy_pct`, `gpu.2.util_pct`.

Every series is stored and served in series/<range>.json, so the page can start
showing a metric later without an agent update. history/<range>.json carries only
the CORE set the page draws today, to keep those files small.
"""

from __future__ import annotations

import re

HOST_METRICS: dict[str, int] = {  # metric -> decimals
    "cpu_pct": 1, "cpu_user_pct": 1, "cpu_system_pct": 1, "cpu_iowait_pct": 1, "cpu_steal_pct": 1,
    "load1": 2, "load5": 2, "load15": 2,
    "mem_pct": 1, "mem_used_gib": 1, "mem_cached_gib": 1, "swap_pct": 1,
    "net_rx_mbs": 2, "net_tx_mbs": 2,
    "disk_r_mbs": 2, "disk_w_mbs": 2, "disk_r_iops": 0, "disk_w_iops": 0,
    "procs": 0, "procs_running": 0, "procs_blocked": 0, "users": 0, "containers": 0,
    "cpu_temp_c": 0,
}
MOUNT_METRICS: dict[str, int] = {"used_pct": 1, "used_gib": 1}
NIC_METRICS: dict[str, int] = {"rx_mbs": 2, "tx_mbs": 2}
DISK_METRICS: dict[str, int] = {"r_mbs": 2, "w_mbs": 2, "busy_pct": 1}
GPU_METRICS: dict[str, int] = {
    "util_pct": 0, "mem_util_pct": 0, "mem_pct": 1, "mem_used_gib": 1,
    "power_w": 0, "temp_c": 0, "sm_mhz": 0, "mem_mhz": 0, "fan_pct": 0,
    "pcie_rx_mbs": 1, "pcie_tx_mbs": 1, "enc_pct": 0, "dec_pct": 0,
    "ecc_uncorrected": 0, "procs": 0,
    # 0 or 1 per sample, so a bucket mean is the share of time throttled
    "throttle_power": 2, "throttle_thermal": 2,
}

KINDS: dict[str, dict[str, int]] = {
    "mount": MOUNT_METRICS, "nic": NIC_METRICS, "disk": DISK_METRICS, "gpu": GPU_METRICS,
}

# what history/<range>.json carries (the page today)
CORE: dict[str, frozenset[str]] = {
    "host": frozenset({"cpu_pct", "load1", "mem_pct", "net_rx_mbs", "net_tx_mbs", "disk_r_mbs", "disk_w_mbs"}),
    "mount": frozenset({"used_pct"}),
    "nic": frozenset(),
    "disk": frozenset(),
    "gpu": frozenset({"util_pct", "mem_pct", "power_w", "temp_c"}),
}

MAX_GPUS = 16
MAX_SERIES = 512

NAME_RE = {
    "mount": re.compile(r"[a-z0-9_-]{1,16}"),
    "nic": re.compile(r"[A-Za-z0-9_.-]{1,15}"),
    "disk": re.compile(r"[a-z0-9]{1,15}"),
    "gpu": re.compile(r"\d{1,2}"),
}


def parse(key: str) -> tuple[str, str | None, str] | None:
    """(kind, name or None, metric) for a valid key, else None."""
    first, _, rest = key.partition(".")
    if first == "host":
        return ("host", None, rest) if rest in HOST_METRICS else None
    if first not in KINDS:
        return None
    name, _, metric = rest.rpartition(".")
    if metric not in KINDS[first] or not NAME_RE[first].fullmatch(name):
        return None
    if first == "gpu" and int(name) >= MAX_GPUS:
        return None
    return first, name, metric


def is_valid_key(key: str) -> bool:
    return parse(key) is not None


def decimals(key: str) -> int:
    p = parse(key)
    if p is None:
        raise KeyError(key)
    kind, _, metric = p
    return HOST_METRICS[metric] if kind == "host" else KINDS[kind][metric]


def is_core(key: str) -> bool:
    p = parse(key)
    return p is not None and p[2] in CORE[p[0]]


def series_values(host: dict, mounts: dict, gpus: list[dict], nics: dict | None = None,
                  disks: dict | None = None) -> dict[str, float | None]:
    """Flatten one sample into series values (None means no reading)."""
    out: dict[str, float | None] = {f"host.{m}": host.get(m) for m in HOST_METRICS}
    for label, m in mounts.items():
        for metric in MOUNT_METRICS:
            out[f"mount.{label}.{metric}"] = m.get(metric)
    for name, m in (nics or {}).items():
        for metric in NIC_METRICS:
            out[f"nic.{name}.{metric}"] = m.get(metric)
    for name, m in (disks or {}).items():
        for metric in DISK_METRICS:
            out[f"disk.{name}.{metric}"] = m.get(metric)
    for g in gpus:
        for metric in GPU_METRICS:
            out[f"gpu.{g['i']}.{metric}"] = g.get(metric)
    return out
