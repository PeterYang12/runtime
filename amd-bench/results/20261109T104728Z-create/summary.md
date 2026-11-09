# 3.2 Cold start and concurrency scaling

Template `swesmith-090a7c94c767-m2`, 3 rounds per level, all requests of a round fired at once.
`ready` = create request sent -> first command (`true`) finished; `api` = create call returned.

| Concurrency | Success | Ready avg | Ready min | Ready p50 | Ready p95 | Ready p99 | Ready max | API p50 | API p95 | Wall avg | Throughput (/s) | Start-limit rejections | Host CPU peak | Steal peak | Hugepages peak (MiB) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 3/3 | 238 | 232 | 241 | 241 | 241 | 241 | 49 | 49 | 238 | 4.2 | 0 | 5% | 0% | 214 |
| 10 | 30/30 | 447 | 327 | 424 | 611 | 842 | 842 | 150 | 367 | 673 | 14.9 | 163 | 22% | 0% | 2136 |
| 20 | 60/60 | 662 | 350 | 627 | 1064 | 1514 | 1514 | 333 | 824 | 1215 | 16.5 | 456 | 28% | 0% | 4262 |
| 50 | 150/150 | 1239 | 332 | 1202 | 2264 | 2439 | 2532 | 889 | 2007 | 2444 | 20.5 | 1481 | 34% | 1% | 10642 |
| 100 | 300/300 | 2256 | 390 | 2209 | 4114 | 4467 | 4767 | 1846 | 3854 | 4529 | 22.1 | 3634 | 60% | 6% | 21284 |
| 200 | 600/600 | 6446 | 413 | 5312 | 20765 | 24183 | 24891 | 4929 | 20491 | 15293 | 13.1 | 12108 | 77% | 7% | 42730 |

Latencies in ms.
