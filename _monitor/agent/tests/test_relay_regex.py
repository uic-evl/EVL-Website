"""The web server's relay must pass every file the agent serves, and nothing else."""

import re
from pathlib import Path

from evl_monitor.render import FILES
from evl_monitor.server import ROUTES

SNIPPET = Path(__file__).resolve().parents[2] / "web" / "evl-monitor.conf"


def relay_regexes():
    text = SNIPPET.read_text()
    return [re.compile(m.group(1).replace("(?<", "(?P<"))
            for m in re.finditer(r"location ~ (\^/monitor/data/[^ ]+\$) \{", text)]


def test_snippet_exists_and_has_hosts():
    assert SNIPPET.exists(), "run python _monitor/tools/render_nginx.py"
    assert relay_regexes()


def test_every_agent_file_is_relayed():
    for rx in relay_regexes():
        host = rx.pattern.split("/")[3]
        for name in FILES:
            assert rx.match(f"/monitor/data/{host}/{name}"), (host, name)
        assert rx.match(f"/monitor/data/{host}/healthz")


def test_relay_passes_only_agent_routes():
    for rx in relay_regexes():
        host = rx.pattern.split("/")[3]
        for bad in ("../etc/passwd", "history/2y.json", "now.json.bak", "series/", "x/now.json"):
            assert not rx.match(f"/monitor/data/{host}/{bad}"), bad


def test_agent_routes_match_files():
    assert ROUTES == {"/" + f for f in FILES}
