---
layout: page
permalink: /internal/blueline/07-troubleshooting/common-issues/
title: "Common Issues"
description: "Common Issues on the Blueline HPC cluster"
nav: false
---

Blueline is in a **testing phase**. Job failures, unavailable nodes, and temporary access or performance issues may occur; report reproducible problems in Spear cluster Slack. The network is currently **1 Gb**, and a higher-speed upgrade is planned.

## SSH connection times out

Confirm you are connected through the UIC network (including VPN when remote), and that `blueline.evl.uic.edu` was typed correctly.

## Authentication fails

Check the NetID and use your UIC password. Do not share passwords in Slack. If you receive an unfamiliar host-key change warning, stop and verify with the cluster team.

## Job remains pending

```bash
squeue -u "$USER"
scontrol show job <job_id>
sinfo -N -p compute
```

Pending jobs may be waiting for resources; inspect `Reason=` in Slurm output. Do not assume all configured nodes are currently online.

## Job fails

Check the `.out` file and any error file from your script. Confirm the executable and input paths exist, and that required modules are loaded inside the job script.

## Module not found

```bash
module avail
module spider mpich
```

Only `mpich/5.0.2` is currently confirmed in the documented module catalog.

## Storage is full or slow

```bash
df -h "$HOME"
du -sh ~/project
```

No NFS home backups are provided. Storage quotas have not yet been configured. Report persistent NFS issues in Spear cluster Slack.

See [Getting Help]({{ "/internal/blueline/08-support/getting-help/" | relative_url }}).
