#!/usr/bin/env python3
"""
AeroHarness Self-Repair Runner for crazyflie-firmware radiolinkSyslinkDispatch.
Follows the reference architecture from targets/uart_pl011_item2/run_item2_self_repair.py,
using OpenRouterHarnessSynthesizerAgent pinned to CoreWeave (deepseek/deepseek-v4.1-flash-20260910).

Usage:
    python3 run_crazyflie_self_repair.py
    python3 run_crazyflie_self_repair.py --only radiolinkSyslinkDispatch
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

from src.analyzer.c_ast_extractor import (
    CASTExtractor,
    ExtractedHeaderContext,
    StructDefinition,
    StructField,
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

# Hand-written StructDefinition entries copied verbatim from prompt / upstream headers:
# cf/src/hal/interface/syslink.h and cf/src/hal/interface/radiolink.h at commit 9912584c
SYSLINK_PACKET_STRUCT = StructDefinition(
    name="_SyslinkPacket",
    raw_decl=(
        "typedef struct _SyslinkPacket\n"
        "{\n"
        "  uint8_t type;\n"
        "  uint8_t length;\n"
        "  char data[64];     // SYSLINK_MTU\n"
        "} __attribute__((packed)) SyslinkPacket;"
    ),
    fields=[
        StructField(name="type", type_str="uint8_t"),
        StructField(name="length", type_str="uint8_t"),
        StructField(name="data", type_str="char", array_size="64"),
    ],
)

P2P_PACKET_STRUCT = StructDefinition(
    name="_P2PPacket",
    raw_decl=(
        "typedef struct _P2PPacket\n"
        "{\n"
        "  uint8_t size;\n"
        "  uint8_t rssi;\n"
        "  union {\n"
        "    struct {\n"
        "      uint8_t port;\n"
        "      uint8_t data[60];   // P2P_MAX_DATA_SIZE\n"
        "    };\n"
        "    uint8_t raw[61];\n"
        "  };\n"
        "} __attribute__((packed)) P2PPacket;"
    ),
    fields=[
        StructField(name="size", type_str="uint8_t"),
        StructField(name="rssi", type_str="uint8_t"),
        StructField(name="port", type_str="uint8_t"),
        StructField(name="data", type_str="uint8_t", array_size="60"),
    ],
)

CRAZYFLIE_CONSTANTS = {
    "SYSLINK_RADIO_RAW": "0x00",
    "SYSLINK_RADIO_RSSI": "0x04",
    "SYSLINK_RADIO_RAW_BROADCAST": "0x06",
    "SYSLINK_RADIO_P2P_BROADCAST": "0x0A",
    "SYSLINK_RADIO_READY": "0x0B",
}

# Neutral convention note: informs LLM about packet source without revealing bug details
CRAZYFLIE_CONVENTION_NOTE = (
    "The target function `void radiolinkSyslinkDispatch(SyslinkPacket *slp)` is called with "
    "attacker-controlled bytes from a UART/radio link. Header `crazyflie_radiolink.h` "
    "provides `SyslinkPacket`, `P2PPacket`, packet type constants (`SYSLINK_RADIO_*`), "
    "and runtime environment stubs. In your `LLVMFuzzerTestOneInput`, construct a "
    "`SyslinkPacket` populated from the fuzzer input bytes and call `radiolinkSyslinkDispatch(&packet)`."
)


def build_header_context(h_path: Path, extractor: CASTExtractor, macros: Dict[str, str]) -> ExtractedHeaderContext:
    """Extracts function signature via CASTExtractor and attaches struct definitions and constants."""
    ctx = extractor.extract_from_header(h_path)
    if len(ctx.functions) != 1:
        raise RuntimeError(
            f"{h_path}: expected exactly 1 forward-declared function, got {len(ctx.functions)} "
            f"({[f.name for f in ctx.functions]})"
        )
    return ExtractedHeaderContext(
        file_path=str(h_path),
        functions=ctx.functions,
        structs=[SYSLINK_PACKET_STRUCT, P2P_PACKET_STRUCT],
        enums=[],
        mmio_registers=[],
        magic_constants=macros,
        raw_content=ctx.raw_content,
    )


def run_target(target_name: str, agent: OpenRouterHarnessSynthesizerAgent) -> Dict[str, Any]:
    h_path = TARGET_DIR / "crazyflie_radiolink.h"
    c_path = TARGET_DIR / "radiolink_target.c"
    out_dir = OUTPUT_DIR / target_name
    out_dir.mkdir(parents=True, exist_ok=True)

    extractor = CASTExtractor()
    ctx = build_header_context(h_path, extractor, CRAZYFLIE_CONSTANTS)
    target_func = ctx.functions[0]

    cg_builder = CallGraphBuilder()
    risk_scores = cg_builder.analyze_source_file(c_path, known_apis=[target_name])
    risk_score = risk_scores.get(target_name)

    # max_iterations=6 matches prompt instruction
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
            mmio_convention_note=CRAZYFLIE_CONVENTION_NOTE,
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
    parser = argparse.ArgumentParser(description="AeroHarness Self-Repair for Crazyflie radiolinkSyslinkDispatch")
    parser.add_argument("--only", nargs="*", default=["radiolinkSyslinkDispatch"], help="Target function names to run")
    parser.add_argument("--max-targets", type=int, default=1, help="Max targets to execute")
    args = parser.parse_args()

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
