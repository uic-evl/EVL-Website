---
layout: page
permalink: /internal/blueline/
title: "Blueline"
description: "EVL HPC cluster"
nav: false
---

Blueline is a CPU-only high-performance computing (HPC) cluster operated as an Electronic Visualization Laboratory (EVL) project at the University of Illinois Chicago (UIC). This guide is intended for new and experienced users.

> **Testing-phase notice:** Blueline is newly deployed and still being tested. Errors, interruptions, and changes are expected. Report problems in **Spear cluster Slack**. **The NFS home storage is not backed up**: keep independent copies of important files outside Blueline. The cluster currently uses a **1 Gb network**; a higher-speed network upgrade is planned but has no confirmed deployment date.

## At a glance

| Item | Current configuration |
|---|---|
| Login host | `blueline.evl.uic.edu` |
| Access | From the UIC network (including UIC Wi-Fi or UIC VPN) |
| Authentication | UIC NetID and UIC password |
| Operating system | Rocky Linux 10.2 (Red Quartz) |
| Job scheduler | Slurm |
| Compute partition | `compute` (default) |
| Compute nodes | 16: `blueline-compute-[01-16]` |
| CPUs per node, reported by Slurm | 48 logical CPUs (24 physical cores, 2 threads/core) |
| Memory per node | 128 GB installed; Slurm `RealMemory=125000` MB |
| User storage | NFS-backed `/home/<netid>` |
| Software modules | Lmod; `mpich/5.0.2` available |
| Access requests | Ask Prof. Michael E. Papka or Prof. Zhiling Lan |
| Help / bug reports | Spear cluster Slack |
| Network | Currently 1 Gb; higher-speed upgrade planned |
| Backups | None for NFS home storage |

**Current versus planned:** Blueline currently has only the `compute` partition and `/home` user storage. Additional partitions, software, storage paths, and storage quotas may be introduced later. Their details are not yet finalized.

## Access eligibility

Blueline is an EVL project. To request access, ask **Prof. Michael E. Papka** or **Prof. Zhiling Lan**. Once access is arranged, users log in using their UIC NetID and UIC password; user-account provisioning is handled by the project team.

## Start here

1. [Connect to Blueline]({{ "/internal/blueline/01-getting-started/connecting-to-cluster/" | relative_url }})
2. [Submit your first Slurm job]({{ "/internal/blueline/01-getting-started/first-job/" | relative_url }})
3. [Understand cluster hardware]({{ "/internal/blueline/02-cluster-resources/hardware-overview/" | relative_url }})
4. [Learn Slurm]({{ "/internal/blueline/03-job-scheduling/submitting-jobs/" | relative_url }})
5. [Transfer files]({{ "/internal/blueline/05-data-management/transferring-files/" | relative_url }})
6. [Get help]({{ "/internal/blueline/08-support/getting-help/" | relative_url }})


## Browse documentation

- [Getting Started]({{ "/internal/blueline/01-getting-started/" | relative_url }}) — Connect to Blueline and submit your first job
- [Cluster Resources]({{ "/internal/blueline/02-cluster-resources/" | relative_url }}) — Hardware, partitions and storage on Blueline
- [Job Scheduling]({{ "/internal/blueline/03-job-scheduling/" | relative_url }}) — Submit and manage Slurm jobs on Blueline
- [Software]({{ "/internal/blueline/04-software/" | relative_url }}) — Environment modules and software on Blueline
- [Data Management]({{ "/internal/blueline/05-data-management/" | relative_url }}) — Transfer and manage files safely on Blueline
- [Job Examples]({{ "/internal/blueline/06-examples/" | relative_url }}) — Slurm scripts and CPU computing examples
- [Troubleshooting]({{ "/internal/blueline/07-troubleshooting/" | relative_url }}) — Fix common Blueline access and job problems
- [Support]({{ "/internal/blueline/08-support/" | relative_url }}) — Get assistance with the Blueline HPC cluster

## Job submission convention

Users can submit jobs without specifying a Slurm project account:

```bash
sbatch job.sh
```

`compute` is the default partition. For clarity, examples may explicitly specify `--partition=compute`.

## Documentation status

Some policies and capabilities are **to be confirmed (TBD)**, including validated memory-request behavior, Python environment setup, and future job scheduling limits. The formal support channel identifier is not documented; use the existing Spear cluster Slack. Do not interpret an omitted administrative limit as permission to consume unlimited shared resources.
