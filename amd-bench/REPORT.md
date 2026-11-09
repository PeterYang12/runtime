# E2B Core Operations Performance Benchmark Report (single AMD EPYC node)

Generated at: 2026-11-09 14:10:14 UTC

## 1 Overview

Following the structure of the CubeBench v0.7.3 report, this report benchmarks E2B (Embed, single-node deployment)
on an AMD EPYC server across the following dimensions:

- Cold-start latency
- Concurrency scaling
- Deployment density
- Snapshot creation vs concurrency
- Snapshot creation vs dirty memory size
- Create sandbox from snapshot
- Clone (fork)
- Pause / resume

## 2 Test Environment

| Item | Value |
|---|---|
| OS | Ubuntu 24.04.5 LTS |
| Kernel | 6.8.0-142-generic |
| CPU | AMD EPYC 9555P 64-Core Processor, 64 vCPUs, 1 thread(s)/core |
| Memory | 503 GiB total; hugepages 204800 x 2 MiB |
| Virtualization | DigitalOcean droplet (KVM); sandboxes run nested |
| Storage | templates and snapshots on a DigitalOcean block volume (4.9T, network-attached) |
| Nodes | 1 (E2B Embed, docker compose) |
| E2B api | v0.14.202610271447-39ad7ab6a67 |
| E2B orchestrator | v0.16.202610201713-75c97c0d1da |
| Firecracker | v1.14-0.2.0 |
| Guest kernel | vmlinux-6.1.177_5008931 |
| SDK version | e2b (Python) 2.46.0 |

## 3 Create Sandbox from Template

All times in this chapter are in milliseconds (ms).

### 3.1 Sandbox Spec and Test Image

| Item | Value |
|---|---|
| Spec | 2 vCPU / 2048 MiB |
| Template | `swesmith-090a7c94c767-m2` (SWE-smith task image) |
| Ready | first command (`true`) in the sandbox finished |
| Requests | all requests of a round sent at once; client on the same host as the sandboxes |
| Host CPU | utilization of all 64 vCPUs, sampled every 0.1 s during the measured operation, peak reported (3.3: 5 s average); steal = share taken by the hypervisor. Same method in chapter 4 |
| SDK | e2b (Python) 2.46.0 |

### 3.2 Cold-Start Latency and Concurrency Scaling

Two tables, same method, different templates:

- **Table 3.2-1**: `swesmith-090a7c94c767-m2` (2 vCPU / 2048 MiB, SWE-smith task image), the spec of 3.1, representing the sandboxes RL uses.
- **Table 3.2-2**: `base` (2 vCPU / 512 MiB, E2B's default minimal image), as a reference: with the smallest image the
  numbers mainly reflect E2B's own platform overhead.

**Table 3.2-1: `swesmith-090a7c94c767-m2` (2 vCPU / 2048 MiB)**

| Concurrency | Requests (successful) | avg (ms) | min (ms) | p95 (ms) | max (ms) | Wall/successful sandbox (ms) | Throughput | Host CPU peak | Steal peak |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 3 (3) | 237.6 | 231.7 | 240.7 | 240.7 | 237.6 | 4.2 /s | 5% | 0% |
| 10 | 30 (30) | 447.2 | 327.4 | 611.2 | 842.1 | 67.3 | 14.9 /s | 22% | 0% |
| 20 | 60 (60) | 661.7 | 350.0 | 1064.3 | 1514.3 | 60.8 | 16.5 /s | 28% | 0% |
| 50 | 150 (150) | 1238.9 | 332.0 | 2263.6 | 2531.6 | 48.9 | 20.5 /s | 34% | 1% |
| 100 | 300 (300) | 2256.0 | 390.0 | 4113.7 | 4766.6 | 45.3 | 22.1 /s | 60% | 6% |
| 200 | 600 (600) | 6445.5 | 413.4 | 20764.5 | 24891.5 | 76.5 | 13.1 /s | 77% | 7% |

**Table 3.2-2: `base` (2 vCPU / 512 MiB)**

| Concurrency | Requests (successful) | avg (ms) | min (ms) | p95 (ms) | max (ms) | Wall/successful sandbox (ms) | Throughput | Host CPU peak | Steal peak |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 3 (3) | 62.6 | 56.7 | 68.0 | 68.0 | 62.6 | 16.0 /s | 19% | 0% |
| 10 | 30 (30) | 209.2 | 79.5 | 434.6 | 444.3 | 37.1 | 27.0 /s | 46% | 1% |
| 20 | 60 (60) | 437.7 | 79.3 | 1286.1 | 1607.0 | 64.2 | 15.6 /s | 42% | 1% |
| 50 | 150 (150) | 662.4 | 61.5 | 1408.2 | 2256.1 | 35.4 | 28.2 /s | 25% | 2% |
| 100 | 300 (300) | 1289.9 | 72.5 | 2745.5 | 3432.5 | 31.6 | 31.6 /s | 52% | 2% |
| 200 | 600 (600) | 3935.3 | 84.1 | 11649.3 | 23296.1 | 64.3 | 15.5 /s | 93% | 3% |

### 3.3 Single-Host Deployment Density (Memory Overhead)

| Live sandboxes | Used memory | Per-VM amortized overhead | Host CPU busy (5 s avg) |
|---|---|---|---|
| 0 | 8.3 GiB | - | 0.3% |
| 25 | 13.5 GiB | 210.2 MiB | 0.6% |
| 50 | 18.8 GiB | 214.1 MiB | 0.8% |
| 75 | 24.0 GiB | 214.6 MiB | 0.8% |
| 100 | 29.4 GiB | 215.9 MiB | 1.2% |
| 125 | 34.8 GiB | 217.2 MiB | 1.2% |
| 150 | 40.2 GiB | 217.5 MiB | 1.6% |
| 175 | 45.5 GiB | 217.6 MiB | 1.7% |
| 200 | 50.9 GiB | 218.1 MiB | 1.8% |

## 4 Snapshot Operations

All times in this chapter are in milliseconds (ms). Write size is in MiB.

### 4.1 Snapshot Creation vs Concurrency

| Concurrency | Wall avg (ms) | Wall min (ms) | Wall p95 (ms) | Wall max (ms) | Per-snapshot avg (ms) | Host CPU peak | Steal peak |
|---|---|---|---|---|---|---|---|
| 1 | 211.9 | 199.8 | 218.9 | 218.9 | 211.9 | 5% | 0% |
| 5 | 581.7 | 381.4 | 860.3 | 860.3 | 116.3 | 13% | 0% |
| 10 | 3094.4 | 1836.2 | 3834.0 | 3834.0 | 309.4 | 16% | 0% |

### 4.2 Snapshot Creation vs Dirty Memory Size

| Write size (MiB) | snapshot avg (ms) | snapshot min (ms) | snapshot p95 (ms) | snapshot max (ms) | create sandbox avg (ms) | create sandbox min (ms) | create sandbox p95 (ms) | create sandbox max (ms) | Snapshot host CPU peak | Create sandbox host CPU peak |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 988.8 | 680.3 | 1559.1 | 1559.1 | 257.4 | 252.5 | 260.0 | 260.0 | 5% | 6% |
| 64 | 1016.6 | 830.1 | 1195.0 | 1195.0 | 309.5 | 254.8 | 384.1 | 384.1 | 6% | 6% |
| 128 | 911.2 | 781.8 | 1046.0 | 1046.0 | 265.1 | 254.0 | 273.5 | 273.5 | 5% | 5% |
| 256 | 1041.7 | 784.7 | 1211.1 | 1211.1 | 247.1 | 243.4 | 253.6 | 253.6 | 6% | 3% |
| 512 | 929.5 | 769.5 | 1124.4 | 1124.4 | 249.6 | 236.2 | 264.9 | 264.9 | 6% | 4% |
| 1024 | 1699.5 | 1559.8 | 1805.0 | 1805.0 | 258.2 | 244.6 | 272.9 | 272.9 | 6% | 6% |

### 4.3 Create Sandbox from Snapshot

| Concurrency | n/round | Wall avg (ms) | Wall min (ms) | Wall p95 (ms) | Wall max (ms) | Per-sandbox avg (ms) | Host CPU peak | Steal peak |
|---|---|---|---|---|---|---|---|---|
| 1 | 1 | 248.8 | 240.2 | 256.7 | 256.7 | 248.8 | 4% | 0% |
| 10 | 10 | 525.0 | 507.2 | 537.5 | 537.5 | 52.5 | 22% | 0% |
| 20 | 20 | 1093.3 | 966.2 | 1249.5 | 1249.5 | 54.7 | 24% | 0% |
| 50 | 50 | 2466.1 | 2256.0 | 2587.4 | 2587.4 | 49.3 | 32% | 3% |

### 4.4 Rollback

Not applicable: E2B has no rollback API.

### 4.5 Clone

| Clones (n) | Concurrency | Wall avg (ms) | Wall min (ms) | Wall p95 (ms) | Wall max (ms) | Per-clone avg (ms) | Host CPU peak | Steal peak |
|---|---|---|---|---|---|---|---|---|
| 1 | 1 | 583.0 | 471.9 | 644.3 | 644.3 | 583.0 | 5% | 0% |
| 10 | 1 | 1563.2 | 1337.1 | 1733.2 | 1733.2 | 156.3 | 19% | 0% |
| 50 | 1 | 3649.6 | 3236.0 | 4252.6 | 4252.6 | 73.0 | 88% | 2% |
| 100 | 1 | 5453.5 | 5083.7 | 5820.7 | 5820.7 | 54.5 | 100% | 2% |

### 4.6 Pause / Resume

| Concurrency | pause avg (ms) | pause min (ms) | pause p95 (ms) | pause max (ms) | resume avg (ms) | resume min (ms) | resume p95 (ms) | resume max (ms) | Per-pause avg (ms) | Per-resume avg (ms) | Pause host CPU peak | Resume host CPU peak |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 52.8 | 42.8 | 70.6 | 70.6 | 318.8 | 279.7 | 397.3 | 397.3 | 52.8 | 318.8 | 11% | 23% |
| 5 | 278.2 | 87.9 | 496.3 | 496.3 | 438.9 | 407.1 | 503.6 | 503.6 | 55.6 | 87.8 | 16% | 17% |
| 10 | 889.4 | 305.2 | 2628.8 | 2628.8 | 1439.0 | 672.7 | 3682.0 | 3682.0 | 88.9 | 143.9 | 24% | 24% |

## 5 Issues

1. **Create throughput is capped at ~22 sandboxes/s** (base ~32/s).
   E2B starts at most 3 sandboxes at a time per node; the rest queue and retry. Host CPU peak stays at or below
   60% meanwhile, so the hardware is not the bottleneck. Starting a batch of 512 sandboxes takes ~23 s.
2. **Performance drops at 200 concurrent creates**: throughput falls to 13/s, ready p95 20765 ms,
   host CPU peak 77%. Root cause not yet identified.
3. **Snapshot creation scales poorly with concurrency**: one snapshot takes 212 ms; with 10 at once, per-snapshot p50 is 1757 ms.
4. **The 200-running-sandbox cap per node is far below memory capacity**: an idle sandbox uses ~213 MiB, so the
   400 GiB hugepage pool could hold ~1,926.
5. **Large forks saturate the host CPU**: forking 100 children peaks host CPU at 100%
   (88% for 50), the only operation in these tests that saturates the CPU.

| Concurrency | 1 | 10 | 20 | 50 | 100 | 200 |
|---|---|---|---|---|---|---|
| swesmith throughput (/s) | 4.2 | 14.9 | 16.5 | 20.5 | 22.1 | 13.1 |
| base throughput (/s) | 16.0 | 27.0 | 15.6 | 28.2 | 31.6 | 15.5 |
| swesmith ready p95 (ms) | 241 | 611 | 1064 | 2264 | 4114 | 20765 |
| Start-limit rejections | 0 | 163 | 456 | 1481 | 3634 | 12108 |
| Host CPU peak | 5% | 22% | 28% | 34% | 60% | 77% |
