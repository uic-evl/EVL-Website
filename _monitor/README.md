# EVL server monitor

The page at https://www.evl.uic.edu/internal/monitor/ shows live load, history, GPU use,
containers, models and web services for the EVL servers.

```
browser (www.evl.uic.edu/internal/monitor/, behind the /internal/ password)
   --HTTPS-->  arcade.evl.uic.edu:6161   hub (Docker, arcade)
                 polls over the campus network -->  <id>.evl.uic.edu:9877   agent (Docker, each server)
```

- **The agent** runs on each server. It is a small container that samples that server every
  5 seconds, keeps compact history in SQLite, and serves JSON on port 9877.
- **The hub** runs on arcade. It polls every agent gently, caches what it gets, and serves it
  to the page over HTTPS on port 6161. The servers only ever hear from the hub, however many
  people have the page open.

| Folder | What it holds |
|---|---|
| `agent/` | the agent and hub code (Python), the Dockerfile, the agent's compose files and `install.sh` |
| `hub/` | the hub's compose file and `install-hub.sh` |
| `tools/` | `hosts.py` (checks the host list), `check_dashes.py` |

`_data/monitor.yml` is the list of hosts. The page and the hub both read it.

## How gently the hub polls

| File | When | Interval |
|---|---|---|
| `now.json` | always | 15 s |
| `services.json` | always | 2 min |
| `daily.json` | always | 15 min |
| `host.json`, `spark.json` | always | 10 min |
| `procs.json`, `history/*`, `series/*`, `usage.json` | only while someone has that server open | cached for at least 10 s |

- **One request at a time per server,** with gzip and ETags, and a 3 s timeout.
- **A server that stops answering** is retried after 15 and 30 s, then every minute.
- **The load is fixed:** about 5 small requests a minute per server, measured with 20 pages open.
- **Validation:** every reply is checked against the agent's closed schema before the hub keeps it.

## Files each agent serves (the hub serves the same files at `/<id>/<file>`)

| File | Contents | Refreshed |
|---|---|---|
| `now.json` | current CPU (total, per core, by type), load, memory, swap, network, disk I/O, mounts, NICs, disks, processes, logins, CPU temperature, and per GPU: utilization, memory, power, temperature, clocks, PCIe, encoder/decoder, ECC errors, throttling | 5 s |
| `procs.json` | per GPU: the processes using it (user, container, process name, GPU memory) | 5 s |
| `host.json` | OS, kernel, CPU model and topology, memory, mounts, NICs, disks, GPU models, driver and CUDA versions, the history ranges, and the list of files | 60 s |
| `services.json` | Docker containers (running and stopped: image, state, health, ports, compose project, GPUs used), models served by inference containers, and the web routes in the host's nginx or Caddy config | 60 s (models 5 min) |
| `daily.json` | for each of the last 30 days and today: average CPU %, memory %, GPU utilization %, GPU memory %, 1-minute load, and `load_pct`, the mean of CPU %, memory %, GPU utilization % and GPU memory % (CPU and memory on hosts without GPUs); `hours` counts the hours with data | 1 h |
| `usage.json` | GPU hours and GPU-memory hours per user and container, per day, for 400 days | 1 min |
| `history/<range>.json` | the series the page draws, mean and max | per bucket |
| `series/<range>.json` | every stored series, mean, max and min | per bucket |
| `spark.json` | the last 24 hours of CPU, memory and GPU means | 10 min |
| `healthz` | 200 while sampling, 503 if stalled, and the number of requests served | |

The hub also serves `overview.json`, with every host's status (live, stale, offline or planned),
its latest `now.json` and its `daily.json`, in one file for the page's table.

Days in `daily.json` and `usage.json` are calendar days in Chicago time (`MONITOR_TZ`). History
ranges and their bucket widths:

| Range | Bucket | Points |
|---|---|---|
| `1h` | 10 s | 360 |
| `24h` | 2 min | 720 |
| `7d` | 10 min | 1008 |
| `30d` | 1 h | 720 |
| `1y` | 12 h | 730 |

The history database has a fixed size: older buckets are dropped as new ones close. It takes
about 30 MB for a 4-GPU host, in the `evl-monitor_data` Docker volume.

The hub's data is readable by anyone who can reach arcade on port 6161; only the page is behind
the `/internal/` password. The files never contain process command lines, environment variables
or IP addresses, and each payload is checked against a closed schema before it is served.

## Reach a server

The servers are reachable only inside UIC. From elsewhere, go through the jump host:

```sh
ssh -J fabiom@compaas-dlv.evl.uic.edu:2222 <user>@<id>.evl.uic.edu
```

## Install the agent on a server

You need Docker with compose v2. On GPU servers you also need the NVIDIA container toolkit
(`nvidia-ctk runtime configure --runtime=docker`, then restart Docker).

```sh
sudo git clone --depth 1 --filter=blob:none --sparse --branch deployment \
  https://github.com/uic-evl/EVL-Website.git /opt/evl-monitor
sudo git -C /opt/evl-monitor sparse-checkout set _monitor/agent _monitor/hub _data
sudo /opt/evl-monitor/_monitor/agent/install.sh <id>
```

`<id>` is the host's id in `_data/monitor.yml`, for example `arcade`. The script:

- detects GPUs (NVIDIA runtime) and SSSD accounts;
- builds the image on the server;
- starts two containers, `evl-monitor-agent` and `evl-monitor-docker-proxy`, with
  `restart: always`, and enables Docker at boot, so both come back after a reboot;
- checks every file the agent serves.

If the server runs `ufw`, let the hub on arcade reach the agent:

```sh
sudo ufw allow from 131.193.183.175 to any port 9877 proto tcp
```

On arcade itself, the hub reaches the local agent from a Docker network address instead:

```sh
sudo ufw allow from 172.16.0.0/12 to any port 9877 proto tcp
```

## Install the hub on arcade

After the agent, on arcade only:

```sh
sudo /opt/evl-monitor/_monitor/hub/install-hub.sh
```

The script finds the `*.evl.uic.edu` certificate in arcade's nginx config. It then starts
`evl-monitor-hub` on port 6161 (`restart: always`) and waits for the first poll round. The hub
reloads the certificate when it is renewed, and rereads `_data/monitor.yml` when it changes.

## Update

```sh
sudo git -C /opt/evl-monitor pull
sudo /opt/evl-monitor/_monitor/agent/install.sh <id>
sudo /opt/evl-monitor/_monitor/hub/install-hub.sh   # arcade only
```

History is kept across updates and restarts.

## Add a server

Step by step, with the firewall checks and what to do when a server shows offline:
[ADDING-A-SERVER.md](ADDING-A-SERVER.md). In short:

1. Install the agent on the new server (above) and let arcade reach its port 9877.
2. Add the host to `_data/monitor.yml` with `status: live`, in a pull request.
3. After the merge, `sudo git -C /opt/evl-monitor pull` on arcade. The hub starts polling
   the new server within 30 seconds, without a restart.

## Run it locally

Fake agents behind the real hub, with the hosts from `_data/monitor.yml`:

```sh
cd _monitor/agent && pip install -e ".[test]"
python -m evl_monitor.fakegw --port 4001                  # add --stale utk --offline sage200 to see those states
# with the site running locally (docker compose up, or bundle exec jekyll serve):
# http://localhost:8080/internal/monitor/?data=http://localhost:4001
```

Tests: `cd _monitor/agent && pytest` (the HTTPS tests use the `openssl` command).

Check the hub or an agent:

```sh
python -m evl_monitor.check https://arcade.evl.uic.edu:6161/<id>/ --id <id>
```

## Settings

`install.sh` writes `_monitor/agent/.env`; `install-hub.sh` writes `_monitor/hub/.env`. These
variables can be set before running them:

| Variable | Default | Meaning |
|---|---|---|
| `MONITOR_PORT` | `9877` | port the agent serves on |
| `MONITOR_MOUNTS` | `auto` | `auto` (local filesystems, up to 8) or `label:/path,...` |
| `MONITOR_PROCS` | `full` | `full` (users, containers, names), `count` (numbers only) or `off` |
| `HUB_PORT` | `6161` | port the hub serves on |
| `HUB_TLS_CERT`, `HUB_TLS_KEY` | from nginx | the hub's certificate and key |
| `HUB_NOW_SECONDS` | `15` | how often the hub asks each agent for `now.json` |

## Remove

```sh
sudo docker compose -f /opt/evl-monitor/_monitor/agent/compose.yaml -p evl-monitor down      # keeps history
sudo docker compose -f /opt/evl-monitor/_monitor/hub/compose.yaml -p evl-monitor-hub down    # arcade
```
