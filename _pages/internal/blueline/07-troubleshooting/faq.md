---
layout: page
permalink: /internal/blueline/07-troubleshooting/faq/
title: "Frequently Asked Questions"
description: "Frequently Asked Questions on the Blueline HPC cluster"
nav: false
---

**Do I need to be on UIC's network?**  Yes. Connect via UIC Wi-Fi, UIC VPN, or another authorized UIC-connected system.

**Which username do I use?**  Your UIC NetID.

**Do I need `--account` for `sbatch`?**  No, not in the current Blueline setup.

**Which partition should I select?**  `compute`. It is the default, so specifying it is optional.

**Can I run a CPU-heavy command on the login node?**  Use a Slurm job instead. Formal login-node enforcement rules are still TBD.

**How many CPUs can I request?**  Each compute node advertises 48 *logical* CPUs (24 physical cores). Site-specific per-job and per-user limits are TBD.

**Can I use GPUs?**  No. Blueline is CPU-only.

**Where do my files go?**  Under `/home/<netid>` on NFS.

**Is scratch storage available?**  No separate scratch storage is currently documented.

**What application modules are available?**  `mpich/5.0.2` is confirmed; use `module avail` for live information.

**Is my home directory backed up?**  No. NFS home directories are **not backed up**; maintain your own copies elsewhere.

**Is Blueline fully production-ready?**  No. It is currently in testing, and issues are expected.

**How fast is the cluster network?**  Currently 1 Gb. A higher-speed network upgrade is planned; no timeline has been confirmed.

**How do I request access?**  Contact Prof. Michael E. Papka or Prof. Zhiling Lan.

**Where do I get help?**  Spear cluster Slack.
