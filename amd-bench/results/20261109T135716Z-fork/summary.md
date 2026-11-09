# 4.5 Clone (fork)

Template `swesmith-090a7c94c767-m2`; one running sandbox forked into n children, 3 rounds.
`fork call` = fork request until the SDK returned the children; `all ready` = until every child finished a first command.

| n | Success | Fork call avg | min | max | All ready avg | min | max | Per-fork avg (all ready / n) |
|---|---|---|---|---|---|---|---|---|
| 1 | 3/3 | 391 | 270 | 458 | 583 | 472 | 644 | 583 |
| 10 | 30/30 | 1252 | 1021 | 1422 | 1563 | 1337 | 1733 | 156 |
| 50 | 150/150 | 2569 | 2155 | 3149 | 3650 | 3236 | 4253 | 73 |
| 100 | 300/300 | 2984 | 2779 | 3167 | 5453 | 5084 | 5821 | 55 |

Latencies in ms.
