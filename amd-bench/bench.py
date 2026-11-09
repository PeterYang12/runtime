#!/usr/bin/env python3
"""E2B single-node benchmark on AMD EPYC, structured after CubeBench v0.7.3.

Subcommands (one per report section):
  env      record the test environment (report section 2)
  create   cold start and concurrency scaling (report section 3.2)

Every run writes into results/<UTC timestamp>-<test>/:
  env.md        environment snapshot
  raw.jsonl     one line per sandbox operation
  summary.json  per-level statistics
  summary.md    the table for the report

Connection settings come from the environment (E2B_API_URL, E2B_SANDBOX_URL,
E2B_API_KEY); `run.sh` exports them from the local compose stack.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMPOSE_DIR = ROOT.parent / "embed" / "compose"


# ---------------------------------------------------------------- helpers

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_run_dir(test: str) -> Path:
    d = ROOT / "results" / f"{now_utc().strftime('%Y%m%dT%H%M%SZ')}-{test}"
    d.mkdir(parents=True, exist_ok=False)
    return d


def sh(cmd: str, cwd: Path | None = None) -> str:
    r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    return (r.stdout + r.stderr).strip()


def pct(values: list[float], p: float) -> float:
    """Nearest-rank percentile of an unsorted list."""
    if not values:
        return float("nan")
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round(p / 100 * len(s) + 0.5)) - 1))
    return s[k]


def stats_ms(values_s: list[float]) -> dict:
    v = [x * 1000 for x in values_s]
    if not v:
        return {k: None for k in ("avg", "min", "p50", "p95", "p99", "max")}
    return {
        "avg": statistics.fmean(v),
        "min": min(v),
        "p50": pct(v, 50),
        "p95": pct(v, 95),
        "p99": pct(v, 99),
        "max": max(v),
    }


def fmt(x) -> str:
    return "-" if x is None else f"{x:.0f}"


# ------------------------------------------------------------ host sampler

def _read_cpu() -> tuple[int, int, int]:
    """(total, idle+iowait, steal) jiffies from the aggregate cpu line."""
    with open("/proc/stat") as f:
        parts = f.readline().split()[1:]
    vals = [int(x) for x in parts]
    total = sum(vals[:8])  # user..steal; guest is already in user
    idle = vals[3] + vals[4]
    steal = vals[7] if len(vals) > 7 else 0
    return total, idle, steal


def _hugepages_free() -> int:
    with open("/proc/meminfo") as f:
        for line in f:
            if line.startswith("HugePages_Free:"):
                return int(line.split()[1])
    return -1


class HostSampler:
    """Samples host CPU busy %, steal % and free hugepages every interval."""

    def __init__(self, interval: float = 0.1):
        self.interval = interval
        self.samples: list[dict] = []
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def _sample(self) -> None:
        cur = _read_cpu()
        dt = cur[0] - self._prev[0]
        if dt <= 0:
            return
        self.samples.append({
            "t": time.time(),
            "cpu_busy_pct": 100 * (dt - (cur[1] - self._prev[1])) / dt,
            "steal_pct": 100 * (cur[2] - self._prev[2]) / dt,
            "hugepages_free": _hugepages_free(),
        })
        self._prev = cur

    def _run(self):
        while not self._stop.wait(self.interval):
            self._sample()

    def __enter__(self):
        self._prev = _read_cpu()
        self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._t.join()
        self._sample()  # cover the tail of the window, so sub-interval operations still get a reading

    def summary(self) -> dict:
        if not self.samples:
            return {"cpu_busy_peak_pct": None, "steal_peak_pct": None, "hugepages_used_peak_mib": None}
        hp_total = int(sh("awk '/HugePages_Total/{print $2}' /proc/meminfo") or 0)
        return {
            "cpu_busy_peak_pct": max(s["cpu_busy_pct"] for s in self.samples),
            "steal_peak_pct": max(s["steal_pct"] for s in self.samples),
            "hugepages_used_peak_mib": (hp_total - min(s["hugepages_free"] for s in self.samples)) * 2,
        }


def host_peaks(samplers: list, prefix: str = "") -> dict:
    """Peak host CPU busy % and steal % over several measured windows (only the measured operations)."""
    samples = [x for h in samplers for x in h.samples]
    if not samples:
        return {f"{prefix}cpu_busy_peak_pct": None, f"{prefix}steal_peak_pct": None}
    return {f"{prefix}cpu_busy_peak_pct": max(x["cpu_busy_pct"] for x in samples),
            f"{prefix}steal_peak_pct": max(x["steal_pct"] for x in samples)}


def orchestrator_rejections(since: datetime) -> int:
    """Start-limit rejections (ResourceExhausted) the orchestrator logged since `since`."""
    out = sh(
        f"docker compose logs --since {since.strftime('%Y-%m-%dT%H:%M:%SZ')} orchestrator 2>/dev/null"
        " | grep -c ResourceExhausted",
        cwd=COMPOSE_DIR,
    )
    try:
        return int(out.splitlines()[-1])
    except (ValueError, IndexError):
        return -1


def running_sandboxes() -> int:
    from e2b import Sandbox
    return len(Sandbox.list().next_items())


def wait_idle(timeout: float = 120) -> None:
    """Wait until no sandbox runs and the hugepage pool is back to full."""
    hp_total = int(sh("awk '/HugePages_Total/{print $2}' /proc/meminfo") or 0)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if running_sandboxes() == 0 and _hugepages_free() >= hp_total:
            return
        time.sleep(1)
    print("  warning: host not idle after cleanup timeout", file=sys.stderr)


# --------------------------------------------------------------------- env

def write_env(run_dir: Path) -> None:
    import importlib.metadata as md

    def grab(cmd):
        return sh(cmd)

    env_pins = sh(
        "grep -E '^(E2B_API_IMAGE|E2B_ORCHESTRATOR_VERSION|E2B_ENVD_VERSION|E2B_KERNEL_VERSION|"
        "E2B_FIRECRACKER_VERSION|HUGEPAGES|NBDS_MAX)=' .env | sed 's/ #.*//'",
        cwd=COMPOSE_DIR,
    )
    text = f"""# Test environment

Recorded: {now_utc().isoformat(timespec='seconds')}

## Host
- OS: {grab("grep PRETTY_NAME /etc/os-release | cut -d= -f2 | tr -d '\"'")}
- Kernel: {platform.release()}
- Virtualization: {grab("systemd-detect-virt")} guest (DigitalOcean droplet); sandboxes run nested
- CPU: {grab("lscpu | sed -n 's/^Model name: *//p'")}, {grab("nproc")} vCPUs, {grab("lscpu | sed -n 's/^Thread(s) per core: *//p'")} thread(s)/core
- Memory: {grab("free -g | awk '/Mem:/{print $2}'")} GiB total; hugepages {grab("awk '/HugePages_Total/{print $2}' /proc/meminfo")} x 2 MiB
- Storage: templates/snapshots on {grab("findmnt -n -o SOURCE /var/lib/e2b")} ({grab("lsblk -dn -o SIZE /dev/sda")}, DigitalOcean block volume); root {grab("lsblk -dn -o SIZE /dev/vda")}
- Nodes: 1 (E2B Embed, docker compose)

## E2B stack
```
{env_pins}
```
- Python SDK: e2b {md.version('e2b')}
- Client: same host, direct to api :3000 / client-proxy :3002 (no nginx, no WAN)
"""
    (run_dir / "env.md").write_text(text)


def cmd_env(args) -> None:
    d = new_run_dir("env")
    write_env(d)
    print((d / "env.md").read_text())
    print(f"written to {d}")


# ------------------------------------------------------------------ create

def _create_one(template: str, barrier: threading.Barrier, cmd: str) -> dict:
    from e2b import Sandbox
    barrier.wait()
    rec: dict = {"t0": time.time()}
    p0 = time.perf_counter()
    try:
        sbx = Sandbox.create(template, timeout=600)
        p1 = time.perf_counter()
        sbx.commands.run(cmd)
        p2 = time.perf_counter()
        rec.update(ok=True, sandbox_id=sbx.sandbox_id, api_s=p1 - p0, ready_s=p2 - p0, sbx=sbx)
    except Exception as e:  # noqa: BLE001 - every failure is a data point
        rec.update(ok=False, error=f"{type(e).__name__}: {str(e)[:200]}", ready_s=time.perf_counter() - p0)
    rec["t_end"] = time.time()
    return rec


def _kill_all(sbxs) -> None:
    def k(s):
        try:
            s.kill()
        except Exception:  # noqa: BLE001
            pass
    with ThreadPoolExecutor(32) as ex:
        list(ex.map(k, sbxs))


def _kill_stragglers() -> None:
    """Kill anything still listed, e.g. a sandbox whose create succeeded server-side but timed out client-side."""
    from e2b import Sandbox
    for info in Sandbox.list().next_items():
        try:
            Sandbox.kill(info.sandbox_id)
        except Exception:  # noqa: BLE001
            pass


def cmd_create(args, test_name: str = "create", title: str = "3.2 Cold start and concurrency scaling") -> None:
    d = new_run_dir(test_name)
    write_env(d)
    levels = [int(x) for x in args.levels.split(",")]
    raw = open(d / "raw.jsonl", "w")
    summary = []
    print(f"template={args.template} levels={levels} rounds={args.rounds} -> {d}")

    if running_sandboxes():
        sys.exit("refusing to start: sandboxes are already running on this node")

    for c in levels:
        api_s, ready_s, walls, errors = [], [], [], []
        since = now_utc()
        with HostSampler() as hs:
            for r in range(args.rounds):
                barrier = threading.Barrier(c)
                with ThreadPoolExecutor(c) as ex:
                    recs = list(ex.map(lambda _: _create_one(args.template, barrier, args.cmd), range(c)))
                ok = [x for x in recs if x["ok"]]
                walls.append(max(x["t_end"] for x in recs) - min(x["t0"] for x in recs))
                sbxs = [x.pop("sbx") for x in recs if "sbx" in x]
                for x in recs:
                    raw.write(json.dumps({"test": test_name, "template": args.template, "concurrency": c,
                                          "round": r, **x}) + "\n")
                    if x["ok"]:
                        api_s.append(x["api_s"])
                        ready_s.append(x["ready_s"])
                    else:
                        errors.append(x["error"])
                raw.flush()
                _kill_all(sbxs)
                _kill_stragglers()
                print(f"  c={c:>3} round {r + 1}/{args.rounds}: ok {len(ok)}/{c}, wall {walls[-1]*1000:.0f} ms")
                wait_idle()
        host = hs.summary()
        n_total = c * args.rounds
        row = {
            "concurrency": c,
            "success": len(ready_s),
            "total": n_total,
            "ready_ms": stats_ms(ready_s),
            "api_ms": stats_ms(api_s),
            "wall_avg_ms": statistics.fmean(walls) * 1000,
            "throughput_per_s": (len(ready_s) / args.rounds) / statistics.fmean(walls),
            "start_limit_rejections": orchestrator_rejections(since),
            "errors": sorted(set(errors))[:5],
            **host,
        }
        summary.append(row)
    raw.close()

    (d / "summary.json").write_text(json.dumps({"template": args.template, "rounds": args.rounds,
                                                  "cmd": args.cmd, "levels": summary}, indent=2))
    lines = [
        f"# {title}",
        "",
        f"Template `{getattr(args, 'template_label', args.template)}` (`{args.template}`), {args.rounds} rounds per level, all requests of a round fired at once.",
        f"`ready` = create request sent -> first command (`{args.cmd}`) finished; `api` = create call returned.",
        "",
        "| Concurrency | Success | Ready avg | Ready min | Ready p50 | Ready p95 | Ready p99 | Ready max "
        "| API p50 | API p95 | Wall avg | Throughput (/s) | Start-limit rejections | Host CPU peak | Steal peak "
        "| Hugepages peak (MiB) |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in summary:
        rd, ap = r["ready_ms"], r["api_ms"]
        lines.append(
            f"| {r['concurrency']} | {r['success']}/{r['total']} | {fmt(rd['avg'])} | {fmt(rd['min'])} | "
            f"{fmt(rd['p50'])} | {fmt(rd['p95'])} | {fmt(rd['p99'])} | {fmt(rd['max'])} | {fmt(ap['p50'])} | "
            f"{fmt(ap['p95'])} | {r['wall_avg_ms']:.0f} | {r['throughput_per_s']:.1f} | "
            f"{r['start_limit_rejections']} | {fmt(r['cpu_busy_peak_pct'])}% | {fmt(r['steal_peak_pct'])}% | "
            f"{fmt(r['hugepages_used_peak_mib'])} |"
        )
    errs = [e for r in summary for e in r["errors"]]
    if errs:
        lines += ["", "Errors (distinct, first few):", *[f"- `{e}`" for e in sorted(set(errs))[:10]]]
    lines += ["", "Latencies in ms."]
    (d / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


# ---------------------------------------------------- shared for 3.3 / 4.x

def _connect_env():
    """Fail early when the node is busy, so no test measures someone else's load."""
    if running_sandboxes():
        sys.exit("refusing to start: sandboxes are already running on this node")


def _spawn(template: str, n: int, cmd: str = "true") -> list:
    """Create n sandboxes (all at once) and return the Sandbox objects; raises if any failed."""
    barrier = threading.Barrier(n)
    with ThreadPoolExecutor(n) as ex:
        recs = list(ex.map(lambda _: _create_one(template, barrier, cmd), range(n)))
    bad = [r["error"] for r in recs if not r["ok"]]
    sbxs = [r["sbx"] for r in recs if r["ok"]]
    if bad:
        _kill_all(sbxs)
        raise RuntimeError(f"{len(bad)}/{n} setup creates failed: {bad[0]}")
    return sbxs


def _timed_concurrent(items: list, op) -> tuple[list[dict], float]:
    """Run op(item) for all items at once; per-op latency (s) and the round's wall time (s)."""
    barrier = threading.Barrier(len(items))

    def one(item):
        barrier.wait()
        p0 = time.perf_counter()
        t0 = time.time()
        try:
            res = op(item)
            return {"ok": True, "lat_s": time.perf_counter() - p0, "t0": t0, "t_end": time.time(), "res": res}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "lat_s": time.perf_counter() - p0, "t0": t0, "t_end": time.time(),
                    "error": f"{type(e).__name__}: {str(e)[:200]}"}

    with ThreadPoolExecutor(len(items)) as ex:
        recs = list(ex.map(one, items))
    return recs, max(r["t_end"] for r in recs) - min(r["t0"] for r in recs)


def _delete_snapshots(ids) -> None:
    from e2b import Sandbox
    for sid in ids:
        try:
            Sandbox.delete_snapshot(sid)
        except Exception as e:  # noqa: BLE001
            print(f"  warning: could not delete snapshot {sid}: {e}", file=sys.stderr)


def _all_snapshot_ids() -> list[str]:
    from e2b import Sandbox
    return [s.snapshot_id for s in Sandbox.list_snapshots().next_items()]



def _write_table(d: Path, title: str, intro: list[str], header: list[str], rows: list[list], data: dict) -> None:
    (d / "summary.json").write_text(json.dumps(data, indent=2))
    lines = [f"# {title}", "", *intro, "",
             "| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    errs = sorted({e for r in data.get("rows", []) for e in r.get("errors", [])})
    if errs:
        lines += ["", "Errors (distinct, first few):", *[f"- `{e}`" for e in errs[:10]]]
    lines += ["", "Latencies in ms."]
    (d / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def _mem_used_non_huge_mib() -> float:
    """Host memory in use outside the hugepage pool (MiB)."""
    m = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, v = line.split(":", 1)
            m[k] = int(v.split()[0])
    used_kib = (m["MemTotal"] - m["MemFree"] - m["Buffers"] - m["Cached"] - m["SReclaimable"]
                - m["HugePages_Total"] * m["Hugepagesize"])
    return used_kib / 1024


def _cpu_busy_over(seconds: float) -> float:
    a = _read_cpu()
    time.sleep(seconds)
    b = _read_cpu()
    dt = b[0] - a[0] or 1
    return 100 * (dt - (b[1] - a[1])) / dt


# ------------------------------------------------------------- 3.3 density

def cmd_density(args) -> None:
    from e2b import Sandbox
    _connect_env()
    d = new_run_dir("density")
    write_env(d)
    raw = open(d / "raw.jsonl", "w")
    hp_total = int(sh("awk '/HugePages_Total/{print $2}' /proc/meminfo"))
    time.sleep(args.settle)
    base_hp = (hp_total - _hugepages_free()) * 2
    base_mem = _mem_used_non_huge_mib()
    base_cpu = _cpu_busy_over(5)
    rows, live = [], []
    print(f"template={args.template} step={args.step} max={args.max} -> {d}")
    try:
        while len(live) < args.max:
            n = min(args.step, args.max - len(live))
            live += _spawn(args.template, n)
            time.sleep(args.settle)  # let fresh guests finish faulting memory in
            hp_used = (hp_total - _hugepages_free()) * 2 - base_hp
            mem_used = _mem_used_non_huge_mib() - base_mem
            cpu = _cpu_busy_over(5)
            fc_rss = sh("ps -C firecracker -o rss= | awk '{s+=$1} END {print s/1024}'")
            row = {"live": len(live), "hugepages_used_mib": hp_used, "other_mem_used_mib": mem_used,
                   "per_vm_hugepages_mib": hp_used / len(live), "per_vm_other_mib": mem_used / len(live),
                   "firecracker_rss_total_mib": float(fc_rss or 0), "idle_cpu_busy_pct": cpu,
                   "idle_cpu_delta_pct": cpu - base_cpu}
            raw.write(json.dumps(row) + "\n")
            raw.flush()
            rows.append(row)
            print(f"  live={len(live):>3} hugepages {hp_used:.0f} MiB, other {mem_used:.0f} MiB, idle cpu {cpu:.1f}%")
    finally:
        _kill_all(live)
        _kill_stragglers()
        raw.close()
    table = [[r["live"], f"{r['hugepages_used_mib']:.0f}", f"{r['per_vm_hugepages_mib']:.1f}",
              f"{r['other_mem_used_mib']:.0f}", f"{r['per_vm_other_mib']:.1f}",
              f"{r['firecracker_rss_total_mib']:.0f}", f"{r['idle_cpu_busy_pct']:.1f}%"] for r in rows]
    _write_table(
        d, "3.3 Single-host density (idle sandboxes)",
        [f"Template `{args.template}`; {args.step} sandboxes added per step, measured after {args.settle:.0f} s settle.",
         f"Baseline before any sandbox: hugepages used {base_hp:.0f} MiB, other memory used {base_mem:.0f} MiB, "
         f"host CPU busy {base_cpu:.1f}%.",
         "Guest memory comes from the hugepage pool; `other` is host memory outside it "
         "(Firecracker processes, orchestrator, kernel); page cache and reclaimable slab are excluded."],
        ["Live sandboxes", "Hugepages used (MiB)", "Hugepages per VM (MiB)", "Other mem used (MiB)",
         "Other per VM (MiB)", "Firecracker RSS total (MiB)", "Host CPU busy (idle sandboxes)"],
        table, {"template": args.template, "baseline": {"hugepages_mib": base_hp, "other_mib": base_mem,
                                                        "cpu_busy_pct": base_cpu}, "rows": rows})


# -------------------------------------------- 4.1 snapshot vs concurrency

def cmd_snapshot(args) -> None:
    _connect_env()
    d = new_run_dir("snapshot")
    write_env(d)
    raw = open(d / "raw.jsonl", "w")
    levels = [int(x) for x in args.levels.split(",")]
    rows = []
    print(f"template={args.template} levels={levels} rounds={args.rounds} -> {d}")
    for c in levels:
        lats, walls, errors, hs_all = [], [], [], []
        for r in range(args.rounds):
            sbxs = _spawn(args.template, c)
            with HostSampler() as hs:
                recs, wall = _timed_concurrent(sbxs, lambda s: s.create_snapshot().snapshot_id)
            hs_all.append(hs)
            walls.append(wall)
            for x in recs:
                raw.write(json.dumps({"concurrency": c, "round": r, **x}) + "\n")
                (lats if x["ok"] else errors).append(x["lat_s"] if x["ok"] else x["error"])
            _delete_snapshots([x["res"] for x in recs if x["ok"]])
            _kill_all(sbxs)
            _kill_stragglers()
            print(f"  c={c:>2} round {r + 1}/{args.rounds}: wall {wall * 1000:.0f} ms")
            wait_idle()
        rows.append({"concurrency": c, "success": len(lats), "total": c * args.rounds,
                     "wall_ms": stats_ms(walls), "lat_ms": stats_ms(lats),
                     "per_snapshot_avg_ms": statistics.fmean(walls) * 1000 / c, "errors": sorted(set(errors))[:5],
                     **host_peaks(hs_all)})
    raw.close()
    table = [[r["concurrency"], f"{r['success']}/{r['total']}", fmt(r["wall_ms"]["avg"]), fmt(r["wall_ms"]["min"]),
              fmt(r["wall_ms"]["p95"]), fmt(r["wall_ms"]["max"]), fmt(r["lat_ms"]["p50"]), fmt(r["lat_ms"]["p95"]),
              f"{r['per_snapshot_avg_ms']:.1f}"] for r in rows]
    _write_table(d, "4.1 Snapshot creation vs concurrency",
                 [f"Template `{args.template}`; c running sandboxes snapshotted at once, {args.rounds} rounds.",
                  "Each snapshot is deleted after the round."],
                 ["Concurrency", "Success", "Wall avg", "Wall min", "Wall p95", "Wall max", "Per-op p50",
                  "Per-op p95", "Per-snapshot avg (wall/c)"], table,
                 {"template": args.template, "rows": rows})


# ------------------------------------------ 4.2 snapshot vs dirty memory

FILL_CMD = ("nohup python3 -c \"import os,time; b=os.urandom({n}*1048576); "
            "open('/tmp/.fill_ready','w').close(); time.sleep(10**6)\" >/dev/null 2>&1 &")


def cmd_snapshot_dirty(args) -> None:
    from e2b import Sandbox
    _connect_env()
    d = new_run_dir("snapshot-dirty")
    write_env(d)
    raw = open(d / "raw.jsonl", "w")
    sizes = [int(x) for x in args.sizes.split(",")]
    rows = []
    print(f"template={args.template} sizes={sizes} MiB rounds={args.rounds} -> {d}")
    for mib in sizes:
        snap_lats, create_lats, errors, hs_snap, hs_create = [], [], [], [], []
        for r in range(args.rounds):
            (s,) = _spawn(args.template, 1)
            snap_id = None
            try:
                if mib:
                    s.commands.run(FILL_CMD.format(n=mib))
                    s.commands.run("for i in $(seq 600); do [ -f /tmp/.fill_ready ] && exit 0; sleep 0.1; done; exit 1",
                                   timeout=120)
                with HostSampler() as hs1:
                    p0 = time.perf_counter()
                    snap_id = s.create_snapshot().snapshot_id
                    snap_lat = time.perf_counter() - p0
                with HostSampler() as hs2:
                    p1 = time.perf_counter()
                    s2 = Sandbox.create(snap_id, timeout=300)
                    s2.commands.run("true")
                    create_lat = time.perf_counter() - p1
                hs_snap.append(hs1)
                hs_create.append(hs2)
                s2.kill()
                snap_lats.append(snap_lat)
                create_lats.append(create_lat)
                raw.write(json.dumps({"dirty_mib": mib, "round": r, "snapshot_s": snap_lat,
                                      "create_from_snapshot_s": create_lat}) + "\n")
                print(f"  {mib:>5} MiB round {r + 1}: snapshot {snap_lat * 1000:.0f} ms, "
                      f"create-from-snapshot {create_lat * 1000:.0f} ms")
            except Exception as e:  # noqa: BLE001
                errors.append(f"{type(e).__name__}: {str(e)[:200]}")
                print(f"  {mib:>5} MiB round {r + 1}: FAIL {errors[-1]}")
            finally:
                if snap_id:
                    _delete_snapshots([snap_id])
                _kill_all([s])
                _kill_stragglers()
                wait_idle()
            raw.flush()
        rows.append({"dirty_mib": mib, "success": len(snap_lats), "total": args.rounds,
                     "snapshot_ms": stats_ms(snap_lats), "create_ms": stats_ms(create_lats),
                     "errors": sorted(set(errors))[:5],
                     **host_peaks(hs_snap, "snapshot_"), **host_peaks(hs_create, "create_")})
    raw.close()
    table = [[r["dirty_mib"], f"{r['success']}/{r['total']}",
              *[fmt(r["snapshot_ms"][k]) for k in ("avg", "min", "p95", "max")],
              *[fmt(r["create_ms"][k]) for k in ("avg", "min", "p95", "max")]] for r in rows]
    _write_table(d, "4.2 Snapshot creation vs dirty memory",
                 [f"Template `{args.template}`; a guest process holds N MiB of random bytes (dirty, non-zero pages) "
                  f"when the snapshot is taken; {args.rounds} rounds per size.",
                  "`create from snapshot` = create request -> first command finished in a sandbox started from it."],
                 ["Dirty MiB", "Success", "Snapshot avg", "Snapshot min", "Snapshot p95", "Snapshot max",
                  "Create-from-snapshot avg", "min", "p95", "max"], table,
                 {"template": args.template, "rows": rows})


# ------------------------------------------- 4.3 create from snapshot

def cmd_from_snapshot(args) -> None:
    _connect_env()
    (s,) = _spawn(args.template, 1)
    snap_id = s.create_snapshot().snapshot_id
    _kill_all([s])
    wait_idle()
    print(f"snapshot {snap_id} of {args.template}")
    try:
        args.template_label = f"snapshot of {args.template}"
        args.template = snap_id
        cmd_create(args, test_name="from-snapshot", title="4.3 Create sandbox from snapshot")
    finally:
        _delete_snapshots([snap_id])


# ------------------------------------------------------------- 4.5 fork

def cmd_fork(args) -> None:
    from e2b import Sandbox
    _connect_env()
    d = new_run_dir("fork")
    write_env(d)
    raw = open(d / "raw.jsonl", "w")
    counts = [int(x) for x in args.counts.split(",")]
    before = set(_all_snapshot_ids())
    rows = []
    print(f"template={args.template} counts={counts} rounds={args.rounds} -> {d}")
    for n in counts:
        call_lats, ready_lats, errors, ok_n, hs_all = [], [], [], 0, []
        for r in range(args.rounds):
            (src,) = _spawn(args.template, 1)
            forks = []
            try:
                hs = HostSampler().__enter__()
                hs_all.append(hs)
                p0 = time.perf_counter()
                res = src.fork(count=n)
                call_lat = time.perf_counter() - p0
                forks = [f for f in res if isinstance(f, Sandbox)]
                errs = [f"{type(f).__name__}: {str(f)[:200]}" for f in res if not isinstance(f, Sandbox)]
                recs, _ = _timed_concurrent(forks, lambda f: f.commands.run("true").exit_code) if forks else ([], 0)
                ready_lat = time.perf_counter() - p0
                hs.__exit__(None, None, None)
                ok_n += sum(1 for x in recs if x["ok"])
                errors += errs + [x["error"] for x in recs if not x["ok"]]
                call_lats.append(call_lat)
                ready_lats.append(ready_lat)
                raw.write(json.dumps({"count": n, "round": r, "fork_call_s": call_lat, "all_ready_s": ready_lat,
                                      "forks_ok": sum(1 for x in recs if x["ok"])}) + "\n")
                print(f"  n={n:>3} round {r + 1}: fork call {call_lat * 1000:.0f} ms, "
                      f"all {len(forks)} ready {ready_lat * 1000:.0f} ms")
            except Exception as e:  # noqa: BLE001
                errors.append(f"{type(e).__name__}: {str(e)[:200]}")
                print(f"  n={n:>3} round {r + 1}: FAIL {errors[-1]}")
            finally:
                if hs._t.is_alive():
                    hs.__exit__(None, None, None)
                _kill_all(forks + [src])
                _kill_stragglers()
                _delete_snapshots(set(_all_snapshot_ids()) - before)
                wait_idle()
            raw.flush()
        rows.append({"count": n, "success": ok_n, "total": n * args.rounds, "call_ms": stats_ms(call_lats),
                     "ready_ms": stats_ms(ready_lats),
                     "per_fork_avg_ms": statistics.fmean(ready_lats) * 1000 / n if ready_lats else None,
                     "errors": sorted(set(errors))[:5], **host_peaks(hs_all)})
    raw.close()
    table = [[r["count"], f"{r['success']}/{r['total']}", *[fmt(r["call_ms"][k]) for k in ("avg", "min", "max")],
              *[fmt(r["ready_ms"][k]) for k in ("avg", "min", "max")], fmt(r["per_fork_avg_ms"])] for r in rows]
    _write_table(d, "4.5 Clone (fork)",
                 [f"Template `{args.template}`; one running sandbox forked into n children, {args.rounds} rounds.",
                  "`fork call` = fork request until the SDK returned the children; "
                  "`all ready` = until every child finished a first command."],
                 ["n", "Success", "Fork call avg", "min", "max", "All ready avg", "min", "max",
                  "Per-fork avg (all ready / n)"], table, {"template": args.template, "rows": rows})


# ---------------------------------------------------- 4.6 pause / resume

def cmd_pause(args) -> None:
    from e2b import Sandbox
    _connect_env()
    d = new_run_dir("pause")
    write_env(d)
    raw = open(d / "raw.jsonl", "w")
    levels = [int(x) for x in args.levels.split(",")]
    rows = []
    print(f"template={args.template} levels={levels} rounds={args.rounds} -> {d}")
    for c in levels:
        p_lats, r_lats, p_walls, r_walls, errors, hs_p, hs_r = [], [], [], [], [], [], []
        for r in range(args.rounds):
            sbxs = _spawn(args.template, c)
            ids = [s.sandbox_id for s in sbxs]
            try:
                with HostSampler() as hs1:
                    precs, pwall = _timed_concurrent(sbxs, lambda s: s.pause())
                with HostSampler() as hs2:
                    rrecs, rwall = _timed_concurrent(
                        ids, lambda i: Sandbox.connect(i, timeout=600).commands.run("true").exit_code)
                hs_p.append(hs1)
                hs_r.append(hs2)
                p_walls.append(pwall)
                r_walls.append(rwall)
                for kind, recs, lats in (("pause", precs, p_lats), ("resume", rrecs, r_lats)):
                    for x in recs:
                        raw.write(json.dumps({"op": kind, "concurrency": c, "round": r,
                                              **{k: v for k, v in x.items() if k != "res"}}) + "\n")
                        (lats if x["ok"] else errors).append(x["lat_s"] if x["ok"] else f"{kind}: {x['error']}")
                print(f"  c={c:>2} round {r + 1}: pause wall {pwall * 1000:.0f} ms, resume wall {rwall * 1000:.0f} ms")
            finally:
                for i in ids:
                    try:
                        Sandbox.kill(i)
                    except Exception:  # noqa: BLE001
                        pass
                _kill_stragglers()
                wait_idle()
            raw.flush()
        rows.append({"concurrency": c, "pause_ok": len(p_lats), "resume_ok": len(r_lats), "total": c * args.rounds,
                     "pause_wall_ms": stats_ms(p_walls), "resume_wall_ms": stats_ms(r_walls),
                     "pause_ms": stats_ms(p_lats), "resume_ms": stats_ms(r_lats),
                     "errors": sorted(set(errors))[:5], **host_peaks(hs_p, "pause_"), **host_peaks(hs_r, "resume_")})
    raw.close()
    table = [[r["concurrency"], f"{r['pause_ok']}/{r['total']}", f"{r['resume_ok']}/{r['total']}",
              *[fmt(r["pause_wall_ms"][k]) for k in ("avg", "min", "p95", "max")],
              f"{r['pause_wall_ms']['avg'] / r['concurrency']:.1f}",
              *[fmt(r["resume_wall_ms"][k]) for k in ("avg", "min", "p95", "max")],
              f"{r['resume_wall_ms']['avg'] / r['concurrency']:.1f}"] for r in rows]
    _write_table(d, "4.6 Pause / resume",
                 [f"Template `{args.template}`; c sandboxes paused at once, then resumed at once, {args.rounds} rounds.",
                  "Pause keeps memory (full snapshot). Resume = connect -> first command finished."],
                 ["Concurrency", "Pause ok", "Resume ok", "Pause wall avg", "min", "p95", "max", "Per-pause avg",
                  "Resume wall avg", "min", "p95", "max", "Per-resume avg"], table,
                 {"template": args.template, "rows": rows})


# -------------------------------------------------------------------- main

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="test", required=True)

    sub.add_parser("env", help="record the test environment").set_defaults(fn=cmd_env)

    c = sub.add_parser("create", help="3.2 cold start and concurrency scaling")
    c.add_argument("--template", required=True, help="template ID or alias")
    c.add_argument("--levels", default="1,10,20,50,100,200", help="comma-separated concurrency levels")
    c.add_argument("--rounds", type=int, default=3, help="rounds per concurrency level")
    c.add_argument("--cmd", default="true", help="first command run in each sandbox")
    c.set_defaults(fn=cmd_create)

    t = sub.add_parser("density", help="3.3 single-host density")
    t.add_argument("--template", required=True)
    t.add_argument("--step", type=int, default=25, help="sandboxes added per step")
    t.add_argument("--max", type=int, default=200, help="stop at this many live sandboxes")
    t.add_argument("--settle", type=float, default=15, help="seconds to wait after each step")
    t.set_defaults(fn=cmd_density)

    t = sub.add_parser("snapshot", help="4.1 snapshot creation vs concurrency")
    t.add_argument("--template", required=True)
    t.add_argument("--levels", default="1,5,10")
    t.add_argument("--rounds", type=int, default=5)
    t.set_defaults(fn=cmd_snapshot)

    t = sub.add_parser("snapshot-dirty", help="4.2 snapshot creation vs dirty memory")
    t.add_argument("--template", required=True)
    t.add_argument("--sizes", default="0,64,128,256,512,1024", help="MiB of dirty memory")
    t.add_argument("--rounds", type=int, default=3)
    t.set_defaults(fn=cmd_snapshot_dirty)

    t = sub.add_parser("from-snapshot", help="4.3 create sandbox from snapshot")
    t.add_argument("--template", required=True, help="template the snapshot is taken from")
    t.add_argument("--levels", default="1,10,20,50")
    t.add_argument("--rounds", type=int, default=3)
    t.add_argument("--cmd", default="true")
    t.set_defaults(fn=cmd_from_snapshot)

    t = sub.add_parser("fork", help="4.5 clone (fork)")
    t.add_argument("--template", required=True)
    t.add_argument("--counts", default="1,10,50,100", help="children per fork call")
    t.add_argument("--rounds", type=int, default=3)
    t.set_defaults(fn=cmd_fork)

    t = sub.add_parser("pause", help="4.6 pause / resume")
    t.add_argument("--template", required=True)
    t.add_argument("--levels", default="1,5,10")
    t.add_argument("--rounds", type=int, default=5)
    t.set_defaults(fn=cmd_pause)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
