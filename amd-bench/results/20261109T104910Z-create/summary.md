# 3.2 Cold start and concurrency scaling

Template `base`, 3 rounds per level, all requests of a round fired at once.
`ready` = create request sent -> first command (`true`) finished; `api` = create call returned.

| Concurrency | Success | Ready avg | Ready min | Ready p50 | Ready p95 | Ready p99 | Ready max | API p50 | API p95 | Wall avg | Throughput (/s) | Start-limit rejections | Host CPU peak | Steal peak | Hugepages peak (MiB) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 3/3 | 63 | 57 | 63 | 68 | 68 | 68 | 51 | 57 | 63 | 16.0 | 0 | 19% | 0% | 162 |
| 10 | 30/30 | 209 | 79 | 198 | 435 | 444 | 444 | 181 | 421 | 371 | 27.0 | 169 | 46% | 1% | 1698 |
| 20 | 60/60 | 438 | 79 | 365 | 1286 | 1607 | 1607 | 343 | 1271 | 1284 | 15.6 | 467 | 42% | 1% | 3404 |
| 50 | 150/150 | 662 | 61 | 617 | 1408 | 1582 | 2256 | 600 | 1398 | 1770 | 28.2 | 1385 | 25% | 2% | 8524 |
| 100 | 300/300 | 1290 | 73 | 1218 | 2745 | 3145 | 3432 | 1205 | 2725 | 3164 | 31.6 | 3264 | 52% | 2% | 17120 |
| 200 | 600/600 | 3935 | 84 | 3280 | 11649 | 21166 | 23296 | 3215 | 11631 | 12866 | 15.5 | 9687 | 93% | 3% | 34976 |

Latencies in ms.
