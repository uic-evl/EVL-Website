import pytest

from evl_monitor import tiers as tiers_mod
from evl_monitor.config import Config, ConfigError

from .conftest import env


def test_default_tiers_are_valid_for_every_interval():
    for interval in (1, 2, 5, 10):
        tiers_mod.validate(tiers_mod.DEFAULT_TIERS, interval)


def test_default_tiers_serve_the_documented_windows():
    spans = {t.range: t.step * t.serve for t in tiers_mod.DEFAULT_TIERS}
    assert spans == {"1h": 3600, "24h": 86400, "7d": 7 * 86400, "30d": 30 * 86400, "1y": 365 * 86400}


@pytest.mark.parametrize("spec, why", [
    ("2:6:5,3:6:5,8:6:5,16:6:5,32:6:5", "not a multiple"),
    ("2:2:2,4:6:5,8:6:5,16:6:5,32:6:5", "less than one"),
    ("2:6:7,4:6:5,8:6:5,16:6:5,32:6:5", "exceeds keep"),
    ("2:6:5,4:6:5", "needs 5"),
])
def test_bad_tiers_are_rejected(spec, why):
    with pytest.raises(tiers_mod.TierError, match=why):
        tiers_mod.validate(tiers_mod.parse(spec), 1)


def test_interval_must_divide_first_step():
    with pytest.raises(tiers_mod.TierError, match="must divide"):
        tiers_mod.validate(tiers_mod.DEFAULT_TIERS, 3)


def test_tiny_tiers_need_dev_flag():
    e = env()
    del e["MONITOR_DEV"]
    with pytest.raises(ConfigError, match="MONITOR_DEV"):
        Config.from_env(e)


def test_config_parses_mounts_and_modes():
    cfg = Config.from_env(env(MONITOR_MOUNTS="root:/,data:/data", MONITOR_GPU="on", MONITOR_PROCS="count"))
    assert cfg.mounts == (("root", "/"), ("data", "/data"))
    assert cfg.gpu == "on" and cfg.procs == "count"


@pytest.mark.parametrize("key, value", [
    ("MONITOR_ID", "Bad_ID"),
    ("MONITOR_MOUNTS", "root:relative"),
    ("MONITOR_MOUNTS", "a:/,a:/x"),
    ("MONITOR_GPU", "maybe"),
    ("MONITOR_INTERVAL", "3"),
])
def test_config_rejects(key, value):
    with pytest.raises((ConfigError, ValueError)):
        Config.from_env(env(**{key: value}))
