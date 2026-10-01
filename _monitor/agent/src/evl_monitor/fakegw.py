"""Several fake hosts behind the production URL layout, for page development.

    python -m evl_monitor.fakegw --port 4001 \
        --hosts arcade:4,sage200:2,utk:1 --stale utk --offline sage200

serves http://localhost:4001/monitor/data/<id>/<file> with a year of synthetic
history per host. A `--stale` host publishes once and then stops sampling; an
`--offline` host answers 502, like the nginx relay does for a dead host. CORS is
open to localhost origins so a local Jekyll server can read it.
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
from .publish import Publisher
from .server import BoundedServer, Handler
from .store import Store

PATH_RE = re.compile(r"^/monitor/data/(?P<id>[a-z0-9][a-z0-9-]{0,31})(?P<file>/.*)$")
LOCAL_ORIGIN_RE = re.compile(r"^http://(localhost|127\.0\.0\.1)(:\d+)?$")


class Host:
    def __init__(self, ident: str, gpus: int, root: str, clock):
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
        self.stop = threading.Event()

    def run(self, once: bool) -> None:
        if once:
            self.agent.tick(int(RealClock().time()))
            return
        self.agent.run(self.stop)


def make_handler(hosts: dict[str, Host], offline: set[str]):
    class GatewayHandler(Handler):
        def resolve(self, path):
            m = PATH_RE.match(path)
            if not m or m["id"] in offline or m["id"] not in hosts:
                return None, None, path
            h = hosts[m["id"]]
            return h.publisher, h.agent.health, m["file"]

        def end_headers(self):
            origin = self.headers.get("Origin") if hasattr(self, "headers") else None
            if origin and LOCAL_ORIGIN_RE.match(origin):
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Access-Control-Expose-Headers", "Date, ETag")
            super().end_headers()

    return GatewayHandler


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=4001)
    ap.add_argument("--hosts", default="arcade:4,sage200:2,utk:1")
    ap.add_argument("--stale", default="")
    ap.add_argument("--offline", default="")
    args = ap.parse_args(argv)

    clock = RealClock()
    root = tempfile.mkdtemp(prefix="evl-fakegw-")
    stale = {s for s in args.stale.split(",") if s}
    offline = {s for s in args.offline.split(",") if s}
    hosts = {}
    for item in args.hosts.split(","):
        ident, _, gpus = item.partition(":")
        hosts[ident] = Host(ident, int(gpus or 0), root, clock)
    for ident, h in hosts.items():
        threading.Thread(target=h.run, args=(ident in stale,), daemon=True).start()

    srv = BoundedServer(("127.0.0.1", args.port), make_handler(hosts, offline), 64)
    print(f"fake relay on http://127.0.0.1:{args.port}/monitor/data/<id>/  hosts: {', '.join(hosts)}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
