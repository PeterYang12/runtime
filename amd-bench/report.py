#!/usr/bin/env python3
"""Generate REPORT.md (English) from the result directories, in the CubeBench v0.7.3 report format
(heading -> table, units stated per chapter); section 5 adds our own analysis.

The runs that make up the report are pinned in RUNS, so later ad-hoc runs in
results/ do not change it. Re-run after replacing a pinned run:

    .venv/bin/python report.py
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent

RES = ROOT / "results"

RUNS = {
    "create": "20261109T104728Z-create",
    "create_base": "20261109T104910Z-create",
    "density": "20261109T105628Z-density",
    "snapshot": "20261109T135541Z-snapshot",
    "snapshot_dirty": "20261109T135625Z-snapshot-dirty",
    "from_snapshot": "20261109T110123Z-from-snapshot",
    "fork": "20261109T135716Z-fork",
    "pause": "20261109T135804Z-pause",
}


def raw(key: str) -> list[dict]:
    return [json.loads(l) for l in (RES / RUNS[key] / "raw.jsonl").read_text().splitlines() if l.strip()]


def summary(key: str) -> dict:
    return json.loads((RES / RUNS[key] / "summary.json").read_text())


def pct(v: list[float], p: float) -> float:
    s = sorted(v)
    k = max(0, min(len(s) - 1, int(round(p / 100 * len(s) + 0.5)) - 1))
    return s[k]


def st(v: list[float]) -> tuple[str, str, str, str]:
    """avg, min, p95, max in ms (input in ms)."""
    return tuple(f"{x:.1f}" for x in (statistics.fmean(v), min(v), pct(v, 95), max(v)))


def table(header: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def round_walls(recs: list[dict], key: str = "concurrency", extra: str | None = None) -> dict:
    """{level: [wall_ms per round]} from per-op records carrying t0/t_end."""
    by = defaultdict(list)
    for r in recs:
        if extra and r.get("op") != extra:
            continue
        by[(r[key], r["round"])].append(r)
    walls = defaultdict(list)
    for (lvl, _), rs in sorted(by.items()):
        walls[lvl].append((max(x["t_end"] for x in rs) - min(x["t0"] for x in rs)) * 1000)
    return walls


# ----------------------------------------------------------------- sections

def sec_create(key: str) -> str:
    recs = raw(key)
    host = {r["concurrency"]: r for r in summary(key)["levels"]}
    rows = []
    for c in sorted({r["concurrency"] for r in recs}):
        rs = [r for r in recs if r["concurrency"] == c]
        ok = [r for r in rs if r["ok"]]
        rounds = len({r["round"] for r in rs})
        walls = round_walls(rs)[c]
        ready = [r["ready_s"] * 1000 for r in ok]
        per_round_ok = len(ok) / rounds
        rows.append([c, f"{len(rs)} ({len(ok)})", *st(ready),
                     f"{statistics.fmean(walls) / per_round_ok:.1f}",
                     f"{per_round_ok / (statistics.fmean(walls) / 1000):.1f} /s",
                     f"{host[c]['cpu_busy_peak_pct']:.0f}%", f"{host[c]['steal_peak_pct']:.0f}%"])
    return table(["Concurrency", "Requests (successful)", "avg (ms)", "min (ms)",
                  "p95 (ms)", "max (ms)", "Wall/successful sandbox (ms)",
                  "Throughput", "Host CPU peak", "Steal peak"], rows)


def sec_density() -> str:
    s = summary("density")
    base_other = s["baseline"]["other_mib"]
    rows = [[0, f"{base_other / 1024:.1f} GiB", "-", f"{s['baseline']['cpu_busy_pct']:.1f}%"]]
    for r in s["rows"]:
        used = base_other + r["hugepages_used_mib"] + r["other_mem_used_mib"]
        rows.append([r["live"], f"{used / 1024:.1f} GiB",
                     f"{(r['hugepages_used_mib'] + r['other_mem_used_mib']) / r['live']:.1f} MiB",
                     f"{r['idle_cpu_busy_pct']:.1f}%"])
    return table(["Live sandboxes", "Used memory",
                  "Per-VM amortized overhead",
                  "Host CPU busy (5 s avg)"], rows)


def cpu(row: dict, prefix: str = "") -> list[str]:
    """[CPU peak, steal peak] cells of a summary row."""
    c, st_ = row.get(f"{prefix}cpu_busy_peak_pct"), row.get(f"{prefix}steal_peak_pct")
    return ["-" if c is None else f"{c:.0f}%", "-" if st_ is None else f"{st_:.0f}%"]


def rows_by(key: str, field: str) -> dict:
    s = summary(key)
    return {r[field]: r for r in (s.get("rows") or s.get("levels"))}


def sec_snapshot() -> str:
    walls = round_walls(raw("snapshot"))
    host = rows_by("snapshot", "concurrency")
    rows = [[c, *st(w), f"{statistics.fmean(w) / c:.1f}", *cpu(host[c])] for c, w in sorted(walls.items())]
    return table(["Concurrency", "Wall avg (ms)", "Wall min (ms)", "Wall p95 (ms)",
                  "Wall max (ms)",
                  "Per-snapshot avg (ms)", "Host CPU peak", "Steal peak"], rows)


def sec_snapshot_dirty() -> str:
    by = defaultdict(lambda: ([], []))
    for r in raw("snapshot_dirty"):
        by[r["dirty_mib"]][0].append(r["snapshot_s"] * 1000)
        by[r["dirty_mib"]][1].append(r["create_from_snapshot_s"] * 1000)
    host = rows_by("snapshot_dirty", "dirty_mib")
    rows = [[mib, *st(s), *st(c), cpu(host[mib], "snapshot_")[0], cpu(host[mib], "create_")[0]]
            for mib, (s, c) in sorted(by.items())]
    return table(["Write size (MiB)", "snapshot avg (ms)", "snapshot min (ms)", "snapshot p95 (ms)",
                  "snapshot max (ms)", "create sandbox avg (ms)", "create sandbox min (ms)", "create sandbox p95 (ms)",
                  "create sandbox max (ms)", "Snapshot host CPU peak",
                  "Create sandbox host CPU peak"], rows)


def sec_from_snapshot() -> str:
    recs = raw("from_snapshot")
    walls = round_walls(recs)
    host = rows_by("from_snapshot", "concurrency")
    rows = [[c, c, *st(w), f"{statistics.fmean(w) / c:.1f}", *cpu(host[c])] for c, w in sorted(walls.items())]
    return table(["Concurrency", "n/round", "Wall avg (ms)", "Wall min (ms)", "Wall p95 (ms)",
                  "Wall max (ms)",
                  "Per-sandbox avg (ms)", "Host CPU peak", "Steal peak"], rows)


def sec_fork() -> str:
    by = defaultdict(list)
    for r in raw("fork"):
        by[r["count"]].append(r["all_ready_s"] * 1000)
    host = rows_by("fork", "count")
    rows = [[n, 1, *st(w), f"{statistics.fmean(w) / n:.1f}", *cpu(host[n])] for n, w in sorted(by.items())]
    return table(["Clones (n)", "Concurrency", "Wall avg (ms)", "Wall min (ms)", "Wall p95 (ms)",
                  "Wall max (ms)",
                  "Per-clone avg (ms)", "Host CPU peak", "Steal peak"], rows)


def sec_pause() -> str:
    recs = raw("pause")
    pw, rw = round_walls(recs, extra="pause"), round_walls(recs, extra="resume")
    host = rows_by("pause", "concurrency")
    rows = [[c, *st(pw[c]), *st(rw[c]), f"{statistics.fmean(pw[c]) / c:.1f}", f"{statistics.fmean(rw[c]) / c:.1f}",
             cpu(host[c], "pause_")[0], cpu(host[c], "resume_")[0]] for c in sorted(pw)]
    return table(["Concurrency", "pause avg (ms)", "pause min (ms)", "pause p95 (ms)", "pause max (ms)",
                  "resume avg (ms)", "resume min (ms)", "resume p95 (ms)", "resume max (ms)",
                  "Per-pause avg (ms)", "Per-resume avg (ms)",
                  "Pause host CPU peak", "Resume host CPU peak"], rows)


def sec_issues() -> str:
    """Section 5: the problems found, short, numbers from the pinned runs."""
    sw, bs = summary("create")["levels"], summary("create_base")["levels"]
    peak = max(sw[:-1], key=lambda r: r["throughput_per_s"])
    peak_b = max(bs[:-1], key=lambda r: r["throughput_per_s"])
    last = sw[-1]
    cpu_ok = max(r["cpu_busy_peak_pct"] for r in sw[:-1])
    snap = {r["concurrency"]: r for r in summary("snapshot")["rows"]}
    dens = summary("density")["rows"][-1]
    per_vm = dens["hugepages_used_mib"] / dens["live"]
    fit = 204800 * 2 / per_vm
    fk = sorted(summary("fork")["rows"], key=lambda r: r["count"])
    fk_big, fk_mid = fk[-1], fk[-2]
    t = table(["Concurrency", *[str(r["concurrency"]) for r in sw]],
              [["swesmith throughput (/s)", *[f"{r['throughput_per_s']:.1f}" for r in sw]],
               ["base throughput (/s)", *[f"{r['throughput_per_s']:.1f}" for r in bs]],
               ["swesmith ready p95 (ms)", *[f"{r['ready_ms']['p95']:.0f}" for r in sw]],
               ["Start-limit rejections", *[str(r["start_limit_rejections"]) for r in sw]],
               ["Host CPU peak", *[f"{r['cpu_busy_peak_pct']:.0f}%" for r in sw]]])
    return f"""1. **Create throughput is capped at ~{peak['throughput_per_s']:.0f} sandboxes/s** (base ~{peak_b['throughput_per_s']:.0f}/s).
   E2B starts at most 3 sandboxes at a time per node; the rest queue and retry. Host CPU peak stays at or below
   {cpu_ok:.0f}% meanwhile, so the hardware is not the bottleneck. Starting a batch of 512 sandboxes takes ~{512 / peak['throughput_per_s']:.0f} s.
2. **Performance drops at {last['concurrency']} concurrent creates**: throughput falls to {last['throughput_per_s']:.0f}/s, ready p95 {last['ready_ms']['p95']:.0f} ms,
   host CPU peak {last['cpu_busy_peak_pct']:.0f}%. Root cause not yet identified.
3. **Snapshot creation scales poorly with concurrency**: one snapshot takes {snap[1]['wall_ms']['avg']:.0f} ms; with 10 at once, per-snapshot p50 is {snap[10]['lat_ms']['p50']:.0f} ms.
4. **The 200-running-sandbox cap per node is far below memory capacity**: an idle sandbox uses ~{per_vm:.0f} MiB, so the
   400 GiB hugepage pool could hold ~{fit:,.0f}.
5. **Large forks saturate the host CPU**: forking {fk_big['count']} children peaks host CPU at {fk_big['cpu_busy_peak_pct']:.0f}%
   ({fk_mid['cpu_busy_peak_pct']:.0f}% for {fk_mid['count']}), the only operation in these tests that saturates the CPU.

{t}"""



# ------------------------------------------------------------------- report

def env_table() -> str:
    env = (RES / RUNS["create"] / "env.md").read_text()

    def pick(prefix: str) -> str:
        for line in env.splitlines():
            if line.startswith(prefix):
                return line[len(prefix):].strip()
        return "-"

    pins = {l.split("=", 1)[0]: l.split("=", 1)[1] for l in env.splitlines() if "=" in l and l.startswith("E2B_")}
    return table(["Item", "Value"], [
        ["OS", pick("- OS:")],
        ["Kernel", pick("- Kernel:")],
        ["CPU", pick("- CPU:")],
        ["Memory", pick("- Memory:")],
        ["Virtualization", "DigitalOcean droplet (KVM); sandboxes run nested"],
        ["Storage", "templates and snapshots on a DigitalOcean block volume (4.9T, network-attached)"],
        ["Nodes", "1 (E2B Embed, docker compose)"],
        ["E2B api", pins.get("E2B_API_IMAGE", "-").rsplit(":", 1)[-1]],
        ["E2B orchestrator", pins.get("E2B_ORCHESTRATOR_VERSION", "-")],
        ["Firecracker", pins.get("E2B_FIRECRACKER_VERSION", "-")],
        ["Guest kernel", pins.get("E2B_KERNEL_VERSION", "-")],
        ["SDK version", pick("- Python SDK:").replace("e2b ", "e2b (Python) ")],
    ])


def render_en(tpl: str, generated: str) -> str:
    return f"""# E2B Core Operations Performance Benchmark Report (single AMD EPYC node)

Generated at: {generated}

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

{env_table()}

## 3 Create Sandbox from Template

All times in this chapter are in milliseconds (ms).

### 3.1 Sandbox Spec and Test Image

{table(["Item", "Value"], [
    ["Spec", "2 vCPU / 2048 MiB"],
    ["Template", f"`{tpl}` (SWE-smith task image)"],
    ["Ready", "first command (`true`) in the sandbox finished"],
    ["Requests", "all requests of a round sent at once; client on the same host as the sandboxes"],
    ["Host CPU", "utilization of all 64 vCPUs, sampled every 0.1 s during the measured operation, peak reported "
                 "(3.3: 5 s average); steal = share taken by the hypervisor. Same method in chapter 4"],
    ["SDK", "e2b (Python) 2.46.0"],
])}

### 3.2 Cold-Start Latency and Concurrency Scaling

Two tables, same method, different templates:

- **Table 3.2-1**: `{tpl}` (2 vCPU / 2048 MiB, SWE-smith task image), the spec of 3.1, representing the sandboxes RL uses.
- **Table 3.2-2**: `base` (2 vCPU / 512 MiB, E2B's default minimal image), as a reference: with the smallest image the
  numbers mainly reflect E2B's own platform overhead.

**Table 3.2-1: `{tpl}` (2 vCPU / 2048 MiB)**

{sec_create("create")}

**Table 3.2-2: `base` (2 vCPU / 512 MiB)**

{sec_create("create_base")}

### 3.3 Single-Host Deployment Density (Memory Overhead)

{sec_density()}

## 4 Snapshot Operations

All times in this chapter are in milliseconds (ms). Write size is in MiB.

### 4.1 Snapshot Creation vs Concurrency

{sec_snapshot()}

### 4.2 Snapshot Creation vs Dirty Memory Size

{sec_snapshot_dirty()}

### 4.3 Create Sandbox from Snapshot

{sec_from_snapshot()}

### 4.4 Rollback

Not applicable: E2B has no rollback API.

### 4.5 Clone

{sec_fork()}

### 4.6 Pause / Resume

{sec_pause()}

## 5 Issues

{sec_issues()}
"""


def main() -> None:
    tpl = summary("create")["template"]
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    (ROOT / "REPORT.md").write_text(render_en(tpl, generated))
    print("wrote REPORT.md")


if __name__ == "__main__":
    main()
