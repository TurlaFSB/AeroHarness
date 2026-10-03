#!/usr/bin/env python3
"""
Work Plan item 2 driver: runs the real SelfRepairOrchestrator against all 18 prepared
uart_pl011.c targets, tracking first-attempt-success vs. final-success and iteration
count per function (the exact statistic item 2 exists to produce).

Two modes, chosen automatically:

  - REAL mode: set GEMINI_API_KEY_1 through GEMINI_API_KEY_4 (at least one; up to four
    for rotation) in the environment. Uses RotatingHarnessSynthesizerAgent so a
    quota-exhausted/failing key is detected (via the real agent's own model_used field,
    never a guess) and rotated past, rather than silently falling back to deterministic
    template generation and mislabeling that as real data. THIS is the mode Antigravity
    must run in -- it is what actually produces item 2's data.

  - OFFLINE SMOKE-TEST mode: no keys set. Uses the plain, unmodified
    HarnessSynthesizerAgent with no API key, which exercises its deterministic
    fallback path. This produces NO valid item-2 data (the fallback harness has no
    self-repair reasoning in it at all) -- it exists ONLY to prove the wiring
    (CASTExtractor parsing, ExtractedHeaderContext construction, CompilerOracle,
    SmokeTestOracle) is structurally correct before burning any real API quota on it.
    Every record this mode produces is tagged "OFFLINE_SMOKE_TEST" in the report so it
    can never be mistaken for real data downstream.

Usage:
    python3 run_item2_self_repair.py                 # runs all 18 targets
    python3 run_item2_self_repair.py --only pl011_err_check pl011_isr_tx_enable
    python3 run_item2_self_repair.py --max-targets 3  # smoke-test a handful first
"""
import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).parent))

from src.analyzer.c_ast_extractor import (  # noqa: E402
    CASTExtractor,
    EnumDefinition,
    ExtractedHeaderContext,
    StructDefinition,
    StructField,
)
from src.analyzer.call_graph import CallGraphBuilder  # noqa: E402
from src.oracle.repair_loop import SelfRepairOrchestrator  # noqa: E402
from src.synthesizer.agent import HarnessSynthesizerAgent  # noqa: E402
from config.settings import get_settings  # noqa: E402
from item2_target_bodies import TARGETS  # noqa: E402
from rotating_agent import AllKeysExhaustedError, RotatingHarnessSynthesizerAgent  # noqa: E402

ITEM2_DIR = Path(__file__).parent
INCLUDE_ISOLATED_DIR = REPO_ROOT / "harnesses" / "include_isolated"
OUTPUT_DIR = ITEM2_DIR / "output"

# Hand-written StructDefinition entries for the two real structs this driver's
# functions actually touch (pl011_regs, pl011_data). Both are PLAIN tagged structs in
# the real source (no typedef), which is exactly why CASTExtractor's own regex-based
# struct extraction can't find them automatically (see FAILURE_TAXONOMY.md) -- these
# are supplied by hand instead so the LLM's prompt is not context-free. Field lists
# match common_stubs.h and the real upstream header exactly.
PL011_REGS_STRUCT = StructDefinition(
    name="pl011_regs",
    raw_decl=(
        "struct pl011_regs {\n"
        "    uint32_t dr;\n"
        "    union { uint32_t rsr; uint32_t ecr; };\n"
        "    uint32_t reserved_0[4];\n"
        "    uint32_t fr;\n"
        "    uint32_t reserved_1;\n"
        "    uint32_t ilpr, ibrd, fbrd, lcr_h, cr, ifls, imsc, ris, mis, icr, dmacr;\n"
        "}; // accessed via volatile struct pl011_regs *uart = get_uart(dev);"
    ),
    fields=[
        StructField(name="dr", type_str="uint32_t"),
        StructField(name="fr", type_str="uint32_t"),
        StructField(name="cr", type_str="uint32_t"),
        StructField(name="imsc", type_str="uint32_t"),
        StructField(name="ris", type_str="uint32_t"),
        StructField(name="mis", type_str="uint32_t"),
        StructField(name="icr", type_str="uint32_t"),
        StructField(name="rsr", type_str="uint32_t"),
    ],
)

PL011_DATA_STRUCT = StructDefinition(
    name="pl011_data",
    raw_decl=(
        "struct pl011_data {\n"
        "    struct uart_config uart_cfg;\n"
        "    bool sbsa;\n"
        "    uint32_t clk_freq;\n"
        "    volatile bool sw_call_txdrdy;\n"
        "    uart_irq_callback_user_data_t irq_cb;\n"
        "    struct k_spinlock irq_cb_lock;\n"
        "    void *irq_cb_data;\n"
        "}; // reached via: struct pl011_data *data = (struct pl011_data *)dev->data;"
    ),
    fields=[
        StructField(name="sbsa", type_str="bool"),
        StructField(name="clk_freq", type_str="uint32_t"),
        StructField(name="sw_call_txdrdy", type_str="volatile bool"),
        StructField(name="irq_cb", type_str="uart_irq_callback_user_data_t"),
        StructField(name="irq_cb_data", type_str="void *"),
    ],
)


def build_header_context(h_path: Path, extractor: CASTExtractor, macros: dict) -> ExtractedHeaderContext:
    """Real function-signature extraction via the (bug-fixed) CASTExtractor, with
    hand-written struct/magic-constant context supplied on top -- see module docstring
    and FAILURE_TAXONOMY.md for why the struct/MMIO extraction can't be automatic here."""
    ctx = extractor.extract_from_header(h_path)
    if len(ctx.functions) != 1:
        raise RuntimeError(
            f"{h_path}: expected exactly 1 forward-declared function, got {len(ctx.functions)} "
            f"({[f.name for f in ctx.functions]}) -- CASTExtractor's regex may have matched "
            f"something unexpected in this header; do not proceed without checking by hand."
        )
    return ExtractedHeaderContext(
        file_path=str(h_path),
        functions=ctx.functions,
        structs=[PL011_REGS_STRUCT, PL011_DATA_STRUCT],
        enums=[],
        mmio_registers=[],
        magic_constants=macros,
        raw_content=ctx.raw_content,
    )


def build_agent(offline: bool):
    if offline:
        print("!!! OFFLINE SMOKE-TEST MODE -- no GEMINI_API_KEY_1..4 set. This run produces "
              "NO valid item-2 data; it only proves the wiring works. !!!", file=sys.stderr)
        return HarnessSynthesizerAgent(api_key=None)
    keys = [os.getenv(f"GEMINI_API_KEY_{i}") for i in range(1, 5)]
    keys = [k for k in keys if k]
    if not keys:
        raise RuntimeError("No GEMINI_API_KEY_1..4 found but offline=False was requested")
    print(f"REAL mode: {len(keys)} API key(s) loaded for rotation.", file=sys.stderr)
    # NOTE (Oct 2 2026): previously hardcoded model_name="gemini-1.5-pro",
    # fallback_model="gemini-2.0-flash" literally here, a second independent copy of
    # config/settings.py's primary_model/fallback_model. Both of those model names are
    # now confirmed deprecated/shut down by Google as of Oct 2026 (see
    # FAILURE_TAXONOMY.md), which is almost certainly why every key failed on its very
    # first call in the second real run (1 call per key, not the ~20 a genuine
    # quota-exhaustion shape would show). Reading from get_settings() here means there is
    # exactly one place left to fix once the correct model string is confirmed live
    # (see ANTIGRAVITY_TASK_ITEM2.md's revision note) -- this file no longer needs its
    # own edit when that happens.
    settings = get_settings()
    return RotatingHarnessSynthesizerAgent(
        api_keys=keys, model_name=settings.primary_model, fallback_model=settings.fallback_model
    )


def run_one_target(t, agent, offline: bool) -> dict:
    h_path = ITEM2_DIR / f"{t.name}.h"
    c_path = ITEM2_DIR / f"{t.name}.c"
    out_dir = OUTPUT_DIR / t.name

    extractor = CASTExtractor()
    ctx = build_header_context(h_path, extractor, t.macros)
    target_func = ctx.functions[0]

    cg_builder = CallGraphBuilder()
    risk_scores = cg_builder.analyze_source_file(c_path, known_apis=[t.name])
    risk_score = risk_scores.get(t.name)

    orchestrator = SelfRepairOrchestrator(agent=agent, max_iterations=5)

    record = {
        "target": t.name,
        "ccn": t.ccn,
        "offline_smoke_test": offline,
    }

    try:
        outcome = orchestrator.run_synthesis_and_repair(
            header_context=ctx,
            target_api=target_func,
            risk_score=risk_score,
            header_path=h_path,
            target_c_files=[c_path],
            include_dirs=[ITEM2_DIR, INCLUDE_ISOLATED_DIR],
            output_dir=out_dir,
            externally_linked=True,
        )
        record.update({
            "status": "SUCCESS" if outcome.success else "FAILED_TO_CONVERGE",
            "success": outcome.success,
            "first_attempt_success": outcome.success and outcome.total_iterations == 1,
            "total_iterations": outcome.total_iterations,
            "harness_file_path": outcome.harness_file_path,
            "binary_path": outcome.binary_path,
            "failure_reason": outcome.failure_reason,
            "history": [h.model_dump() for h in outcome.history],
        })
    except AllKeysExhaustedError as e:
        record.update({
            "status": "ALL_KEYS_EXHAUSTED",
            "success": None,
            "first_attempt_success": None,
            "total_iterations": None,
            "error": str(e),
        })

    if not offline and hasattr(agent, "calls_per_key"):
        record["calls_per_key_cumulative"] = dict(agent.calls_per_key)

    return record


# Statuses that represent a genuine, final result for a target -- once a target has one
# of these recorded, it must never be silently re-attempted (each target gets exactly one
# real attempt, by design; see "Do not re-run" in ANTIGRAVITY_TASK_ITEM2.md).
# ALL_KEYS_EXHAUSTED is deliberately NOT included here: it means the target never actually
# got a real attempt (success/total_iterations are null), so it must be retried once quota
# is available again, not treated as done.
_TERMINAL_STATUSES = {"SUCCESS", "FAILED_TO_CONVERGE"}


def _load_existing_report(report_path: Path) -> dict:
    """
    Returns {target_name: record} for whatever's already in item2_report.json, or {} if the
    file doesn't exist / can't be parsed.

    NOTE (Oct 3 2026): added after discovering `main()` previously had NO merge step at all --
    it unconditionally overwrote item2_report.json with ONLY the current invocation's
    `results` list. Combined with the documented `--only <remaining targets>` resume workflow,
    this meant every resume after an ALL_KEYS_EXHAUSTED stop silently discarded every earlier
    target's real record from the report (confirmed: a real resume run that only re-attempted
    1 target produced a report containing exactly that 1 record, with the prior run's 3
    SUCCESS + 2 FAILED_TO_CONVERGE + 1 ALL_KEYS_EXHAUSTED records gone). The only reason those
    6 records weren't permanently lost is that they'd already been pasted into a chat report
    and recovered from there by hand -- not something this project can rely on going forward.
    Fixed by loading any existing report first and merging into it (see main()) instead of
    blindly overwriting.
    """
    if not report_path.exists():
        return {}
    try:
        existing = json.loads(report_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"WARNING: could not parse existing {report_path} ({e!r}); "
              f"treating as empty rather than risk overwriting it blindly. "
              f"If this is unexpected, stop and inspect the file by hand.", file=sys.stderr)
        return {}
    return {r["target"]: r for r in existing if "target" in r}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*", default=None, help="run only these target names")
    parser.add_argument("--max-targets", type=int, default=None, help="stop after N targets")
    parser.add_argument(
        "--force", nargs="*", default=[],
        help="target names to re-attempt even if they already have a terminal "
             "(SUCCESS/FAILED_TO_CONVERGE) record -- use only deliberately, never by default; "
             "each target is meant to get exactly one real attempt."
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    offline = not any(os.getenv(f"GEMINI_API_KEY_{i}") for i in range(1, 5))
    agent = build_agent(offline)

    report_path = OUTPUT_DIR / "item2_report.json"
    existing_by_name = _load_existing_report(report_path)

    targets = TARGETS
    if args.only:
        targets = [t for t in targets if t.name in args.only]
    if args.max_targets:
        targets = targets[: args.max_targets]

    skipped = []
    targets_to_run = []
    for t in targets:
        prior = existing_by_name.get(t.name)
        if prior and prior.get("status") in _TERMINAL_STATUSES and t.name not in args.force:
            skipped.append((t.name, prior["status"]))
            continue
        targets_to_run.append(t)

    if skipped:
        print(f"Skipping {len(skipped)} target(s) that already have a terminal result "
              f"(pass --force <name> to deliberately re-attempt one): "
              + ", ".join(f"{name} ({status})" for name, status in skipped), file=sys.stderr)

    for t in targets_to_run:
        print(f"\n=== {t.name} (CCN {t.ccn}) ===", file=sys.stderr)
        record = run_one_target(t, agent, offline)
        print(json.dumps(record, indent=2, default=str), file=sys.stderr)
        existing_by_name[t.name] = record  # merge into the full picture, never overwrite it
        if record["status"] == "ALL_KEYS_EXHAUSTED":
            print("All keys exhausted -- stopping run here. Resume later with fresh "
                  "daily quota by re-running with --only <remaining targets> (or no --only "
                  "at all -- targets with a terminal result are now skipped automatically).",
                  file=sys.stderr)
            break

    # Write back in TARGETS' canonical order so the report's target ordering stays stable
    # across runs, with any names not in TARGETS (shouldn't happen, but don't silently drop
    # them) appended at the end.
    canonical_order = [t.name for t in TARGETS]
    ordered_results = [existing_by_name[name] for name in canonical_order if name in existing_by_name]
    ordered_results += [v for k, v in existing_by_name.items() if k not in canonical_order]

    report_path.write_text(json.dumps(ordered_results, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {report_path} ({len(ordered_results)} target(s) total, "
          f"{len(targets_to_run)} attempted this run)", file=sys.stderr)


if __name__ == "__main__":
    main()
