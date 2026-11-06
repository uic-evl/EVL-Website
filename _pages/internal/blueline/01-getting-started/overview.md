---
layout: page
permalink: /internal/blueline/01-getting-started/overview/
title: "Getting Started"
description: "Getting Started on the Blueline HPC cluster"
nav: false
---

Blueline is an EVL CPU-only HPC project at UIC with 16 Slurm compute nodes. The cluster is **in testing**; problems and service changes are expected. **NFS home directories are not backed up**. Users connect to the login host and schedule computational work on compute nodes.

## Workflow

1. Connect from UIC Wi-Fi, UIC VPN, or another UIC-connected host.
2. SSH to `blueline.evl.uic.edu` using your UIC NetID.
3. Keep files under your NFS-backed home directory (`/home/<netid>`).
4. Submit a batch job with `sbatch job.sh`.
5. Check progress with `squeue -u "$USER"` and inspect generated output files.

Avoid running computationally intensive applications directly on the login node; use Slurm.

Next: [Connect to the cluster]({{ "/internal/blueline/01-getting-started/connecting-to-cluster/" | relative_url }}).
