"""The history tier table.

Each tier is a fixed bucket width (`step`), a row budget per series (`keep`) and the
number of buckets one history file serves (`serve`). Tier k is always built from
stored rows of tier k-1, so steps must nest and every finer tier must hold at least
one full window of the next coarser tier.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Tier:
    index: int
    range: str  # history file name, e.g. "24h"
    step: int  # seconds
    keep: int  # rows kept per series
    serve: int  # buckets served in history/<range>.json


DEFAULT_TIERS: tuple[Tier, ...] = (
    Tier(0, "1h", 10, 420, 360),
    Tier(1, "24h", 120, 750, 720),
    Tier(2, "7d", 600, 1020, 1008),
    Tier(3, "30d", 3600, 744, 720),
    Tier(4, "1y", 43200, 732, 730),
)

RANGES = tuple(t.range for t in DEFAULT_TIERS)

# spark.json: the last 24 h of means from this tier
SPARK_TIER = 2
SPARK_POINTS = 144


class TierError(ValueError):
    pass


def validate(tiers: tuple[Tier, ...], interval: int) -> None:
    if len(tiers) != len(RANGES):
        raise TierError(f"expected {len(RANGES)} tiers, got {len(tiers)}")
    if tiers[0].step % interval:
        raise TierError(f"sample interval {interval}s must divide the first step {tiers[0].step}s")
    for k, t in enumerate(tiers):
        if t.index != k or t.range != RANGES[k]:
            raise TierError(f"tier {k} must be index {k}, range {RANGES[k]}")
        if t.step <= 0 or t.keep <= 0 or t.serve <= 0:
            raise TierError(f"tier {t.range}: step, keep and serve must be positive")
        if t.serve > t.keep:
            raise TierError(f"tier {t.range}: serve {t.serve} exceeds keep {t.keep}")
        if k:
            fine = tiers[k - 1]
            if t.step % fine.step:
                raise TierError(f"tier {t.range}: step {t.step} is not a multiple of {fine.step}")
            if fine.keep * fine.step < t.step + fine.step:
                raise TierError(
                    f"tier {fine.range} keeps {fine.keep * fine.step}s, "
                    f"less than one {t.range} window plus one bucket"
                )


def parse(spec: str) -> tuple[Tier, ...]:
    """Parse MONITOR_TIERS, `step:keep:serve,...` with one entry per range (tests and dev)."""
    parts = [p.strip() for p in spec.split(",") if p.strip()]
    if len(parts) != len(RANGES):
        raise TierError(f"MONITOR_TIERS needs {len(RANGES)} entries")
    out = []
    for k, part in enumerate(parts):
        try:
            step, keep, serve = (int(x) for x in part.split(":"))
        except ValueError as exc:
            raise TierError(f"bad tier entry {part!r}, want step:keep:serve") from exc
        out.append(Tier(k, RANGES[k], step, keep, serve))
    return tuple(out)


def signature(tiers: tuple[Tier, ...]) -> str:
    return ",".join(f"{t.step}" for t in tiers)
