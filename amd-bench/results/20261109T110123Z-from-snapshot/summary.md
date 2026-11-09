# 4.3 Create sandbox from snapshot

Template `snapshot of swesmith-090a7c94c767-m2` (`3bv8o13758z74xzoe361:default`), 3 rounds per level, all requests of a round fired at once.
`ready` = create request sent -> first command (`true`) finished; `api` = create call returned.

| Concurrency | Success | Ready avg | Ready min | Ready p50 | Ready p95 | Ready p99 | Ready max | API p50 | API p95 | Wall avg | Throughput (/s) | Start-limit rejections | Host CPU peak | Steal peak | Hugepages peak (MiB) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 3/3 | 249 | 240 | 250 | 257 | 257 | 257 | 47 | 53 | 249 | 4.0 | 0 | 4% | 0% | 210 |
| 10 | 30/30 | 411 | 309 | 411 | 527 | 534 | 534 | 163 | 323 | 525 | 19.0 | 166 | 22% | 0% | 2110 |
| 20 | 60/60 | 621 | 289 | 573 | 1143 | 1247 | 1247 | 306 | 934 | 1093 | 18.3 | 460 | 24% | 0% | 4220 |
| 50 | 150/150 | 1210 | 330 | 1166 | 2172 | 2534 | 2565 | 863 | 1947 | 2466 | 20.3 | 1475 | 32% | 3% | 10500 |

Latencies in ms.
