# 4.2 Snapshot creation vs dirty memory

Template `swesmith-090a7c94c767-m2`; a guest process holds N MiB of random bytes (dirty, non-zero pages) when the snapshot is taken; 3 rounds per size.
`create from snapshot` = create request -> first command finished in a sandbox started from it.

| Dirty MiB | Success | Snapshot avg | Snapshot min | Snapshot p95 | Snapshot max | Create-from-snapshot avg | min | p95 | max |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 3/3 | 989 | 680 | 1559 | 1559 | 257 | 252 | 260 | 260 |
| 64 | 3/3 | 1017 | 830 | 1195 | 1195 | 310 | 255 | 384 | 384 |
| 128 | 3/3 | 911 | 782 | 1046 | 1046 | 265 | 254 | 273 | 273 |
| 256 | 3/3 | 1042 | 785 | 1211 | 1211 | 247 | 243 | 254 | 254 |
| 512 | 3/3 | 930 | 769 | 1124 | 1124 | 250 | 236 | 265 | 265 |
| 1024 | 3/3 | 1700 | 1560 | 1805 | 1805 | 258 | 245 | 273 | 273 |

Latencies in ms.
