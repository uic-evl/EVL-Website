"""Fake agents behind the real hub, for page development.

    python -m evl_monitor.fakegw --port 4001 [--stale utk] [--offline sage200]

reads the site's _data/monitor.yml (names, groups, planned hosts, GPU counts from the
`gpus` field), starts one fake agent per live host on a local port with a year of
synthetic history, and serves the real hub on http://localhost:4001 with CORS for
localhost. A `--stale` host publishes once and then stops sampling; an `--offline`
host has no agent at all. Open the local site with ?data=http://localhost:4001
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
import threading

from . import fake
from .agent import Agent
from .clock import RealClock
from .config import Config
from .hub import HostEntry, Hub, make_hub_server
from .publish import Publisher
from .server import make_server
from .store import Store

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "..", "..", "..", "_data", "monitor.yml"))
LOCAL_ORIGINS = ("http://localhost:8080", "http://127.0.0.1:8080", "http://localhost:4000", "http://127.0.0.1:4000")


class FakeAgent:
    def __init__(self, ident: str, gpus: int, root: str, clock, stale: bool):
        env = {"MONITOR_ID": ident, "MONITOR_FAKE": "1", "MONITOR_FAKE_GPUS": str(gpus),
               "MONITOR_MOUNTS": "root:/,data:/data"}
        self.cfg = Config.from_env(env)
        self.store = Store(os.path.join(root, f"{ident}.sqlite3"), self.cfg.tiers)
        fake.backfill(self.store, self.cfg, clock.time())
        self.publisher = Publisher()
        collectors = fake.FakeCollectors(self.cfg, clock)
        self.agent = Agent(self.cfg, clock, collectors, self.store, self.publisher)
        self.agent.startup()
        collectors.start_services(self.agent.publish_services, self.agent.gpu_use)
        self.server = make_server("127.0.0.1", 0, self.publisher, self.agent.health)
        self.port = self.server.server_address[1]
        self.stale = stale
        self.stop = threading.Event()

    def start(self) -> None:
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        if self.stale:
            self.agent.tick(int(RealClock().time()))
        else:
            threading.Thread(target=self.agent.run, args=(self.stop,), daemon=True).start()


def gpu_count(text: str | None) -> int:
    m = re.match(r"\s*(\d+)\s*x", text or "")
    return int(m.group(1)) if m else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=4001)
    ap.add_argument("--hosts-file", default=DATA)
    ap.add_argument("--stale", default="")
    ap.add_argument("--offline", default="")
    args = ap.parse_args(argv)

    import yaml

    with open(args.hosts_file) as f:
        data = yaml.safe_load(f)
    stale = {s for s in args.stale.split(",") if s}
    offline = {s for s in args.offline.split(",") if s}
    clock = RealClock()
    root = tempfile.mkdtemp(prefix="evl-fakegw-")
    entries = []
    for g in data["groups"]:
        for hid in g["hosts"]:
            h = data["hosts"][hid]
            port = 1  # nothing listens there: offline
            if h.get("status") == "live" and hid not in offline:
                a = FakeAgent(hid, gpu_count(h.get("gpus")), root, clock, hid in stale)
                a.start()
                port = a.port
            entries.append(HostEntry(id=hid, name=h.get("name", hid), group=g["name"], fqdn="127.0.0.1",
                                     status="live" if h.get("status") == "live" else "planned", port=port))

    hub = Hub(lambda: entries)
    hub.refresh_hosts(force=True)
    server = make_hub_server(hub, "127.0.0.1", args.port, LOCAL_ORIGINS)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"fake hub on http://127.0.0.1:{args.port}/overview.json  hosts: {', '.join(e.id for e in entries)}",
          flush=True)
    stop = threading.Event()
    try:
        hub.run(stop)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
