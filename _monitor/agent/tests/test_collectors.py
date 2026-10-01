"""Collector fault injection: every failure becomes nulls, never an exception."""

import os
import threading
import time
import types

import pytest

from evl_monitor.collect import gpu as gpu_mod
from evl_monitor.collect import host as host_mod
from evl_monitor.collect.containers import ContainerNames
from evl_monitor.collect.host import HostCollector
from evl_monitor.collect.procs import comm_of, container_id_of, uid_of
from evl_monitor.collect.section import section
from evl_monitor.collect.users import UserResolver
from evl_monitor.config import Config
from evl_monitor.rates import Rates

from .conftest import env

CID = "a" * 64


@pytest.fixture
def procfs(tmp_path):
    root = tmp_path / "proc"
    (root / "1" / "net").mkdir(parents=True)
    (root / "1" / "net" / "dev").write_text(
        "Inter-|   Receive  |  Transmit\n face |bytes packets|bytes\n"
        "    lo: 1000 10 0 0 0 0 0 0 1000 10 0 0 0 0 0 0\n"
        "  eno1: 5000000 10 0 0 0 0 0 0 2000000 10 0 0 0 0 0 0\n"
        "docker0: 999 1 0 0 0 0 0 0 999 1 0 0 0 0 0 0\n")
    (root / "diskstats").write_text(
        "   8       0 sda 10 0 2048 0 10 0 4096 0 0 0 0\n"
        "   8       1 sda1 10 0 2048 0 10 0 4096 0 0 0 0\n"
        " 259       0 nvme0n1 10 0 1000 0 10 0 1000 0 0 0 0\n")
    (root / "stat").write_text("cpu  1 2 3 4\nprocs_running 7\nprocs_blocked 1\n")
    (root / "1" / "mounts").write_text(
        "/dev/nvme0n1p2 / ext4 rw 0 0\n"
        "tmpfs /run tmpfs rw 0 0\n"
        "/dev/nvme0n1p1 /boot/efi vfat rw 0 0\n"
        "/dev/md0 /data xfs rw 0 0\n"
        "/dev/md0 /srv/data-bind xfs rw 0 0\n"
        "overlay /var/lib/docker/overlay2/x/merged overlay rw 0 0\n"
        "nas:/export /mnt/nas nfs4 rw 0 0\n"
        "/dev/sdb1 /mnt/my\\040disk ext4 rw 0 0\n"
        "/dev/sdc1 /scratch/fast ext4 rw 0 0\n")
    for pid, uid, comm, cgroup in [
        (100, 1001, "python3", f"0::/system.slice/docker-{CID}.scope\n"),
        (200, 0, "Xorg", "0::/init.scope\n"),
        (300, 1002, "weird\x01name/../", f"0::/../{'b' * 64}\n"),
    ]:
        d = root / str(pid)
        d.mkdir()
        (d / "status").write_text(f"Name:\t{comm}\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n")
        (d / "comm").write_text(comm + "\n")
        (d / "cgroup").write_text(cgroup)
        (d / "cmdline").write_text("python3\0--token=SECRET\0")
    return str(root)


def test_section_returns_fresh_fallback():
    fb = {"x": None, "l": []}
    out = section("t", lambda: 1 / 0, fb)
    out["l"].append(1)
    assert section("t", lambda: 1 / 0, fb) == {"x": None, "l": []}


def test_rates_reset_and_first_reading():
    r = Rates()
    assert r.rate("a", 100, 0.0) is None
    assert r.rate("a", 200, 1.0) == 100
    assert r.rate("a", 50, 2.0) is None  # counter reset
    assert r.rate("a", 150, 3.0) == 100
    assert r.rate("b", 1, 5.0) is None and r.rate("b", 2, 5.0) is None  # dt == 0


def test_net_and_disk_from_procfs(procfs, tmp_path):
    cfg = Config.from_env(env(MONITOR_PROCFS=procfs, MONITOR_HOSTFS=str(tmp_path / "nohostfs")))
    t = [0.0]
    h = HostCollector(cfg, lambda: t[0])
    h.sample()
    dev = os.path.join(procfs, "1/net/dev")
    text = open(dev).read().replace("5000000", "7000000").replace("2000000", "3000000")
    open(dev, "w").write(text)
    ds = os.path.join(procfs, "diskstats")
    stats = open(ds).read().replace(" 2048 ", " 4096 ")
    open(ds, "w").write(stats)
    t[0] = 1.0
    s = h.sample()
    host = s["host"]
    assert host["net_rx_mbs"] == pytest.approx(2.0)  # 2 MB over 1 s, eno1 only
    assert host["net_tx_mbs"] == pytest.approx(1.0)
    assert set(s["nics"]) == {"eno1"} and s["nics"]["eno1"]["rx_mbs"] == pytest.approx(2.0)
    # sda read 2048 more sectors (sda1 is a partition and is not double counted)
    assert host["disk_r_mbs"] == pytest.approx(2048 * 512 / 1e6)
    assert set(s["disks"]) == {"sda", "nvme0n1"} and s["disks"]["nvme0n1"]["r_mbs"] == 0
    assert host["procs"] == 4 and host["procs_running"] == 7 and host["procs_blocked"] == 1


def test_mount_discovery(procfs, tmp_path):
    cfg = Config.from_env(env(MONITOR_PROCFS=procfs, MONITOR_HOSTFS=str(tmp_path)))
    assert cfg.mounts_auto
    found = HostCollector(cfg, time.monotonic).discover_mounts()
    # local filesystems, one per device, no /boot, /run, docker layers, NFS or odd paths
    assert found == (("root", "/"), ("data", "/data"), ("scratch_fast", "/scratch/fast"))


def test_mount_labels_are_unique():
    from evl_monitor.collect.host import mount_label
    taken = {"data"}
    assert mount_label("/data", taken) == "data_2"
    assert mount_label("/a/very/long/path/name/here", set()) == "a_very_long_path"


def test_users_counted_from_host_utmp(tmp_path):
    import struct

    from evl_monitor.collect.host import UTMP_RECORD
    run = tmp_path / "run"
    run.mkdir()
    rec = bytearray(UTMP_RECORD)
    data = b""
    for ut_type in (7, 7, 8, 2):  # two logins, one dead process, one boot record
        struct.pack_into("<h", rec, 0, ut_type)
        data += bytes(rec)
    (run / "utmp").write_bytes(data)
    cfg = Config.from_env(env(MONITOR_HOSTFS=str(tmp_path)))
    assert HostCollector(cfg, time.monotonic)._users() == {"users": 2}


def test_psutil_raising_gives_nulls_others_survive(monkeypatch, procfs, tmp_path):
    class Boom:
        def __getattr__(self, name):
            raise RuntimeError("psutil broke")
    cfg = Config.from_env(env(MONITOR_PROCFS=procfs, MONITOR_HOSTFS=str(tmp_path)))
    h = HostCollector(cfg, time.monotonic)
    monkeypatch.setattr(host_mod, "psutil", Boom())
    s = h.sample()
    assert s["host"]["cpu_pct"] is None and s["host"]["mem_pct"] is None
    assert s["host"]["load1"] is not None  # os.getloadavg still works
    assert s["mounts"]["root"]["total_gib"] is not None


def test_missing_mount_is_null(tmp_path):
    cfg = Config.from_env(env(MONITOR_HOSTFS=str(tmp_path), MONITOR_MOUNTS="root:/,gone:/does/not/exist"))
    mounts = HostCollector(cfg, time.monotonic).sample()["mounts"]
    assert mounts["gone"] == {"path": "/does/not/exist", "used_pct": None, "used_gib": None, "total_gib": None}
    assert mounts["root"]["used_pct"] is not None


def test_procs_reads(procfs):
    assert uid_of(procfs, 100) == 1001
    assert container_id_of(procfs, 100) == CID
    assert container_id_of(procfs, 200) is None
    assert container_id_of(procfs, 300) == "b" * 64  # private cgroup namespace path
    assert comm_of(procfs, 300) == "weird_name_.._"
    assert uid_of(procfs, 999) is None


def test_users_passwd_reload_and_fallbacks(tmp_path):
    etc = tmp_path / "etc"
    etc.mkdir()
    pw = etc / "passwd"
    pw.write_text("root:x:0:0::/root:/bin/sh\nalice:x:1001:1001::/home/alice:/bin/sh\n")
    r = UserResolver(str(tmp_path), nss=False)
    assert r.name(1001) == "alice" and r.name(5) == "uid 5"
    pw.write_text("root:x:0:0::/root:/bin/sh\nbob:x:1001:1001::/home/bob:/bin/sh\n")
    os.utime(pw, (time.time() + 5, time.time() + 5))
    assert r.name(1001) == "bob"


def test_users_nss_slow_then_cached(tmp_path):
    gate = threading.Event()

    def slow(uid):
        gate.wait(5)
        return "netid@uic.edu"
    r = UserResolver(str(tmp_path), nss=True, budget=0.1, lookup=slow)
    assert r.name(4242) == "uid 4242"  # over budget
    assert r.name(4242) == "uid 4242"  # still pending: no second wait
    gate.set()
    time.sleep(0.2)
    assert r.name(4242) == "netid"  # domain stripped, cached


def test_users_nss_error_and_bad_names(tmp_path):
    def fail(uid):
        raise KeyError(uid)
    assert UserResolver(str(tmp_path), lookup=fail).name(7) == "uid 7"
    assert UserResolver(str(tmp_path), lookup=lambda u: "bad name;").name(8) == "uid 8"


def test_container_names_cache_and_unavailable():
    calls = []

    def fetcher(path):
        calls.append(path)
        return [{"Id": CID, "Names": ["/nim-gemma4"]}]
    t = [0.0]
    c = ContainerNames("/sock", lambda: t[0], fetcher)
    assert c.name(CID) == "nim-gemma4" and c.status == "ok"
    assert c.name(CID) == "nim-gemma4" and len(calls) == 1
    assert c.name("c" * 64) == "c" * 12 and len(calls) == 1  # unknown id within 5 s: no refetch
    t[0] = 31
    c.name(CID)
    assert len(calls) == 2

    def down(path):
        raise OSError("no socket")
    d = ContainerNames("/sock", lambda: 0.0, down)
    assert d.name(CID) == CID[:12] and d.status == "unavailable"
    assert ContainerNames("", lambda: 0.0).name(CID) is None


# NVML ----------------------------------------------------------------------------


class NVMLError(Exception):
    pass


class NVMLError_NotSupported(NVMLError):  # noqa: N801
    pass


class NVMLError_GpuIsLost(NVMLError):  # noqa: N801
    pass


def fake_nvml(count=2, lost=(), mig=(), hang=None, init_error=None):
    n = types.SimpleNamespace()
    n.NVMLError = NVMLError
    n.NVMLError_GpuIsLost = NVMLError_GpuIsLost
    n.NVML_DEVICE_MIG_ENABLE = 1
    n.NVML_TEMPERATURE_GPU = 0
    n.NVML_CLOCK_SM = 1

    def init():
        if init_error:
            raise init_error
    n.nvmlInit = init
    n.nvmlShutdown = lambda: None
    n.nvmlDeviceGetCount = lambda: count
    n.nvmlDeviceGetHandleByIndex = lambda i: i
    n.nvmlDeviceGetName = lambda h: b"NVIDIA H100 80GB HBM3"
    n.nvmlDeviceGetMigMode = lambda h: (1 if h in mig else 0, 0)

    def util(h):
        if hang is not None:
            hang.wait(10)
        if h in lost:
            raise NVMLError_GpuIsLost()
        if h in mig:
            raise NVMLError_NotSupported()
        return types.SimpleNamespace(gpu=90, memory=50)
    n.nvmlDeviceGetUtilizationRates = util
    n.nvmlDeviceGetMemoryInfo = lambda h: types.SimpleNamespace(used=40 * 2**30, total=80 * 2**30)
    n.nvmlDeviceGetPowerUsage = lambda h: 612_000
    n.nvmlDeviceGetEnforcedPowerLimit = lambda h: 700_000
    n.nvmlDeviceGetTemperature = lambda h, s: 61
    n.nvmlDeviceGetClockInfo = lambda h, c: 1980
    n.nvmlDeviceGetCurrentClocksEventReasons = lambda h: 0x4 | 0x20
    n.nvmlDeviceGetComputeRunningProcesses = lambda h: [types.SimpleNamespace(pid=100, usedGpuMemory=70 * 2**30)]
    n.nvmlDeviceGetGraphicsRunningProcesses = lambda h: [types.SimpleNamespace(pid=100, usedGpuMemory=None),
                                                         types.SimpleNamespace(pid=200, usedGpuMemory=None)]
    n.nvmlDeviceGetPcieThroughput = lambda h, which: 2000 if which == 1 else 500
    n.nvmlDeviceGetEncoderUtilization = lambda h: [3, 167000]
    n.nvmlDeviceGetDecoderUtilization = lambda h: [4, 167000]
    n.nvmlDeviceGetTotalEccErrors = lambda h, kind, counter: 0

    def no_fan(h):
        raise NVMLError_NotSupported()
    n.nvmlDeviceGetFanSpeed = no_fan
    n.nvmlSystemGetDriverVersion = lambda: "570.133.20"
    n.nvmlSystemGetCudaDriverVersion = lambda: 12080
    return n


def sampler(nvml, mono=time.monotonic):
    return gpu_mod.GpuSampler(5, "on", mono, backend_factory=lambda: gpu_mod.NvmlBackend(nvml))


def test_gpu_ok():
    snap = sampler(fake_nvml()).sample_once()
    assert snap.status == "ok" and len(snap.gpus) == 2
    g = snap.gpus[0]
    assert g["util_pct"] == 90 and g["power_w"] == 612 and g["mem_pct"] == 50
    assert g["throttle"] == ["sw_power_cap", "sw_thermal"]
    assert g["throttle_power"] == 1 and g["throttle_thermal"] == 1
    assert g["mem_util_pct"] == 50 and g["mem_mhz"] == 1980
    assert g["pcie_rx_mbs"] == pytest.approx(2000 * 1024 / 1e6) and g["enc_pct"] == 3 and g["dec_pct"] == 4
    assert g["ecc_uncorrected"] == 0
    assert g["fan_pct"] is None  # passive datacenter card: NotSupported becomes null
    assert snap.procs[0] == [(100, 70 * 2**30, "compute"), (200, None, "graphics")]  # deduplicated by pid
    assert snap.facts["cuda"] == "12.8" and snap.facts["devices"][0]["name"] == "NVIDIA H100 80GB HBM3"


def test_gpu_init_error_then_retry():
    t = [0.0]
    s = sampler(fake_nvml(init_error=NVMLError("boom")), lambda: t[0])
    assert s.sample_once().status == "nvml_error"
    s.backend_factory = lambda: gpu_mod.NvmlBackend(fake_nvml())
    t[0] = 30
    assert s.sample_once().status == "nvml_error"  # retries only every 60 s
    t[0] = 61
    assert s.sample_once().status == "ok"


def test_gpu_lost_nulls_only_that_gpu():
    snap = sampler(fake_nvml(count=2, lost={1})).sample_once()
    assert snap.gpus[0]["util_pct"] == 90
    assert snap.gpus[1]["util_pct"] is None and snap.gpus[1]["i"] == 1 and snap.procs[1] == []


def test_gpu_mig_has_no_util_and_no_procs():
    snap = sampler(fake_nvml(count=1, mig={0})).sample_once()
    g = snap.gpus[0]
    assert g["mig"] is True and g["util_pct"] is None and g["procs"] is None
    assert g["mem_pct"] == 50  # parent-device memory still reads


def test_gpu_hang_reports_stalled():
    hang = threading.Event()
    t = [0.0]
    s = sampler(fake_nvml(count=1), lambda: t[0])
    s._latest = (0.0, s.sample_once())
    s.backend.n.nvmlDeviceGetUtilizationRates = lambda h: hang.wait(10)
    t[0] = 16  # more than 3 intervals since the last snapshot
    snap = s.latest(max_age=15)
    assert snap.status == "stalled" and snap.gpus[0]["util_pct"] is None
    hang.set()


def test_gpu_off_is_disabled():
    s = gpu_mod.GpuSampler(5, "off")
    assert s.latest(15).status == "disabled"
