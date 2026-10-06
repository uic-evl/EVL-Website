#!/usr/bin/env python3
"""Login service for nginx auth_request, checking users against Active Directory.

A drop-in successor to nginx-ad-proxy: /auth still accepts HTTP Basic credentials and the
X-Auth-Groups / X-Auth-Users headers, and adds a session cookie set by a login form so browsers
see an HTML page instead of their own password dialog.

Endpoints, all reached through nginx on 127.0.0.1 (see nginx-internal.conf):
  GET  /auth     200 when the request carries a valid session cookie or valid Basic credentials
                 and the user passes the group/user check; 401 otherwise (403 for a valid user
                 who is not allowed). Sets X-Auth-User on success.
  POST /login    form fields username, password, next. Binds to AD as the user, sets the cookie
                 and redirects to next; on failure redirects to /login/?error=...&next=...
  GET  /logout   clears the cookie and redirects to /.
  GET  /healthz  200.

Configuration is read from the environment (see README.md).
"""

import base64
import hashlib
import hmac
import html
import json
import logging
import os
import re
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

import ldap3
from ldap3.core.exceptions import LDAPException

# ----------------------------------------------------------------------------- configuration

AD_HOST = os.environ.get("AD_HOST", "")
AD_PORT = int(os.environ.get("AD_PORT", "389"))
AD_USE_TLS = os.environ.get("AD_USE_TLS", "1") == "1"          # StartTLS on 389; ignored on 636
AD_DOMAIN = os.environ.get("AD_DOMAIN", "")                      # NetBIOS name (UIC) or DNS name (ad.uic.edu)
AD_BASEDN = [b for b in os.environ.get("AD_BASEDN", "").split("|") if b]
SESSION_SECRET = os.environ.get("SESSION_SECRET", "")
SESSION_HOURS = float(os.environ.get("SESSION_HOURS", "12"))
COOKIE_NAME = os.environ.get("COOKIE_NAME", "evl_session")
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "1") == "1"
LOGIN_PAGE = os.environ.get("LOGIN_PAGE", "/login/")
LISTEN = os.environ.get("LISTEN", "0.0.0.0:8000")
MAX_FAILURES = int(os.environ.get("MAX_FAILURES", "5"))          # per client IP ...
LOCKOUT_SECONDS = int(os.environ.get("LOCKOUT_SECONDS", "60"))   # ... before this pause

USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
log = logging.getLogger("ad-auth")

# ----------------------------------------------------------------------------- sessions

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def make_session(user: str, groups: list[str]) -> str:
    """A signed, self-contained token: payload.signature, valid for SESSION_HOURS."""
    payload = json.dumps({"u": user, "g": groups, "exp": int(time.time() + SESSION_HOURS * 3600)}, separators=(",", ":"))
    body = _b64(payload.encode())
    sig = _b64(hmac.new(SESSION_SECRET.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def read_session(token: str):
    """The payload of a valid, unexpired token, else None."""
    try:
        body, sig = token.split(".", 1)
        expected = _b64(hmac.new(SESSION_SECRET.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(_unb64(body))
        if data.get("exp", 0) < time.time():
            return None
        return data
    except (ValueError, TypeError, json.JSONDecodeError):
        return None

# ----------------------------------------------------------------------------- active directory

def ad_login(username: str, password: str):
    """Bind to AD as the user. Returns the user's group names (CNs) on success, None on bad credentials.
    Raises LDAPException when the directory cannot be reached."""
    if not password:
        return None
    use_ssl = AD_PORT == 636
    server = ldap3.Server(AD_HOST, port=AD_PORT, use_ssl=use_ssl, get_info=ldap3.NONE, connect_timeout=5)
    if "." in AD_DOMAIN:
        bind_user, auth = f"{username}@{AD_DOMAIN}", ldap3.SIMPLE
    else:
        bind_user, auth = f"{AD_DOMAIN}\\{username}", ldap3.NTLM
    conn = ldap3.Connection(server, user=bind_user, password=password, authentication=auth, receive_timeout=10)
    conn.open()
    if AD_USE_TLS and not use_ssl:
        conn.start_tls()
    if not conn.bind():
        conn.unbind()
        return None
    groups: list[str] = []
    for base in AD_BASEDN:
        try:
            conn.search(base, f"(sAMAccountName={ldap3.utils.conv.escape_filter_chars(username)})", attributes=["memberOf"])
        except LDAPException as e:
            log.warning("group lookup failed in %s: %s", base, e)
            continue
        for entry in conn.entries:
            for dn in entry.memberOf.values if "memberOf" in entry else []:
                m = re.match(r"CN=([^,]+)", dn, re.IGNORECASE)
                if m:
                    groups.append(m.group(1))
    conn.unbind()
    return sorted(set(groups))


def allowed(user: str, groups: list[str], allowed_groups: str, allowed_users: str) -> bool:
    """The nginx-ad-proxy rule: with no restriction every authenticated user passes; otherwise the
    user must be in one of the listed groups or be one of the listed users."""
    want_groups = {g.strip().lower() for g in allowed_groups.split(",") if g.strip()}
    want_users = {u.strip().lower() for u in allowed_users.split(",") if u.strip()}
    if not want_groups and not want_users:
        return True
    return user.lower() in want_users or bool(want_groups & {g.lower() for g in groups})

# ----------------------------------------------------------------------------- brute-force pause

_failures: dict[str, list[float]] = {}
_failures_lock = threading.Lock()


def locked(ip: str) -> bool:
    now = time.time()
    with _failures_lock:
        recent = [t for t in _failures.get(ip, []) if now - t < LOCKOUT_SECONDS]
        _failures[ip] = recent
        return len(recent) >= MAX_FAILURES


def note_failure(ip: str) -> None:
    with _failures_lock:
        _failures.setdefault(ip, []).append(time.time())

# ----------------------------------------------------------------------------- http

class Handler(BaseHTTPRequestHandler):
    server_version = "evl-ad-auth/1.0"

    def log_message(self, fmt, *args):  # quieter than the default, and never the query string
        log.info("%s %s %s", self.client_ip(), self.command, self.path.split("?")[0])

    def client_ip(self) -> str:
        return self.headers.get("X-Real-IP") or self.headers.get("X-Forwarded-For", "").split(",")[0].strip() or self.client_address[0]

    def cookie(self, name: str):
        for part in self.headers.get("Cookie", "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == name:
                return v
        return None

    def send(self, status, headers=None, body: bytes = b""):
        self.send_response(status)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def redirect(self, location: str, extra_headers=None):
        self.send(HTTPStatus.SEE_OTHER, {"Location": location, **(extra_headers or {})})

    def set_cookie_header(self, value: str, max_age: int) -> str:
        attrs = [f"{COOKIE_NAME}={value}", "Path=/", "HttpOnly", "SameSite=Lax", f"Max-Age={max_age}"]
        if COOKIE_SECURE:
            attrs.append("Secure")
        return "; ".join(attrs)

    # --- GET

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/auth":
            return self.handle_auth()
        if path == "/logout":
            return self.redirect("/", {"Set-Cookie": self.set_cookie_header("", 0)})
        if path == "/healthz":
            return self.send(HTTPStatus.OK, {"Content-Type": "text/plain"}, b"ok\n")
        self.send(HTTPStatus.NOT_FOUND, {"Content-Type": "text/plain"}, b"not found\n")

    do_HEAD = do_GET

    def handle_auth(self):
        allowed_groups = self.headers.get("X-Auth-Groups", "")
        allowed_users = self.headers.get("X-Auth-Users", "")

        # 1. Session cookie set by the login form.
        token = self.cookie(COOKIE_NAME)
        session = read_session(token) if token else None
        if session:
            if allowed(session["u"], session.get("g", []), allowed_groups, allowed_users):
                return self.send(HTTPStatus.OK, {"X-Auth-User": session["u"]})
            return self.send(HTTPStatus.FORBIDDEN)

        # 2. HTTP Basic, for scripts and for curl. Never sends a WWW-Authenticate challenge back,
        #    so browsers get the login page from nginx instead of their password dialog.
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Basic "):
            try:
                user, _, password = base64.b64decode(auth[6:]).decode().partition(":")
            except (ValueError, UnicodeDecodeError):
                return self.send(HTTPStatus.UNAUTHORIZED)
            if not USERNAME_RE.match(user) or locked(self.client_ip()):
                return self.send(HTTPStatus.UNAUTHORIZED)
            try:
                groups = ad_login(user, password)
            except LDAPException as e:
                log.error("AD unreachable: %s", e)
                return self.send(HTTPStatus.BAD_GATEWAY)
            if groups is None:
                note_failure(self.client_ip())
                return self.send(HTTPStatus.UNAUTHORIZED)
            if allowed(user, groups, allowed_groups, allowed_users):
                return self.send(HTTPStatus.OK, {"X-Auth-User": user})
            return self.send(HTTPStatus.FORBIDDEN)

        self.send(HTTPStatus.UNAUTHORIZED)

    # --- POST

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/login":
            return self.send(HTTPStatus.NOT_FOUND, {"Content-Type": "text/plain"}, b"not found\n")
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > 4096:
            return self.send(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        form = parse_qs(self.rfile.read(length).decode(errors="replace"), keep_blank_values=True)
        user = form.get("username", [""])[0].strip()
        password = form.get("password", [""])[0]
        nxt = form.get("next", ["/"])[0]
        if not nxt.startswith("/") or nxt.startswith("//"):
            nxt = "/"
        ip = self.client_ip()

        def fail(code: str):
            return self.redirect(f"{LOGIN_PAGE}?error={code}&next={quote(nxt, safe='/?=&')}")

        if locked(ip):
            return fail("locked")
        if not USERNAME_RE.match(user):
            note_failure(ip)
            return fail("bad")
        try:
            groups = ad_login(user, password)
        except LDAPException as e:
            log.error("AD unreachable: %s", e)
            return fail("error")
        if groups is None:
            note_failure(ip)
            log.info("login failed for %s from %s", user, ip)
            return fail("bad")
        log.info("login ok for %s from %s (%d groups)", user, ip, len(groups))
        token = make_session(user, groups)
        self.redirect(nxt, {"Set-Cookie": self.set_cookie_header(token, int(SESSION_HOURS * 3600))})


def main():
    missing = [k for k, v in {"AD_HOST": AD_HOST, "AD_DOMAIN": AD_DOMAIN, "SESSION_SECRET": SESSION_SECRET}.items() if not v]
    if missing:
        sys.exit(f"missing environment variables: {', '.join(missing)}")
    if len(SESSION_SECRET) < 32:
        sys.exit("SESSION_SECRET must be at least 32 characters (try: openssl rand -hex 32)")
    host, _, port = LISTEN.rpartition(":")
    httpd = ThreadingHTTPServer((host or "0.0.0.0", int(port)), Handler)
    log.info("listening on %s, AD %s:%d (%s), sessions %.0fh", LISTEN, AD_HOST, AD_PORT, AD_DOMAIN, SESSION_HOURS)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
