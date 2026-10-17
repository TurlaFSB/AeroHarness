#!/usr/bin/env python3
"""Unsigned-wrap probe for the Work Plan item 2 PL011 harnesses.

Why: the pl011_set_baudrate defect is `baudrate * 16U` wrapping in 32 bits. A plain
fuzz run only notices it when the wrap happens to produce a zero divisor (a few values in
2**32), so a 100,000-run stability gate can miss it. Clang's
`-fsanitize=unsigned-integer-overflow` reports the *wrap itself*, which happens for
15/16 of random 32-bit values, i.e. on the first executions.

This script rebuilds each SUCCESS harness with that check (report-and-continue), runs a
short fixed-seed campaign, and lists the reports whose source location is in the code
under test, using the same location classifier as the self-repair loop's crash triage.
Unsigned wrap is defined behaviour in C and is sometimes intended (hashes, counters), so
each report is a *candidate* to review, not a defect. Measuring how many reports each
target produces is the point of running this before turning it into a gate.

Makes NO API calls. Needs clang++ and FuzzedDataProvider.h (ships with clang).

Usage:
    python3 ubsan_wrap_probe.py --out-root <run folder> [--runs 20000] [--seed 1]
        [--only TARGET] [--item2-dir DIR]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
from src.oracle.crash_triage import parse_ubsan_reports, target_side_ubsan  # noqa: E402


def probe(target, item2_dir, out_root, runs, seed):
    tdir = out_root / target
    harness = tdir / f"fuzz_{target}.cpp"
    cfile = item2_dir / f"{target}.c"
    hfile = item2_dir / f"{target}.h"
    if not harness.exists() or not cfile.exists():
        return {"target": target, "error": "harness or driver .c missing"}
    binp = tdir / "wrap_bin"
    inc = ["-I" + str(item2_dir), "-I" + str(REPO), "-I" + str(REPO / "fake_zephyr"),
           "-I" + str(REPO / "zephyr-src" / "drivers" / "serial")]
    cmd = (["clang++", "-fsanitize=fuzzer,address,undefined,unsigned-integer-overflow",
            "-fno-sanitize-recover=address", "-O1", "-g", "-w"] + inc
           + [harness.name, str(cfile), "-o", "wrap_bin"])
    cb = subprocess.run(cmd, cwd=tdir, capture_output=True, text=True)
    if cb.returncode != 0:
        return {"target": target, "error": "build failed", "stderr": cb.stderr[-800:]}
    try:
        fr = subprocess.run(["./wrap_bin", f"-runs={runs}", f"-seed={seed}", "-timeout=5",
                             "-max_len=512", "-print_final_stats=0"],
                            cwd=tdir, capture_output=True, text=True, timeout=180)
        err, rc = fr.stderr, fr.returncode
    except subprocess.TimeoutExpired as e:
        err, rc = (e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr) or "", None
    tps = [cfile, hfile]
    reps = target_side_ubsan(err, tps)
    allr = parse_ubsan_reports(err)
    try:
        binp.unlink()
    except OSError:
        pass
    return {"target": target, "exit_code": rc,
            "target_side": [f"{Path(r.file).name}:{r.line}:{r.col} {r.message}" for r in reps],
            "all_report_count": len(allr)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--item2-dir", default=str(REPO / "targets" / "uart_pl011_item2"))
    ap.add_argument("--out-root", required=True)
    ap.add_argument("--runs", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--only")
    a = ap.parse_args()
    if not shutil.which("clang++"):
        sys.exit("clang++ not found on PATH")
    item2, out_root = Path(a.item2_dir), Path(a.out_root).resolve()
    rec = json.load(open(out_root / "item2_report.json"))
    targets = [r["target"] for r in rec if r.get("status") == "SUCCESS"]
    if a.only:
        targets = [a.only]
    print(f"run folder: {out_root}\nruns={a.runs} seed={a.seed} targets={len(targets)}\n")
    results = [probe(t, item2, out_root, a.runs, a.seed) for t in targets]
    for r in results:
        if "error" in r:
            print(f"  {r['target']:30s} ERROR {r['error']} {r.get('stderr','')}")
            continue
        print(f"  {r['target']:30s} target-side reports: {len(r['target_side'])}  "
              f"(all reports: {r['all_report_count']}, exit {r['exit_code']})")
        for line in r["target_side"]:
            print(f"      {line}")
    c = Counter(len(r.get("target_side", [])) > 0 for r in results if "error" not in r)
    print(f"\ntargets with >=1 target-side report: {c[True]} of {c[True] + c[False]}")


if __name__ == "__main__":
    main()
