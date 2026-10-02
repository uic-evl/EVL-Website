#!/bin/sh
# Install or update the EVL monitor hub (arcade only).
#
#   sudo ./install-hub.sh
#
# The hub polls every agent listed in _data/monitor.yml and serves the page's data over
# HTTPS on port 6161, with this machine's *.evl.uic.edu certificate (found in its nginx
# config; set HUB_TLS_CERT and HUB_TLS_KEY to choose others). Run it again after
# `git pull` to update; a changed host list is picked up without it.
set -eu

PORT="${HUB_PORT:-6161}"
die() { echo "install-hub.sh: $*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "run with sudo (it reads the TLS key's location and writes .env)"
command -v docker >/dev/null || die "docker is not installed"
docker compose version >/dev/null 2>&1 || die "docker compose v2 is not installed"

cd "$(dirname "$0")"
HERE="$(pwd)"

# back up after a reboot: Docker itself must start at boot
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
  for unit in docker.service containerd.service; do
    if systemctl list-unit-files "$unit" >/dev/null 2>&1 && ! systemctl is-enabled --quiet "$unit" 2>/dev/null; then
      systemctl enable "$unit" >/dev/null 2>&1 && echo "Enabled $unit at boot."
    fi
  done
fi

HOSTS_DIR="${HUB_HOSTS_DIR:-$(cd ../.. && pwd)/_data}"
[ -f "$HOSTS_DIR/monitor.yml" ] || die "no $HOSTS_DIR/monitor.yml; add it to the checkout: git sparse-checkout add _data"

# the certificate this machine's nginx already serves
CERT="${HUB_TLS_CERT:-}"
KEY="${HUB_TLS_KEY:-}"
if [ -z "$CERT" ] || [ -z "$KEY" ]; then
  conf="$(grep -RlsE '^[[:space:]]*ssl_certificate[[:space:]]' /etc/nginx/sites-enabled /etc/nginx/conf.d /etc/nginx/nginx.conf 2>/dev/null | head -1 || true)"
  [ -n "$conf" ] || die "no ssl_certificate in this machine's nginx config; set HUB_TLS_CERT and HUB_TLS_KEY"
  CERT="$(grep -hE '^[[:space:]]*ssl_certificate[[:space:]]' "$conf" | head -1 | awk '{print $2}' | tr -d '";')"
  KEY="$(grep -hE '^[[:space:]]*ssl_certificate_key[[:space:]]' "$conf" | head -1 | awk '{print $2}' | tr -d '";')"
fi
[ -r "$CERT" ] || die "cannot read certificate $CERT"
[ -r "$KEY" ] || die "cannot read key $KEY"
if command -v openssl >/dev/null; then
  echo "Certificate: $CERT"
  openssl x509 -in "$CERT" -noout -subject -enddate | sed 's/^/  /'
  openssl x509 -in "$CERT" -noout -checkend 0 >/dev/null || die "the certificate has expired"
fi

if ! docker ps --format '{{.Names}}' | grep -qx evl-monitor-hub; then
  if command -v ss >/dev/null && ss -ltnH "sport = :$PORT" | grep -q .; then
    die "port $PORT is already in use on this host"
  fi
fi

TAG="$(git rev-parse --short HEAD 2>/dev/null || echo local)"
cat > .env <<EOF
# written by install-hub.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ)
HUB_TAG=$TAG
HUB_PORT=$PORT
HUB_HOSTS_DIR=$HOSTS_DIR
HUB_CERT_DIR=$(dirname "$CERT")
HUB_CERT_FILE=$(basename "$CERT")
HUB_KEY_DIR=$(dirname "$KEY")
HUB_KEY_FILE=$(basename "$KEY")
HUB_DEV=${HUB_DEV:-}
EOF

echo "Building and starting the monitor hub $TAG on port $PORT ..."
docker compose up -d --build --remove-orphans --wait --wait-timeout 180

FQDN="${HUB_FQDN:-$(hostname -f 2>/dev/null || hostname)}"
echo "Waiting for the first poll round ..."
i=0
while [ $i -lt 20 ]; do
  if out="$(docker exec evl-monitor-hub python -c "
import json, ssl, urllib.request
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
d = json.load(urllib.request.urlopen('https://127.0.0.1:6161/overview.json', context=ctx, timeout=5))
print(' '.join(h['id'] + '=' + h['status'] for h in d['hosts']))
" 2>/dev/null)"; then
    case "$out" in *connecting*) ;; *) break ;; esac
  fi
  i=$((i + 1))
  sleep 3
done
echo "Hosts: ${out:-no answer}"

# the hub reaches this machine's own agent from a Docker network address
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
  if ! ufw status | grep -E "(^| )9877" | grep -q "172.16.0.0/12"; then
    echo "note: ufw is active. If this machine's own agent shows offline, let the hub reach it with:"
    echo "      sudo ufw allow from 172.16.0.0/12 to any port 9877 proto tcp"
  fi
fi
echo "Done. The hub starts again with Docker after a reboot."
echo "Check from your browser: https://$FQDN:$PORT/overview.json"
