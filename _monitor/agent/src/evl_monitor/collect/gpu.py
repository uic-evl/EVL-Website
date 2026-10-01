"""NVIDIA GPUs through NVML, sampled on a thread of its own.

A GPU that hangs inside a driver call (an Xid 79, a reset) must not stall host
sampling, so the sampler thread publishes snapshots with their age and the main loop
only reads the latest one.
"""

from __future__ import annotations

import logging
import threading
import time

log = logging.getLogger(__name__)

GIB = 1024**3

THROTTLE_BITS = (
    (0x1, "gpu_idle"),
    (0x2, "app_clocks"),
    (0x4, "sw_power_cap"),
    (0x8, "hw_slowdown"),
    (0x10, "sync_boost"),
    (0x20, "sw_thermal"),
    (0x40, "hw_thermal"),
    (0x80, "hw_power_brake"),
    (0x100, "display_clocks"),
)
THROTTLE_VOCAB = tuple(name for _, name in THROTTLE_BITS)

GPU_STATUS = ("ok", "absent", "disabled", "nvml_error", "stalled")

EMPTY_GPU = {
    "util_pct": None,
    "mem_util_pct": None,
    "mem_pct": None,
    "mem_used_gib": None,
    "mem_total_gib": None,
    "power_w": None,
    "power_limit_w": None,
    "temp_c": None,
    "sm_mhz": None,
    "mem_mhz": None,
    "fan_pct": None,
    "pcie_rx_mbs": None,
    "pcie_tx_mbs": None,
    "enc_pct": None,
    "dec_pct": None,
    "ecc_uncorrected": None,
    "procs": None,
    "mig": None,
    "throttle": [],
    "throttle_power": None,
    "throttle_thermal": None,
}

POWER_BITS = 0x4 | 0x80  # sw power cap, hw power brake
THERMAL_BITS = 0x8 | 0x20 | 0x40  # hw slowdown, sw thermal, hw thermal
KB = 1024


def throttle_names(mask: int | None) -> list[str]:
    if not mask:
        return []
    return [name for bit, name in THROTTLE_BITS if mask & bit]


class GpuSnapshot:
    def __init__(self, status: str, gpus: list[dict], procs: dict[int, list[tuple[int, int | None, str]]],
                 facts: dict):
        self.status = status
        self.gpus = gpus  # per-GPU readings
        self.procs = procs  # gpu index -> [(pid, used_bytes, kind)]
        self.facts = facts  # driver, cuda, devices


EMPTY_FACTS = {"driver": None, "cuda": None, "devices": []}


class NvmlBackend:
    """Thin wrapper so tests can substitute a fake pynvml module."""

    def __init__(self, nvml=None):
        if nvml is None:
            import pynvml as nvml  # nvidia-ml-py
        self.n = nvml

    def call(self, fn, *args, default=None):
        try:
            return getattr(self.n, fn)(*args)
        except self.n.NVMLError as exc:
            lost = getattr(self.n, "NVMLError_GpuIsLost", None)
            if lost is not None and isinstance(exc, lost):
                raise
            return default


class GpuSampler(threading.Thread):
    def __init__(self, interval: float, mode: str, monotonic=time.monotonic, backend_factory=NvmlBackend):
        super().__init__(name="gpu-sampler", daemon=True)
        self.interval = interval
        self.mode = mode
        self.monotonic = monotonic
        self.backend_factory = backend_factory
        self.backend: NvmlBackend | None = None
        self._next_init = 0.0
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._latest: tuple[float, GpuSnapshot] | None = None
        initial = "disabled" if mode == "off" else "nvml_error"
        self._latest = (self.monotonic(), GpuSnapshot(initial, [], {}, dict(EMPTY_FACTS)))

    def stop(self) -> None:
        self._stop.set()

    def latest(self, max_age: float) -> GpuSnapshot:
        with self._lock:
            at, snap = self._latest
        if self.mode != "off" and self.monotonic() - at > max_age:
            gpus = [dict(EMPTY_GPU, i=g["i"]) for g in snap.gpus]
            return GpuSnapshot("stalled", gpus, {}, snap.facts)
        return snap

    def run(self) -> None:
        if self.mode == "off":
            return
        while not self._stop.is_set():
            snap = self.sample_once()
            with self._lock:
                self._latest = (self.monotonic(), snap)
            self._stop.wait(self.interval)

    # sampling -------------------------------------------------------------

    def _ensure_init(self) -> str | None:
        if self.backend is not None:
            return None
        now = self.monotonic()
        if now < self._next_init:
            return "nvml_error"
        self._next_init = now + 60
        try:
            backend = self.backend_factory()
            backend.n.nvmlInit()
        except ImportError:
            return "absent"
        except Exception as exc:  # noqa: BLE001
            name = type(exc).__name__
            log.info("NVML init failed: %s", name)
            # no driver library in the container means no GPU here, not a failure
            return "absent" if "LibraryNotFound" in name or "DriverNotLoaded" in name else "nvml_error"
        self.backend = backend
        return None

    def sample_once(self) -> GpuSnapshot:
        err = self._ensure_init()
        if err:
            return GpuSnapshot(err, [], {}, dict(EMPTY_FACTS))
        b = self.backend
        assert b is not None
        try:
            count = b.n.nvmlDeviceGetCount()
        except Exception:  # noqa: BLE001
            self._reset()
            return GpuSnapshot("nvml_error", [], {}, dict(EMPTY_FACTS))
        gpus, procs, devices = [], {}, []
        for i in range(min(count, 16)):
            g, p, dev = self._one(b, i)
            gpus.append(g)
            procs[i] = p
            devices.append(dev)
        driver = b.call("nvmlSystemGetDriverVersion")
        cuda_raw = b.call("nvmlSystemGetCudaDriverVersion")
        cuda = f"{cuda_raw // 1000}.{(cuda_raw % 1000) // 10}" if isinstance(cuda_raw, int) else None
        facts = {"driver": _text(driver), "cuda": cuda, "devices": devices}
        return GpuSnapshot("ok" if count else "absent", gpus, procs, facts)

    def _reset(self) -> None:
        try:
            if self.backend is not None:
                self.backend.n.nvmlShutdown()
        except Exception:  # noqa: BLE001
            pass
        self.backend = None

    def _one(self, b: NvmlBackend, i: int) -> tuple[dict, list, dict]:
        n = b.n
        g = dict(EMPTY_GPU, i=i, throttle=[])
        dev = {"i": i, "name": None, "mem_total_gib": None, "power_limit_w": None, "mig": None}
        procs: list[tuple[int, int | None, str]] = []
        try:
            h = n.nvmlDeviceGetHandleByIndex(i)
            dev["name"] = _text(b.call("nvmlDeviceGetName", h))
            mig = b.call("nvmlDeviceGetMigMode", h)
            mig_on = bool(mig and mig[0] == getattr(n, "NVML_DEVICE_MIG_ENABLE", 1))
            g["mig"] = dev["mig"] = mig_on
            util = b.call("nvmlDeviceGetUtilizationRates", h)
            g["util_pct"] = int(util.gpu) if util is not None else None
            g["mem_util_pct"] = int(util.memory) if util is not None else None
            mem = b.call("nvmlDeviceGetMemoryInfo", h)
            if mem is not None and mem.total:
                g["mem_used_gib"] = mem.used / GIB
                g["mem_total_gib"] = dev["mem_total_gib"] = mem.total / GIB
                g["mem_pct"] = mem.used / mem.total * 100
            power = b.call("nvmlDeviceGetPowerUsage", h)
            g["power_w"] = power / 1000 if power is not None else None
            limit = b.call("nvmlDeviceGetEnforcedPowerLimit", h)
            g["power_limit_w"] = dev["power_limit_w"] = limit / 1000 if limit is not None else None
            g["temp_c"] = b.call("nvmlDeviceGetTemperature", h, getattr(n, "NVML_TEMPERATURE_GPU", 0))
            g["sm_mhz"] = b.call("nvmlDeviceGetClockInfo", h, getattr(n, "NVML_CLOCK_SM", 1))
            g["mem_mhz"] = b.call("nvmlDeviceGetClockInfo", h, getattr(n, "NVML_CLOCK_MEM", 2))
            g["fan_pct"] = b.call("nvmlDeviceGetFanSpeed", h)  # NotSupported on passive cards
            rx = b.call("nvmlDeviceGetPcieThroughput", h, getattr(n, "NVML_PCIE_UTIL_RX_BYTES", 1))
            tx = b.call("nvmlDeviceGetPcieThroughput", h, getattr(n, "NVML_PCIE_UTIL_TX_BYTES", 0))
            g["pcie_rx_mbs"] = rx * KB / 1e6 if isinstance(rx, (int, float)) else None
            g["pcie_tx_mbs"] = tx * KB / 1e6 if isinstance(tx, (int, float)) else None
            enc = b.call("nvmlDeviceGetEncoderUtilization", h)
            dec = b.call("nvmlDeviceGetDecoderUtilization", h)
            g["enc_pct"] = enc[0] if enc else None
            g["dec_pct"] = dec[0] if dec else None
            g["ecc_uncorrected"] = b.call(
                "nvmlDeviceGetTotalEccErrors", h,
                getattr(n, "NVML_MEMORY_ERROR_TYPE_UNCORRECTED", 1), getattr(n, "NVML_VOLATILE_ECC", 0))
            mask = b.call("nvmlDeviceGetCurrentClocksEventReasons", h)
            if mask is None:
                mask = b.call("nvmlDeviceGetCurrentClocksThrottleReasons", h)
            g["throttle"] = throttle_names(mask)
            if isinstance(mask, int):
                g["throttle_power"] = 1 if mask & POWER_BITS else 0
                g["throttle_thermal"] = 1 if mask & THERMAL_BITS else 0
            if not mig_on:
                seen: set[int] = set()
                for fn, kind in (("nvmlDeviceGetComputeRunningProcesses", "compute"),
                                 ("nvmlDeviceGetGraphicsRunningProcesses", "graphics")):
                    for p in b.call(fn, h, default=[]) or []:
                        if p.pid in seen:
                            continue
                        seen.add(p.pid)
                        used = getattr(p, "usedGpuMemory", None)
                        procs.append((int(p.pid), int(used) if isinstance(used, int) else None, kind))
                g["procs"] = len(procs)
        except Exception as exc:  # noqa: BLE001 - one lost GPU nulls only itself
            log.info("GPU %d unavailable: %s", i, type(exc).__name__)
            g = dict(EMPTY_GPU, i=i, throttle=[])
            procs = []
        return g, procs, dev


def _text(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, bytes):
        v = v.decode("utf-8", "replace")
    return str(v)
