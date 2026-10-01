"""The site's host list, _data/monitor.yml: load it, check it, list the live hosts.

Used by render_nginx.py (the web server's relay config) and by CI.
  python hosts.py            print the live hosts as JSON
"""

from __future__ import annotations

import json
import os
import re
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "..", "_data", "monitor.yml")

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
FQDN_RE = re.compile(r"^[a-z0-9.-]+\.[a-z]{2,}$")
ALLOWED = {"name", "fqdn", "status", "gpu", "gpus", "cpus", "memory", "role"}


class DataError(ValueError):
    pass


def load(path: str = DATA) -> dict:
    with open(path) as f:
        data = yaml.safe_load(f)
    hosts = data.get("hosts") or {}
    grouped = [h for g in data.get("groups") or [] for h in g.get("hosts") or []]
    for hid, h in hosts.items():
        if not ID_RE.match(hid):
            raise DataError(f"host id {hid!r} must match {ID_RE.pattern}")
        extra = set(h) - ALLOWED
        if extra:
            raise DataError(f"{hid}: unknown keys {sorted(extra)} (this file is public)")
        if h.get("status") not in ("live", "planned"):
            raise DataError(f"{hid}: status must be live or planned")
        if not FQDN_RE.match(str(h.get("fqdn", ""))):
            raise DataError(f"{hid}: fqdn missing or malformed")
    missing = set(grouped) - set(hosts)
    if missing:
        raise DataError(f"groups name unknown hosts: {sorted(missing)}")
    if len(grouped) != len(set(grouped)) or set(grouped) != set(hosts):
        raise DataError("every host must appear in exactly one group")
    fqdns = [h["fqdn"] for h in hosts.values()]
    if len(fqdns) != len(set(fqdns)):
        raise DataError("fqdns must be unique")
    return data


def live_hosts(data: dict) -> list[dict]:
    return [{"id": hid, "fqdn": h["fqdn"]}
            for hid, h in sorted(data["hosts"].items()) if h["status"] == "live"]


def main() -> int:
    try:
        print(json.dumps(live_hosts(load()), indent=2))
    except DataError as exc:
        print(f"_data/monitor.yml: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
