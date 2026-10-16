#!/usr/bin/env python3
"""Deterministic report for one Ablation G run.

Reads only files that run_ablation_g.py already wrote (results JSON, call
ledger JSONL, per-attempt harness_attemptN_result.json files) and prints the
summary tables, so that numbers in a write-up are computed by code rather than
transcribed by hand or by an agent.

Usage:
    python3 report_ablation_g.py <results.json> [--ledger calls.jsonl] [--logs logs_dir]
        [--compare label=results.json ...]

The ledger and logs paths default to the names run_ablation_g.py derives from
the results file name. Standard library only.
"""
import argparse
import collections
import glob
import json
import math
import os
import re
import statistics
import sys


def mcnemar_exact(b, c):
    """Two-sided exact McNemar p-value (binomial, p=0.5)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def load_results(path):
    with open(path) as f:
        return json.load(f)


def trials(results):
    for target, rows in results.items():
        for r in rows:
            yield target, r


def summarize(results):
    out = {}
    for target, rows in results.items():
        n = len(rows)
        one = sum(1 for r in rows if r.get("oracle_absent_success"))
        loop = sum(1 for r in rows if r.get("oracle_present_success"))
        succ_attempts = [r["oracle_present_attempts"] for r in rows if r.get("oracle_present_success")]
        out[target] = dict(n=n, one=one, loop=loop, attempts=succ_attempts)
    return out


_PATH_RE = re.compile(r"(/[^\s:'\"]+)+")
_LOC_RE = re.compile(r":\d+(:\d+)?")
_HEX_RE = re.compile(r"0x[0-9a-fA-F]+")


def first_error_line(text):
    """Normalised first diagnostic line: paths, line numbers, addresses removed."""
    if not text:
        return "(no error text)"
    for line in text.splitlines():
        if "error:" in line or "ERROR:" in line or "undefined reference" in line:
            line = _PATH_RE.sub("<path>", line)
            line = _LOC_RE.sub("", line)
            line = _HEX_RE.sub("<addr>", line)
            return re.sub(r"\s+", " ", line).strip()[:140]
    return re.sub(r"\s+", " ", text.strip().splitlines()[0])[:140]


def collect_errors(logs_dir):
    """attempt-1 error per trial, and last-attempt error for trials that never succeeded."""
    first, last = [], []
    if not logs_dir or not os.path.isdir(logs_dir):
        return first, last, False
    for tdir in sorted(glob.glob(os.path.join(logs_dir, "*", "trial_*"))):
        a1 = os.path.join(tdir, "harness_attempt1_result.json")
        if not os.path.exists(a1):
            continue
        m1 = json.load(open(a1))
        if m1.get("success"):
            continue
        first.append(first_error_line(m1.get("error_text")))
        files = glob.glob(os.path.join(tdir, "oracle_present_loop", "harness_attempt*_result.json"))
        if not files:
            continue
        files.sort(key=lambda p: int(re.search(r"attempt(\d+)_result", p).group(1)))
        ml = json.load(open(files[-1]))
        if not ml.get("success"):
            last.append(first_error_line(ml.get("error_text")))
    return first, last, True


def ledger_summary(path):
    if not path or not os.path.exists(path):
        return None
    rows = [json.loads(l) for l in open(path) if l.strip()]
    return dict(
        calls=len(rows),
        cost=sum(r.get("cost_usd") or 0 for r in rows),
        providers=collections.Counter(str(r.get("provider")) for r in rows),
        served=sorted({str(r.get("served_model")) for r in rows}),
        reasoning=sum(1 for r in rows if (r.get("reasoning_tokens") or 0) > 0),
        nonstop=sum(1 for r in rows if r.get("finish_reason") not in ("stop", None)),
        zero_out=sum(1 for r in rows if (r.get("completion_tokens") or 0) == 0),
    )


def table(rows, header):
    w = [max(len(str(x)) for x in col) for col in zip(header, *rows)]
    fmt = " | ".join("{:<%d}" % x for x in w)
    lines = [fmt.format(*header), "-+-".join("-" * x for x in w)]
    lines += [fmt.format(*[str(c) for c in r]) for r in rows]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results")
    ap.add_argument("--ledger")
    ap.add_argument("--logs")
    ap.add_argument("--compare", nargs="*", default=[], help="label=results.json")
    a = ap.parse_args()

    base = os.path.basename(a.results)
    slug = base[len("ablation_g_results_"):-len(".json")] if base.startswith("ablation_g_results_") else None
    d = os.path.dirname(a.results)
    ledger = a.ledger or (os.path.join(d, f"ablation_g_calls_{slug}.jsonl") if slug else None)
    logs = a.logs or (os.path.join(d, f"ablation_g_logs_{slug}") if slug else None)

    res = load_results(a.results)
    s = summarize(res)
    tot = lambda k: sum(v[k] for v in s.values())
    n = tot("n")
    pairs = list(trials(res))
    b = sum(1 for _, r in pairs if (not r.get("oracle_absent_success")) and r.get("oracle_present_success"))
    c = sum(1 for _, r in pairs if r.get("oracle_absent_success") and not r.get("oracle_present_success"))
    both = sum(1 for _, r in pairs if r.get("oracle_absent_success") and r.get("oracle_present_success"))
    neither = n - b - c - both

    print(f"RESULTS FILE: {a.results}  (trials: {n})\n")
    print("== Per target ==")
    rows = []
    for t, v in s.items():
        at = v["attempts"]
        rows.append([t, f"{v['one']}/{v['n']}", f"{v['loop']}/{v['n']}",
                     f"{statistics.mean(at):.2f}" if at else "N/A"])
    allat = [x for v in s.values() for x in v["attempts"]]
    rows.append(["OVERALL", f"{tot('one')}/{n}", f"{tot('loop')}/{n}",
                 f"{statistics.mean(allat):.2f}" if allat else "N/A"])
    print(table(rows, ["target", "one-shot", "loop", "mean attempt of loop successes"]))

    print("\n== Paired outcome ==")
    print(f"both succeed {both} | both fail {neither} | loop rescued (b) {b} | one-shot only (c) {c}")
    print(f"McNemar exact two-sided p = {mcnemar_exact(b, c):.3g}  (b={b}, c={c})")
    if allat:
        dist = collections.Counter(allat)
        print("Loop-success attempt distribution:",
              ", ".join(f"attempt {k}: {dist[k]}" for k in sorted(dist)),
              f"| median {statistics.median(allat)}")

    first, last, have_logs = collect_errors(logs)
    print("\n== Failure patterns ==")
    if not have_logs:
        print(f"(logs dir not found: {logs})")
    else:
        for name, errs in (("attempt-1 failures", first), ("final failures (never succeeded)", last)):
            print(f"\n{name}: n={len(errs)}; 'redefinition of': {sum('redefinition of' in e for e in errs)}")
            for e, k in collections.Counter(errs).most_common(10):
                print(f"  {k:4d}  {e}")

    L = ledger_summary(ledger)
    print("\n== Ledger ==")
    if L is None:
        print(f"(ledger not found: {ledger})")
    else:
        print(f"calls {L['calls']} | cost ${L['cost']:.4f} | providers {dict(L['providers'])}")
        print(f"served_model {L['served']} | reasoning_tokens>0: {L['reasoning']} | "
              f"finish_reason!=stop: {L['nonstop']} | zero-completion calls: {L['zero_out']}")

    if a.compare:
        print("\n== Comparison (read-only from other results files) ==")
        sets = [("this run", s)]
        for item in a.compare:
            label, _, p = item.partition("=")
            sets.append((label, summarize(load_results(p))))
        targets = list(s)
        rows = []
        for t in targets + ["OVERALL"]:
            row = [t]
            for _, ss in sets:
                if t == "OVERALL":
                    n_ = sum(v["n"] for v in ss.values())
                    row.append(f"{sum(v['one'] for v in ss.values())}/{n_} -> {sum(v['loop'] for v in ss.values())}/{n_}")
                else:
                    v = ss.get(t)
                    row.append(f"{v['one']}/{v['n']} -> {v['loop']}/{v['n']}" if v else "n/a")
            rows.append(row)
        print("cells are one-shot -> loop")
        print(table(rows, ["target"] + [l for l, _ in sets]))


if __name__ == "__main__":
    sys.exit(main())
