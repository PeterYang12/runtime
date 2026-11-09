# 4.6 Pause / resume

Template `swesmith-090a7c94c767-m2`; c sandboxes paused at once, then resumed at once, 5 rounds.
Pause keeps memory (full snapshot). Resume = connect -> first command finished.

| Concurrency | Pause ok | Resume ok | Pause wall avg | min | p95 | max | Per-pause avg | Resume wall avg | min | p95 | max | Per-resume avg |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 5/5 | 5/5 | 53 | 43 | 71 | 71 | 52.8 | 319 | 280 | 397 | 397 | 318.8 |
| 5 | 25/25 | 25/25 | 278 | 88 | 496 | 496 | 55.6 | 439 | 407 | 504 | 504 | 87.8 |
| 10 | 50/50 | 50/50 | 889 | 305 | 2629 | 2629 | 88.9 | 1439 | 673 | 3682 | 3682 | 143.9 |

Latencies in ms.
