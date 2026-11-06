---
layout: page
permalink: /internal/blueline/02-cluster-resources/hardware-overview/
title: "Hardware Overview"
description: "Hardware Overview on the Blueline HPC cluster"
nav: false
---

## Compute capacity

Blueline provides **16 Dell PowerEdge R630 compute nodes**, named `blueline-compute-01` through `blueline-compute-16`. A separate head node has the same hardware profile but is reserved for management and is **not** counted as a compute node.

| Hardware | Per compute node | Across 16 compute nodes |
|---|---|---|
| CPU | 2 × Intel Xeon E5-2670 v3 at 2.30 GHz | 32 processors |
| Physical cores | 24 (12 per socket) | 384 |
| Hardware threads | 48 (2 per core) | 768 |
| Installed RAM | 128 GB DDR4 ECC (8 × 16 GB, DDR4-2133 reported) | 2,048 GB total installed |
| Memory slots | 24, with 8 populated | — |

The hardware inventory reports a **maximum memory capacity of 3,072 GB per node**. This is a platform-reported maximum, **not installed or available memory**.

## What Slurm reports

The provided node configuration is:

```text
NodeName=blueline-compute-[01-16] CPUs=48 Sockets=2 CoresPerSocket=12 ThreadsPerCore=2 RealMemory=125000 State=UNKNOWN
```

`CPUs=48` means Slurm sees **48 logical CPUs** per node; because hyperthreading is enabled, these are not 48 independent physical cores. `RealMemory=125000` is the configured memory value in Slurm (MB), and may be smaller than installed memory.

`State=UNKNOWN` was present in the supplied configuration string. It does **not** establish the current live node state; check `sinfo -N` or `scontrol show node` for the latest state.

## Network

The cluster currently uses a **1 Gb network**. A higher-speed network is planned, but deployment timing and final specifications are **TBD**. Multi-node communication-intensive jobs may be particularly sensitive to available network bandwidth.

## Inspect available nodes

```bash
sinfo -N -p compute
scontrol show nodes
```

Avoid assuming all nodes are currently idle or available.
