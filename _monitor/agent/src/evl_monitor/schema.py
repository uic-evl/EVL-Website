"""Closed schemas for every public payload.

The page is public, so nothing may leave the agent by accident. Every key must be
declared, and every string must be an enum value, a narrow pattern, or free text at a
path declared here (OS name, GPU model, the user, container and process name of a GPU
process). A new field that is not declared fails validation and is not published.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable

from . import registry
from .collect.gpu import GPU_STATUS, THROTTLE_VOCAB
from .tiers import RANGES

PROCS_STATUS = ("ok", "count", "off", "unsupported", "error")
CONTAINERS_STATUS = ("ok", "unavailable", "off")
PROC_KIND = ("compute", "graphics")

# key names that must never appear anywhere in a public payload
FORBIDDEN_KEYS = frozenset({
    "cmdline", "cmd", "args", "argv", "environ", "env", "ip", "ips", "addr", "address",
    "mac", "uuid", "serial", "pid", "hostname", "password", "token", "secret",
})


class SchemaError(ValueError):
    def __init__(self, path: str, why: str):
        super().__init__(f"{path}: {why}")
        self.path = path


class Node:
    null = False

    def check(self, v, path: str) -> None:
        raise NotImplementedError


def _null_ok(node: Node, v, path: str) -> bool:
    if v is None:
        if node.null:
            return True
        raise SchemaError(path, "null not allowed")
    return False


class Int(Node):
    def __init__(self, lo: int | None = None, hi: int | None = None, null: bool = False):
        self.lo, self.hi, self.null = lo, hi, null

    def check(self, v, path):
        if _null_ok(self, v, path):
            return
        if isinstance(v, bool) or not isinstance(v, int):
            raise SchemaError(path, "expected an integer")
        if (self.lo is not None and v < self.lo) or (self.hi is not None and v > self.hi):
            raise SchemaError(path, "integer out of range")


class Num(Node):
    def __init__(self, null: bool = True):
        self.null = null

    def check(self, v, path):
        if _null_ok(self, v, path):
            return
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise SchemaError(path, "expected a finite number")


class Bool(Node):
    def __init__(self, null: bool = False):
        self.null = null

    def check(self, v, path):
        if _null_ok(self, v, path):
            return
        if not isinstance(v, bool):
            raise SchemaError(path, "expected a boolean")


class Enum(Node):
    def __init__(self, values: Iterable[str], null: bool = False):
        self.values, self.null = frozenset(values), null

    def check(self, v, path):
        if _null_ok(self, v, path):
            return
        if v not in self.values:
            raise SchemaError(path, "value outside the closed vocabulary")


class Text(Node):
    """A string matching an anchored pattern. Use narrow patterns: only the free-text
    paths declared below get the wide PRINTABLE pattern."""

    def __init__(self, pattern: str, maxlen: int, null: bool = False):
        self.re, self.maxlen, self.null = re.compile(pattern), maxlen, null

    def check(self, v, path):
        if _null_ok(self, v, path):
            return
        if not isinstance(v, str) or len(v) > self.maxlen or not self.re.fullmatch(v):
            raise SchemaError(path, "string does not match its declared pattern")


class List(Node):
    def __init__(self, item: Node, max_len: int):
        self.item, self.max_len = item, max_len

    def check(self, v, path):
        if not isinstance(v, list) or len(v) > self.max_len:
            raise SchemaError(path, f"expected a list of at most {self.max_len}")
        for i, x in enumerate(v):
            self.item.check(x, f"{path}[{i}]")


class Obj(Node):
    def __init__(self, fields: dict[str, Node], required: Iterable[str] | None = None, null: bool = False):
        for k in fields:
            assert k not in FORBIDDEN_KEYS, k
        self.fields = fields
        self.required = frozenset(fields if required is None else required)
        self.null = null

    def check(self, v, path):
        if _null_ok(self, v, path):
            return
        if not isinstance(v, dict):
            raise SchemaError(path, "expected an object")
        for k in v:
            if k not in self.fields:
                raise SchemaError(f"{path}.{k}", "undeclared key")
        for k in self.required:
            if k not in v:
                raise SchemaError(f"{path}.{k}", "missing key")
        for k, x in v.items():
            self.fields[k].check(x, f"{path}.{k}")


class Map(Node):
    def __init__(self, key_pattern: str, value: Node, max_len: int):
        self.key_re, self.value, self.max_len = re.compile(key_pattern), value, max_len

    def check(self, v, path):
        if not isinstance(v, dict) or len(v) > self.max_len:
            raise SchemaError(path, f"expected a map of at most {self.max_len}")
        for k, x in v.items():
            if not isinstance(k, str) or not self.key_re.fullmatch(k) or k in FORBIDDEN_KEYS:
                raise SchemaError(f"{path}.<key>", "map key does not match its pattern")
            self.value.check(x, f"{path}.{k}")


# patterns ---------------------------------------------------------------------

ID = Text(r"[a-z0-9][a-z0-9-]{0,31}", 32)
SEMVER = Text(r"\d{1,3}\.\d{1,3}\.\d{1,3}", 11)
MOUNT_LABEL = r"[a-z0-9_-]{1,16}"
PRINTABLE = r"[\x20-\x7e]*"  # declared free text only
VERSIONISH = r"[0-9A-Za-z.+_-]*"
USER = Text(r"uid \d{1,10}|[A-Za-z0-9._-]{1,32}", 32)
CONTAINER = Text(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", 128, null=True)
PROC_NAME = Text(r"[A-Za-z0-9._:+ -]{1,15}", 15, null=True)

TS = Int(0)
V1 = Int(1, 1)

MOUNT_PATH = Text(r"/[A-Za-z0-9._/-]{0,63}", 64)
NIC_NAME = r"[A-Za-z0-9_.-]{1,15}"
DISK_NAME = r"[a-z0-9]{1,15}"

HOST_NOW = Obj({
    **{k: Num() for k in registry.HOST_METRICS},
    "cores": Int(1, null=True),
    "mem_total_gib": Num(), "swap_used_gib": Num(), "swap_total_gib": Num(),
}, required=())

GPU_NOW = Obj({
    "i": Int(0, registry.MAX_GPUS - 1),
    **{k: Num() for k in registry.GPU_METRICS if k != "procs"},
    "mem_total_gib": Num(), "power_limit_w": Num(),
    "procs": Int(0, null=True), "mig": Bool(null=True),
    "throttle": List(Enum(THROTTLE_VOCAB), len(THROTTLE_VOCAB)),
}, required=("i",))

NOW = Obj({
    "v": V1, "id": ID, "agent": SEMVER, "ts": TS, "seq": Int(0), "interval": Int(1, 60),
    "boot_ts": Int(0, null=True),
    "host": HOST_NOW,
    "cpu_cores_pct": List(Num(), 1024),
    "mounts": Map(MOUNT_LABEL, Obj({"path": MOUNT_PATH, "used_pct": Num(), "used_gib": Num(),
                                    "total_gib": Num()}), 8),
    "nics": Map(NIC_NAME, Obj({"rx_mbs": Num(), "tx_mbs": Num()}), 16),
    "disks": Map(DISK_NAME, Obj({"r_mbs": Num(), "w_mbs": Num(), "busy_pct": Num()}), 32),
    "gpu_status": Enum(GPU_STATUS),
    "procs_status": Enum(PROCS_STATUS),
    "gpus": List(GPU_NOW, registry.MAX_GPUS),
})

PROCS = Obj({
    "v": V1, "id": ID, "ts": TS,
    "procs_status": Enum(PROCS_STATUS),
    "containers_status": Enum(CONTAINERS_STATUS),
    "gpus": List(Obj({
        "i": Int(0, registry.MAX_GPUS - 1),
        "more": Int(0),
        "procs": List(Obj({
            "user": USER, "container": CONTAINER, "name": PROC_NAME,
            "kind": Enum(PROC_KIND), "mem_gib": Num(),
        }), 32),
    }), registry.MAX_GPUS),
})

HOST = Obj({
    "v": V1, "id": ID, "agent": SEMVER, "ts": TS, "interval": Int(1, 60), "boot_ts": Int(0, null=True),
    "gpu_status": Enum(GPU_STATUS),
    "facts": Obj({
        "os": Text(PRINTABLE, 128, null=True),
        "kernel": Text(PRINTABLE, 128, null=True),
        "cpu_model": Text(PRINTABLE, 128, null=True),
        "gpu_driver": Text(VERSIONISH, 32, null=True),
        "cuda": Text(VERSIONISH, 16, null=True),
    }),
    "cpu": Obj({"sockets": Int(1, null=True), "cores": Int(1, null=True),
                "threads": Int(1, null=True), "max_mhz": Int(0, null=True)}),
    "mem": Obj({"total_gib": Num(), "swap_total_gib": Num()}),
    "mounts": Map(MOUNT_LABEL, Obj({"path": MOUNT_PATH, "total_gib": Num()}), 8),
    "nics": List(Text(NIC_NAME, 15), 16),
    "disks": List(Text(DISK_NAME, 15), 32),
    "gpus": List(Obj({
        "i": Int(0, registry.MAX_GPUS - 1),
        "name": Text(PRINTABLE, 96, null=True),
        "mem_total_gib": Num(), "power_limit_w": Num(), "mig": Bool(null=True),
    }), registry.MAX_GPUS),
    "ranges": List(Obj({"range": Enum(RANGES), "step": Int(1), "n": Int(1)}), len(RANGES)),
    "files": List(Text(r"[a-z0-9/]{1,24}\.json", 32), 32),
})

MAX_POINTS = 2000
SERIES = List(Num(), MAX_POINTS)
MEAN_MAX = Obj({"mean": SERIES, "max": SERIES})

HISTORY = Obj({
    "v": V1, "id": ID, "range": Enum(RANGES), "start": TS, "step": Int(1), "n": Int(1, MAX_POINTS),
    "host": Obj({k: MEAN_MAX for k in registry.HOST_METRICS}, required=()),
    "mounts": Map(MOUNT_LABEL, Obj({"used_pct": Obj({"mean": SERIES})}), 8),
    "gpus": List(Obj({"i": Int(0, registry.MAX_GPUS - 1),
                      **{k: MEAN_MAX for k in registry.GPU_METRICS}}, required=("i",)),
                 registry.MAX_GPUS),
})

SPARK = Obj({
    "v": V1, "id": ID, "start": TS, "step": Int(1), "n": Int(1, MAX_POINTS),
    "cpu_pct": SERIES, "mem_pct": SERIES, "gpu_util_pct": SERIES,
})


class SeriesKeys(Map):
    """series/<range>.json: every stored series, keyed by its registry key."""

    def __init__(self, value: Node, max_len: int):
        super().__init__(r"[A-Za-z0-9_.-]{1,48}", value, max_len)

    def check(self, v, path):
        super().check(v, path)
        for k in v:
            if not registry.is_valid_key(k):
                raise SchemaError(f"{path}.<key>", "not a registry series key")


FULL = Obj({
    "v": V1, "id": ID, "range": Enum(RANGES), "start": TS, "step": Int(1), "n": Int(1, MAX_POINTS),
    "series": SeriesKeys(Obj({"mean": SERIES, "max": SERIES, "min": SERIES}), registry.MAX_SERIES),
})

SERVICES = Obj({
    "v": V1, "id": ID, "ts": TS,
    "containers_status": Enum(CONTAINERS_STATUS),
    "containers": List(Obj({
        "name": Text(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", 128),
        "image": Text(r"[A-Za-z0-9._/:@-]{1,200}", 200, null=True),
        "state": Enum(("created", "running", "paused", "restarting", "removing", "exited", "dead"), null=True),
        "health": Enum(("healthy", "unhealthy", "starting"), null=True),
        "status": Text(r"[A-Za-z0-9 ()-]{0,64}", 64, null=True),
        "created_ts": Int(0, null=True),
        "ports": List(Obj({"public": Int(0, 65535, null=True), "private": Int(0, 65535),
                           "bind": Enum(("any", "loopback", "other")),
                           "proto": Enum(("tcp", "udp", "sctp"))}), 32),
        "project": Text(r"[A-Za-z0-9_.-]{1,64}", 64, null=True),
        "service": Text(r"[A-Za-z0-9_.-]{1,64}", 64, null=True),
        "gpus": List(Int(0, registry.MAX_GPUS - 1), registry.MAX_GPUS),
        "gpu_mem_gib": Num(),
    }), 500),
    "models": List(Obj({
        "id": Text(r"[A-Za-z0-9._/:@+-]{1,128}", 128, null=True),
        "container": Text(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", 128),
        "port": Int(0, 65535, null=True),
        "kind": Enum(("openai", "ollama", "image")),
        "max_len": Int(0, null=True),
        "auth": Bool(),
    }), 200),
    "models_ts": Int(0, null=True),
    "routes_source": Enum(("nginx", "caddy", "none")),
    "routes": List(Obj({
        "url": Text(r"https?://[a-z0-9.-]+(:\d{1,5})?(/[A-Za-z0-9._~/-]*)?", 256),
        "port": Int(0, 65535, null=True),
        "container": Text(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", 128, null=True),
    }), 500),
})

TZ = Text(r"[A-Za-z_]{1,20}(/[A-Za-z0-9_+-]{1,30}){0,2}", 64)
DATE = Text(r"\d{4}-\d{2}-\d{2}", 10)

USAGE = Obj({
    "v": V1, "id": ID, "ts": TS, "tz": TZ,
    "days": List(Obj({
        "day": TS, "date": DATE,
        "rows": List(Obj({"user": USER, "container": CONTAINER, "gpu_h": Num(), "mem_gib_h": Num()}), 500),
    }), 400),
})

DAILY = Obj({
    "v": V1, "id": ID, "ts": TS, "tz": TZ,
    "days": List(Obj({
        "date": DATE, "day": TS, "hours": Int(0, 25),
        "cpu_pct": Num(), "mem_pct": Num(), "gpu_util_pct": Num(), "gpu_mem_pct": Num(),
        "load1": Num(), "load_pct": Num(),
    }), 40),
})


def validate(schema: Node, payload) -> None:
    schema.check(payload, "$")


def forbidden_keys(payload, path: str = "$") -> list[str]:
    """Every path whose key is in FORBIDDEN_KEYS (a belt on top of the closed schema)."""
    hits = []
    if isinstance(payload, dict):
        for k, v in payload.items():
            if isinstance(k, str) and k.lower() in FORBIDDEN_KEYS:
                hits.append(f"{path}.{k}")
            hits.extend(forbidden_keys(v, f"{path}.{k}"))
    elif isinstance(payload, list):
        for i, v in enumerate(payload):
            hits.extend(forbidden_keys(v, f"{path}[{i}]"))
    return hits
