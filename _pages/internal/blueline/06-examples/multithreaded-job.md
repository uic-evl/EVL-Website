---
layout: page
permalink: /internal/blueline/06-examples/multithreaded-job/
title: "Example: Multithreaded / OpenMP-Style Job"
description: "Example: Multithreaded / OpenMP-Style Job on the Blueline HPC cluster"
nav: false
---

Save as `threads.sh`:

```bash
#!/bin/bash
#SBATCH --job-name=threads
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --time=00:10:00
#SBATCH --output=threads-%j.out

set -euo pipefail
export OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK"
printf 'Allocated logical CPUs for task: %s\n' "$OMP_NUM_THREADS"
printf 'Host: %s\n' "$(hostname)"
# Replace the next line with your own compiled OpenMP program:
# ./my_openmp_program
```

Submit with `sbatch threads.sh`. This template demonstrates the resource request and environment variable, but does not run a real OpenMP calculation until you supply an executable.

Blueline exposes 48 logical CPUs per node (24 physical cores plus hyperthreading). Benchmark to choose the best CPU count for your application.
