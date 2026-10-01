"""Slow-changing host facts for host.json: OS, kernel, CPU model and topology."""

from __future__ import annotations

import os
import platform

from .section import section

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None


def _os_name(hostfs: str) -> str | None:
    for path in (os.path.join(hostfs, "etc/os-release"), "/etc/os-release"):
        if os.path.exists(path):
            with open(path) as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        return line.split("=", 1)[1].strip().strip('"') or None
            break
    if platform.system() == "Darwin":
        return "macOS " + platform.mac_ver()[0]
    return None


def _cpu(procfs: str) -> dict:
    model = None
    sockets = set()
    path = os.path.join(procfs, "cpuinfo")
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                key, _, value = line.partition(":")
                key = key.strip()
                if key == "model name" and model is None:
                    model = value.strip()
                elif key == "physical id":
                    sockets.add(value.strip())
    if model is None:
        model = platform.processor() or None
    freq = psutil.cpu_freq() if psutil is not None else None
    return {
        "model": model,
        "sockets": len(sockets) or None,
        "cores": psutil.cpu_count(logical=False) if psutil is not None else None,
        "threads": psutil.cpu_count(logical=True) if psutil is not None else os.cpu_count(),
        "max_mhz": int(freq.max) if freq and freq.max else None,
    }


def collect(hostfs: str, procfs: str) -> dict:
    cpu = section(
        "facts:cpu",
        lambda: _cpu(procfs),
        {"model": None, "sockets": None, "cores": None, "threads": None, "max_mhz": None},
    )
    return {
        "os": section("facts:os", lambda: _os_name(hostfs), None),
        "kernel": section("facts:kernel", lambda: platform.release() or None, None),
        "cpu": cpu,
        "boot_ts": section("facts:boot", lambda: int(psutil.boot_time()), None),
    }
