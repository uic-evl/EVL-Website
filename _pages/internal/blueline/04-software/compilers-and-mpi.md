---
layout: page
permalink: /internal/blueline/04-software/compilers-and-mpi/
title: "MPI and Compilers"
description: "MPI and Compilers on the Blueline HPC cluster"
nav: false
---

MPICH version **5.0.2** is available through Lmod:

```bash
module load mpich/5.0.2
module list
command -v mpicc
command -v mpiexec
```

MPI compiler wrappers and executable paths should be verified on Blueline. In particular, **MPICH's multi-node launch integration with Slurm has not yet been tested and documented**. The example in [MPI jobs]({{ "/internal/blueline/06-examples/mpi-job/" | relative_url }}) is a starting template, not a verified production recipe.

Other compiler module versions and supported toolchains are **TBD**.
