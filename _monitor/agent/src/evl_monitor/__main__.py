"""Run the agent: python -m evl_monitor"""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading
import time

from .agent import Agent, RealCollectors
from .clock import RealClock
from .config import Config, ConfigError
from .publish import Publisher
from .server import make_server
from .store import Store

log = logging.getLogger("evl_monitor")

WATCHDOG_TICKS = 6


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("MONITOR_LOG_LEVEL", "WARNING").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        cfg = Config.from_env()
    except (ConfigError, ValueError) as exc:
        print(f"evl-monitor: {exc}", file=sys.stderr)
        return 2

    clock = RealClock()
    store = Store(cfg.db, cfg.tiers)
    if cfg.fake:
        from . import fake

        if cfg.fake_backfill:
            fake.backfill(store, cfg, clock.time())
        collectors = fake.FakeCollectors(cfg, clock)
    else:
        collectors = RealCollectors(cfg, clock)

    publisher = Publisher()
    agent = Agent(cfg, clock, collectors, store, publisher)
    agent.startup()
    collectors.start()
    collectors.start_services(agent.publish_services, agent.gpu_use)

    server = make_server(cfg.bind, cfg.port, publisher, agent.health, cfg.cors_origins, cfg.max_conn)
    threading.Thread(target=server.serve_forever, name="http", daemon=True).start()

    stop = threading.Event()

    def on_signal(signum, _frame):
        stop.set()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    def watchdog():
        started = time.monotonic()
        while not stop.wait(cfg.interval):
            last = agent.last_tick if agent.last_tick is not None else started
            if time.monotonic() - last > WATCHDOG_TICKS * cfg.interval:
                log.error("no completed tick in %d intervals; exiting so Docker restarts us", WATCHDOG_TICKS)
                os._exit(70)

    threading.Thread(target=watchdog, name="watchdog", daemon=True).start()

    agent.run(stop)

    server.shutdown()
    collectors.stop()
    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
