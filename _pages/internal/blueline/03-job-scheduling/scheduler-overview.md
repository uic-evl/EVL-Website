---
layout: page
permalink: /internal/blueline/03-job-scheduling/scheduler-overview/
title: "Slurm Overview"
description: "Slurm Overview on the Blueline HPC cluster"
nav: false
---

Slurm is the scheduler for Blueline's CPU-only compute nodes. Users request resources, submit jobs, and check their status from the login node.

| Command | Purpose |
|---|---|
| `sbatch job.sh` | Submit a batch script |
| `squeue -u "$USER"` | View queued and running jobs |
| `sinfo` | View partition/node status |
| `scontrol show job <id>` | Inspect a job |
| `scancel <id>` | Cancel a job |
| `srun` | Launch job tasks / request interactive resources |
| `salloc` | Obtain an interactive allocation |

Current setup: default partition `compute`, and no need to explicitly pass a project account. Administrative time limits are not configured at present. Other scheduling controls are **TBD**.
