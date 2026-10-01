"""Who holds a GPU: owner uid, process name and container id for an NVML pid.

Reads only /proc/<pid>/status (the Uid line), /proc/<pid>/comm and /proc/<pid>/cgroup.
It never opens cmdline or environ: arguments and environment variables can carry
secrets, and the page is public.
"""

from __future__ import annotations

import os
import re

CONTAINER_ID_RE = re.compile(r"[0-9a-f]{64}")
NAME_BAD_RE = re.compile(r"[^A-Za-z0-9._:+ -]")


def _read(procfs: str, pid: int, name: str) -> str | None:
    try:
        with open(os.path.join(procfs, str(pid), name)) as f:
            return f.read()
    except OSError:
        return None


def uid_of(procfs: str, pid: int) -> int | None:
    status = _read(procfs, pid, "status")
    if status is None:
        return None
    for line in status.splitlines():
        if line.startswith("Uid:"):
            fields = line.split()
            if len(fields) >= 2 and fields[1].isdigit():
                return int(fields[1])
    return None


def comm_of(procfs: str, pid: int) -> str | None:
    comm = _read(procfs, pid, "comm")
    if comm is None:
        return None
    clean = NAME_BAD_RE.sub("_", comm.strip())[:15]
    return clean or None


def container_id_of(procfs: str, pid: int) -> str | None:
    """The 64-hex container id in the cgroup path, for Docker (systemd or cgroupfs
    drivers) and containerd alike; None for a process on the host itself."""
    cgroup = _read(procfs, pid, "cgroup")
    if cgroup is None:
        return None
    for line in cgroup.splitlines():
        m = CONTAINER_ID_RE.search(line)
        if m:
            return m.group(0)
    return None
