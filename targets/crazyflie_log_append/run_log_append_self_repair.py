#!/usr/bin/env python3
"""
AeroHarness Self-Repair Runner for crazyflie-firmware logAppendBlockV2.
Uses OpenRouterHarnessSynthesizerAgent pinned to CoreWeave (deepseek/deepseek-v4.1-flash-20260910).
"""
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = TARGET_DIR / "output"

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(TARGET_DIR))

from config.settings import get_settings
from src.analyzer.c_ast_extractor import (
    CASTExtractor,
    ExtractedHeaderContext,
)
from src.analyzer.call_graph import CallGraphBuilder
from src.oracle.repair_loop import SelfRepairOrchestrator
from openrouter_synthesizer_agent import (
    OpenRouterHarnessSynthesizerAgent,
    REQUIRED_MODEL,
    PINNED_PROVIDER,
    SPEND_CAP_USD,
    load_openrouter_key,
)

CONSTANTS = {
    "LOG_TYPE_MASK": "0x0f",
    "LOG_MAX_LEN": "26",
    "FIXED_BLOCK_ID": "42",
}

CONVENTION_NOTE = (
    "Target function: `int logAppendBlockV2(int id, struct ops_setting_v2 * settings, int len)` "
    "from Crazyflie's dynamic logging system (`src/modules/src/log.c`). Header `crazyflie_log_append.h` declares the function, "
    "`struct ops_setting_v2`, and `FIXED_BLOCK_ID` (42).\n"
    "In your `LLVMFuzzerTestOneInput`, construct a libFuzzer harness that:\n"
    "1. Requires at least 3 bytes (`if (size < sizeof(struct ops_setting_v2)) return 0;`).\n"
    "2. Consumes exactly one `struct ops_setting_v2` (3 bytes total: 1 byte `logType`, 2 bytes `id`) directly and unconstrained from the fuzzer input (e.g. using `memcpy(&setting, data, sizeof(setting))` or via `FuzzedDataProvider`).\n"
    "3. Calls `logAppendBlockV2(FIXED_BLOCK_ID, &setting, 1)` with a single-entry array (`len = 1`) and the fixed block ID `FIXED_BLOCK_ID` (not fuzzer controlled).\n"
    "CRITICAL: Do NOT restrict or clamp `logType` — all 3 bytes must come directly from the fuzzer input unconstrained."
)


def build_header_context(h_path: Path, extractor: CASTExtractor, macros: Dict[str, str]) -> ExtractedHeaderContext:
    ctx = extractor.extract_from_header(h_path)
    if len(ctx.functions) != 1:
        raise RuntimeError(
            f"{h_path}: expected exactly 1 forward-declared function, got {len(ctx.functions)} "
            f"({[f.name for f in ctx.functions]})"
        )
    return ExtractedHeaderContext(
        file_path=str(h_path),
        functions=ctx.functions,
        structs=[],
        enums=[],
        mmio_registers=[],
        magic_constants=macros,
        raw_content=ctx.raw_content,
    )


def run_target(target_name: str, agent: OpenRouterHarnessSynthesizerAgent) -> Dict[str, Any]:
    h_path = TARGET_DIR / "crazyflie_log_append.h"
    c_path = TARGET_DIR / "log_append_target.c"
    out_dir = OUTPUT_DIR / target_name
    out_dir.mkdir(parents=True, exist_ok=True)

    extractor = CASTExtractor()
    ctx = build_header_context(h_path, extractor, CONSTANTS)
    target_func = ctx.functions[0]

    cg_builder = CallGraphBuilder()
    risk_scores = cg_builder.analyze_source_file(c_path, known_apis=[target_name])
    risk_score = risk_scores.get(target_name)

    orchestrator = SelfRepairOrchestrator(
        agent=agent,
        max_iterations=6,
    )

    record: Dict[str, Any] = {
        "target": target_name,
        "model_requested": agent.model_name,
        "pinned_provider": PINNED_PROVIDER,
        "spend_cap_usd": SPEND_CAP_USD,
    }

    try:
        outcome = orchestrator.run_synthesis_and_repair(
            header_context=ctx,
            target_api=target_func,
            risk_score=risk_score,
            header_path=h_path,
            target_c_files=[c_path],
            include_dirs=[TARGET_DIR],
            output_dir=out_dir,
            externally_linked=True,
            mmio_convention_note=CONVENTION_NOTE,
        )

        record.update({
            "status": "SUCCESS" if outcome.success else "FAILED_TO_CONVERGE",
            "success": outcome.success,
            "first_attempt_success": outcome.success and outcome.total_iterations == 1,
            "total_iterations": outcome.total_iterations,
            "harness_file_path": outcome.harness_file_path,
            "binary_path": outcome.binary_path,
            "failure_reason": outcome.failure_reason,
            "final_harness_code": outcome.final_harness_code,
            "history": [h.model_dump() for h in outcome.history],
            "total_cost_usd": agent.total_cost_usd,
            "total_calls": agent.total_calls,
            "prompt_tokens": agent.total_prompt_tokens,
            "completion_tokens": agent.total_completion_tokens,
        })
    except RuntimeError as re_err:
        err_msg = str(re_err)
        status = "FAILED_AFTER_RETRIES" if "failed after 12 attempts" in err_msg else "RUNTIME_ERROR"
        if "SPEND_CAP_EXCEEDED" in err_msg:
            status = "SPEND_CAP_EXCEEDED"
        record.update({
            "status": status,
            "success": False,
            "failure_reason": err_msg,
            "total_cost_usd": agent.total_cost_usd,
            "total_calls": agent.total_calls,
        })

    result_path = out_dir / "repair_record.json"
    result_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def main():
    parser = argparse.ArgumentParser(description="AeroHarness Self-Repair for Crazyflie logAppendBlockV2")
    parser.add_argument("--only", nargs="*", default=["logAppendBlockV2"], help="Target function names to run")
    parser.add_argument("--max-targets", type=int, default=1, help="Max targets to execute")
    args = parser.parse_args()

    # Configure smoke test runs to verify harness linkage and startup stability
    settings = get_settings()
    settings.smoke_test_runs = 1

    api_key = load_openrouter_key()
    ledger_file = OUTPUT_DIR / "openrouter_calls.jsonl"

    agent = OpenRouterHarnessSynthesizerAgent(
        api_key=api_key,
        model_name=REQUIRED_MODEL,
        ledger_path=ledger_file,
    )

    targets_to_run = args.only[:args.max_targets]
    print(f"=== Starting AeroHarness Self-Repair for Crazyflie Target ===")
    print(f"Target: {targets_to_run}")
    print(f"Model: {REQUIRED_MODEL} via OpenRouter pinned to {PINNED_PROVIDER}")
    print(f"Spend Cap: ${SPEND_CAP_USD:.2f}")

    for t_name in targets_to_run:
        res = run_target(t_name, agent)
        print(f"\nTarget {t_name} Completed:")
        print(f"  Status: {res.get('status')}")
        print(f"  Iterations: {res.get('total_iterations', 0)}")
        print(f"  Success: {res.get('success')}")
        print(f"  Total Spend: ${agent.total_cost_usd:.5f} ({agent.total_calls} calls)")
        if res.get("binary_path"):
            print(f"  Binary: {res.get('binary_path')}")


if __name__ == "__main__":
    main()
