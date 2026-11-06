---
layout: page
permalink: /internal/blueline/05-data-management/storage-guidelines/
title: "Storage Guidelines"
description: "Storage Guidelines on the Blueline HPC cluster"
nav: false
---

The supported user storage path is `/home/<netid>` on the shared NFS filesystem. No separate scratch or project directory is currently documented.

## Recommendations

- Organize projects into separate directories under your home directory.
- Check space periodically with `du -sh ~/project` and `df -h "$HOME"`.
- Avoid hammering the NFS server with very many tiny file operations when alternatives exist.
- **No backups are provided for the NFS home directories.** Keep independent copies of important data outside Blueline, and do not treat `/home` as the sole copy of research data.
- Remove obsolete large temporary data when it is no longer needed.

No home-directory quota is configured at present, but quotas are planned. Specific future quota values and cleanup/retention schedules are **TBD**. The current backup policy is **no NFS home backups**.
