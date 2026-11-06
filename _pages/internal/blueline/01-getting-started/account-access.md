---
layout: page
permalink: /internal/blueline/01-getting-started/account-access/
title: "Accounts and Access"
description: "Accounts and Access on the Blueline HPC cluster"
nav: false
---

## Who can request access?

Blueline is an **EVL project**. For access, contact **Prof. Michael E. Papka** or **Prof. Zhiling Lan**. The project team handles account provisioning; users do not need to create Slurm accounting records or perform provisioning themselves. Access is not automatically granted to all UIC NetID holders.

## Credentials

Log in using your **UIC NetID** and **UIC password**. Never share your password or place it inside job scripts.

## Network requirement

Blueline is reachable only through the UIC network. Use UIC Wi-Fi when onsite, UIC VPN when offsite, or a UIC-connected host if authorized.

For VPN instructions, see the [UIC VPN service page](https://it.uic.edu/services/faculty-staff/uic-network/uic-vpn/).

## Linux login versus Slurm account

Your UIC NetID identifies you when connecting to Linux. A separate Slurm *project account* does **not** need to be provided when submitting a job on the current Blueline setup; `sbatch job.sh` works without `--account`.

A Slurm *job allocation* is different: the scheduler still assigns CPUs and memory to each running job.

## Unconfirmed details

- Password change or multifactor prompts: **TBD**.
- Initial access troubleshooting contact: see [support]({{ "/internal/blueline/08-support/getting-help/" | relative_url }}).
