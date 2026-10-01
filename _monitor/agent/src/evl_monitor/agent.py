"""The sampling loop: collect, roll up, render, publish."""

from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass, field

from . import days as days_mod
from . import registry, render, schema
from .collect import facts as facts_mod
from .collect.containers import ContainerNames
from .collect.gpu import GpuSampler, GpuSnapshot
from .collect.host import HostCollector
from .collect.procs import comm_of, container_id_of, uid_of
from .collect.section import section
from .collect.services import ServicesSampler
from .collect.users import UserResolver
from .config import Config
from .engine import Engine
from .publish import Publisher
from .store import DAY, Store
from .tiers import SPARK_POINTS, SPARK_TIER, Tier

log = logging.getLogger(__name__)

GIB = 1024**3
MAX_PROCS_PER_GPU = 32
FACTS_EVERY = 600.0
HOST_JSON_EVERY = 60.0
CHECKPOINT_EVERY = 3600.0
USAGE_FLUSH_EVERY = 60.0
DAILY_TIER = 3  # daily.json is built from the 1 h buckets (31 days kept)


@dataclass
class RawSample:
    sample: dict  # host, per_core, mounts, nics, disks (see HostCollector.sample)
    gpu_status: str
    gpus: list[dict]
    gpu_facts: dict
    procs_status: str = "off"
    containers_status: str = "off"
    procs: list[dict] = field(default_factory=list)


class RealCollectors:
    def __init__(self, cfg: Config, clock):
        self.cfg = cfg
        self.host = HostCollector(cfg, clock.monotonic)
        self.gpu = GpuSampler(cfg.interval, "off" if cfg.gpu == "off" else "on", clock.monotonic)
        self.users = UserResolver(cfg.hostfs, cfg.nss, cfg.strip_domain)
        sock = cfg.docker_sock if cfg.procs == "full" else ""
        self.containers = ContainerNames(sock, clock.monotonic)

    def start(self) -> None:
        self.gpu.start()

    def start_services(self, publish, gpu_use) -> None:
        self.services = ServicesSampler(self.containers, self.cfg.hostfs, self.cfg.fqdn, publish, gpu_use)
        self.services.start()

    def stop(self) -> None:
        self.gpu.stop()
        if getattr(self, "services", None) is not None:
            self.services.stop()

    def facts(self) -> dict:
        return facts_mod.collect(self.cfg.hostfs, self.cfg.procfs)

    def sample(self) -> RawSample:
        sample = self.host.sample()
        sample["host"]["containers"] = section("containers", self.containers.count, None)
        snap = self.gpu.latest(max_age=3 * self.cfg.interval)
        status, containers_status, per_gpu = section(
            "procs", lambda: self._procs(snap), ("error", self.containers.status, []))
        return RawSample(sample, snap.status, snap.gpus, snap.facts, status, containers_status, per_gpu)

    def _procs(self, snap: GpuSnapshot) -> tuple[str, str, list[dict]]:
        if self.cfg.procs == "off":
            return "off", "off", []
        if snap.status != "ok":
            return "unsupported", "off", []
        if all(g.get("mig") for g in snap.gpus):
            return "unsupported", "off", []
        if self.cfg.procs == "count":
            return "count", "off", []
        procfs = self.cfg.procfs
        out = []
        for g in snap.gpus:
            i = g["i"]
            rows = []
            for pid, used, kind in snap.procs.get(i, []):
                uid = uid_of(procfs, pid)
                if uid is None:
                    continue  # exited between the NVML listing and this read
                rows.append({
                    "user": self.users.name(uid),
                    "container": self.containers.name(container_id_of(procfs, pid)),
                    "name": comm_of(procfs, pid),
                    "kind": kind,
                    "mem_gib": round(used / GIB, 1) if used is not None else None,
                })
            rows.sort(key=lambda p: -(p["mem_gib"] or 0))
            out.append({"i": i, "more": max(0, len(rows) - MAX_PROCS_PER_GPU),
                        "procs": rows[:MAX_PROCS_PER_GPU]})
        return "ok", self.containers.status, out


def cache_control(path: str, tiers: tuple[Tier, ...]) -> str:
    if path in ("/now.json", "/procs.json"):
        return "public, max-age=2"
    if path == "/host.json":
        return "public, max-age=60"
    if path in ("/spark.json", "/usage.json"):
        return "public, max-age=300"
    if path == "/services.json":
        return "public, max-age=30"
    for t in tiers:
        if path in (f"/history/{t.range}.json", f"/series/{t.range}.json"):
            return f"public, max-age={max(5, t.step // 2)}"
    return "no-store"


class Agent:
    def __init__(self, cfg: Config, clock, collectors, store: Store, publisher: Publisher):
        self.cfg = cfg
        self.clock = clock
        self.collectors = collectors
        self.store = store
        self.publisher = publisher
        self.engine = Engine(store, cfg.tiers)
        self.seq = 0
        self.last_tick: float | None = None
        self._facts: dict = {}
        self._facts_at = -math.inf
        self._host_json_at = -math.inf
        self._checkpoint_at = clock.monotonic()
        self._usage: dict[tuple[int, str, str], list[float]] = {}
        self._usage_at = clock.monotonic()
        self._first = True
        self._last_gpu_facts: dict = {}
        self._last_shape: tuple = ()
        self._gpu_use: dict[str, tuple[list[int], float]] = {}

    # services (published by the services thread) -------------------------------

    def gpu_use(self) -> dict[str, tuple[list[int], float]]:
        return dict(self._gpu_use)

    def publish_services(self, parts: dict) -> None:
        self._put("/services.json", render.services_payload(self.cfg.id, self.clock.time(), parts),
                  schema.SERVICES)

    def _note_gpu_use(self, procs: list[dict]) -> None:
        use: dict[str, tuple[set, float]] = {}
        for g in procs:
            for p in g["procs"]:
                if p["container"]:
                    gpus, mem = use.get(p["container"], (set(), 0.0))
                    gpus.add(g["i"])
                    use[p["container"]] = (gpus, mem + (p["mem_gib"] or 0.0))
        self._gpu_use = {k: (sorted(v[0]), v[1]) for k, v in use.items()}

    # publishing ----------------------------------------------------------

    def _encode(self, path: str, payload: dict, node: schema.Node):
        try:
            return render.encode(payload, node, cache_control(path, self.cfg.tiers))
        except render.RenderError:
            return None

    def _put(self, path: str, payload: dict, node: schema.Node) -> bool:
        entry = self._encode(path, payload, node)
        if entry is None:
            return False
        self.publisher.put(path, entry)
        return True

    def render_history(self, changed: set[int], end: int) -> None:
        for k in sorted(changed):
            tier = self.cfg.tiers[k]
            start, data = self.store.window(tier, end, tier.serve)
            self._put(f"/history/{tier.range}.json",
                      render.history_payload(self.cfg.id, tier, start, data), schema.HISTORY)
            path = f"/series/{tier.range}.json"
            self.publisher.put_lazy(path, lambda t=tier, s=start, d=data, p=path: self._encode(
                p, render.full_payload(self.cfg.id, t, s, d), schema.FULL))
        if DAILY_TIER in changed:
            self.render_daily()
        if SPARK_TIER in changed:
            tier = self.cfg.tiers[SPARK_TIER]
            start, data = self.store.window(tier, end, SPARK_POINTS)
            self._put("/spark.json", render.spark_payload(self.cfg.id, tier, start, data), schema.SPARK)

    def render_usage(self) -> None:
        rows = self.store.usage()
        self._put("/usage.json", render.usage_payload(self.cfg.id, self.clock.time(), self.cfg.tz, rows),
                  schema.USAGE)

    def render_daily(self) -> None:
        tier = self.cfg.tiers[DAILY_TIER]
        now = self.clock.time()
        since = days_mod.day_start(now - render.DAILY_DAYS * DAY, self.cfg.tz)
        rows = self.store.daily_rows(tier, since)
        self._put("/daily.json", render.daily_payload(self.cfg.id, now, self.cfg.tz, rows), schema.DAILY)

    # per-user GPU usage ----------------------------------------------------------

    def _account(self, ts: int, procs: list[dict]) -> None:
        """Each (user, container) holding a GPU earns one interval of GPU time per GPU it
        holds, plus its GPU memory times the interval."""
        day = days_mod.day_start(ts, self.cfg.tz)
        dt = self.cfg.interval
        for g in procs:
            held: dict[tuple[str, str], float] = {}
            for p in g["procs"]:
                key = (p["user"], p["container"] or "")
                held[key] = held.get(key, 0.0) + (p["mem_gib"] or 0.0)
            for (user, container), mem in held.items():
                acc = self._usage.setdefault((day, user, container), [0.0, 0.0])
                acc[0] += dt
                acc[1] += mem * dt

    def _flush_usage(self) -> None:
        if self._usage:
            rows = {k: (v[0], v[1]) for k, v in self._usage.items()}
            self._usage = {}
            self.store.add_usage(rows, self.clock.time())
        self.render_usage()

    # loop ----------------------------------------------------------------------

    def startup(self) -> None:
        step = self.cfg.tiers[0].step
        fine_end = int(self.clock.time() // step) * step
        self.store.catch_up(fine_end)
        self.render_history(set(range(len(self.cfg.tiers))), fine_end)
        self.render_usage()

    def tick(self, ts: int) -> None:
        mono = self.clock.monotonic()
        s = self.collectors.sample()
        if mono - self._facts_at > FACTS_EVERY:
            self._facts = self.collectors.facts()
            self._facts_at = mono
        sample = s.sample
        if not self._first:
            values = registry.series_values(sample["host"], sample["mounts"], s.gpus,
                                            sample.get("nics"), sample.get("disks"))
            changed = self.engine.add(ts, values)
            if changed:
                self.render_history(changed, self.engine.open_t)
            if s.procs_status == "ok":
                self._account(ts, s.procs)
        self._note_gpu_use(s.procs if s.procs_status == "ok" else [])
        self._first = False

        self._put("/now.json", render.now_payload(
            self.cfg.id, ts, self.seq, self.cfg.interval, self._facts.get("boot_ts"),
            sample, s.gpu_status, s.procs_status, s.gpus), schema.NOW)
        self._put("/procs.json", render.procs_payload(
            self.cfg.id, ts, s.procs_status, s.containers_status, s.procs), schema.PROCS)

        shape = (tuple(sample["mounts"]), tuple(sample.get("nics") or ()), tuple(sample.get("disks") or ()))
        if (mono - self._host_json_at > HOST_JSON_EVERY or s.gpu_facts != self._last_gpu_facts
                or shape != self._last_shape):
            if self._put("/host.json", render.host_payload(
                    self.cfg.id, ts, self.cfg.interval, self._facts, sample,
                    s.gpu_status, s.gpu_facts, self.cfg.tiers), schema.HOST):
                self._host_json_at = mono
                self._last_gpu_facts = s.gpu_facts
                self._last_shape = shape
        if mono - self._usage_at > USAGE_FLUSH_EVERY:
            self._flush_usage()
            self._usage_at = mono
        if mono - self._checkpoint_at > CHECKPOINT_EVERY:
            self.store.checkpoint()
            self._checkpoint_at = mono
        self.seq += 1
        self.last_tick = self.clock.monotonic()

    def shutdown(self) -> None:
        try:
            self._flush_usage()
        except Exception:  # noqa: BLE001
            log.exception("could not flush GPU usage on shutdown")

    def health(self) -> tuple[bool, dict]:
        if self.last_tick is None:
            return False, {"ok": False, "age_s": None, "seq": self.seq}
        age = self.clock.monotonic() - self.last_tick
        ok = age < 3 * self.cfg.interval
        return ok, {"ok": ok, "age_s": int(age), "seq": self.seq}

    def run(self, stop: threading.Event) -> None:
        interval = self.cfg.interval
        nxt = math.ceil(self.clock.time() / interval) * interval
        while self.clock.wait_until(nxt, stop):
            try:
                self.tick(int(nxt))
            except Exception:  # noqa: BLE001 - keep sampling; the watchdog catches a wedge
                log.exception("tick failed")
            nxt += interval
            now = self.clock.time()
            if nxt <= now:  # fell behind: skip missed ticks rather than burst
                nxt = math.ceil(now / interval) * interval
                if nxt <= now:
                    nxt += interval
        self.shutdown()
