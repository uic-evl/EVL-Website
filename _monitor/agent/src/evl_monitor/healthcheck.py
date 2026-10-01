"""Docker HEALTHCHECK: exit 0 when the agent's last tick is fresh."""

from __future__ import annotations

import os
import sys
import urllib.request


def main() -> int:
    port = os.environ.get("MONITOR_PORT", "9877")
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=3) as resp:
            return 0 if resp.status == 200 else 1
    except OSError:
        return 1


if __name__ == "__main__":
    sys.exit(main())
