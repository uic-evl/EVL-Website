"""Synthetic hosts for page development and CI (MONITOR_FAKE=1).

Values are deterministic functions of the host id and the time, so a reload shows
the same curves. GPU i follows pattern i % 4: pegged (a NIM model), idle, bursty
(training jobs), and MIG (no utilization, no process list).
"""

from __future__ import annotations

import hashlib
import math

from . import registry
from .agent import RawSample
from .store import Store
from .tiers import Tier

DAY = 86400.0


def _noise(seed: int, t: float, salt: int) -> float:
    """Deterministic value in [-1, 1) for a (seed, time bucket, salt)."""
    h = hashlib.blake2b(f"{seed}:{int(t)}:{salt}".encode(), digest_size=4).digest()
    return int.from_bytes(h, "big") / 2**31 - 1.0


def _seed(ident: str) -> int:
    return int.from_bytes(hashlib.blake2b(ident.encode(), digest_size=4).digest(), "big")


def host_values(seed: int, t: float) -> dict:
    phase = (seed % 1000) / 1000 * 2 * math.pi
    day = math.sin(2 * math.pi * t / DAY + phase)
    cpu = max(0.0, min(100.0, 35 + 25 * day + 6 * _noise(seed, t / 30, 1)))
    mem = max(0.0, min(100.0, 48 + 10 * math.sin(2 * math.pi * t / (7 * DAY) + phase) + 2 * _noise(seed, t / 60, 2)))
    return {
        "cpu_pct": cpu,
        "load1": cpu / 100 * 64 * (1 + 0.1 * _noise(seed, t / 30, 3)),
        "mem_pct": mem,
        "net_rx_mbs": max(0.0, 40 + 35 * day + 20 * _noise(seed, t / 20, 4)),
        "net_tx_mbs": max(0.0, 8 + 6 * day + 4 * _noise(seed, t / 20, 5)),
        "disk_r_mbs": max(0.0, 15 + 12 * _noise(seed, t / 40, 6)),
        "disk_w_mbs": max(0.0, 25 + 20 * _noise(seed, t / 40, 7)),
    }


def gpu_values(seed: int, i: int, t: float) -> dict:
    pattern = i % 4
    if pattern == 0:  # pegged by an inference server
        util = 96 + 3 * _noise(seed, t / 10, 10 + i)
        mem = 89.6
    elif pattern == 1:  # idle
        util = max(0.0, 1 + _noise(seed, t / 10, 10 + i))
        mem = 0.6
    elif pattern == 2:  # bursty training job, 20 min on, 20 min off
        on = int(t // 1200) % 2 == 0
        util = (85 + 10 * _noise(seed, t / 10, 10 + i)) if on else 2.0
        mem = 62.0 if on else 0.6
    else:  # MIG: NVML reports no utilization
        util = None
        mem = 45.0 + 5 * _noise(seed, t / 600, 20 + i)
    busy = (util or 30) / 100
    return {
        "util_pct": util,
        "mem_pct": mem,
        "power_w": 70 + 600 * busy + 10 * _noise(seed, t / 10, 30 + i),
        "temp_c": 32 + 35 * busy + 2 * _noise(seed, t / 60, 40 + i),
    }


class FakeCollectors:
    def __init__(self, cfg, clock):
        self.cfg = cfg
        self.clock = clock
        self.seed = _seed(cfg.id)
        self.n_gpus = max(0, min(cfg.fake_gpus, registry.MAX_GPUS))

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def start_services(self, publish, gpu_use) -> None:
        publish(fake_services(self.cfg.id, int(self.clock.time())))

    def facts(self) -> dict:
        return {
            "os": "Ubuntu 24.04.1 LTS",
            "kernel": "6.8.0-45-generic",
            "cpu": {"model": "AMD EPYC 9554 64-Core Processor", "sockets": 2, "cores": 128,
                    "threads": 256, "max_mhz": 3750},
            "boot_ts": int(self.clock.time() - 12 * DAY),
        }

    def sample(self) -> RawSample:
        t = self.clock.time()
        hv = host_values(self.seed, t)
        mem_total = 1007.6
        cpu = hv["cpu_pct"]
        host = dict(hv)
        host.update({
            "cpu_user_pct": cpu * 0.72, "cpu_system_pct": cpu * 0.2, "cpu_iowait_pct": cpu * 0.05,
            "cpu_steal_pct": 0.0, "load5": hv["load1"] * 0.95, "load15": hv["load1"] * 0.9, "cores": 256,
            "mem_used_gib": mem_total * hv["mem_pct"] / 100, "mem_total_gib": mem_total,
            "mem_cached_gib": mem_total * 0.3, "swap_pct": 0.0, "swap_used_gib": 0.0, "swap_total_gib": 8.0,
            "disk_r_iops": hv["disk_r_mbs"] * 40, "disk_w_iops": hv["disk_w_mbs"] * 30,
            "procs": 1400 + int(cpu * 4), "procs_running": int(hv["load1"]), "procs_blocked": 0,
            "users": 3, "containers": 14, "cpu_temp_c": 40 + cpu / 3,
        })
        per_core = [max(0.0, min(100.0, cpu + 20 * _noise(self.seed, t / 5, 100 + c))) for c in range(32)]
        mounts = {}
        for k, (label, path) in enumerate(self.cfg.mounts):
            total = 1862.0 * (k + 1)
            pct = 40 + 10 * k + 0.5 * math.sin(2 * math.pi * t / (30 * DAY))
            mounts[label] = {"path": path, "used_pct": pct, "used_gib": total * pct / 100, "total_gib": total}
        nics = {"eno1": {"rx_mbs": hv["net_rx_mbs"] * 0.8, "tx_mbs": hv["net_tx_mbs"] * 0.8},
                "ib0": {"rx_mbs": hv["net_rx_mbs"] * 0.2, "tx_mbs": hv["net_tx_mbs"] * 0.2}}
        disks = {"nvme0n1": {"r_mbs": hv["disk_r_mbs"] * 0.6, "w_mbs": hv["disk_w_mbs"] * 0.6,
                             "busy_pct": min(100.0, hv["disk_w_mbs"] / 2)},
                 "nvme1n1": {"r_mbs": hv["disk_r_mbs"] * 0.4, "w_mbs": hv["disk_w_mbs"] * 0.4,
                             "busy_pct": min(100.0, hv["disk_w_mbs"] / 3)}}
        sample = {"host": host, "per_core": per_core, "mounts": mounts, "nics": nics, "disks": disks}

        gpus, devices, procs = [], [], []
        total_gib = 79.6
        for i in range(self.n_gpus):
            gv = gpu_values(self.seed, i, t)
            mig = i % 4 == 3
            util = gv["util_pct"] or 0
            g = {
                "i": i, "util_pct": gv["util_pct"], "mem_util_pct": None if mig else util * 0.6,
                "mem_pct": gv["mem_pct"],
                "mem_used_gib": total_gib * gv["mem_pct"] / 100, "mem_total_gib": total_gib,
                "power_w": gv["power_w"], "power_limit_w": 700, "temp_c": gv["temp_c"],
                "sm_mhz": 1980 if util > 10 else 345, "mem_mhz": 2619, "fan_pct": None,
                "pcie_rx_mbs": util * 120.0, "pcie_tx_mbs": util * 30.0, "enc_pct": 0, "dec_pct": 0,
                "ecc_uncorrected": 0,
                "mig": mig, "throttle": ["sw_power_cap"] if util > 90 else ["gpu_idle"] if util < 5 else [],
                "throttle_power": 1 if util > 90 else 0, "throttle_thermal": 0,
            }
            rows = []
            if not mig and gv["mem_pct"] > 5:
                rows.append({"user": "alice" if i % 2 == 0 else "bob",
                             "container": "nim-gemma4" if i % 4 == 0 else "train-xyz",
                             "name": "python3", "kind": "compute",
                             "mem_gib": round(g["mem_used_gib"] - 0.5, 1)})
            g["procs"] = None if mig else len(rows)
            gpus.append(g)
            procs.append({"i": i, "more": 0, "procs": rows})
            devices.append({"i": i, "name": "NVIDIA H100 80GB HBM3", "mem_total_gib": total_gib,
                            "power_limit_w": 700, "mig": mig})
        status = "ok" if self.n_gpus else "absent"
        gpu_facts = {"driver": "570.133.20", "cuda": "12.8", "devices": devices} if self.n_gpus else \
            {"driver": None, "cuda": None, "devices": []}
        return RawSample(sample, status, gpus, gpu_facts,
                         "ok" if self.n_gpus else "unsupported",
                         "ok" if self.n_gpus else "off", procs if self.n_gpus else [])


def fake_services(ident: str, now: int) -> dict:
    fqdn = f"{ident}.evl.uic.edu"

    def c(name, image, port, gpus=(), health="healthy", state="running", project=None):
        return {"name": name, "image": image, "state": state, "health": health if state == "running" else None,
                "status": "Up 3 days (healthy)" if state == "running" else "Exited (0) 2 days ago",
                "created_ts": now - 5 * 86400,
                "ports": [{"public": port, "private": port, "bind": "loopback", "proto": "tcp"}] if port else [],
                "project": project, "service": name if project else None,
                "gpus": list(gpus), "gpu_mem_gib": 71.3 * len(gpus)}
    containers = [
        c("nim-gemma4", "nvcr.io/nim/google/gemma-4-31b-it:latest", 8000, gpus=(0,), project="llm"),
        c("train-xyz", "nvcr.io/nvidia/pytorch:25.01-py3", None, gpus=(2,), health=None),
        c("open-webui", "ghcr.io/open-webui/open-webui:main", 9000, project="chat"),
        c("congat-web", "congat:latest", 8101, health=None, project="congat"),
        c("old-demo", "demo:0.1", None, state="exited"),
    ]
    models = [
        {"id": "google/gemma-4-31b-it", "container": "nim-gemma4", "port": 8000, "kind": "openai",
         "max_len": 131072, "auth": False},
    ]
    routes = [
        {"url": f"https://{fqdn}:9000/", "port": 9000, "container": "open-webui"},
        {"url": f"https://{fqdn}/congat/", "port": 8101, "container": "congat-web"},
        {"url": f"https://{fqdn}/v1/", "port": 8000, "container": "nim-gemma4"},
    ]
    return {"containers_status": "ok", "containers": containers, "models": models, "models_ts": now,
            "routes_source": "nginx", "routes": routes}


def backfill(store: Store, cfg, now: float) -> None:
    """Fill every tier with synthetic history up to `now` (only into an empty store)."""
    if store.last_bucket() is not None:
        return
    from .clock import FakeClock

    tiers: tuple[Tier, ...] = cfg.tiers
    a = tiers[0].step
    fine_end = int(now // a) * a
    clock = FakeClock(fine_end)
    fc = FakeCollectors(cfg, clock)
    rows = []
    for tier in tiers:
        hi = (fine_end // tier.step) * tier.step
        n = int(tier.step // cfg.interval)
        for w in range(hi - tier.keep * tier.step, hi, tier.step):
            clock.set_wall(w + tier.step / 2)
            s = fc.sample()
            vals = registry.series_values(s.sample["host"], s.sample["mounts"], s.gpus,
                                          s.sample["nics"], s.sample["disks"])
            for key, v in vals.items():
                if v is None:
                    continue
                spread = abs(v) * 0.15 + 1
                rows.append((tier.index, key, w, n, v, v + spread, max(0.0, v - spread)))
    store.load_rows(rows, fine_end, last_a=fine_end - a)
