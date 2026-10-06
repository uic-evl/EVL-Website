---
layout: page
permalink: /internal/ai-services/
title: AI Servers and Services
description: AI equipment, models and services available to EVLers
nav: false
toc:
  sidebar: left
---

*Last edited October 6, 2026. Source: [AI Servers and Services](https://docs.google.com/document/d/1ztuJ7YWnXJW5oil8GNIUodhIi1QCnejQ6kFpBo95h3s/edit?usp=sharing) (Google Doc).*

## Equipment

### Workstations

Interactive systems with a screen and keyboard. Most logins are connected to UIC Active Directory (AD, using your UIC NetID).

#### ARCADE

- 2x rendering servers, running Windows 11
  - AMD EPYC Genoa 9354 with **768 GB RAM**, 1 TB OS SSD, 8 TB data SSD, 100 Gbps NIC
  - **NVIDIA RTX 6000 Blackwell, 96 GB GPU RAM**
  - Login with AD (UIC NetID)
- PC connected to the stereo 3D projector, running Windows 11
  - **NVIDIA RTX 5090**

#### EVL Main Lab

- 6x high-end graphics workstations running Windows 11
  - **NVIDIA RTX 5090 / 5080**
  - As of August 2026:
    - Three workstations on AD (UIC NetID) for general use, named VR02, SAGE01 and SAGE02
    - Three dedicated desktop workstations (can be changed): VR, …

### Servers

Arcade AI 01 and 02 are still waiting to be deployed in the EVL server room. More services and capacity will be available when they come online.

The servers, organized by funding:

#### DOCC / ARCADE

- [arcade.evl.uic.edu](https://arcade.evl.uic.edu)
  - Linux
  - **4x NVIDIA H100 80 GB**
  - 2x Intel Xeon Platinum 8468
  - **1 TB RAM**
- arcade-ai-01.evl.uic.edu
  - Linux
  - PowerEdge XE7745 4U chassis
  - 2x AMD EPYC 9555 3.20 GHz
  - **4x NVIDIA H200 NVL, 141 GB HBM3e, 4-way NVLink bridge**
  - **1.1 TB RAM**
- arcade-ai-02.evl.uic.edu
  - Linux
  - PowerEdge XE7745 4U chassis
  - 2x AMD EPYC 9555 3.20 GHz
  - **4x NVIDIA H200 NVL, 141 GB HBM3e, 4-way NVLink bridge**
  - **1.1 TB RAM**

#### SAGE3

- [sage200.evl.uic.edu](https://sage200.evl.uic.edu)
  - Linux
  - **2x NVIDIA H200 NVL, 141 GB HBM3e**
  - 2x AMD EPYC 9655 96-core processor
  - **1.5 TB RAM**

#### UrbanTK

- utk.evl.uic.edu
  - AMD EPYC 9354 32-core processor
  - **368 GB RAM**
  - **NVIDIA RTX PRO 6000 Blackwell Max-Q Workstation Edition, 96 GB**

#### Storage Server

- TBD, budgeted on the DOCC grant.

## Services

Most applications and services are deployed on Linux using Docker containers, with a single NGINX installation per node. NGINX handles HTTPS certificates and proxies the various services to HTTP on localhost. The only management needed is base routing per application (allocating a route such as `/myapplication`) and port management (each application exposes a single port over HTTP). Docker Compose is used when an application needs several containers (frontend, backend, database, …).

### LLM

Two LLMs are currently deployed, subject to updates and different choices:

- **Gemma 4 31B** (`gemma4`): model from Google, a dense server-grade model optimized for heavy reasoning and coding tasks
  - Deployed on arcade.evl.uic.edu, over 2x H100
  - Container: `nvcr.io/nim/google/gemma-4-31b-it:latest`
- **Llama 4 Scout 17B** (`llama-4-scout-17b-16e`): model from Meta, leveraging a mixture-of-experts architecture to offer industry-leading performance in text and image understanding
  - Deployed on sage200.evl.uic.edu, over 2x H200
  - Container: `nvcr.io/nim/meta/llama-4-scout-17b-16e-instruct:latest`

The infrastructure of choice for now is the NVIDIA NIM deployment: "NVIDIA NIM provides containers to self-host GPU-accelerated inferencing microservices for pretrained and customized AI models across clouds, data centers, and RTX AI PCs and workstations. NIM microservices expose industry-standard APIs for simple integration into AI applications, development frameworks, and workflows and optimize response latency and throughput for each combination of foundation model and GPU."

NVIDIA NIM works as a container repository of models, packaged by NVIDIA, known to work on NVIDIA hardware and optimized for it. Usually it comes bundled with a web server (NVIDIA Triton, vLLM, …) to access the model remotely and to optimize either throughput or latency, depending on the hardware available. The containers are then exposed to the network with NGINX on a specific route. The models can be managed by LiteLLM if we need API keys and accounting (logs, budget, …).

### Other Models

For other uses, we also run smaller models specific to some applications on a shared GPU (H100):

- **Automatic Speech Recognition (ASR)**
  - `nemotron-asr-streaming`: Nemotron 3.5 ASR is a multilingual, streaming ASR model engineered to deliver high-quality multilingual transcription across both low-latency streaming and high-throughput batch workloads.
- **Text processing**
  - `olmocr-server`: olmOCR 2 is an open-source tool designed for high-throughput conversion of PDFs and other documents into plain text while preserving natural reading order. It supports tables, equations, handwriting, and more.
    - A vLLM instance serving olmOCR for PDF documents. Container: `vllm/vllm-openai:latest`
  - `llama-nemotron-embed`: multilingual, cross-lingual embedding model for long-document QA retrieval, supporting 26 languages. Container: `nvcr.io/nim/nvidia/llama-nemotron-embed-1b-v2:latest`
  - `llama-nemotron-rerank`: the Llama Nemotron Reranking 1B model is optimized for providing a logit score that represents how relevant a document is to a given query. The model was fine-tuned for multilingual, cross-lingual text question-answering retrieval, with support for long documents (up to 8192 tokens). Container: `nvcr.io/nim/nvidia/llama-nemotron-rerank-1b-v2:latest`

### AI Gateway

LLM access is controlled through an instance of **LiteLLM AI Gateway**, an open-source, self-hosted proxy server that lets you connect applications to over 100 large language model providers using a single, unified, OpenAI-compatible API.

- Deployed on sage200.evl.uic.edu
- Administrators can create teams, budgets and **API keys** for any of the models under management.
- Exposes an OpenAI-compatible API that can be used by most software packages, such as the native **OpenAI Python** module or LiteLLM's own Python library. (LiteLLM is an open-source Python library that provides a unified, OpenAI-compatible interface to call over 100 LLM APIs. Instead of juggling multiple SDKs, authentication formats and code variations for different AI vendors, LiteLLM acts as a single abstraction bridge.)
- **Request an API key for users, a project, or a class.**

Example:

```python
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ.get("LITELLM_API_KEY"),
    base_url="https://sage200.evl.uic.edu",
)

completion = client.chat.completions.create(
    model="gemma4",
    messages=[
        {"role": "developer", "content": "Talk like a PhD."},
        {"role": "user", "content": "How do I check if a Python object is an instance of a class?"},
    ],
)

print(completion.choices[0].message.content)
```

### AI Chat

We deployed an OpenWebUI instance for interactive LLM chat with Gemma 4 and Llama 4, linked to the LLMs running at EVL.

- Deployed at: [https://arcade.evl.uic.edu:9000](https://arcade.evl.uic.edu:9000)
- OpenWebUI: "Run AI on your own terms. Connect any model, extend with code, and protect what matters without compromise. Your models, your data, your machine, wherever you open it." [https://openwebui.com/](https://openwebui.com/)

### Web Hosting

Data science applications are hosted on the arcade.evl.uic.edu web server. We deployed a system of Docker containers and NGINX routing to host many applications. Students and faculty involved in the DOCC grant can deploy their application. See [https://arcade.evl.uic.edu/](https://arcade.evl.uic.edu/) for more information.

Applications:

- **ConGAT**: context-aware graph attention visual analysis for 3D region-of-interest discovery in multiplexed microscopy images, by Hossein Fathollahian et al.
- **BioSET**: interactive visual analysis of biomarker co-localization in large multi-volume tissue data.
- **Scout**: visual analytics for exploring urban data, by Kazi Shahrukh Omar et al.
- **Loom**: multi-region analysis of spatial transcriptomics with local neighborhoods and global trajectories, by Siyuan Zhao et al.
- **Vitral**: a framework for reproducible design studies in visual analytics, by Gustavo Moreira et al.
- **CrossFit**: web application for checking and comparing models, by Tahsen Islam Sajon et al.
- **ASR**: continuous live Automatic Speech Recognition in the browser, via a GPU-accelerated NVIDIA ASR NIM, with speaker diarization, background LLM analyzers, and Markdown export.
- **SAGE3**: open-source platform designed to help individuals and teams collaborate effectively, with AI in the loop.
- **VR Gaussian Splats**: immersive viewing of 3D Gaussian splatting scenes in virtual reality.
- **VIPS it**: large image processor for SAGE3, converting gigapixel images into zoomable tiles, built on libvips.
- **3D Video Player**: frame-exact WebCodecs video player with stereo 3D rendering, synchronizing any number of clients to a shared clock, up to tiled video-wall deployments.
