#!/usr/bin/env python3
"""clang-tidy quality gate over the harnesses Ablation G counted as SUCCESS.

"SUCCESS" in run_ablation_g.py means the harness compiled, linked and survived a
short sanitizer run. That is a weak oracle: it does not say the harness is free of
the defect classes a static analyzer would flag (null dereference, dead store,
uninitialized read, etc.). This script re-reads every final passing harness from a
run's log directory, runs clang-tidy's DEFAULT check set over it with the same
include paths the run compiled with, and reports how many "successful" harnesses
clang-tidy still has something to say about, and what.

It makes NO API calls and does not modify anything. It never runs clang-tidy with
-fix. It is the read-only, zero-cost follow-up to Ablation E (work plan item 5):
E asked whether lint helps INSIDE the repair loop (null result); this asks whether
lint flags anything in the harnesses that already passed the loop.

Only warnings located in the harness file itself are counted (warnings from repo
headers and from the appended target body are dropped), so the result reflects the
generated harness code, not the driver under test.

Usage:
    python3 lint_gate_ablation_g.py <results.json> [results.json ...] \
        [--logs DIR] [--clang-tidy clang-tidy] [--list] [--max-warnings-shown 3]

For each results file the logs dir and the ext/original mock set are inferred from
the file name (…_mockext… -> harnesses/include_ext is added first), exactly as
run_ablation_g.py derives them, unless --logs is given (single-file only).
"""
import argparse
import collections
import glob
import json
import os
import re
import shutil
import subprocess
import sys

MARKER = "// === APPENDED TARGET FUNCTION ==="
_DIAG_RE = re.compile(r"^(\S+?):(\d+):(\d+): (warning|error|note): ")
_CHECK_RE = re.compile(r"\[([A-Za-z0-9.\-]+(?:,[A-Za-z0-9.\-]+)*)\]\s*$")


def repo_root():
    return os.path.abspath(os.path.dirname(os.path.abspath(__file__)))


def include_flags(use_ext):
    root = repo_root()
    flags = []
    if use_ext:
        flags.append("-I" + os.path.join(root, "harnesses", "include_ext"))
    flags += ["-I" + os.path.join(root, "harnesses", "include"), "-I" + root]
    return flags


def final_harness_path(logs, target, trial, row):
    tdir = os.path.join(logs, target, f"trial_{trial}")
    if row.get("oracle_absent_success"):
        return os.path.join(tdir, "harness_attempt1.cpp")
    k = row.get("oracle_present_attempts")
    return os.path.join(tdir, "oracle_present_loop", f"harness_attempt{k}.cpp")


def harness_only(text):
    """The generated harness part, before the appended real target body."""
    return text.split(MARKER, 1)[0] if MARKER in text else text


def filter_warnings(output, harness_basename):
    """Return (count, checks) for clang-tidy 'warning' diagnostics whose location is
    the harness file. Errors, notes, summary lines and other files are dropped."""
    checks = collections.Counter()
    n = 0
    for line in output.split("\n"):
        m = _DIAG_RE.match(line)
        if not m or m.group(4) != "warning":
            continue
        if os.path.basename(m.group(1)) != harness_basename:
            continue
        n += 1
        cm = _CHECK_RE.search(line)
        if cm:
            for chk in cm.group(1).split(","):
                checks[chk] += 1
        else:
            checks["(uncategorized)"] += 1
    return n, checks


def run_tidy(clang_tidy, path, use_ext):
    """Run clang-tidy on a copy that keeps only the harness part (so the appended
    real driver body is not analyzed) in a temp file beside the original."""
    text = open(path, errors="replace").read()
    tmp = path + ".lintgate.cpp"
    with open(tmp, "w") as f:
        f.write(harness_only(text))
    try:
        res = subprocess.run(
            [clang_tidy, os.path.basename(tmp), "--"] + include_flags(use_ext),
            cwd=os.path.dirname(tmp), capture_output=True, text=True, timeout=60)
        out = res.stdout + res.stderr
    except subprocess.TimeoutExpired:
        return None, None, "timeout"
    except Exception as e:
        return None, None, f"invocation failed: {e}"
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    if "unable to handle compilation" in out.lower() or "error reading" in out.lower():
        return None, None, "clang-tidy could not parse the harness"
    cnt, checks = filter_warnings(out, os.path.basename(tmp))
    return cnt, checks, out


def gate_one(results_path, logs_override, clang_tidy, list_flagged, max_shown):
    base = os.path.basename(results_path)
    slug = base[len("ablation_g_results_"):-len(".json")] if base.startswith("ablation_g_results_") else None
    use_ext = bool(slug and "_mockext" in slug)
    logs = logs_override or (os.path.join(os.path.dirname(results_path), f"ablation_g_logs_{slug}") if slug else None)
    res = json.load(open(results_path))
    per = collections.defaultdict(collections.Counter)
    checks_total = collections.Counter()
    flagged, missing, unparsed = [], 0, 0
    for target, rows in res.items():
        for r in rows:
            if not r.get("oracle_present_success"):
                continue
            path = final_harness_path(logs, target, r["trial"], r)
            if not os.path.exists(path):
                missing += 1
                continue
            cnt, checks, _ = run_tidy(clang_tidy, path, use_ext)
            per[target]["audited"] += 1
            if cnt is None:
                unparsed += 1
                per[target]["unparsed"] += 1
                continue
            if cnt == 0:
                per[target]["clean"] += 1
            else:
                per[target]["flagged"] += 1
                per[target]["warnings"] += cnt
                checks_total.update(checks)
                flagged.append((path, cnt, checks))
    print(f"\n=== clang-tidy quality gate: {base} ===")
    print(f"mock set: {'extended (include_ext first)' if use_ext else 'original (include only)'} | logs: {logs}")
    hdr = ["target", "audited", "clean", "flagged", "warnings", "unparsed"]
    rows = []
    tot = collections.Counter()
    for tgt in res:
        c = per[tgt]
        tot.update(c)
        rows.append([tgt, c["audited"], c["clean"], c["flagged"], c["warnings"], c["unparsed"]])
    rows.append(["TOTAL", tot["audited"], tot["clean"], tot["flagged"], tot["warnings"], tot["unparsed"]])
    w = [max(len(str(x)) for x in col) for col in zip(hdr, *rows)]
    fmt = " | ".join("{:<%d}" % x for x in w)
    print(fmt.format(*hdr))
    print("-+-".join("-" * x for x in w))
    for r in rows:
        print(fmt.format(*[str(x) for x in r]))
    if missing:
        print(f"\nsuccessful trials whose final harness file was not found: {missing}")
    if checks_total:
        print("\nwarning types across flagged harnesses (check: count):")
        for chk, n in checks_total.most_common():
            print(f"  {n:4d}  {chk}")
    else:
        print("\nNo clang-tidy warnings in any passing harness (every successful harness is lint-clean).")
    if list_flagged and flagged:
        print("\nflagged harnesses:")
        for path, cnt, checks in flagged[:max_shown] if max_shown else flagged:
            print(f"  {cnt:3d}  {path}  {dict(checks)}")
    return tot, checks_total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results", nargs="+")
    ap.add_argument("--logs", help="override logs dir (single results file only)")
    ap.add_argument("--clang-tidy", default=shutil.which("clang-tidy") or "clang-tidy")
    ap.add_argument("--list", action="store_true", help="list flagged harness paths")
    ap.add_argument("--max-warnings-shown", type=int, default=0,
                    help="cap the number of flagged harnesses listed (0 = all)")
    a = ap.parse_args()
    if a.logs and len(a.results) != 1:
        sys.exit("--logs can only be used with a single results file")
    if not shutil.which(a.clang_tidy) and not os.path.exists(a.clang_tidy):
        sys.exit(f"clang-tidy not found: {a.clang_tidy}")
    grand = collections.Counter()
    grand_checks = collections.Counter()
    for rp in a.results:
        tot, checks = gate_one(rp, a.logs, a.clang_tidy, a.list, a.max_warnings_shown)
        grand.update(tot)
        grand_checks.update(checks)
    if len(a.results) > 1:
        print("\n=== GRAND TOTAL across all results files ===")
        print(f"audited {grand['audited']} | clean {grand['clean']} | flagged {grand['flagged']} "
              f"| warnings {grand['warnings']} | unparsed {grand['unparsed']}")
        if grand_checks:
            print("warning types:", dict(grand_checks.most_common()))


if __name__ == "__main__":
    sys.exit(main())
