"""services.json: containers, models and routes."""

import os
import urllib.error

from evl_monitor import schema
from evl_monitor.collect import services
from evl_monitor.render import services_payload

ITEMS = [
    {"Id": "a" * 64, "Names": ["/nim-gemma4"], "Image": "nvcr.io/nim/google/gemma-4-31b-it:latest",
     "State": "running", "Status": "Up 3 hours (healthy)", "Created": 1789000000,
     "Ports": [{"IP": "127.0.0.1", "PrivatePort": 8000, "PublicPort": 8000, "Type": "tcp"}],
     "Labels": {"com.docker.compose.project": "llm"}},
    {"Id": "b" * 64, "Names": ["/vllm-ocr"], "Image": "vllm/vllm-openai:latest", "State": "running",
     "Status": "Up 2 days", "Created": 1789000000,
     "Ports": [{"IP": "0.0.0.0", "PrivatePort": 8000, "PublicPort": 8010, "Type": "tcp"}], "Labels": {}},
    {"Id": "c" * 64, "Names": ["/litellm"], "Image": "ghcr.io/berriai/litellm:main-latest", "State": "running",
     "Status": "Up 9 days (unhealthy)", "Created": 1789000000,
     "Ports": [{"IP": "127.0.0.1", "PrivatePort": 4000, "PublicPort": 4000, "Type": "tcp"}], "Labels": {}},
    {"Id": "d" * 64, "Names": ["/ollama"], "Image": "ollama/ollama", "State": "running", "Status": "Up 1 hour",
     "Created": 1789000000,
     "Ports": [{"IP": "127.0.0.1", "PrivatePort": 11434, "PublicPort": 11434, "Type": "tcp"}], "Labels": {}},
    {"Id": "e" * 64, "Names": ["/web"], "Image": "nginx:1.27", "State": "exited",
     "Status": "Exited (0) 2 days ago", "Created": 1789000000, "Ports": [], "Labels": {}},
    {"Id": "f" * 64, "Names": ["/bad name"], "Image": "x", "State": "running", "Ports": [], "Labels": {}},
]


def test_container_rows():
    rows = services.container_rows(ITEMS, {"nim-gemma4": ([1, 0], 140.2)})
    by = {r["name"]: r for r in rows}
    assert "bad name" not in by
    assert by["nim-gemma4"]["health"] == "healthy" and by["nim-gemma4"]["gpus"] == [0, 1]
    assert by["litellm"]["health"] == "unhealthy" and by["vllm-ocr"]["health"] is None
    assert by["nim-gemma4"]["project"] == "llm" and by["nim-gemma4"]["ports"][0]["public"] == 8000
    assert rows[-1]["name"] == "web"  # stopped containers sort last


def fake_get(url):
    if url == "http://127.0.0.1:8000/v1/models":
        raise OSError("connection refused")  # NIM still loading
    if url == "http://127.0.0.1:8010/v1/models":
        return {"data": [{"id": "allenai/olmOCR-2-7B", "max_model_len": 16384}, {"id": "bad id; x"}]}
    if url == "http://127.0.0.1:4000/v1/models":
        raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)
    if url == "http://127.0.0.1:11434/api/tags":
        return {"models": [{"name": "llama3.1:8b"}]}
    raise AssertionError(f"unexpected probe {url}")


def test_probe_models():
    rows = services.container_rows(ITEMS, {})
    models = services.probe_models(rows, fake_get)
    got = {(m["container"], m["id"], m["kind"], m["auth"]) for m in models}
    assert got == {
        ("nim-gemma4", "google/gemma-4-31b-it", "image", False),  # from the image while it loads
        ("vllm-ocr", "allenai/olmOCR-2-7B", "openai", False),
        ("litellm", None, "openai", True),
        ("ollama", "llama3.1:8b", "ollama", False),
    }
    assert next(m for m in models if m["container"] == "vllm-ocr")["max_len"] == 16384


NGINX = """
user www-data;
http {
    upstream sagebackend { server 127.0.0.1:3333; }
    include /etc/nginx/conf.d/*.conf;
    include /etc/nginx/sites-enabled/*;
}
"""
SITE = """
server {
    listen 80; server_name _; return 301 https://$host$request_uri;
}
server {
    listen 443 ssl;
    server_name arcade.evl.uic.edu;
    location / { root /var/www; }
    location /congat/ { proxy_pass http://127.0.0.1:8101/; }   # an app
    location ^~ /scout { proxy_pass http://localhost:8102; }
    location ~ \\.php$ { proxy_pass http://127.0.0.1:9999; }
    location /sage/ { proxy_pass http://sagebackend; }
    location /remote/ { proxy_pass http://10.0.0.5:8000; }
}
server {
    listen 9000 ssl;
    server_name arcade.evl.uic.edu;
    location / { proxy_pass http://127.0.0.1:3000; }
}
"""


def test_nginx_routes(tmp_path):
    etc = tmp_path / "etc" / "nginx"
    (etc / "sites-available").mkdir(parents=True)
    (etc / "sites-enabled").mkdir()
    (etc / "conf.d").mkdir()
    (etc / "nginx.conf").write_text(NGINX)
    (etc / "sites-available" / "arcade").write_text(SITE)
    # an absolute symlink, as Debian makes them: must resolve inside hostfs
    os.symlink("/etc/nginx/sites-available/arcade", etc / "sites-enabled" / "arcade")
    routes = services.nginx_routes(str(tmp_path), "arcade.evl.uic.edu")
    assert routes == [
        {"url": "https://arcade.evl.uic.edu/congat/", "port": 8101},
        {"url": "https://arcade.evl.uic.edu/scout", "port": 8102},
        {"url": "https://arcade.evl.uic.edu/sage/", "port": 3333},
        {"url": "https://arcade.evl.uic.edu:9000/", "port": 3000},
    ]


CADDY = """
# utk
utk.evl.uic.edu {
    handle_path /curio/* {
        reverse_proxy localhost:5002
    }
    handle {
        reverse_proxy 127.0.0.1:8080
    }
}
other.example.org {
    reverse_proxy 10.1.1.1:80
}
"""


def test_caddy_routes(tmp_path):
    d = tmp_path / "etc" / "caddy"
    d.mkdir(parents=True)
    (d / "Caddyfile").write_text(CADDY)
    assert services.routes(str(tmp_path), None) == ("caddy", [
        {"url": "https://utk.evl.uic.edu/curio/", "port": 5002},
        {"url": "https://utk.evl.uic.edu/", "port": 8080},
    ])


def test_routes_none(tmp_path):
    assert services.routes(str(tmp_path), None) == ("none", [])


class FakeContainers:
    status = "ok"

    def items(self):
        return ITEMS


def test_sampler_payload_validates(tmp_path):
    published = []
    s = services.ServicesSampler(FakeContainers(), str(tmp_path), "arcade.evl.uic.edu",
                                 published.append, lambda: {}, probe=fake_get)
    parts = s.once()
    payload = services_payload("arcade", 1_790_000_000, parts)
    schema.validate(schema.SERVICES, payload)
    assert not schema.forbidden_keys(payload)
