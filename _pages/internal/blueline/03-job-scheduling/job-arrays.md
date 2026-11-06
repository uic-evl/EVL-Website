---
layout: page
permalink: /internal/blueline/03-job-scheduling/job-arrays/
title: "Job Arrays"
description: "Job Arrays on the Blueline HPC cluster"
nav: false
---

Use a Slurm job array when you have many independent, similar tasks.

Save as `array.sh`:

```bash
#!/bin/bash
#SBATCH --job-name=array-demo
#SBATCH --partition=compute
#SBATCH --array=1-5
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=00:05:00
#SBATCH --output=array-%A_%a.out

set -euo pipefail
echo "Array job: $SLURM_ARRAY_JOB_ID"
echo "Task index: $SLURM_ARRAY_TASK_ID"
echo "Compute node: $(hostname)"
```

Submit:

```bash
sbatch array.sh
```

`%A` substitutes the array's primary job ID; `%a` substitutes the array task ID. Concurrent array limits and array-specific site policies remain **TBD**.
