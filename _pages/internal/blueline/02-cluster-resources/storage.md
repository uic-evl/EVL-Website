---
layout: page
permalink: /internal/blueline/02-cluster-resources/storage/
title: "Storage Overview"
description: "Storage Overview on the Blueline HPC cluster"
nav: false
---

## Available user storage

Each user has an NFS-backed home directory:

```text
/home/<netid>
```

This is the only documented user storage location at present. The home filesystem is shared over NFS, so files in the shared home directory are accessible for jobs that run on compute nodes.

Check your directory:

```bash
printf '%s\n' "$HOME"
df -h "$HOME"
```

## Policies

Storage quotas are **not currently configured**, but are planned. **NFS home storage is not backed up.** Keep independent copies of any important data outside Blueline. No specific capacity entitlement or retention period has been provided.

There is no documented `/scratch` or `/projects` service yet; do not build scripts that depend on those paths.

See [storage guidelines]({{ "/internal/blueline/05-data-management/storage-guidelines/" | relative_url }}).
