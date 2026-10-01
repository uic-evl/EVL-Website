import os

import pytest

from evl_monitor import tiers as tiers_mod
from evl_monitor.clock import FakeClock
from evl_monitor.store import Store

# tiny tiers: steps 2, 4, 8, 16, 32 seconds, 6 rows kept, 5 served
TINY_SPEC = "2:6:5,4:6:5,8:6:5,16:6:5,32:6:5"
TINY = tiers_mod.parse(TINY_SPEC)


@pytest.fixture
def tiny():
    tiers_mod.validate(TINY, 1)
    return TINY


@pytest.fixture
def clock():
    return FakeClock(start=1_790_000_000.0)


@pytest.fixture
def db_path(tmp_path):
    return os.path.join(tmp_path, "monitor.sqlite3")


@pytest.fixture
def store(db_path, tiny):
    s = Store(db_path, tiny)
    yield s
    s.db.close()


def env(**kw):
    base = {"MONITOR_ID": "test", "MONITOR_DEV": "1", "MONITOR_INTERVAL": "1", "MONITOR_TIERS": TINY_SPEC}
    base.update({k: str(v) for k, v in kw.items()})
    return base
