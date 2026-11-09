# 3.3 Single-host density (idle sandboxes)

Template `swesmith-090a7c94c767-m2`; 25 sandboxes added per step, measured after 15 s settle.
Baseline before any sandbox: hugepages used 0 MiB, other memory used 8527 MiB, host CPU busy 0.3%.
Guest memory comes from the hugepage pool; `other` is host memory outside it (Firecracker processes, orchestrator, kernel); page cache and reclaimable slab are excluded.

| Live sandboxes | Hugepages used (MiB) | Hugepages per VM (MiB) | Other mem used (MiB) | Other per VM (MiB) | Firecracker RSS total (MiB) | Host CPU busy (idle sandboxes) |
|---|---|---|---|---|---|---|
| 25 | 5306 | 212.2 | -51 | -2.0 | 84 | 0.6% |
| 50 | 10624 | 212.5 | 79 | 1.6 | 169 | 0.8% |
| 75 | 15944 | 212.6 | 152 | 2.0 | 253 | 0.8% |
| 100 | 21248 | 212.5 | 339 | 3.4 | 338 | 1.2% |
| 125 | 26580 | 212.6 | 575 | 4.6 | 422 | 1.2% |
| 150 | 31888 | 212.6 | 742 | 4.9 | 507 | 1.6% |
| 175 | 37198 | 212.6 | 880 | 5.0 | 591 | 1.7% |
| 200 | 42528 | 212.6 | 1094 | 5.5 | 675 | 1.8% |

Latencies in ms.
