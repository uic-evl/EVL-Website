---
layout: page
permalink: /internal/blueline/03-job-scheduling/submitting-jobs/
title: "Submitting Batch Jobs"
description: "Submitting Batch Jobs on the Blueline HPC cluster"
nav: false
---

Create a shell script with `#SBATCH` directives, then run `sbatch job.sh`.

```bash
#!/bin/bash
#SBATCH --job-name=example
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=00:10:00
#SBATCH --output=%x-%j.out

set -euo pipefail
hostname
date
```

Submit:

```bash
sbatch job.sh
```

## Important options

| Directive | Meaning |
|---|---|
| `--job-name` | Human-readable job name |
| `--partition=compute` | Select current partition (optional because it is the default) |
| `--nodes=1` | Number of compute nodes |
| `--ntasks=1` | Number of parallel tasks |
| `--cpus-per-task=1` | Logical CPUs allocated to each task |
| `--time=HH:MM:SS` | Requested time limit for the job |
| `--output` | Job stdout path; `%j` is job ID |

Slurm reports 48 logical CPUs per compute node, across 24 physical cores. CPU hyperthreading may affect performance; start with modest requests and benchmark.

Memory requests such as `--mem` are standard Slurm options, but their behavior on Blueline has **not yet been verified**. Inspect `scontrol show partition compute` and test with a small job before adding site-specific guidance.

See [job examples]({{ "/internal/blueline/06-examples/" | relative_url }}).
