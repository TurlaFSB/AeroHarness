#!/usr/bin/env python3
"""Static validity audit of the harnesses that Ablation G counted as SUCCESS.

"SUCCESS" in run_ablation_g.py means the harness compiles, links and survives a
short sanitizer run. It does not say the harness exercises its target. This script
re-reads, for every trial counted as a success, the final passing
harness_attemptN.cpp from the run's log directory and reports four checks:

  calls_target   LLVMFuzzerTestOneInput's body calls the target function
  defines_target the harness part (before the appended target) also defines it
                 (should be 0: it would be a redefinition)
  stubs_callee   the harness defines, itself, a function that the appended target
                 calls (e.g. a no-op pl011_set_baudrate), so that callee's code is
                 never run
  uses_input     LLVMFuzzerTestOneInput's body uses the fuzz data/size beyond
                 the signature

These are text-level heuristics (comments stripped, braces matched), not proofs:
they find the obvious ways a harness can pass without testing anything, and they
list every flagged file so a human can check. They make no API calls.

Usage:
    python3 audit_ablation_g_harnesses.py <results.json> [--logs logs_dir] [--list-flagged]
"""
import argparse
import collections
import json
import os
import re
import sys

MARKER = "// === APPENDED TARGET FUNCTION ==="
KEYWORDS = {"if", "for", "while", "switch", "return", "sizeof", "defined", "else", "do",
            "case", "static_cast", "reinterpret_cast", "const_cast", "ARG_UNUSED", "BIT",
            "GENMASK", "DEVICE_MMIO_GET", "K_SPINLOCK", "assert", "memcpy", "memset"}


def strip_comments(src):
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return re.sub(r"//[^\n]*", " ", src)


def find_body(src, name):
    """Text of the first function body whose signature mentions `name(`; '' if none."""
    m = re.search(r"\b" + re.escape(name) + r"\s*\([^;{]*\)\s*(?:const\s*)?\{", src)
    if not m:
        return ""
    i, depth = m.end() - 1, 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[i + 1:j]
    return src[i + 1:]


def defined_functions(src):
    """Names of functions with a body in `src` (heuristic: name(...) {)."""
    return set(re.findall(r"\b([A-Za-z_]\w*)\s*\([^;{}]*\)\s*(?:const\s*)?\{", src)) - KEYWORDS


def called_names(src):
    return set(re.findall(r"\b([A-Za-z_]\w*)\s*\(", src)) - KEYWORDS


def audit_file(path, target):
    text = open(path, errors="replace").read()
    if MARKER in text:
        harness, appended = text.split(MARKER, 1)
    else:
        harness, appended = text, ""
    harness, appended = strip_comments(harness), strip_comments(appended)
    body = find_body(harness, "LLVMFuzzerTestOneInput")
    calls = bool(re.search(r"\b" + re.escape(target) + r"\s*\(", body))
    defines = target in defined_functions(harness)
    callees = (called_names(appended) - {target}) if appended else set()
    stubbed = sorted(callees & defined_functions(harness))
    body_in = re.sub(r"\(void\)\s*(?:data|size)\s*;", " ", body)  # a bare (void)data does not count as use
    uses_input = bool(re.search(r"\bdata\b|\bsize\b|FuzzedDataProvider", body_in))
    return dict(calls_target=calls, defines_target=defines, stubbed=stubbed,
                uses_input=uses_input, has_marker=bool(appended))


def final_harness_path(logs, target, trial, row):
    tdir = os.path.join(logs, target, f"trial_{trial}")
    if row.get("oracle_absent_success"):
        return os.path.join(tdir, "harness_attempt1.cpp")
    k = row.get("oracle_present_attempts")
    return os.path.join(tdir, "oracle_present_loop", f"harness_attempt{k}.cpp")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results")
    ap.add_argument("--logs")
    ap.add_argument("--list-flagged", action="store_true")
    a = ap.parse_args()
    base = os.path.basename(a.results)
    slug = base[len("ablation_g_results_"):-len(".json")] if base.startswith("ablation_g_results_") else None
    logs = a.logs or os.path.join(os.path.dirname(a.results), f"ablation_g_logs_{slug}")
    res = json.load(open(a.results))
    per = collections.defaultdict(collections.Counter)
    flagged, missing = [], []
    for target, rows in res.items():
        for r in rows:
            if not r.get("oracle_present_success"):
                continue
            path = final_harness_path(logs, target, r["trial"], r)
            if not os.path.exists(path):
                missing.append(path)
                continue
            c = audit_file(path, target)
            per[target]["audited"] += 1
            per[target]["calls_target"] += c["calls_target"]
            per[target]["defines_target"] += c["defines_target"]
            per[target]["stubs_callee"] += bool(c["stubbed"])
            per[target]["uses_input"] += c["uses_input"]
            ok = c["calls_target"] and not c["defines_target"] and c["uses_input"]
            per[target]["clean"] += bool(ok)
            if not ok or c["stubbed"]:
                flagged.append((path, c))
    print(f"RESULTS FILE: {a.results}\nLOG DIR: {logs}\n")
    hdr = ["target", "audited", "calls target", "defines target", "stubs callee", "uses input",
           "clean (calls, no redefinition, uses input)"]
    rows = []
    tot = collections.Counter()
    for t in res:
        c = per[t]
        tot.update(c)
        rows.append([t, c["audited"], c["calls_target"], c["defines_target"], c["stubs_callee"],
                     c["uses_input"], c["clean"]])
    rows.append(["TOTAL", tot["audited"], tot["calls_target"], tot["defines_target"],
                 tot["stubs_callee"], tot["uses_input"], tot["clean"]])
    w = [max(len(str(x)) for x in col) for col in zip(hdr, *rows)]
    f = " | ".join("{:<%d}" % x for x in w)
    print(f.format(*hdr))
    print("-+-".join("-" * x for x in w))
    for r in rows:
        print(f.format(*[str(x) for x in r]))
    print(f"\nsuccessful trials whose final harness file was not found: {len(missing)}")
    for m in missing[:10]:
        print("  missing:", m)
    stub_names = collections.Counter(n for _, c in flagged for n in c["stubbed"])
    if stub_names:
        print("\nstubbed callees (name: harnesses):", dict(stub_names))
    print(f"flagged harnesses (not clean, or stubs a callee): {len(flagged)}")
    if a.list_flagged:
        for p, c in flagged:
            print(" ", p, {k: v for k, v in c.items() if k != "has_marker"})


if __name__ == "__main__":
    sys.exit(main())
