---
layout: page
permalink: /internal/blueline/01-getting-started/first-job/
title: "Your First Slurm Job"
description: "Your First Slurm Job on the Blueline HPC cluster"
nav: false
---

This tutorial uses standard shell commands and requires no additional application modules.

## 1. Connect and create a working directory

```bash
ssh <netid>@blueline.evl.uic.edu
mkdir -p ~/blueline-first-job
cd ~/blueline-first-job
```

Replace `<netid>` with your NetID before running the SSH command.

## 2. Create a job script

Save this as `job.sh`:

```bash
#!/bin/bash
#SBATCH --job-name=first-job
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=00:05:00
#SBATCH --output=first-job-%j.out

set -euo pipefail
printf 'Job ID: %s\n' "$SLURM_JOB_ID"
printf 'Host: %s\n' "$(hostname)"
printf 'Date: %s\n' "$(date)"
```

The `--time` line sets a maximum duration for **this job**, even though an administrative time limit has not been configured.

## 3. Submit it

```bash
sbatch job.sh
```

Slurm prints a job ID if submission is accepted. No `--account` flag is needed for Blueline's current configuration.

## 4. Monitor and read output

```bash
squeue -u "$USER"
ls -l first-job-*.out
cat first-job-*.out
```

The file appears after the job starts; you might need to check again after it finishes. `squeue` only shows queued/running jobs, so a completed job may disappear.

## 5. Cancel if necessary

```bash
scancel <job_id>
```

Replace `<job_id>` with the numeric ID Slurm returned.

Next: [Submitting jobs]({{ "/internal/blueline/03-job-scheduling/submitting-jobs/" | relative_url }}).
