---
layout: page
permalink: /internal/blueline/06-examples/mpi-job/
title: "Example: Multi-Node MPI Job (Template — Not Yet Validated)"
description: "Example: Multi-Node MPI Job (Template — Not Yet Validated) on the Blueline HPC cluster"
nav: false
---

MPICH 5.0.2 is available via Lmod, but multi-node launcher compatibility with Slurm still needs site testing. **Do not treat this template as a verified working multi-node recipe.**

Save as `mpi.sh`:

```bash
#!/bin/bash
#SBATCH --job-name=mpi-demo
#SBATCH --partition=compute
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=2
#SBATCH --time=00:10:00
#SBATCH --output=mpi-%j.out

set -euo pipefail
module load mpich/5.0.2
# Build or stage your MPI executable before submitting this job.
# Confirm with support whether srun or mpiexec is the supported launcher.
# Example to test ONLY after launcher validation:
# srun ./my_mpi_program
printf 'Allocated nodes: %s\n' "$SLURM_JOB_NODELIST"
printf 'Tasks requested: %s\n' "$SLURM_NTASKS"
```

The job above prints the requested allocation but does not execute MPI; remove the comments and supply a verified MPI program only after the cluster team tests the supported launch method.
