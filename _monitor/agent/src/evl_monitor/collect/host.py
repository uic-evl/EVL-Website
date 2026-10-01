"""Host CPU, load, memory, network, disk I/O, mounts, processes and logins.

Inside the container, /proc/stat, /proc/meminfo, /proc/loadavg and /proc/diskstats
already describe the whole host. Network counters are per network namespace, so they
are read from /proc/1/net/dev, which with `pid: host` is the host's init process; the
host's mount table is /proc/1/mounts for the same reason.
"""

from __future__ import annotations

import os
import re
import struct

from ..config import Config
from ..rates import Rates
from .section import section

try:
    import psutil
except ImportError:  # pragma: no cover - psutil is a hard dependency
    psutil = None

GIB = 1024**3
MB = 1_000_000
SECTOR = 512

WHOLE_DISK_RE = re.compile(r"^(nvme\d+n\d+|sd[a-z]+|vd[a-z]+|xvd[a-z]+|hd[a-z]+)$")
VIRTUAL_NIC_RE = re.compile(
    r"^(lo|docker\d*|veth.*|br-.*|virbr.*|cni.*|flannel.*|cali.*|tun.*|tap.*|tailscale.*|wg.*|zt.*|vxlan.*|kube.*)$"
)
NIC_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,15}$")
MOUNT_PATH_RE = re.compile(r"^/[A-Za-z0-9._/-]{0,63}$")

# local filesystems only: a statvfs on a dead network mount can block forever
LOCAL_FS = {"ext2", "ext3", "ext4", "xfs", "btrfs", "zfs", "f2fs", "bcachefs", "jfs", "reiserfs"}
SKIP_MOUNT_PREFIXES = ("/boot", "/snap", "/var/snap", "/var/lib/docker", "/var/lib/containerd",
                       "/var/lib/kubelet", "/run", "/proc", "/sys", "/dev", "/tmp")
MAX_MOUNTS = 8
MAX_NICS = 16
MAX_DISKS = 32

UTMP_RECORD = 384  # glibc x86_64 struct utmp
USER_PROCESS = 7

CPU_SENSORS = ("coretemp", "k10temp", "zenpower", "cpu_thermal", "acpitz")

HOST_KEYS = (
    "cpu_pct", "cpu_user_pct", "cpu_system_pct", "cpu_iowait_pct", "cpu_steal_pct", "cores",
    "load1", "load5", "load15",
    "mem_pct", "mem_used_gib", "mem_total_gib", "mem_cached_gib",
    "swap_pct", "swap_used_gib", "swap_total_gib",
    "net_rx_mbs", "net_tx_mbs", "disk_r_mbs", "disk_w_mbs", "disk_r_iops", "disk_w_iops",
    "procs", "procs_running", "procs_blocked", "users", "containers", "cpu_temp_c",
)
EMPTY_HOST = {k: None for k in HOST_KEYS}


def mount_label(path: str, taken: set[str]) -> str:
    base = "root" if path == "/" else re.sub(r"[^a-z0-9_-]", "_", path.strip("/").lower().replace("/", "_"))
    base = (base or "root")[:16]
    label, n = base, 2
    while label in taken:
        suffix = f"_{n}"
        label = base[: 16 - len(suffix)] + suffix
        n += 1
    return label


class HostCollector:
    def __init__(self, cfg: Config, monotonic):
        self.cfg = cfg
        self.monotonic = monotonic
        self.rates = Rates()
        self._primed = False
        self._mounts: tuple[tuple[str, str], ...] = cfg.mounts
        self._mounts_at = -1e9
        if psutil is not None:
            for fn in (lambda: psutil.cpu_percent(interval=None),
                       lambda: psutil.cpu_percent(interval=None, percpu=True),
                       lambda: psutil.cpu_times_percent(interval=None)):
                try:
                    fn()  # baselines for the first real reading
                except Exception:  # noqa: BLE001
                    pass

    def _p(self, *parts: str) -> str:
        return os.path.join(self.cfg.procfs, *parts)

    # cpu, load, memory ------------------------------------------------------

    def _cpu(self) -> dict:
        # interval=None is non-blocking: the average since the previous call
        pct = float(psutil.cpu_percent(interval=None))
        times = psutil.cpu_times_percent(interval=None)
        primed = self._primed
        return {
            "cpu_pct": pct if primed else None,
            "cpu_user_pct": (times.user + getattr(times, "nice", 0.0)) if primed else None,
            "cpu_system_pct": (times.system + getattr(times, "irq", 0.0) + getattr(times, "softirq", 0.0))
            if primed else None,
            "cpu_iowait_pct": getattr(times, "iowait", None) if primed else None,
            "cpu_steal_pct": getattr(times, "steal", None) if primed else None,
            "cores": psutil.cpu_count(logical=True),
        }

    def _per_core(self) -> list:
        per = psutil.cpu_percent(interval=None, percpu=True)
        return [round(float(x), 0) for x in per] if self._primed else []

    def _load(self) -> dict:
        l1, l5, l15 = os.getloadavg()
        return {"load1": l1, "load5": l5, "load15": l15}

    def _memory(self) -> dict:
        vm = psutil.virtual_memory()
        sw = psutil.swap_memory()
        used = vm.total - vm.available
        cached = getattr(vm, "cached", 0) + getattr(vm, "buffers", 0)
        return {
            "mem_pct": used / vm.total * 100 if vm.total else None,
            "mem_used_gib": used / GIB,
            "mem_total_gib": vm.total / GIB,
            "mem_cached_gib": cached / GIB,
            "swap_pct": sw.used / sw.total * 100 if sw.total else None,
            "swap_used_gib": sw.used / GIB,
            "swap_total_gib": sw.total / GIB,
        }

    # processes, logins, temperature ---------------------------------------

    def _procs(self) -> dict:
        procs = sum(1 for d in os.listdir(self.cfg.procfs) if d.isdigit())
        running = blocked = None
        with open(self._p("stat")) as f:
            for line in f:
                if line.startswith("procs_running"):
                    running = int(line.split()[1])
                elif line.startswith("procs_blocked"):
                    blocked = int(line.split()[1])
        return {"procs": procs, "procs_running": running, "procs_blocked": blocked}

    def _users(self) -> dict:
        """Login sessions counted from the host's utmp (a count only, no names)."""
        for rel in ("run/utmp", "var/run/utmp"):
            path = os.path.join(self.cfg.hostfs, rel)
            if os.path.isfile(path) and not os.path.islink(path):
                with open(path, "rb") as f:
                    data = f.read(UTMP_RECORD * 4096)
                n = 0
                for off in range(0, len(data) - UTMP_RECORD + 1, UTMP_RECORD):
                    (ut_type,) = struct.unpack_from("<h", data, off)
                    if ut_type == USER_PROCESS:
                        n += 1
                return {"users": n}
        return {"users": None}

    def _cpu_temp(self) -> dict:
        temps = psutil.sensors_temperatures() if hasattr(psutil, "sensors_temperatures") else {}
        readings = [t.current for name in CPU_SENSORS for t in temps.get(name, []) if t.current]
        return {"cpu_temp_c": max(readings) if readings else None}

    # network ------------------------------------------------------------------

    def _physical(self, iface: str) -> bool:
        if self.cfg.net_ifaces:
            return iface in self.cfg.net_ifaces
        sysnet = os.path.join(self.cfg.hostfs, "sys/class/net")
        if os.path.isdir(sysnet):
            return os.path.exists(os.path.join(sysnet, iface, "device"))
        return not VIRTUAL_NIC_RE.match(iface)

    def _net_counters(self) -> dict[str, tuple[float, float]]:
        path = self._p("1/net/dev")
        out: dict[str, tuple[float, float]] = {}
        if os.path.exists(path):
            with open(path) as f:
                for line in f.readlines()[2:]:
                    name, _, rest = line.partition(":")
                    name = name.strip()
                    fields = rest.split()
                    if len(fields) < 9 or not NIC_NAME_RE.match(name) or not self._physical(name):
                        continue
                    out[name] = (float(fields[0]), float(fields[8]))
        else:  # not Linux (development): psutil sees this machine's NICs
            for name, c in psutil.net_io_counters(pernic=True).items():
                if NIC_NAME_RE.match(name) and self._physical(name):
                    out[name] = (float(c.bytes_recv), float(c.bytes_sent))
        return dict(sorted(out.items())[:MAX_NICS])

    def _net(self) -> tuple[dict, dict]:
        now = self.monotonic()
        nics = {}
        rx_total = tx_total = None
        for name, (rx, tx) in self._net_counters().items():
            r = self.rates.rate(f"rx:{name}", rx, now)
            t = self.rates.rate(f"tx:{name}", tx, now)
            nics[name] = {"rx_mbs": r / MB if r is not None else None,
                          "tx_mbs": t / MB if t is not None else None}
            if r is not None:
                rx_total = (rx_total or 0.0) + r
            if t is not None:
                tx_total = (tx_total or 0.0) + t
        host = {"net_rx_mbs": rx_total / MB if rx_total is not None else None,
                "net_tx_mbs": tx_total / MB if tx_total is not None else None}
        return host, nics

    # disk -----------------------------------------------------------------------

    def _disk_counters(self) -> dict[str, tuple[float, float, float, float, float]]:
        """name -> (read bytes, write bytes, reads, writes, io ms)."""
        path = self._p("diskstats")
        out = {}
        if os.path.exists(path):
            with open(path) as f:
                for line in f:
                    x = line.split()
                    if len(x) < 13 or not WHOLE_DISK_RE.match(x[2]):
                        continue
                    out[x[2]] = (float(x[5]) * SECTOR, float(x[9]) * SECTOR, float(x[3]), float(x[7]), float(x[12]))
        else:
            for name, c in (psutil.disk_io_counters(perdisk=True) or {}).items():
                if re.fullmatch(r"[a-z0-9]{1,15}", name):
                    out[name] = (float(c.read_bytes), float(c.write_bytes), float(c.read_count),
                                 float(c.write_count), float(getattr(c, "busy_time", 0)))
        return dict(sorted(out.items())[:MAX_DISKS])

    def _disk(self) -> tuple[dict, dict]:
        now = self.monotonic()
        disks = {}
        totals = {"r": None, "w": None, "ri": None, "wi": None}
        for name, (rb, wb, rn, wn, ms) in self._disk_counters().items():
            r = self.rates.rate(f"rb:{name}", rb, now)
            w = self.rates.rate(f"wb:{name}", wb, now)
            ri = self.rates.rate(f"rn:{name}", rn, now)
            wi = self.rates.rate(f"wn:{name}", wn, now)
            busy = self.rates.rate(f"ms:{name}", ms, now)
            disks[name] = {
                "r_mbs": r / MB if r is not None else None,
                "w_mbs": w / MB if w is not None else None,
                "busy_pct": min(100.0, busy / 10) if busy is not None else None,  # ms per s -> %
            }
            for k, v in (("r", r), ("w", w), ("ri", ri), ("wi", wi)):
                if v is not None:
                    totals[k] = (totals[k] or 0.0) + v
        host = {
            "disk_r_mbs": totals["r"] / MB if totals["r"] is not None else None,
            "disk_w_mbs": totals["w"] / MB if totals["w"] is not None else None,
            "disk_r_iops": totals["ri"],
            "disk_w_iops": totals["wi"],
        }
        return host, disks

    # mounts -----------------------------------------------------------------------

    def discover_mounts(self) -> tuple[tuple[str, str], ...]:
        """Local filesystems from the host's mount table, one per device, at most 8."""
        found: list[tuple[str, str]] = []
        seen_dev: set[str] = set()
        with open(self._p("1/mounts")) as f:
            rows = [line.split() for line in f]
        rows = [r for r in rows if len(r) >= 3]
        rows.sort(key=lambda r: (r[1] != "/", len(r[1]), r[1]))
        taken: set[str] = set()
        for dev, path, fstype, *_ in rows:
            path = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), path)  # \040 is a space
            if fstype not in LOCAL_FS or dev in seen_dev or not MOUNT_PATH_RE.match(path):
                continue
            if path != "/" and path.startswith(SKIP_MOUNT_PREFIXES):
                continue
            seen_dev.add(dev)
            label = mount_label(path, taken)
            taken.add(label)
            found.append((label, path))
            if len(found) >= MAX_MOUNTS:
                break
        return tuple(found) or (("root", "/"),)

    def mounts_config(self) -> tuple[tuple[str, str], ...]:
        if not self.cfg.mounts_auto:
            return self.cfg.mounts
        now = self.monotonic()
        if now - self._mounts_at > 300:
            self._mounts = section("mounts:discover", self.discover_mounts, self._mounts or (("root", "/"),))
            self._mounts_at = now
        return self._mounts

    def _mount_path(self, path: str) -> str:
        root = self.cfg.hostfs
        if os.path.isdir(root):
            return os.path.join(root, path.lstrip("/")) if path != "/" else root
        return path

    def mount(self, path: str) -> dict:
        st = os.statvfs(self._mount_path(path))
        total = st.f_blocks * st.f_frsize
        used = (st.f_blocks - st.f_bfree) * st.f_frsize
        avail = st.f_bavail * st.f_frsize
        denom = used + avail
        return {
            "path": path,
            "used_pct": used / denom * 100 if denom else None,
            "used_gib": used / GIB,
            "total_gib": total / GIB,
        }

    # sample ---------------------------------------------------------------------------

    def sample(self) -> dict:
        host = dict(EMPTY_HOST)
        per_core: list = []
        if psutil is not None:
            host.update(section("cpu", self._cpu, {k: None for k in (
                "cpu_pct", "cpu_user_pct", "cpu_system_pct", "cpu_iowait_pct", "cpu_steal_pct", "cores")}))
            per_core = section("cpu:per_core", self._per_core, [])
            host.update(section("memory", self._memory, {k: None for k in (
                "mem_pct", "mem_used_gib", "mem_total_gib", "mem_cached_gib",
                "swap_pct", "swap_used_gib", "swap_total_gib")}))
            host.update(section("temp", self._cpu_temp, {"cpu_temp_c": None}))
        host.update(section("load", self._load, {"load1": None, "load5": None, "load15": None}))
        host.update(section("procs", self._procs, {"procs": None, "procs_running": None, "procs_blocked": None}))
        host.update(section("users", self._users, {"users": None}))
        net_host, nics = section("net", self._net, ({"net_rx_mbs": None, "net_tx_mbs": None}, {}))
        host.update(net_host)
        disk_host, disks = section("disk", self._disk, (
            {"disk_r_mbs": None, "disk_w_mbs": None, "disk_r_iops": None, "disk_w_iops": None}, {}))
        host.update(disk_host)
        mounts = {}
        for label, path in self.mounts_config():
            empty = {"path": path, "used_pct": None, "used_gib": None, "total_gib": None}
            mounts[label] = section(f"mount:{label}", lambda p=path: self.mount(p), empty)
        self._primed = True
        return {"host": host, "per_core": per_core, "mounts": mounts, "nics": nics, "disks": disks}
