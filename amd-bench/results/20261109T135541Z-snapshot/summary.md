# 4.1 Snapshot creation vs concurrency

Template `swesmith-090a7c94c767-m2`; c running sandboxes snapshotted at once, 5 rounds.
Each snapshot is deleted after the round.

| Concurrency | Success | Wall avg | Wall min | Wall p95 | Wall max | Per-op p50 | Per-op p95 | Per-snapshot avg (wall/c) |
|---|---|---|---|---|---|---|---|---|
| 1 | 5/5 | 212 | 200 | 219 | 219 | 215 | 219 | 211.9 |
| 5 | 25/25 | 582 | 381 | 860 | 860 | 429 | 753 | 116.3 |
| 10 | 50/50 | 3094 | 1836 | 3834 | 3834 | 1757 | 3191 | 309.4 |

Latencies in ms.
