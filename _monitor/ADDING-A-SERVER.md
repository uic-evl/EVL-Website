# Adding a server to the monitor

This guide adds a Linux server to the page at https://www.evl.uic.edu/internal/monitor/. For
example, it covers arcade-ai-01 or arcade-ai-02 once they are racked, or the storage server.
It takes about 15 minutes per server.

How the pieces fit: each server runs the **agent** (a Docker container on port 9877). The
**hub** on arcade polls every agent listed in `_data/monitor.yml` and serves the data to the
page on port 6161. A new server needs the agent installed, a firewall opening for the hub, and
an entry in `_data/monitor.yml`.

## What you need

- **The server:**
  - Linux with Docker and Docker Compose v2.
  - If it has NVIDIA GPUs: the NVIDIA driver and the NVIDIA container toolkit.
  - A DNS name under `evl.uic.edu` (the hub only polls `*.evl.uic.edu`).
- **Access:**
  - An account on the server that can use `sudo`.
  - SSH through the jump host, since the servers are reachable only inside UIC:
    ```sh
    ssh -J fabiom@compaas-dlv.evl.uic.edu:2222 <user>@<name>.evl.uic.edu
    ```
  - The same kind of access to arcade, to update the hub's host list.

## 1. Check the server

On the new server:

```sh
docker compose version                       # Docker Compose v2
docker info --format '{{json .Runtimes}}'    # GPU servers: must list "nvidia"
nvidia-smi --query-gpu=name --format=csv     # GPU servers: lists the GPUs
```

If a GPU server's runtimes do not list `nvidia`, install the NVIDIA container toolkit, then run:

```sh
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker    # this restarts every container on the server
```

## 2. Install the agent

Still on the new server. `<id>` is a short lowercase name for it, such as `arcade-ai-01`; use
the same id in `_data/monitor.yml` (step 4).

```sh
sudo git clone --depth 1 --filter=blob:none --sparse --branch deployment \
  https://github.com/uic-evl/EVL-Website.git /opt/evl-monitor
sudo git -C /opt/evl-monitor sparse-checkout set _monitor/agent
sudo /opt/evl-monitor/_monitor/agent/install.sh <id>
```

The script:
- detects GPUs and directory (SSSD) accounts;
- builds the agent on the server;
- starts `evl-monitor-agent` and `evl-monitor-docker-proxy`, which come back by themselves
  after a reboot;
- checks every file the agent serves.

It ends with `ok: http://127.0.0.1:9877/` and `Done.`

## 3. Let the hub reach the agent

The hub on arcade connects to the agent on port 9877 from arcade's address, 131.193.183.175.
If the server runs `ufw` (the install script says so), allow it:

```sh
sudo ufw allow from 131.193.183.175 to any port 9877 proto tcp
```

Then check from **arcade**:

```sh
curl -s -m 3 http://<name>.evl.uic.edu:9877/healthz; echo
```

It must print something like `{"ok":true,...}`. If it prints nothing after 3 seconds, a
firewall is still in the way: check `sudo ufw status` on the new server, or ask EVL IT whether
the campus network blocks 9877 between the two machines.

## 4. Add the server to `_data/monitor.yml`

In a pull request to `uic-evl/EVL-Website`, add the server under `hosts` and list its id in
one of the `groups`. If the server is already listed as `planned`, change it to `live`.

```yaml
groups:
  - id: docc
    name: DOCC / ARCADE
    hosts: [arcade, arcade-ai-01, arcade-ai-02]

hosts:
  arcade-ai-01:
    name: ARCADE AI 01                  # shown on the page
    fqdn: arcade-ai-01.evl.uic.edu      # must end in .evl.uic.edu
    status: live                        # live: polled; planned: "Not reporting yet"
    gpu: true
    gpus: 4x NVIDIA H200 NVL (NVLink)   # shown on the page; the agent reads the real GPUs
    cpus: 2x AMD EPYC 9555
    memory: 1.1 TB
    role: what the server is for        # optional
```

- **Every host must appear in exactly one group,** and ids and names must be unique.
- **The check:** the "Monitor checks" workflow tests this on the pull request. Locally, run
  `python _monitor/tools/hosts.py`.
- **Merging redeploys the site,** and the page then shows the new row.

## 5. Tell the hub

After the pull request is merged, on **arcade**:

```sh
sudo git -C /opt/evl-monitor pull
```

The hub rereads the host list within 30 seconds and starts polling the new server, with no
restart. To check, open https://arcade.evl.uic.edu:6161/overview.json and find the new id with
`"status": "live"`. The row on https://www.evl.uic.edu/internal/monitor/ turns live within 15
seconds of that.

## When something is wrong

`overview.json` gives each server a `status` and, when it is offline, an `error`:

| What you see | What it means | What to do |
|---|---|---|
| `"error": "timeout"` | the hub's connection to port 9877 gets no answer | a firewall: repeat step 3 and its `curl` check from arcade |
| `"error": "unreachable"` | the server refuses the connection | the agent is not running: `sudo docker ps` and `sudo docker logs evl-monitor-agent` on the server, then rerun `install.sh <id>` |
| `"error": "dns"` | the name in `fqdn` does not resolve | fix `fqdn` in `_data/monitor.yml`, or wait for the DNS record |
| `"error": "http_error"` | the agent answers with an error, for example while it is starting | wait a minute; if it stays, `sudo docker logs evl-monitor-agent` on the server |
| `"error": "bad_payload"` | the agent answers with something the hub rejects | the agent is out of date: on the server, `sudo git -C /opt/evl-monitor pull`, then rerun `install.sh <id>` |
| the server is missing from `overview.json` | the hub does not have the new host list | step 5 (`git pull` on arcade); check that `fqdn` ends in `.evl.uic.edu` |
| the page row says "Not reporting yet" | the deployed site still has `status: planned` | merge the pull request from step 4 and wait for the site deploy |
| "No GPUs" on a GPU server | Docker has no NVIDIA runtime | step 1, then rerun `install.sh <id>` |

A server that stops answering is retried every minute, so a fix shows up on the page within a
minute.

## Updating a server

```sh
sudo git -C /opt/evl-monitor pull
sudo /opt/evl-monitor/_monitor/agent/install.sh <id>
```

History is kept.

## Removing a server

1. In `_data/monitor.yml`, set its `status` to `planned`, or delete it from `hosts` and from its
   group, in a pull request. After the merge, run `sudo git -C /opt/evl-monitor pull` on arcade.
2. On the server:
   ```sh
   sudo docker compose -f /opt/evl-monitor/_monitor/agent/compose.yaml -p evl-monitor down      # keeps history
   sudo docker compose -f /opt/evl-monitor/_monitor/agent/compose.yaml -p evl-monitor down -v   # deletes it
   ```

## Servers installed from the `monitor` branch

arcade, sage200 and utk were first installed from the `monitor` branch, before the pull
request was merged. To move such a server to `deployment`:

```sh
sudo git -C /opt/evl-monitor remote set-branches origin deployment
sudo git -C /opt/evl-monitor fetch --depth 1 origin deployment
sudo git -C /opt/evl-monitor checkout -B deployment FETCH_HEAD
```

Then continue with "Updating a server" above.
