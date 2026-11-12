---
layout: page
permalink: /internal/dgx/
title: "DGX Cluster"
description: "DGX Spark Cluster: Developer Access and Setup"
nav: false
---

This guide is for developers who have access to the **four-node DGX Spark cluster**. Set up your account once, then use the GPUs for **inference, training, fine-tuning, or your own research code**. No particular model framework or repository is required.

> **Shared cluster:** There is no job scheduler managing these GPUs yet. Coordinate with other developers before using GPUs, starting distributed jobs, or stopping containers. Do not change system networking or other users' processes.

## 1. Log in with your UIC NetID

From your computer (on a network permitted to reach the server):

```bash
ssh YOUR_NETID@spark-01.evl.uic.edu
```

Enter your **UIC NetID password** when prompted. Replace `YOUR_NETID` with your actual NetID in this command; subsequent commands run on Spark 1 unless noted otherwise.

The cluster nodes are:

| Node | Management IP | Role |
| --- | --- | --- |
| Spark 1 | `192.168.1.80` | Login/head node |
| Spark 2 | `192.168.1.243` | Worker |
| Spark 3 | `192.168.1.26` | Worker |
| Spark 4 | `192.168.1.109` | Worker |

Your NetID account must also be enabled on the worker nodes. If a worker rejects your login, ask the cluster administrator to check your access.

## 2. Check Docker access

On Spark 1:

```bash
id -nG
docker ps
```

`docker ps` should run **without `sudo`** and without a Docker socket permission error. Your active groups will normally include `docker`. If access fails, **log out and back in once**, then try again. If it still fails, contact the administrator; do not change system groups or Docker permissions yourself.

You will check Docker access on the other three nodes in Step 4.

## 3. Set up passwordless SSH between Sparks (one time)

The cluster uses SSH to start workers and move model files over the ConnectX-7 network. Run NVIDIA's `discover-sparks` helper **as your normal NetID user, not with `sudo`**.

**On Spark 1:**

```bash
wget https://raw.githubusercontent.com/NVIDIA/dgx-spark-playbooks/refs/heads/main/nvidia/connect-two-sparks/assets/discover-sparks
chmod +x discover-sparks
./discover-sparks
```

Enter your NetID password when prompted for nearby nodes. This discovers Spark 2 and Spark 4 and configures SSH keys for them.

**Next, connect from Spark 1 to Spark 2:**

```bash
ssh 10.20.0.12
```

**On Spark 2, run the helper again** so it can also configure Spark 3:

```bash
wget https://raw.githubusercontent.com/NVIDIA/dgx-spark-playbooks/refs/heads/main/nvidia/connect-two-sparks/assets/discover-sparks
chmod +x discover-sparks
./discover-sparks
```

The helper uses `~/.ssh/id_ed25519_shared` and distributes that shared private key to discovered nodes. This is the cluster's documented setup method; use it only if your account is authorized for this shared-key arrangement. **Never share the private key outside your own cluster account.**

## 4. Verify SSH host keys and Docker permissions

Host-key trust and passwordless authentication are **different checks**. The first time you connect to an SSH endpoint, check its displayed server-key fingerprint against the administrator's trusted fingerprint before accepting it. Do not disable host-key checking or erase your whole `known_hosts` file.

### Check the complete physical ring

Starting on **Spark 2** (where Step 3 left you), run these commands **one at a time**:

```bash
# On Spark 2 → Spark 3
ssh 10.20.2.13

# Now on Spark 3 → Spark 4
ssh 10.20.4.14

# Now on Spark 4 → Spark 1
ssh 10.20.6.11
```

You have now checked the complete route **Spark 1 → 2 → 3 → 4 → 1**. SSH should succeed without asking for your account password once key setup is complete. Type `exit` **four times** to return to your original shell on Spark 1.

Also check Spark 1's other direct CX7 neighbor:

```bash
ssh 10.20.6.14 hostname   # Spark 1 → Spark 4
```

### Check head-to-worker management SSH and Docker

On **Spark 1**:

```bash
for ip in 192.168.1.243 192.168.1.26 192.168.1.109; do
  echo "=== $ip ==="
  ssh "$USER@$ip" 'hostname; id -nG; docker ps >/dev/null && echo "Docker: OK"'
done
```

Verify any new host-key prompts. Each worker should report `Docker: OK`, and after the initial SSH setup these connections should not require account passwords.

> **Optional SSH aliases:** You may add friendly names to `~/.ssh/config`, but they do not replace host-key verification. **Do not configure permanent `ProxyJump` routes for model copies:** the repository constructs those routes automatically when needed.

## 5. Optional: configure the `spark-vllm-docker` inference example

**[`spark-vllm-docker`](https://github.com/eugr/spark-vllm-docker) is an optional example for distributed vLLM inference**, not the cluster software and not a prerequisite for PyTorch, Hugging Face, training, or other projects. Its `.env` file is read by **its own launcher only**.

If you want to use this example, create **your own checkout** on Spark 1:

```bash
cd ~
git clone https://github.com/eugr/spark-vllm-docker.git
cd spark-vllm-docker
```

If you already cloned the repository, use that directory instead. Create or inspect **this repository’s** `.env`:

```bash
nano .env
```

Use the cluster's configured four-node ring values below (do not replace the working topology with the generic two-node `.env.example`):

```dotenv
CLUSTER_NODES=192.168.1.80,192.168.1.243,192.168.1.26,192.168.1.109
CLUSTER_LINKS='[{"192.168.1.80":"10.20.0.11","192.168.1.243":"10.20.0.12"},{"192.168.1.243":"10.20.2.12","192.168.1.26":"10.20.2.13"},{"192.168.1.26":"10.20.4.13","192.168.1.109":"10.20.4.14"},{"192.168.1.109":"10.20.6.14","192.168.1.80":"10.20.6.11"}]'
LOCAL_IP=192.168.1.80
ETH_IF=wlP9s9
IB_IF=rocep1s0f0,roceP2p1s0f0,rocep1s0f1,roceP2p1s0f1
CONTAINER_NCCL_NET_PLUGIN=none
CONTAINER_NCCL_IB_SUBNET_AWARE_ROUTING=1
CONTAINER_NCCL_IB_MERGE_NICS=0
CONTAINER_NCCL_ALGO=Ring
```

These are the values used by the established cluster configuration; the shown `CLUSTER_LINKS` describes one rail per cable. If the administrator provides an updated dual-rail `.env`, use that instead. Do **not** add `COPY_HOSTS` for this ring.

Save the file, then run:

```bash
chmod 600 .env
./launch-cluster.sh --check-config
```

**Do not rerun network setup scripts or overwrite Netplan.** Running `--discover` is usually unnecessary if you have the supplied `.env`; on this ring, incomplete automatic discovery can produce an incomplete configuration.

## 6. Choose a development workflow

You can use your own Python projects, containers, models, datasets, and frameworks. **A repository recipe does not turn four GPUs into one GPU**; your chosen framework must explicitly support distributed execution.

| Goal | Suggested tooling | Nodes |
| --- | --- | --- |
| Prototype or run a smaller model | PyTorch / Hugging Face Transformers | 1 |
| Serve one model split across four GPUs | vLLM with tensor parallelism | 4 |
| Train a model faster with data parallelism | PyTorch Distributed Data Parallel (DDP) | 4 |
| Fine-tune a model larger than one Spark can hold | Hugging Face Accelerate + FSDP, or NVIDIA NeMo | Up to 4 after validation |

**Before any GPU run:** check availability with `nvidia-smi` on the intended Sparks and coordinate with other users. A successful `docker ps` means you have Docker access; it does **not** mean the GPU is free. Use a unique output directory and avoid other users’ container names or ports.

### Example A — Run a small model on one Spark (no vLLM repository)

Create a workspace on the Spark you intend to use:

```bash
mkdir -p ~/my-inference && cd ~/my-inference
```

Create `infer.py`:

```python
from transformers import pipeline

generator = pipeline(
    "text-generation",
    model="Qwen/Qwen2.5-0.5B-Instruct",
    device=0,
)
result = generator(
    [{"role": "user", "content": "Explain what a GPU cluster is."}],
    max_new_tokens=100,
)
print(result[0]["generated_text"][-1]["content"])
```

Run it in a PyTorch container (first run downloads the image and model):

```bash
docker run --rm --gpus all --ipc=host \
  -v "$PWD:/workspace" -w /workspace \
  -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
  nvcr.io/nvidia/pytorch:25.11-py3 \
  bash -lc 'pip install -q transformers==4.57.1 && python infer.py'
```

This uses **one GPU** and does not affect or depend on the four-node vLLM launcher.

### Example B — Serve an LLM on all four Sparks (vLLM example)

Only if you chose to set up the repository in Step 5:

```bash
cd ~/spark-vllm-docker

# Review what will run; does not launch containers
./run-recipe.sh recipes/qwen3.8-27b-nvfp4-dflash2.yaml --tp 4 --dry-run

# Run only when all four GPUs are available to you
./run-recipe.sh recipes/qwen3.8-27b-nvfp4-dflash2.yaml --tp 4 --setup
```

When the service is ready, check it on Spark 1:

```bash
curl -i http://localhost:8000/health
curl -s http://localhost:8000/v1/models | python3 -m json.tool
./launch-cluster.sh status
```

**This is an inference example, not a training system.** You may write your own vLLM configuration or use other inference engines. Do not stop or replace another developer’s service.

### Example C — Train across all four Sparks with PyTorch DDP

This is a **minimal distributed-training example** that runs one training process per GPU. DDP keeps a **full copy of the small model on each GPU** and synchronizes gradients; it is not model sharding. For larger-than-one-GPU training, see Example D.

**Prerequisites:** all four GPUs available; Docker and NVIDIA GPU support on all nodes; matching container image on each node; a reachable management network; and administrator-validated NCCL communication over this **switchless ring**. The following is an illustrative job to test and adapt, **not a four-node training run validated on this cluster**.

**1.** On Spark 1, create `~/spark-training/train_ddp.py`:

```python
import os
import torch
import torch.distributed as dist
from torch import nn
from torch.nn.parallel import DistributedDataParallel as DDP

dist.init_process_group("nccl")
local_rank = int(os.environ["LOCAL_RANK"])
torch.cuda.set_device(local_rank)

model = nn.Sequential(nn.Linear(32, 64), nn.ReLU(), nn.Linear(64, 1))
model = DDP(model.to(f"cuda:{local_rank}"), device_ids=[local_rank])
optimizer = torch.optim.AdamW(model.parameters(), lr=0.001)

for step in range(20):
    x = torch.randn(64, 32, device=f"cuda:{local_rank}")
    y = x.sum(dim=1, keepdim=True)
    optimizer.zero_grad()
    loss = nn.functional.mse_loss(model(x), y)
    loss.backward()  # synchronizes gradients over the four nodes
    optimizer.step()
    if dist.get_rank() == 0:
        print(f"step={step} loss={loss.item():.4f}", flush=True)

print(f"Finished rank {dist.get_rank()} / {dist.get_world_size()}", flush=True)
dist.destroy_process_group()
```

**2.** Copy your script to the other three Sparks. This example does **not** assume a shared home filesystem:

```bash
cd ~/spark-training
for ip in 192.168.1.243 192.168.1.26 192.168.1.109; do
  ssh "$USER@$ip" 'mkdir -p ~/spark-training'
  scp train_ddp.py "$USER@$ip:~/spark-training/"
done
```

**3.** Pull the training image on each Spark, and open **one terminal per Spark**. In each terminal, connect to that Spark and change `RANK` as shown:

| Terminal | Spark | `RANK` |
| --- | --- | --- |
| 1 | Spark 1 / `192.168.1.80` | `0` |
| 2 | Spark 2 / `192.168.1.243` | `1` |
| 3 | Spark 3 / `192.168.1.26` | `2` |
| 4 | Spark 4 / `192.168.1.109` | `3` |

```bash
# Run on EACH Spark, using its own rank 0, 1, 2 or 3
RANK=0  # <-- change on the other three nodes

docker pull nvcr.io/nvidia/pytorch:25.11-py3

docker run --rm --gpus all --network=host --ipc=host \
  -v "$HOME/spark-training:/workspace" -w /workspace \
  -e RANK="$RANK" \
  -e NCCL_NET_PLUGIN=none \
  -e NCCL_IB_SUBNET_AWARE_ROUTING=1 \
  -e NCCL_IB_MERGE_NICS=0 \
  -e NCCL_ALGO=Ring \
  -e NCCL_IB_HCA=rocep1s0f0,roceP2p1s0f0,rocep1s0f1,roceP2p1s0f1 \
  nvcr.io/nvidia/pytorch:25.11-py3 \
  bash -lc 'torchrun --nnodes=4 --nproc-per-node=1 \
    --node-rank="$RANK" --master-addr=192.168.1.80 \
    --master-port=29541 train_ddp.py'
```

All four commands must be running for the job to start. Use a **different, unused master port** for concurrent jobs. If it works, rank 0 prints training losses and every terminal reports completion. If NCCL selects an unreachable interface, work with the administrator to choose the **management-facing `NCCL_SOCKET_IFNAME` on each node**; interface names need not match. Do not change Netplan or disable SSH host-key verification.

### Example D — Fine-tune a larger LLM across multiple nodes

For real LLM fine-tuning, start with **Hugging Face Accelerate + FSDP** or NVIDIA's PyTorch/NeMo training examples. Unlike DDP, **FSDP shards model parameters, gradients and optimizer state**, helping models fit across multiple GPUs. LoRA/QLoRA can further reduce trainable memory.

For an existing Accelerate-compatible training script (`train.py`), the **multi-node launch pattern** is:

```bash
# Execute on EACH of the four nodes, with MACHINE_RANK = 0,1,2,3
MACHINE_RANK=0  # change on each node

accelerate launch --multi_gpu \
  --num_machines 4 --num_processes 4 \
  --machine_rank "$MACHINE_RANK" \
  --main_process_ip 192.168.1.80 --main_process_port 29542 \
  train.py
```

This **does not automatically enable FSDP**: configure your training script and Accelerate's `distributed_type: FSDP` settings first, use compatible environments on all four nodes, copy your data/code or use shared storage, and validate the ring's NCCL behavior. Do not paste this into a shell expecting it to train an LLM without a real training script, model, dataset and configuration.

Useful maintained starting points:

- [NVIDIA: Fine-Tune with PyTorch](https://github.com/NVIDIA/dgx-spark-playbooks/blob/main/nvidia/playbook-pytorch-fine-tune/README.md) — LoRA/QLoRA and an **officially documented two-node** Accelerate/FSDP path. Its Docker Swarm configuration requires administrator coordination; **do not initialize Swarm or restart Docker on the shared cluster**.
- [NVIDIA: Fine-Tune with NeMo](https://build.nvidia.com/spark/nemo-fine-tune/instructions) — model fine-tuning examples for DGX Spark; check the supported multi-node path before adapting it to four nodes.
- [PyTorch: torchrun](https://docs.pytorch.org/docs/stable/elastic/run.html) and [DDP tutorial](https://docs.pytorch.org/tutorials/intermediate/ddp_tutorial.html) — custom distributed training.
- [Hugging Face: Launching Accelerate scripts](https://huggingface.co/docs/accelerate/main/basic_tutorials/launch) — multi-machine configuration and launch parameters.
- [NVIDIA: NCCL for multiple Sparks](https://build.nvidia.com/spark/nccl) — verifying GPU-to-GPU communication before distributed training.

> **Topology note:** Our cluster is a **four-node direct-connected RoCE ring, not a switched fabric**. The `spark-vllm-docker` project has validated full-ring **inference** with special NCCL settings; this does **not** automatically validate arbitrary four-node training frameworks. Start with the small DDP test above before attempting long fine-tuning runs. Three-node selections may also need topology-specific work rather than assuming they can use the same fast RDMA path.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| `docker ps` gives permission denied | Sign out and back in; ask the administrator to verify your access on that Spark. |
| SSH asks for a password | Check the two `discover-sparks` runs and SSH key setup for your account. |
| `Host key verification failed` | Verify the exact endpoint and its trusted fingerprint; don't disable checking. |
| Spark 1 cannot directly SSH to Spark 3 over CX7 | Expected: Spark 3 is not a direct QSFP neighbor. The vLLM repository handles jumps for its **file transfers**, not for general RDMA routing. |
| `.env` check fails | For the **optional vLLM example only**, verify the repository-specific node and link configuration. |
| PyTorch job hangs during initialization | Make sure all four ranks started; check the master address/port, matching PyTorch versions, GPU visibility and administrator-validated NCCL transport on the ring. |
| GPU out of memory or port already used | Another developer may be running a job; coordinate instead of killing their processes. |

The cluster networking is already configured. **Do not rerun connection/setup scripts, change Netplan, initialize Docker Swarm, or alter other users' containers** as part of normal development.

