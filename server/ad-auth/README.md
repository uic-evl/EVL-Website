# ad-auth: form login for the internal pages

Replaces the `nginx-ad-proxy` container on the www server. Same job (nginx `auth_request` against
Active Directory, same `X-Auth-Groups` / `X-Auth-Users` headers, HTTP Basic still accepted) plus a
login form and a session cookie, so visitors see an HTML page instead of the browser's password
dialog.

Files:

| File | What |
|---|---|
| `auth_service.py` | The service: `/auth`, `/login`, `/logout`, `/healthz` on port 8000 |
| `Dockerfile`, `docker-compose.yml`, `env.example` | How to run it |
| `nginx-internal.conf` | The nginx locations to include in the www server block |
| `../../login/index.html` | The login page, deployed with the site at `/login/` |
| `../../login/denied.html` | Shown to a signed-in user who is not in the allowed groups |

## Install on www

```sh
# 1. the service
scp -r server/ad-auth evlroot@www:~/ad-auth
ssh evlroot@www
cd ~/ad-auth && cp env.example .env
openssl rand -hex 32          # paste as SESSION_SECRET in .env; set AD_* like nginx-ad-proxy's
docker stop nginx-ad-proxy    # it holds 127.0.0.1:8000
docker compose up -d --build
curl -s http://127.0.0.1:8000/healthz   # ok

# 2. nginx
sudo cp nginx-internal.conf /etc/nginx/snippets/evl-internal-auth.conf
# in the www.evl.uic.edu server block: replace the old /auth-ad and /internal/ locations with
#   include snippets/evl-internal-auth.conf;
# and delete any auth_basic / auth_basic_user_file / satisfy lines for /internal/.
sudo nginx -t && sudo systemctl reload nginx
```

The login page itself arrives with the next site deploy (it is `login/index.html` in the repo),
so merge the site change before reloading nginx, or copy the two files into
`/var/www/html/login/` by hand.

## Updating

```sh
# service: re-copy the folder (or git pull), then
cd ~/ad-auth && docker compose up -d --build
# nginx: re-copy the snippet, then
sudo nginx -t && sudo systemctl reload nginx
```

## If something is off

| Symptom | Cause | Fix |
|---|---|---|
| `500 Internal Server Error` on `/internal/` | nginx got an unexpected answer from the auth subrequest: the service is not listening on 127.0.0.1:8000, or it answered 502 because it could not reach AD | `docker logs --tail 20 ad-auth` and `sudo tail /var/log/nginx/error.log`; check the container is up and the `AD_*` settings |
| `404 Not Found` on `/internal/` and `/login/`, even when signed in | the `/login/` and `/internal/` locations had no `root`, and the server block sets its root only inside `location /` | the snippet now sets `root /var/www/html;` in both; check the files exist with `ls /var/www/html/login/` |
| `ModuleNotFoundError: No module named 'Crypto'` / `unsupported hash type MD4` in the service log | NTLM bind (`AD_DOMAIN` without a dot) needs an MD4 implementation | `pycryptodome` is in `requirements.txt`, rebuild; or set `AD_DOMAIN` to the DNS name for a simple bind |
| Browser still shows its own password dialog | an `auth_basic` or `satisfy any` line is left in the `/internal/` location, or a cached Basic credential | remove those lines and reload; clear the site's saved password in the browser |
| Signed in but `Not allowed` page | the account is outside `$xAuthGroups` / `$xAuthUsers` | adjust the variables in the `/internal/` location, or check the group's CN as it appears in AD |
| Everyone signed out at once | `SESSION_SECRET` changed | expected; sign in again |

## Check

- `https://www.evl.uic.edu/internal/` in a browser shows the login page, and after signing in
  the internal page, at the same URL.
- `curl -u netid https://www.evl.uic.edu/internal/` still works for scripts.
- `https://www.evl.uic.edu/auth-ad/logout` signs out.
- `docker logs ad-auth` shows one line per login, never a password.

## Behaviour worth knowing

- Sessions are a signed cookie (HMAC-SHA256 with `SESSION_SECRET`), valid `SESSION_HOURS`, so no
  server-side store; restarting the container keeps everyone signed in, changing the secret signs
  everyone out.
- Five failed attempts from one address pause that address for a minute (`MAX_FAILURES`,
  `LOCKOUT_SECONDS`).
- Group restriction works as in nginx-ad-proxy: set `$xAuthGroups` / `$xAuthUsers` in the nginx
  location. The groups are read once at login and stored in the cookie.
- `AD_DOMAIN` with a dot binds as `user@domain` (simple bind over StartTLS); without a dot it binds
  as `DOMAIN\user` with NTLM. Prefer the DNS form. NTLM needs the `pycryptodome` package, which
  is in `requirements.txt`; without it ldap3 fails with "unsupported hash type MD4".
