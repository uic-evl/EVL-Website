---
layout: page
permalink: /internal/blueline/02-cluster-resources/partitions/
title: "Slurm Partitions"
description: "Slurm Partitions on the Blueline HPC cluster"
nav: false
---

Blueline currently has one partition: **`compute`**. It is configured as the **default** partition.

To inspect it:

```bash
sinfo -o '%P %a %l %D %C'
scontrol show partition compute
```

The default partition is usually marked with `*` in `sinfo` output.

Users can submit with:

```bash
sbatch job.sh
```

Or explicitly select the same partition in a script:

```bash
#SBATCH --partition=compute
```

Additional partitions may be added later. Queue policies, maximum resource requests, and any future partition-specific limits are **TBD**.
