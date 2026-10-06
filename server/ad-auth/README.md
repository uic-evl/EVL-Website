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
