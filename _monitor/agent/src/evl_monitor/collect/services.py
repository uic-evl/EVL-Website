"""What a host offers: its Docker containers, the models they serve, and its web routes.

- Containers come from the docker-proxy (name, image, state, ports, compose labels).
- Models: inference containers (NIM, vLLM, Ollama, LiteLLM, ...) are asked for their
  model list on their published ports (OpenAI `GET /v1/models`, Ollama `GET /api/tags`),
  and a NIM image name also names its model. The agent runs in the host network
  namespace, so 127.0.0.1 here is the host's loopback, where these ports are published.
- Routes: the host's reverse proxy config (nginx, or Caddy on utk) is read through
  /hostfs, and each route to a local port becomes a public URL plus that port's
  container.

Everything is best effort: a failure gives an empty list, never an exception.
"""

from __future__ import annotations

import glob
import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.request

from .containers import NAME_RE, ContainerNames
from .section import section

log = logging.getLogger(__name__)

CONTAINERS_EVERY = 60.0
MODELS_EVERY = 300.0
ROUTES_EVERY = 300.0
PROBE_TIMEOUT = 1.5
MAX_PROBE_BYTES = 1024 * 1024

INFERENCE_RE = re.compile(
    r"(nim|vllm|tgi|text-generation|ollama|litellm|sglang|triton|lmdeploy|llama|openai|tensorrt|infinity|tei)",
    re.I)
NIM_IMAGE_RE = re.compile(r"^nvcr\.io/nim/([a-z0-9._-]+/[a-z0-9._-]+)(?::[A-Za-z0-9._-]+)?$")
MODEL_ID_RE = re.compile(r"^[A-Za-z0-9._/:@+-]{1,128}$")
IMAGE_RE = re.compile(r"^[A-Za-z0-9._/:@-]{1,200}$")
LABEL_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
STATUS_RE = re.compile(r"^[A-Za-z0-9 ()-]{0,64}$")
URL_RE = re.compile(r"^https?://[a-z0-9.-]+(:\d{1,5})?(/[A-Za-z0-9._~/-]*)?$")
LOCAL_HOSTS = {"127.0.0.1", "localhost", "0.0.0.0", "::1", "[::1]", "::", "[::]"}

STATES = ("created", "running", "paused", "restarting", "removing", "exited", "dead")
HEALTH = ("healthy", "unhealthy", "starting")


# containers ---------------------------------------------------------------------


def container_rows(items: list[dict], gpu_use: dict[str, tuple[list[int], float]]) -> list[dict]:
    rows = []
    for it in items:
        name = ((it.get("Names") or [""])[0] or "").lstrip("/")
        if not NAME_RE.match(name):
            continue
        image = it.get("Image") or ""
        status = it.get("Status") or ""
        health = next((h for h in HEALTH if f"({h}" in status or f"(health: {h}" in status), None)
        labels = it.get("Labels") or {}
        ports = []
        for p in it.get("Ports") or []:
            ip = p.get("IP") or ""
            ports.append({
                "public": p.get("PublicPort") if isinstance(p.get("PublicPort"), int) else None,
                "private": p["PrivatePort"],
                # where it listens, never the address itself
                "bind": "any" if ip in ("", "0.0.0.0", "::") else "loopback" if ip in ("127.0.0.1", "::1")
                else "other",
                "proto": p.get("Type") if p.get("Type") in ("tcp", "udp", "sctp") else "tcp",
            })
        uses = gpu_use.get(name, ([], 0.0))
        rows.append({
            "name": name,
            "image": image if IMAGE_RE.match(image) else None,
            "state": it.get("State") if it.get("State") in STATES else None,
            "health": health,
            "status": status if STATUS_RE.match(status) else None,
            "created_ts": it.get("Created") if isinstance(it.get("Created"), int) else None,
            "ports": ports,
            "project": labels.get("com.docker.compose.project") if LABEL_RE.match(
                labels.get("com.docker.compose.project", "") or "") else None,
            "service": labels.get("com.docker.compose.service") if LABEL_RE.match(
                labels.get("com.docker.compose.service", "") or "") else None,
            "gpus": sorted(uses[0]),
            "gpu_mem_gib": round(uses[1], 1),
        })
    rows.sort(key=lambda r: (r["state"] != "running", r["name"]))
    return rows


# models ---------------------------------------------------------------------------


def _get_json(url: str):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "evl-monitor"})
    with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT) as resp:  # noqa: S310 - fixed loopback URLs
        return json.loads(resp.read(MAX_PROBE_BYTES))


def probe_models(containers: list[dict], get_json=_get_json) -> list[dict]:
    models: list[dict] = []
    for c in containers:
        if c["state"] != "running" or not INFERENCE_RE.search(f"{c['image'] or ''} {c['name']}"):
            continue
        found = False
        for p in c["ports"]:
            if p["proto"] != "tcp" or not p["public"] or p["bind"] == "other":
                continue
            ollama = "ollama" in (c["image"] or "").lower()
            url = f"http://127.0.0.1:{p['public']}" + ("/api/tags" if ollama else "/v1/models")
            try:
                body = get_json(url)
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 403):  # LiteLLM and friends: models exist, list needs a key
                    models.append({"id": None, "container": c["name"], "port": p["public"],
                                   "kind": "openai", "max_len": None, "auth": True})
                    found = True
                continue
            except (OSError, ValueError):
                continue
            entries = body.get("models") if ollama else body.get("data")
            for m in entries if isinstance(entries, list) else []:
                mid = m.get("name") if ollama else m.get("id")
                if isinstance(mid, str) and MODEL_ID_RE.match(mid):
                    max_len = m.get("max_model_len")
                    models.append({"id": mid, "container": c["name"], "port": p["public"],
                                   "kind": "ollama" if ollama else "openai",
                                   "max_len": max_len if isinstance(max_len, int) else None, "auth": False})
                    found = True
        m = NIM_IMAGE_RE.match(c["image"] or "")
        if m and not found:
            models.append({"id": m.group(1), "container": c["name"], "port": None, "kind": "image",
                           "max_len": None, "auth": False})
    return models[:200]


# routes -------------------------------------------------------------------------------


def _tokens(text: str):
    text = re.sub(r"(?m)#.*$", "", text)
    for m in re.finditer(r'"[^"]*"|\'[^\']*\'|[{};]|[^\s{};]+', text):
        yield m.group(0).strip("\"'")


class _Nginx:
    def __init__(self, hostfs: str):
        self.hostfs = hostfs
        self.upstreams: dict[str, list[int]] = {}
        self.routes: list[dict] = []

    def host_path(self, path: str, base: str = "/etc/nginx") -> str:
        if not path.startswith("/"):
            path = os.path.join(base, path)
        return os.path.join(self.hostfs, path.lstrip("/"))

    def read(self, pattern: str, depth: int = 0) -> list[str]:
        if depth > 4:
            return []
        out = []
        for p in sorted(glob.glob(self.host_path(pattern))):
            real = p
            for _ in range(8):  # resolve absolute symlinks inside /hostfs, not the container
                if not os.path.islink(real):
                    break
                target = os.readlink(real)
                real = os.path.join(self.hostfs, target.lstrip("/")) if target.startswith("/") \
                    else os.path.join(os.path.dirname(real), target)
            if os.path.isfile(real):
                with open(real, errors="replace") as f:
                    out.append(f.read(512 * 1024))
        return out

    def parse(self, text: str, depth: int = 0) -> None:
        toks = list(_tokens(text))
        stack: list[dict] = []
        i, stmt = 0, []
        while i < len(toks):
            t = toks[i]
            i += 1
            if t == "{":
                ctx = {"kind": stmt[0] if stmt else "", "args": stmt[1:]}
                if ctx["kind"] == "server":
                    ctx.update(names=[], ssl=False, ports=[])
                stack.append(ctx)
                stmt = []
            elif t == "}":
                if stack:
                    stack.pop()
                stmt = []
            elif t == ";":
                self.directive(stmt, stack, depth)
                stmt = []
            else:
                stmt.append(t)

    def directive(self, stmt: list[str], stack: list[dict], depth: int) -> None:
        if not stmt:
            return
        name, args = stmt[0], stmt[1:]
        if name == "include" and args:
            for text in self.read(args[0], depth + 1):
                self.parse(text, depth + 1)
            return
        server = next((c for c in reversed(stack) if c["kind"] == "server"), None)
        if stack and stack[-1]["kind"] == "upstream" and name == "server" and args:
            port = _port_of(args[0])
            if port:
                self.upstreams.setdefault(stack[-1]["args"][0] if stack[-1]["args"] else "", []).append(port)
            return
        if server is None:
            return
        if name == "server_name":
            server["names"].extend(args)
        elif name == "listen" and args:
            if "ssl" in args:
                server["ssl"] = True
            port = _port_of(args[0])
            if port:
                server["ports"].append(port)
        elif name == "proxy_pass" and args:
            loc = next((c for c in reversed(stack) if c["kind"] == "location"), None)
            if loc is None:
                return
            largs = loc["args"]
            if not largs or largs[0] in ("~", "~*", "@") or largs[0].startswith("@"):
                return  # regex and named locations have no single public path
            path = largs[-1]
            self.routes.append({"server": server, "path": path, "proxy": args[0]})

    def resolve(self, fallback_host: str | None) -> list[dict]:
        out = []
        for r in self.routes:
            s = r["server"]
            m = re.match(r"^(https?)://([^/:]+|\[[^\]]+\])(?::(\d+))?", r["proxy"])
            if not m:
                continue
            host = m.group(2)
            if host in self.upstreams:
                ports = self.upstreams[host]
                port = ports[0] if ports else None
            elif host in LOCAL_HOSTS:
                port = int(m.group(3)) if m.group(3) else (443 if m.group(1) == "https" else 80)
            else:
                continue  # proxies to another machine
            names = [n for n in s["names"] if n not in ("_", "localhost") and "*" not in n and not n.startswith("~")]
            name = names[0] if names else fallback_host
            if not name:
                continue
            ssl = s["ssl"] or 443 in s["ports"]
            listen = next((p for p in s["ports"] if p not in (80, 443)), None)
            scheme = "https" if ssl else "http"
            netloc = name if listen is None else f"{name}:{listen}"
            out.append((f"{scheme}://{netloc}{r['path']}", port))
        return [{"url": u, "port": p} for u, p in dict.fromkeys(out)]


def _port_of(addr: str) -> int | None:
    m = re.search(r":(\d{1,5})$", addr) or re.fullmatch(r"(\d{1,5})", addr)
    return int(m.group(1)) if m else None


def nginx_routes(hostfs: str, fallback_host: str | None) -> list[dict]:
    ng = _Nginx(hostfs)
    texts = ng.read("/etc/nginx/nginx.conf")
    if not texts:
        return []
    ng.parse(texts[0])
    return ng.resolve(fallback_host)


def caddy_routes(hostfs: str, fallback_host: str | None) -> list[dict]:
    path = os.path.join(hostfs, "etc/caddy/Caddyfile")
    if not os.path.isfile(path):
        return []
    with open(path, errors="replace") as f:
        lines = [re.sub(r"#.*$", "", line).strip() for line in f.read(512 * 1024).splitlines()]
    out = []
    site: str | None = None
    depth = 0
    handles: list[tuple[int, str]] = []
    for line in lines:
        if not line:
            continue
        opens, closes = line.count("{"), line.count("}")
        head = line.rstrip("{").strip()
        if depth == 0 and opens:
            addr = head.split(",")[0].split()[0] if head else ""
            site = addr if addr and not addr.startswith("(") else None
        elif opens and re.match(r"^(handle_path|handle|route)\s+(/\S*)", head):
            handles.append((depth, re.match(r"^\S+\s+(/\S*)", head).group(1).rstrip("*")))
        m = re.match(r"^reverse_proxy\s+(?:\S+\s+)?(\S+:\d+)", line)
        if m and site is not None:
            port = _port_of(m.group(1))
            host = m.group(1).rsplit(":", 1)[0].replace("http://", "")
            if host in LOCAL_HOSTS and port:
                name = re.sub(r"^https?://", "", site)
                if name.startswith(":") or not name:
                    name = (fallback_host or "") + name
                scheme = "http" if site.startswith("http://") else "https"
                prefix = handles[-1][1] if handles else "/"
                out.append({"url": f"{scheme}://{name}{prefix or '/'}", "port": port})
        depth += opens - closes
        while handles and handles[-1][0] >= depth:
            handles.pop()
        if depth == 0:
            site = None
    return out


def routes(hostfs: str, fallback_host: str | None) -> tuple[str, list[dict]]:
    found = section("routes:nginx", lambda: nginx_routes(hostfs, fallback_host), [])
    if found:
        return "nginx", found
    found = section("routes:caddy", lambda: caddy_routes(hostfs, fallback_host), [])
    return ("caddy", found) if found else ("none", [])


# the thread ---------------------------------------------------------------------------


class ServicesSampler(threading.Thread):
    """Rebuilds services.json on its own thread: probes can take seconds."""

    def __init__(self, containers: ContainerNames, hostfs: str, fqdn: str | None, publish,
                 gpu_use, clock=time, probe=_get_json):
        super().__init__(name="services", daemon=True)
        self.containers = containers
        self.hostfs = hostfs
        self.fqdn = fqdn
        self.publish = publish  # callable(payload_parts)
        self.gpu_use = gpu_use  # callable() -> {container name: ([gpu indices], gpu mem GiB)}
        self.clock = clock
        self.probe = probe
        self._stop = threading.Event()
        self._models: list[dict] = []
        self._models_at = -1e9
        self._models_ts: int | None = None
        self._routes: tuple[str, list[dict]] = ("none", [])
        self._routes_at = -1e9

    def stop(self) -> None:
        self._stop.set()

    def once(self) -> dict:
        now = time.monotonic()
        rows = container_rows(self.containers.items(), self.gpu_use())
        if now - self._models_at > MODELS_EVERY:
            self._models = section("models", lambda: probe_models(rows, self.probe), self._models)
            self._models_at = now
            self._models_ts = int(time.time())
        if now - self._routes_at > ROUTES_EVERY:
            self._routes = routes(self.hostfs, self.fqdn)
            self._routes_at = now
        port_owner = {p["public"]: r["name"] for r in rows for p in r["ports"] if p["public"]}
        source, found = self._routes
        route_rows = [{"url": r["url"], "port": r["port"], "container": port_owner.get(r["port"])}
                      for r in found if URL_RE.match(r["url"])][:500]
        return {
            "containers_status": self.containers.status,
            "containers": rows,
            "models": self._models,
            "models_ts": self._models_ts,
            "routes_source": source,
            "routes": route_rows,
        }

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                self.publish(self.once())
            except Exception:  # noqa: BLE001
                log.exception("services refresh failed")
            self._stop.wait(CONTAINERS_EVERY)
