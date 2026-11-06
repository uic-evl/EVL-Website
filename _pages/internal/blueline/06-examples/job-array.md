---
layout: page
permalink: /internal/blueline/06-examples/job-array/
title: "Example: Job Array"
description: "Example: Job Array on the Blueline HPC cluster"
nav: false
---

Save as `array.sh`:

```bash
#!/bin/bash
#SBATCH --job-name=array
#SBATCH --partition=compute
#SBATCH --array=1-5
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=00:05:00
#SBATCH --output=array-%A_%a.out

set -euo pipefail
echo "Task $SLURM_ARRAY_TASK_ID running on $(hostname)"
```

Submit with `sbatch array.sh`; see [Job Arrays]({{ "/internal/blueline/03-job-scheduling/job-arrays/" | relative_url }}).
