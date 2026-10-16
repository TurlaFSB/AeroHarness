#!/usr/bin/env python3
"""Turn Stage 1's ordering edges into a dispatcher harness (work plan item 11).

Until now nothing consumed `ordering_edges`: the state-machine dispatcher
(`fuzz_state_machine.c`) hard-codes "init first, then poll_out / poll_in / isr"
by hand. This module derives that structure from the Stage 1 output instead:

  * the prerequisite function is the `before` node of the `framework_init_before_*`
    edges (for Zephyr drivers: the init function named in DEVICE_DT_INST_DEFINE);
  * the gated functions are the `after` nodes of those edges, restricted to the
    ones the caller selects;
  * each gated call's arguments come from the parameter types Stage 1 records
    (device pointer -> &dev, a scalar -> next fuzz byte, `T *` -> a local);
  * before each gated call, the registers that function READS (Stage 1's
    `mmio_accesses`, access_type read / read-modify-write) are seeded from the
    fuzz input, which is the data-grounded version of the hand-written
    `regs.mis = data[i+1]; regs.imsc = data[i+1];`.

Scope, stated plainly: the edges exist only for Zephyr-style drivers (see
FAILURE_TAXONOMY.md, work plan item 11), the argument templates cover device
pointers, scalars and one-level pointers, and the scaffold (mocks, struct setup)
is still taken from an existing dispatcher file. Functions outside those
templates are listed as skipped, never silently dropped.

Usage:
    python3 stage1_dispatch_plan.py ast_output.json --select pl011_poll_out,pl011_poll_in,pl011_isr \\
        [--plan plan.json] [--scaffold fuzz_state_machine.c --emit-c out.c]
"""
import argparse
import json
import re
import sys

FRAMEWORK_KINDS = ("framework_init_before_api", "framework_init_before_isr")
DEV_RE = re.compile(r"^(const\s+)?struct\s+device\s*\*$")
SCALAR_RE = re.compile(r"^(const\s+)?(unsigned\s+char|signed\s+char|char|uint8_t|int8_t|uint16_t|int16_t|"
                       r"uint32_t|int32_t|int|unsigned|unsigned\s+int|bool)$")
BYTE_PTR_RE = re.compile(r"^(unsigned\s+char|char|uint8_t)\s*\*$")


def _norm(t):
    return re.sub(r"\s+", " ", t.strip())


def arg_template(param):
    """Return ('dev'|'byte'|'byte_ptr', ...) or None when the type is not covered."""
    t = _norm(param["type"])
    if DEV_RE.match(t):
        return "dev"
    if param.get("is_pointer"):
        return "byte_ptr" if BYTE_PTR_RE.match(t) else None
    return "byte" if SCALAR_RE.match(t) else None


def build_plan(ast, select):
    funcs = ast["functions"]
    fw = [e for e in ast.get("ordering_edges", []) if e.get("kind") in FRAMEWORK_KINDS]
    prereqs = sorted({e["before"] for e in fw})
    if len(prereqs) != 1:
        raise SystemExit(f"expected exactly one framework prerequisite, found {prereqs}; "
                         "this module only handles the single-init Zephyr device model")
    init = prereqs[0]
    ordered_after = {e["after"] for e in fw if e["before"] == init}
    gated, skipped = [], []
    for name in select:
        if name not in funcs:
            skipped.append({"name": name, "reason": "not in Stage 1 output"})
            continue
        if name not in ordered_after:
            skipped.append({"name": name, "reason": f"no framework edge {init} -> {name}; "
                            "no evidence it must follow init"})
            continue
        tpls = [arg_template(p) for p in funcs[name]["params"]]
        if None in tpls:
            bad = [p["type"] for p, t in zip(funcs[name]["params"], tpls) if t is None]
            skipped.append({"name": name, "reason": f"unsupported parameter type(s): {bad}"})
            continue
        reads = sorted({a["register"] for a in funcs[name].get("mmio_accesses", [])
                        if a.get("access_type") in ("read", "read-modify-write")})
        evidence = next(e["evidence"] for e in fw if e["before"] == init and e["after"] == name)
        gated.append({"name": name, "args": tpls, "seed_registers": reads, "evidence": evidence})
    return {"prerequisite": init, "gated": gated, "skipped": skipped}


def emit_chain(plan, indent="        ", skip_regs=frozenset()):
    """C if/else chain: cmd 0 runs the prerequisite, the others are gated on it.

    `skip_regs` are registers the scaffold already seeds (and may deliberately
    constrain, e.g. clearing TXFF so poll_out cannot spin forever); seeding them
    again would undo that.
    """
    L = []
    init = plan["prerequisite"]
    L.append(f"{indent}if (cmd == 0) {{")
    L.append(f"{indent}    {init}(&dev);")
    L.append(f"{indent}    is_initialized = true;")
    for n, g in enumerate(plan["gated"], start=1):
        L.append(f"{indent}}} else if (cmd == {n} && is_initialized) {{")
        L.append(f"{indent}    /* {g['name']}: after {init} ({g['evidence'].split(';')[0]}) */")
        seeds = [r for r in g["seed_registers"] if r not in skip_regs]
        need_next = "byte" in g["args"] or bool(seeds)
        pad = indent + "    "
        if need_next:
            L.append(f"{pad}if (i + 1 < size) {{")
            pad += "    "
        for r in seeds:
            L.append(f"{pad}regs.{r} = data[i+1];")
        call_args, pre = [], []
        for k, t in enumerate(g["args"]):
            if t == "dev":
                call_args.append("&dev")
            elif t == "byte":
                call_args.append("data[++i]")
            else:
                pre.append(f"unsigned char out{k} = 0;")
                call_args.append(f"&out{k}")
        for p in pre:
            L.append(f"{pad}{p}")
        L.append(f"{pad}{g['name']}({', '.join(call_args)});")
        if need_next:
            L.append(f"{indent}    }}")
    L.append(f"{indent}}}")
    return "\n".join(L)


def emit_harness(scaffold_text, plan):
    start = scaffold_text.index("        if (cmd == 0) {")
    loop = scaffold_text.index("for (size_t i = 0; i < size; i++)")
    already = frozenset(re.findall(r"regs\.(\w+)\s*(?:=|&=|\|=)", scaffold_text[loop:start]))
    end_marker = "    }\n    \n    return 0;"
    end = scaffold_text.index(end_marker, start)
    out = scaffold_text[:start] + emit_chain(plan, skip_regs=already) + "\n" + scaffold_text[end:]
    n = len(plan["gated"]) + 1
    out, k = re.subn(r"data\[i\] % \d+", f"data[i] % {n}", out, count=1)
    if k != 1:
        raise SystemExit("scaffold has no `data[i] % N` command selector")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ast_json")
    ap.add_argument("--select", required=True, help="comma-separated function names to include")
    ap.add_argument("--plan", help="write the plan as JSON")
    ap.add_argument("--scaffold", help="existing dispatcher .c whose mocks/setup are reused")
    ap.add_argument("--emit-c", help="write the generated dispatcher harness")
    a = ap.parse_args()
    ast = json.load(open(a.ast_json))
    plan = build_plan(ast, [s for s in a.select.split(",") if s])
    print(json.dumps(plan, indent=2))
    if a.plan:
        json.dump(plan, open(a.plan, "w"), indent=2)
    if a.emit_c:
        if not a.scaffold:
            raise SystemExit("--emit-c needs --scaffold")
        open(a.emit_c, "w").write(emit_harness(open(a.scaffold).read(), plan))
        print(f"wrote {a.emit_c}", file=sys.stderr)


if __name__ == "__main__":
    main()
