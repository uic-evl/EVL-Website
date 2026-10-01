"""Remote check of one agent: python -m evl_monitor.check BASE_URL [--id ID] [--max-age S]

Fetches every published file under BASE_URL (an agent, or the public relay such as
https://www.evl.uic.edu/monitor/data/arcade/), validates each against its schema,
checks the id, and checks that now.json is fresh against the server's Date header.
Exit 0 on success; prints one line per failure otherwise.
"""

from __future__ import annotations

import argparse
import email.utils
import gzip
import json
import sys
import time
import urllib.error
import urllib.request

from . import schema
from .tiers import RANGES

FILES = {
    "now.json": schema.NOW,
    "procs.json": schema.PROCS,
    "host.json": schema.HOST,
    "spark.json": schema.SPARK,
    "usage.json": schema.USAGE,
    "services.json": schema.SERVICES,
    "daily.json": schema.DAILY,
    **{f"history/{r}.json": schema.HISTORY for r in RANGES},
    **{f"series/{r}.json": schema.FULL for r in RANGES},
}


def fetch(url: str, timeout: float = 10) -> tuple[dict, dict]:
    req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip", "User-Agent": "evl-monitor-check"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return json.loads(raw), dict(resp.headers)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--id")
    ap.add_argument("--max-age", type=float, default=None, help="seconds; default 3 intervals")
    args = ap.parse_args(argv)
    base = args.base if args.base.endswith("/") else args.base + "/"

    failures = []
    for name, node in FILES.items():
        try:
            payload, headers = fetch(base + name)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            failures.append(f"{name}: fetch failed: {exc}")
            continue
        try:
            schema.validate(node, payload)
        except schema.SchemaError as exc:
            failures.append(f"{name}: schema: {exc}")
            continue
        if args.id and payload.get("id") != args.id:
            failures.append(f"{name}: id {payload.get('id')!r} != {args.id!r}")
        if name == "now.json":
            date = headers.get("Date")
            server_now = email.utils.parsedate_to_datetime(date).timestamp() if date else time.time()
            max_age = args.max_age if args.max_age is not None else 3 * payload["interval"] + 2
            age = server_now - payload["ts"]
            if age > max_age:
                failures.append(f"now.json: stale, sample is {age:.0f}s old (limit {max_age:.0f}s)")
    for line in failures:
        print(line)
    if not failures:
        print(f"ok: {base}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
