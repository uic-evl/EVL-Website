"""Agent configuration, read once from the environment."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from . import tiers as tiers_mod

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
MOUNT_LABEL_RE = re.compile(r"^[a-z0-9_-]{1,16}$")
MAX_MOUNTS = 8


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    id: str
    port: int = 9877
    bind: str = "0.0.0.0"
    interval: int = 5
    db: str = "/data/monitor.sqlite3"
    hostfs: str = "/hostfs"
    procfs: str = "/proc"
    mounts: tuple[tuple[str, str], ...] = (("root", "/"),)
    mounts_auto: bool = False  # MONITOR_MOUNTS=auto: local filesystems from the host mount table
    net_ifaces: tuple[str, ...] = ()  # empty: physical NICs
    gpu: str = "off"  # on | off | auto
    procs: str = "full"  # full | count | off
    docker_sock: str = "/run/evl-monitor/docker.sock"
    fqdn: str | None = None  # public name for routes whose server block has none
    tz: str = "America/Chicago"  # calendar days for daily.json and usage.json
    nss: bool = True
    strip_domain: bool = True
    cors_origins: tuple[str, ...] = ()
    max_conn: int = 32
    tiers: tuple[tiers_mod.Tier, ...] = tiers_mod.DEFAULT_TIERS
    fake: bool = False
    fake_backfill: bool = False
    fake_gpus: int = 4

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Config:
        env = dict(os.environ if env is None else env)

        def get(name: str, default: str = "") -> str:
            return env.get(name, default).strip()

        def flag(name: str, default: bool) -> bool:
            raw = get(name)
            if not raw:
                return default
            return raw.lower() in ("1", "true", "yes", "on")

        ident = get("MONITOR_ID")
        if not ID_RE.match(ident):
            raise ConfigError("MONITOR_ID must match ^[a-z0-9][a-z0-9-]{0,31}$")

        interval = int(get("MONITOR_INTERVAL", "5"))
        if interval not in (1, 2, 5, 10):
            raise ConfigError("MONITOR_INTERVAL must be 1, 2, 5 or 10")

        mounts = []
        mounts_spec = get("MONITOR_MOUNTS", "auto")
        mounts_auto = mounts_spec in ("", "auto")
        for item in filter(None, (p.strip() for p in ("root:/" if mounts_auto else mounts_spec).split(","))):
            label, sep, path = item.partition(":")
            if not sep or not MOUNT_LABEL_RE.match(label) or not path.startswith("/"):
                raise ConfigError(f"bad MONITOR_MOUNTS entry {item!r}, want label:/path")
            mounts.append((label, path))
        if len(mounts) > MAX_MOUNTS or len({m[0] for m in mounts}) != len(mounts):
            raise ConfigError(f"MONITOR_MOUNTS: at most {MAX_MOUNTS} entries, unique labels")

        ifaces = get("MONITOR_NET_IFACES", "auto")
        net = () if ifaces in ("", "auto") else tuple(i for i in ifaces.split(",") if i)

        gpu = get("MONITOR_GPU", "off").lower()
        procs = get("MONITOR_PROCS", "full").lower()
        if gpu not in ("on", "off", "auto"):
            raise ConfigError("MONITOR_GPU must be on, off or auto")
        if procs not in ("full", "count", "off"):
            raise ConfigError("MONITOR_PROCS must be full, count or off")

        dev = flag("MONITOR_DEV", False)
        tier_spec = get("MONITOR_TIERS")
        if tier_spec and not dev:
            raise ConfigError("MONITOR_TIERS is a development setting; set MONITOR_DEV=1")
        tiers = tiers_mod.parse(tier_spec) if tier_spec else tiers_mod.DEFAULT_TIERS
        tiers_mod.validate(tiers, interval)

        cors = tuple(o.strip() for o in get("MONITOR_CORS_ORIGINS").split(",") if o.strip())

        tz = get("MONITOR_TZ", "America/Chicago")
        try:
            from zoneinfo import ZoneInfo

            ZoneInfo(tz)
        except Exception as exc:  # noqa: BLE001
            raise ConfigError(f"MONITOR_TZ {tz!r} is not a known time zone") from exc

        return cls(
            id=ident,
            port=int(get("MONITOR_PORT", "9877")),
            bind=get("MONITOR_BIND", "0.0.0.0"),
            interval=interval,
            db=get("MONITOR_DB", "/data/monitor.sqlite3"),
            hostfs=get("MONITOR_HOSTFS", "/hostfs"),
            procfs=get("MONITOR_PROCFS", "/proc"),
            mounts=tuple(mounts),
            mounts_auto=mounts_auto,
            net_ifaces=net,
            gpu=gpu,
            procs=procs,
            docker_sock=get("MONITOR_DOCKER_SOCK", "/run/evl-monitor/docker.sock"),
            fqdn=get("MONITOR_FQDN") or None,
            tz=tz,
            nss=get("MONITOR_NSS", "auto").lower() != "off",
            strip_domain=flag("MONITOR_USER_STRIP_DOMAIN", True),
            cors_origins=cors,
            max_conn=int(get("MONITOR_MAX_CONN", "32")),
            tiers=tiers,
            fake=flag("MONITOR_FAKE", False),
            fake_backfill=flag("MONITOR_FAKE_BACKFILL", False),
            fake_gpus=int(get("MONITOR_FAKE_GPUS", "4")),
        )
