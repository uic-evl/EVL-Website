---
layout: page
title: SHF
description: "Scalable and Extensible I/O Runtime and Tools for Next Generation Adaptive Data Layouts"
permalink: /projects/shf-kumar/
date: 2023-10-01
img: images/kumar_shf_2023.png-srcw.jpg
importance: 1
category: research
status: active
tags: [shf]
---

<div class="row justify-content-sm-center">
  <div class="col-sm-8 mt-3 mt-md-0">
    {% include figure.liquid path="/images/kumar_shf_2023.png-srcw.jpg" title="Scalable and Extensible I/O Runtime and Tools for Next Generation Adaptive Data Layouts" class="img-fluid rounded z-depth-1" %}
  </div>
</div>

## Grant

- **Collaborative Research: SHF: Small: Scalable and Extensible I/O Runtime and Tools for Next Generation Adaptive Data Layouts**
- PI: Sidharth Kumar
- Collaborator: Steve Petruzza, Utah State University
- Sponsor: National Science Foundation, Software and Hardware Foundations (SHF) program, Division of Computing and Communication Foundations
- NSF Award <a href="https://www.nsf.gov/awardsearch/show-award/?AWD_ID=2401274" target="_blank" rel="noopener">#2401274</a>, transferred to UIC from the University of Alabama at Birmingham (award #2221811, July 2022)
- Start Date: October 1, 2023
- End Date: June 30, 2027
- Award Amount: $300,165

## Overview

Large-scale scientific simulations on supercomputers have fueled a wave of innovation and discovery across energy, cosmology, earth science, medicine, and national security, and with exascale, applications promise data of ever-increasing size, resolution, and fidelity. Current trends in HPC systems are creating an unprecedented gap between compute and I/O performance, making data movement the slowest component of the simulation-analysis pipeline. Compression and hierarchical data layouts have been proposed to ease this bottleneck, but current solutions lack scalability and portability and do not address the data-management needs of both parallel I/O and analysis workflows, in situ and post hoc, as a whole.

This project develops a scalable and extensible I/O runtime and tools for next-generation adaptive data layouts that inherently combine compression and progressive data access. The layouts are hierarchical, compressed, and tunable: a hierarchical layout allows progressive access to massive data for post-hoc and in situ analysis at any scale, data compression and reduction alleviate data-movement bottlenecks during parallel I/O, and a tunable layout combined with new performance analysis and visualization tools allows data-driven optimization of I/O performance at runtime across workflows and HPC platforms. The work delivers a scalable, tunable parallel I/O runtime with progressive read and write operations; interfaces that support the adaptive layouts in in situ workflows; a WebGPU-powered visualization system that exploits the progressive layout for interactive exploration of large datasets in web browsers; and performance-mining and visualization tools for portable I/O performance prediction and auto-tuning. The solution is evaluated on leadership supercomputers and mid-scale clusters and integrated with large-scale simulation, analysis, and I/O frameworks.

## Links

- Project page on Sidharth Kumar's site: <a href="https://sidharthkumar.io/#projects" target="_blank" rel="noopener">https://sidharthkumar.io/#projects</a>
- NSF award abstract: <a href="https://www.nsf.gov/awardsearch/show-award/?AWD_ID=2401274" target="_blank" rel="noopener">https://www.nsf.gov/awardsearch/show-award/?AWD_ID=2401274</a>
