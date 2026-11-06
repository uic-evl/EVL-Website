---
layout: page
permalink: /internal/blueline/03-job-scheduling/monitoring-jobs/
title: "Monitoring and Canceling Jobs"
description: "Monitoring and Canceling Jobs on the Blueline HPC cluster"
nav: false
---

```bash
squeue -u "$USER"
sinfo -N -p compute
scontrol show job <job_id>
scancel <job_id>
```

Replace `<job_id>` before running the commands.

Common Slurm states include `PD` (pending), `R` (running), `CG` (completing), `CD` (completed), and `F` (failed). `squeue` generally does not list completed jobs.

If accounting commands are available to your user, you may also try:

```bash
sacct -j <job_id> --format=JobID,JobName,State,Elapsed
```

Historical job-accounting availability has not been verified for regular users on Blueline. Always check your job's output and error files.
