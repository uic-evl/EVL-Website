---
layout: page
permalink: /internal/blueline/03-job-scheduling/interactive-jobs/
title: "Interactive Jobs"
description: "Interactive Jobs on the Blueline HPC cluster"
nav: false
---

For interactive computation, obtain compute resources using Slurm instead of launching heavy workloads on the login host.

Example:

```bash
srun --partition=compute --nodes=1 --ntasks=1 --cpus-per-task=1 --time=00:30:00 --pty bash
```

Inside the allocated shell:

```bash
hostname
exit
```

If interactive allocation fails, capture the error and ask for guidance in Spear cluster Slack. Interactive job behavior has not yet been independently validated on Blueline.
