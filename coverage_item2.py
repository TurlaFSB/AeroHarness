#!/usr/bin/env python3
"""llvm-cov line/region/branch coverage for the Work Plan item 2 PL011 harnesses.

The item 2 self-repair run reported 18/18 harnesses reaching compile+link+smoke
SUCCESS, but line coverage of the real driver functions they exercise was never
measured. This script closes that gap: for each SUCCESS target it rebuilds the
harness with coverage instrumentation, runs libFuzzer briefly to generate a
profile, and reports the real target function's coverage with llvm-cov.

It builds the SAME two translation units the self-repair orchestrator does — the
LLM-authored `fuzz_<t>.cpp` harness plus the verbatim real-driver `<t>.c` (which
carries the target function with external linkage and the one `mock_regs_ptr`
definition) — adding only the coverage flags.

Layout assumed (relative to --item2-dir, default: this script's
targets/uart_pl011_item2):
    <item2-dir>/<t>.c, <t>.h, common_stubs.h
    <out-root>/<t>/fuzz_<t>.cpp
    <out-root>/item2_report.json   (the run's report; --report to override)

IMPORTANT: --out-root selects WHICH RUN is measured. The default,
<item2-dir>/output, is the older top-level run (Gemini-era, 15/18). The OpenRouter
DeepSeek runs write to <item2-dir>/output/openrouter_<model>_<provider>[_convnote]/.
The "18/18 with convention note" result in RESULTS.md is the *_convnote folder. The
script prints the run's backend/model/prompt variant so the measured run is explicit.

Include paths mirror the harness build: the item2 dir (headers + common_stubs),
the repo root, fake_zephyr (the mock <zephyr/*.h>), and zephyr-src/drivers/serial
(the real uart_pl011_registers.h). FuzzedDataProvider.h must be available in the
clang install (it ships with clang/compiler-rt) — it is on a normal WSL clang, but
not in every minimal container.

Makes NO API calls. Builds and runs locally only.

Usage:
    python3 coverage_item2.py [--only pl011_set_flow_control] [--runs 300000]
        [--item2-dir DIR] [--report FILE] [--keep]
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys


def repo_root():
    return os.path.abspath(os.path.dirname(os.path.abspath(__file__)))


def build_flags(item2_dir, repo):
    return [
        "-I" + item2_dir,
        "-I" + repo,
        "-I" + os.path.join(repo, "fake_zephyr"),
        "-I" + os.path.join(repo, "zephyr-src", "drivers", "serial"),
    ]


def measure(target, item2_dir, out_root, repo, runs, keep):
    tdir = os.path.join(out_root, target)
    harness = os.path.join(tdir, f"fuzz_{target}.cpp")
    cfile = os.path.join(item2_dir, f"{target}.c")
    if not os.path.exists(harness):
        return {"target": target, "error": f"harness missing: {harness}"}
    if not os.path.exists(cfile):
        return {"target": target, "error": f"driver .c missing: {cfile}"}

    binpath = os.path.join(tdir, "cov_bin")
    prof_raw = os.path.join(tdir, "cov.profraw")
    prof_data = os.path.join(tdir, "cov.profdata")
    cmd = (["clang++", "-fsanitize=fuzzer,address", "-fprofile-instr-generate",
            "-fcoverage-mapping", "-O1", "-fno-inline", "-g", "-w"]
           + build_flags(item2_dir, repo)
           + [os.path.basename(harness), cfile, "-o", "cov_bin"])
    cb = subprocess.run(cmd, cwd=tdir, capture_output=True, text=True)
    if cb.returncode != 0:
        return {"target": target, "error": "build failed",
                "stderr": cb.stderr.strip()[-1200:]}

    env = dict(os.environ, LLVM_PROFILE_FILE=prof_raw)
    corpus = os.path.join(tdir, "cov_corpus")
    art = os.path.join(tdir, "cov_artifacts")
    os.makedirs(corpus, exist_ok=True)
    os.makedirs(art, exist_ok=True)
    crash = None
    try:
        fr = subprocess.run(["./cov_bin", corpus, f"-runs={runs}", "-timeout=5",
                             "-max_len=512", "-print_final_stats=0",
                             f"-artifact_prefix={art}/"],
                            cwd=tdir, capture_output=True, text=True, timeout=180, env=env)
        if fr.returncode != 0 or "ERROR: " in (fr.stderr or ""):
            summ = [l for l in (fr.stderr or "").splitlines() if l.startswith("SUMMARY:")]
            crash = {"exit_code": fr.returncode,
                     "summary": (summ[0] if summ else (fr.stderr or "").strip()[-200:])}
    except subprocess.TimeoutExpired:
        pass  # a hang-prone target still leaves a profile from the runs it did
    if crash or not os.path.exists(prof_raw) or os.path.getsize(prof_raw) == 0:
        # The fuzz run aborted (sanitizer/signal), so the process never wrote its
        # profile and the file is missing or empty. Reporting that as "0% coverage"
        # would be wrong. Replay the corpus saved before the crash (no mutation,
        # crashing input excluded) to get a real profile of what ran, and flag it.
        if os.path.exists(prof_raw):
            os.remove(prof_raw)
        try:
            subprocess.run(["./cov_bin", corpus, "-runs=0", f"-artifact_prefix={art}/"],
                           cwd=tdir, capture_output=True, text=True, timeout=120, env=env)
        except subprocess.TimeoutExpired:
            pass
        if crash is None:
            crash = {"exit_code": None, "summary": "no profile written by the fuzz run"}
    if not os.path.exists(prof_raw) or os.path.getsize(prof_raw) == 0:
        return {"target": target, "error": "no profile produced even after corpus replay",
                "crash": crash}

    pm = subprocess.run(["llvm-profdata", "merge", "-sparse", prof_raw, "-o", prof_data],
                        cwd=tdir, capture_output=True, text=True)
    if pm.returncode != 0:
        return {"target": target, "error": "llvm-profdata merge failed", "stderr": pm.stderr.strip()[-600:]}

    # Per-function coverage report, restricted to the driver .c, as JSON.
    rep = subprocess.run(["llvm-cov", "export", "./cov_bin",
                          f"-instr-profile={prof_data}", cfile, "-summary-only"],
                         cwd=tdir, capture_output=True, text=True)
    out = {"target": target}
    if crash:
        out["crash"] = crash
        found = sorted(glob.glob(os.path.join(art, "crash-*")) + glob.glob(os.path.join(art, "timeout-*")))
        out["crash_inputs"] = found
    try:
        data = json.loads(rep.stdout)
        tot = data["data"][0]["totals"]
        for k in ("lines", "regions", "branches", "functions"):
            if k in tot:
                if tot[k]['count'] == 0:
                    out[k] = "0/0 (n/a)"  # e.g. no branches in straight-line code
                else:
                    out[k] = f"{tot[k]['covered']}/{tot[k]['count']} ({tot[k]['percent']:.1f}%)"
    except Exception:
        out["error"] = "llvm-cov export parse failed"
        out["stderr"] = (rep.stderr or rep.stdout).strip()[-600:]

    if not keep:
        for p in (binpath, prof_raw, prof_data):
            try:
                os.remove(p)
            except OSError:
                pass
        shutil.rmtree(corpus, ignore_errors=True)
        if not crash:
            shutil.rmtree(art, ignore_errors=True)  # keep crash inputs as evidence
    return out


def main():
    ap = argparse.ArgumentParser()
    repo = repo_root()
    ap.add_argument("--item2-dir", default=os.path.join(repo, "targets", "uart_pl011_item2"))
    ap.add_argument("--out-root", help="run folder holding <t>/fuzz_<t>.cpp and item2_report.json "
                    "(default: <item2-dir>/output, the OLD top-level run; for the DeepSeek 18/18 run pass "
                    "<item2-dir>/output/openrouter_..._convnote)")
    ap.add_argument("--report", help="item2_report.json (default: <out-root>/item2_report.json)")
    ap.add_argument("--only", help="measure just this one target (for a cheap smoke test)")
    ap.add_argument("--runs", type=int, default=300000, help="libFuzzer -runs per target")
    ap.add_argument("--keep", action="store_true", help="keep the cov binary/profile/corpus")
    a = ap.parse_args()

    for tool in ("clang++", "llvm-profdata", "llvm-cov"):
        if not shutil.which(tool):
            sys.exit(f"{tool} not found on PATH")

    out_root = os.path.abspath(a.out_root or os.path.join(a.item2_dir, "output"))
    report = a.report or os.path.join(out_root, "item2_report.json")
    if not os.path.exists(report):
        sys.exit(f"report not found: {report}\nPass --out-root <run folder> (e.g. targets/uart_pl011_item2/output/openrouter_..._convnote)")
    rec = json.load(open(report))
    ident = {(r.get("backend", "gemini/offline"), r.get("model"), r.get("provider_pinned"),
              r.get("prompt_variant")) for r in rec}
    print(f"run identity (backend, model, provider, prompt variant): {sorted(ident, key=str)}")
    from collections import Counter
    print(f"report statuses: {dict(Counter(r.get('status') for r in rec))}")
    targets = [r["target"] for r in rec if r.get("status") == "SUCCESS" or r.get("success")]
    if a.only:
        if a.only not in targets:
            print(f"note: {a.only} is not a SUCCESS target in the report; measuring it anyway")
        targets = [a.only]

    print(f"report: {report}")
    print(f"item2 dir: {a.item2_dir}\nout root: {out_root}")
    print(f"measuring {len(targets)} target(s), runs={a.runs}\n")

    rows, errors = [], []
    for t in targets:
        res = measure(t, a.item2_dir, out_root, repo, a.runs, a.keep)
        if "error" in res:
            errors.append(res)
            print(f"  {t:34s} ERROR: {res['error']}")
        else:
            rows.append(res)
            note = ""
            if res.get("crash"):
                note = "   [FUZZ RUN CRASHED - coverage is from pre-crash corpus replay only]"
            print(f"  {t:34s} lines {res.get('lines','-'):18s} regions {res.get('regions','-'):18s} branches {res.get('branches','-')}{note}")

    if rows:
        def pct(s):
            m = re.search(r"\(([\d.]+)%\)", s or "")
            return float(m.group(1)) if m else -1.0
        rows_sorted = sorted(rows, key=lambda r: pct(r.get("lines")))
        print("\n== by line coverage (lowest first) ==")
        for r in rows_sorted:
            print(f"  {r['target']:34s} {r.get('lines','-')}")
        print(f"\nmeasured {len(rows)} ok, {len(errors)} errored")
        crashed = [r for r in rows if r.get("crash")]
        if crashed:
            print("\n== targets whose fuzz run CRASHED (not a coverage result; a finding to triage) ==")
            for r in crashed:
                print(f"- {r['target']}: {r['crash']['summary']}")
                for ci in r.get("crash_inputs", []):
                    print(f"    crashing input kept at: {ci}")
    if errors:
        print("\n== errors (first stderr tail each) ==")
        for e in errors:
            print(f"- {e['target']}: {e['error']}")
            if e.get("stderr"):
                print("   " + e["stderr"].replace("\n", "\n   "))


if __name__ == "__main__":
    sys.exit(main())
