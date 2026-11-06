---
layout: page
permalink: /internal/blueline/06-examples/basic-cpu-job/
title: "Example: Single-CPU Job"
description: "Example: Single-CPU Job on the Blueline HPC cluster"
nav: false
---

Save as `single.sh`:

```bash
#!/bin/bash
#SBATCH --job-name=single
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=00:05:00
#SBATCH --output=single-%j.out

set -euo pipefail
hostname
date
```

Submit using `sbatch single.sh`; check with `squeue -u "$USER"`. This example requires no extra software.
