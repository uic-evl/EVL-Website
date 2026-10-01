#!/usr/bin/env python3
"""Fail if any monitor file contains an en dash (U+2013) or an em dash (U+2014)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATHS = ["_monitor", "_data/monitor.yml", "_pages/monitor.html", "assets/js/monitor.js",
         "_sass/_monitor.scss", ".github/workflows"]
DASHES = (chr(0x2013), chr(0x2014))


def main() -> int:
    bad = 0
    for rel in PATHS:
        base = ROOT / rel
        files = [base] if base.is_file() else sorted(p for p in base.rglob("*") if p.is_file()) if base.exists() else []
        for path in files:
            if any(part in ("__pycache__", ".pytest_cache", ".ruff_cache") for part in path.parts):
                continue
            try:
                text = path.read_text()
            except UnicodeDecodeError:
                continue
            for n, line in enumerate(text.splitlines(), 1):
                if any(d in line for d in DASHES):
                    print(f"{path.relative_to(ROOT)}:{n}: en or em dash")
                    bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
