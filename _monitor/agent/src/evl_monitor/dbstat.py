"""Print history database stats as JSON: python -m evl_monitor.dbstat [path]"""

from __future__ import annotations

import json
import os
import sys

from .config import Config
from .store import Store


def main(argv: list[str]) -> int:
    path = argv[0] if argv else os.environ.get("MONITOR_DB", "/data/monitor.sqlite3")
    env = dict(os.environ)
    env.setdefault("MONITOR_ID", "dbstat")
    cfg = Config.from_env(env)
    store = Store(path, cfg.tiers)
    try:
        print(json.dumps(store.stats(), indent=2))
    finally:
        store.db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
