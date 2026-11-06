---
layout: page
permalink: /internal/blueline/04-software/environment-modules/
title: "Software with Lmod"
description: "Software with Lmod on the Blueline HPC cluster"
nav: false
---

Blueline uses **Lmod** to manage software environment modules.

Useful commands:

```bash
module avail
module list
module spider
module load mpich/5.0.2
module list
module unload mpich/5.0.2
```

The confirmed module tree includes `/soft/modulefiles`, and `mpich/5.0.2` is available. The module was shown with `(L)` in the supplied output, meaning it was loaded in that shell session; this alone does not prove that MPICH loads automatically for every user.

Only MPICH is confirmed as a published application module at present. Other modules may be installed upon request. Check `module avail` for the currently available list.
