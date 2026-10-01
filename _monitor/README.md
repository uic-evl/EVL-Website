# EVL server monitor

The page at https://www.evl.uic.edu/monitor/ shows live load, history, GPU use, containers,
models and web services for the EVL servers.

```
browser --HTTPS--> www.evl.uic.edu (nginx on the web server)
                     /monitor/                 the page (_pages/monitor.html)
                     /monitor/data/<id>/...  --HTTP, campus only-->  <id>.evl.uic.edu:9877
                                                                       evl-monitor agent (Docker)
```

Each server runs the agent, a small container that samples the host every 5 seconds, keeps
compact history in SQLite and serves JSON on port 9877. The servers are reachable only inside
UIC, so the web server's nginx relays `/monitor/data/<id>/<file>` to each agent. The page reads
those URLs from its own origin.

| Folder | What it holds |
|---|---|
| `agent/` | the agent (Python), its Dockerfile, compose files and `install.sh` |
| `web/` | the web server's relay config, generated from `_data/monitor.yml` |
| `tools/` | `render_nginx.py` (writes `web/`), `hosts.py` (checks the host list), `check_dashes.py` |

`_data/monitor.yml` is the list of hosts. The page and the relay config both come from it.

## Files each agent serves

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
| `spark.json` | the last 24 hours of CPU, memory and GPU means, for the overview cards | 10 min |
| `healthz` | 200 while sampling, 503 if stalled | |

Days in `daily.json` and `usage.json` are calendar days in Chicago time (`MONITOR_TZ`).

History ranges and their bucket widths:

| Range | Bucket | Points |
|---|---|---|
| `1h` | 10 s | 360 |
| `24h` | 2 min | 720 |
| `7d` | 10 min | 1008 |
| `30d` | 1 h | 720 |
| `1y` | 12 h | 730 |

The history database has a fixed size: older buckets are dropped as new ones close. It takes
about 30 MB for a 4-GPU host, in the `evl-monitor_data` Docker volume.

Everything in these files is public. They never contain process command lines, environment
variables, IP addresses or hostnames beyond the server's own name. Each payload is checked
against a closed schema before it is served.

## Install on a server

You need Docker with compose v2. On GPU servers you also need the NVIDIA container toolkit
(`nvidia-ctk runtime configure --runtime=docker`, then restart Docker).

```sh
sudo git clone --depth 1 --filter=blob:none --sparse --branch deployment \
  https://github.com/uic-evl/EVL-Website.git /opt/evl-monitor
sudo git -C /opt/evl-monitor sparse-checkout set _monitor/agent
sudo /opt/evl-monitor/_monitor/agent/install.sh <id>
```

`<id>` is the host's id in `_data/monitor.yml`, for example `arcade`. The script:

- detects GPUs (NVIDIA runtime) and SSSD accounts;
- builds the image on the server;
- starts two containers, `evl-monitor-agent` and `evl-monitor-docker-proxy`, with
  `restart: always`, and enables the Docker service at boot, so both come back after a reboot;
- checks every file the agent serves.

If the host runs `ufw`, allow the web server:

```sh
sudo ufw allow from 131.193.78.85 to any port 9877 proto tcp
```

## Update a server

```sh
sudo git -C /opt/evl-monitor pull
sudo /opt/evl-monitor/_monitor/agent/install.sh <id>
```

History is kept across updates and restarts.

## Add a server

1. Add the host to `_data/monitor.yml` with `status: live` (or `planned` until it is racked).
2. Run `python _monitor/tools/render_nginx.py`, which rewrites `_monitor/web/`.
3. Install the agent on the server (above).
4. Update the relay on the web server (below).
5. Open a pull request with the three changed files.

## The relay on the web server

Copy the two generated files and include the snippet once in the `www.evl.uic.edu` server block:

```sh
sudo cp _monitor/web/evl-monitor-http.conf /etc/nginx/conf.d/
sudo cp _monitor/web/evl-monitor.conf /etc/nginx/snippets/
# once: add this line inside the "listen 443" server block for www.evl.uic.edu
#   include snippets/evl-monitor.conf;
sudo nginx -t && sudo systemctl reload nginx
curl -s https://www.evl.uic.edu/monitor/data/<id>/now.json | head -c 200
```

The snippet names `resolver 127.0.0.53`, the systemd-resolved stub. If the web server uses
another resolver, run `render_nginx.py --resolver <ip>`.

## Run it locally

Fake data, on any machine with Docker:

```sh
docker compose -f _monitor/agent/compose.dev.yaml up --build
# http://127.0.0.1:9877/now.json
```

Several fake hosts behind the production URL layout, with one stale and one offline, for
working on the page:

```sh
cd _monitor/agent && pip install -e .
python -m evl_monitor.fakegw --port 4001 --hosts arcade:4,sage200:2,utk:1 --stale utk --offline sage200
# with the site running locally (bundle exec jekyll serve):
# http://localhost:4000/monitor/?data=http://localhost:4001/monitor/data
```

Tests: `cd _monitor/agent && pip install -e ".[test]" && pytest`.

Check a deployed agent, directly or through the relay:

```sh
python -m evl_monitor.check https://www.evl.uic.edu/monitor/data/<id>/ --id <id>
```

## Settings

`install.sh` writes `_monitor/agent/.env`. These variables can be set before running it:

| Variable | Default | Meaning |
|---|---|---|
| `MONITOR_PORT` | `9877` | port the agent serves on |
| `MONITOR_BIND_IP` | `0.0.0.0` | address the agent listens on |
| `MONITOR_MOUNTS` | `auto` | `auto` (local filesystems, up to 8) or `label:/path,...` |
| `MONITOR_PROCS` | `full` | `full` (users, containers, names), `count` (numbers only) or `off` |

## Remove

```sh
cd /opt/evl-monitor/_monitor/agent
sudo docker compose -p evl-monitor down       # keeps history
sudo docker compose -p evl-monitor down -v    # deletes history too
```
