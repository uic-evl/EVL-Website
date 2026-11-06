---
layout: page
permalink: /internal/blueline/03-job-scheduling/best-practices/
title: "Shared-Cluster Best Practices"
description: "Shared-Cluster Best Practices on the Blueline HPC cluster"
nav: false
---

- Run CPU-intensive work on compute nodes via Slurm rather than on the login/management host.
- Request only the CPUs, nodes, and time you need; benchmark scaling before using many threads.
- Remember each node has **24 physical cores / 48 logical CPUs**; hyperthreads are not equivalent to physical cores.
- Write outputs to your home directory unless an administrator documents a different approved path.
- Avoid excessive simultaneous small-file operations on shared NFS storage.
- Check job output and cancel jobs that are no longer needed.
- Keep passwords, access tokens, and other secrets out of scripts and Slack messages.
- Because Blueline is in testing, report unexpected errors in Spear cluster Slack.
- Back up your research data independently: NFS `/home` currently has **no backups**.
- Expect network-intensive distributed jobs to be sensitive to the current **1 Gb** network.

**Policy status:** Lightweight-only login usage is a recommended practice, not yet a formally approved enforcement policy. Administrative job limits, per-user concurrency restrictions, and fair-share rules are **TBD**.
