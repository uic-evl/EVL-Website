"""Fence one collector section so a failure yields its empty shape, never an exception.

Ported from curio's backend/app/monitor/hardware.py `_section`.
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable
from typing import TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")

_failures: dict[str, int] = {}


def section(name: str, fn: Callable[[], T], fallback: T) -> T:
    try:
        out = fn()
    except Exception as exc:  # noqa: BLE001 - this is the fence
        n = _failures.get(name, 0) + 1
        _failures[name] = n
        if n == 1 or n % 720 == 0:  # first failure, then about once an hour at 5 s
            log.warning("collector section %s failed (%d in a row): %s", name, n, type(exc).__name__)
        return copy.deepcopy(fallback)
    _failures.pop(name, None)
    return out


def failures() -> dict[str, int]:
    return dict(_failures)
