---
layout: page
permalink: /internal/blueline/05-data-management/transferring-files/
title: "Transferring Files"
description: "Transferring Files on the Blueline HPC cluster"
nav: false
---

Run transfer commands from **your local computer**, unless otherwise stated. You must be connected to UIC Wi-Fi, UIC VPN, or an authorized UIC-connected host.

Replace `<netid>` with your UIC NetID and local file paths with your actual paths.

## SCP: upload a file

```bash
scp ./input.dat <netid>@blueline.evl.uic.edu:/home/<netid>/
```

## SCP: download a result

```bash
scp <netid>@blueline.evl.uic.edu:/home/<netid>/result.txt ./
```

## rsync: synchronize a directory

```bash
rsync -avP ./project/ <netid>@blueline.evl.uic.edu:/home/<netid>/project/
```

Be careful with `rsync --delete`; it can remove destination files.

## SFTP: interactive file transfer

```bash
sftp <netid>@blueline.evl.uic.edu
```

Inside SFTP, use commands such as `put file.txt`, `get result.txt`, `ls`, and `bye`.

As with SSH, verify the host-key fingerprint through an official channel before accepting a first-time connection.
