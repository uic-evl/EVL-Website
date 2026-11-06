---
layout: page
permalink: /internal/blueline/06-examples/interactive-job/
title: "Example: Interactive Compute Session"
description: "Example: Interactive Compute Session on the Blueline HPC cluster"
nav: false
---

```bash
srun --partition=compute --nodes=1 --ntasks=1 --cpus-per-task=1 --time=00:30:00 --pty bash
```

Use `hostname` to identify the allocated compute host, run your short interactive test, then `exit` to release the shell. Interactive launch behavior is pending verification.
