#!/bin/sh
# Install or update the EVL monitor agent on this server.
#
#   sudo ./install.sh <id>          e.g. sudo ./install.sh arcade
#
# <id> is the host's id in _data/monitor.yml. Run it again after `git pull` to update;
# history is kept in the evl-monitor_data volume. See _monitor/README.md.
set -eu

ID="${1:-}"
PORT="${MONITOR_PORT:-9877}"
BIND="${MONITOR_BIND_IP:-0.0.0.0}"
WEB_SERVER_IP="131.193.78.85"  # www.evl.uic.edu, the relay that reads this agent

die() { echo "install.sh: $*" >&2; exit 1; }

case "$ID" in
  "" ) die "usage: sudo $0 <id>   (the host's id in _data/monitor.yml)" ;;
esac
echo "$ID" | grep -Eq '^[a-z0-9][a-z0-9-]{0,31}$' || die "id must match ^[a-z0-9][a-z0-9-]{0,31}\$"
[ "$(id -u)" -eq 0 ] || die "run with sudo (it reads the docker group and writes .env)"
command -v docker >/dev/null || die "docker is not installed"
docker compose version >/dev/null 2>&1 || die "docker compose v2 is not installed"

cd "$(dirname "$0")"

# a port already taken by something other than this agent?
if ! docker ps --format '{{.Names}}' | grep -qx evl-monitor-agent; then
  if command -v ss >/dev/null && ss -ltnH "sport = :$PORT" | grep -q .; then
    die "port $PORT is already in use on this host; set MONITOR_PORT and update _monitor/web"
  fi
fi

FILES="-f compose.yaml"
GPU="no"
if docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -q nvidia || [ -e /etc/cdi/nvidia.yaml ]; then
  FILES="$FILES -f compose.gpu.yaml"
  GPU="yes"
elif command -v nvidia-smi >/dev/null; then
  echo "warning: nvidia-smi exists but Docker has no nvidia runtime; GPUs will not be monitored."
  echo "         install nvidia-container-toolkit, run 'nvidia-ctk runtime configure --runtime=docker',"
  echo "         restart Docker, then rerun this script."
fi
SSSD="no"
if [ -S /var/lib/sss/pipes/nss ]; then
  FILES="$FILES -f compose.sssd.yaml"
  SSSD="yes"
fi

# the group that owns the socket (usually "docker"); the socket proxy joins it
[ -S /var/run/docker.sock ] || die "no Docker socket at /var/run/docker.sock"
DOCKER_GID="$(stat -c %g /var/run/docker.sock)"
TAG="$(git rev-parse --short HEAD 2>/dev/null || echo local)"
FQDN="$(hostname -f 2>/dev/null || hostname)"

cat > .env <<EOF
# written by install.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ)
MONITOR_ID=$ID
MONITOR_FQDN=$FQDN
MONITOR_TAG=$TAG
MONITOR_PORT=$PORT
MONITOR_BIND_IP=$BIND
DOCKER_GID=$DOCKER_GID
EOF
echo "$FILES" > .compose-files

echo "Building and starting evl-monitor $TAG for '$ID' (GPU: $GPU, SSSD: $SSSD) ..."
# shellcheck disable=SC2086
docker compose $FILES up -d --build --remove-orphans --wait --wait-timeout 180

echo "Checking every file the agent serves ..."
docker exec evl-monitor-agent python -m evl_monitor.check "http://127.0.0.1:$PORT/" --id "$ID"

if command -v ufw >/dev/null && ufw status 2>/dev/null | grep -q "Status: active"; then
  if ! ufw status | grep -q "$PORT"; then
    echo "note: ufw is active. Let the web server reach the agent with:"
    echo "      sudo ufw allow from $WEB_SERVER_IP to any port $PORT proto tcp"
  fi
fi
echo "Done. From the web server: curl -s http://$FQDN:$PORT/healthz"
