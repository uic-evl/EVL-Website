---
layout: page
permalink: /internal/blueline/04-software/python-environments/
title: "Python Environments — TBD"
description: "Python Environments — TBD on the Blueline HPC cluster"
nav: false
---

The recommended Python environment-management method for Blueline has **not yet been established**. Python version, module availability, package-install policy, and use of `venv`/Conda are all **TBD**.

To inspect what is available in your login environment, you can run:

```bash
command -v python3 || true
python3 --version  # only if python3 is present
module avail
```

These checks do not confirm that the same Python environment is appropriate for compute jobs. Avoid creating site-wide installation instructions until the support team confirms the supported approach.
