---
layout: page
permalink: /internal/blueline/01-getting-started/connecting-to-cluster/
title: "Connecting to Blueline"
description: "Connecting to Blueline on the Blueline HPC cluster"
nav: false
---

## Before connecting

Be on the UIC network: UIC Wi-Fi, UIC VPN, or an authorized UIC-connected machine. A direct SSH attempt from an unrelated external network may fail. See [UIC VPN information](https://it.uic.edu/services/faculty-staff/uic-network/uic-vpn/) if you need VPN instructions. If you do not yet have Blueline access, ask Prof. Michael E. Papka or Prof. Zhiling Lan.

## SSH login

Open a terminal (macOS, Linux, or Windows PowerShell with OpenSSH) and enter:

```bash
ssh <netid>@blueline.evl.uic.edu
```

Replace `<netid>` with your UIC NetID (do not type the angle brackets). When prompted, enter your UIC password. Terminal password entry usually does not display characters.

On the first connection, verify the host-key fingerprint through an official administrator-provided channel before accepting it. The fingerprint has not yet been published in this guide.

After login:

```bash
hostname
echo "$HOME"
pwd
```

Your home directory should be `/home/<netid>`.

## Disconnect

```bash
exit
```

## If SSH fails

1. Confirm UIC network/VPN access.
2. Confirm the hostname and NetID are correct.
3. Check whether the host is reachable; firewall policies can prevent `ping` from working even when SSH is available.
4. Contact the team in Spear cluster Slack; avoid posting credentials or private keys.

See [common issues]({{ "/internal/blueline/07-troubleshooting/common-issues/" | relative_url }}).
