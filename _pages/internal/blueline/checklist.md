---
layout: page
permalink: /internal/blueline/checklist/
title: "Internal Verification Checklist"
description: "Internal validation checklist for Blueline documentation"
nav: false
---

The user-facing documentation is complete as a **testing-phase guide**. The following items remain deliberately unverified and must not be presented as confirmed capabilities.

## Scheduling and execution

- Verify `#SBATCH --mem=...` behavior, memory enforcement, and default memory allocation.
- Test `srun --pty bash`, `salloc`, and job arrays with real user permissions.
- Validate MPICH 5.0.2 compile and multi-node launch (`srun` versus `mpiexec`) and document a tested MPI recipe.
- Confirm any future job limits, concurrent-job limits, and fairness policy. Currently no explicit administrative walltime limit is reported.
- Recheck partition names if additional partitions are deployed.

## Software and access

- Decide supported Python environment workflow and exact Python/toolchain modules.
- Publish verified SSH host-key fingerprint and any MFA-specific instructions when available.
- Optional: publish a direct support Slack channel link, if appropriate for internal readers.

## Storage and infrastructure

- NFS `/home` is **not backed up**; do not change this statement without verifying a new backup service.
- Document future quota values, retention rules, and any scratch/project storage only after deployment.
- Update 1 Gb network statement only after higher-speed infrastructure is commissioned.

## Editorial

- Recheck all example scripts against a non-admin UIC test account after cluster changes.
- Keep testing-phase warnings until the project team confirms production readiness.
