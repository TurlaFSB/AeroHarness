"""
Domain-Specific Prompt Templates for AeroHarness Harness Synthesis
"""
from typing import List, Dict, Optional
from src.analyzer.c_ast_extractor import ExtractedHeaderContext, FunctionSignature, StructDefinition
from src.analyzer.call_graph import APIRiskScore


class PromptFactory:
    """Constructs context-rich, constraint-enforcing prompts for LLM fuzz driver generation."""

    @staticmethod
    def get_system_prompt() -> str:
        return """You are AeroHarness, an expert automated cyber reasoning system and firmware vulnerability researcher specializing in C/C++ fuzz driver synthesis, AddressSanitizer, and libFuzzer.

Your objective is to generate a robust, production-grade C++ libFuzzer harness (`LLVMFuzzerTestOneInput`) for an embedded firmware API.

Strict Harness Engineering Rules:
1. Entrypoint Signature: Must strictly implement `extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size)`.
2. Hardware & MMIO Stubbing: Embedded firmware often interacts with hardware registers. You must provide mock implementations of all required hardware accessors (e.g., `hw_read_reg32`, `readl`, `sys_in32`) returning valid state (e.g. READY status bit) so the code never hangs or fails initialization.
3. State Initialization: Instantiate and zero-initialize required context structs (`memset(&ctx, 0, sizeof(ctx))`), call init functions, and pass fuzzer data to the target API.
4. FuzzedDataProvider: If the target requires multiple parameters, structured types, or partitioned buffers, use `<fuzzer/FuzzedDataProvider.h>`.
5. False-Positive Prevention: Do NOT trigger memory leaks or out-of-bounds reads in the harness itself. Validate sizes before dereferencing.
6. Clean Return: Always return 0 at the end of `LLVMFuzzerTestOneInput`.
7. Output Format: Output ONLY the C++ source code inside a single ```cpp ... ``` code block without conversational filler."""

    @staticmethod
    def build_synthesis_prompt(
        header_context: ExtractedHeaderContext,
        target_api: FunctionSignature,
        risk_score: Optional[APIRiskScore],
        header_filename: str
    ) -> str:
        prompt_lines = [
            f"### Target Embedded API: `{target_api.raw_declaration}`",
            f"Header Include: `#include \"{header_filename}\"`\n",
            "### Target Header Summary & Type Definitions:"
        ]

        if header_context.structs:
            prompt_lines.append("\n**Key Structs:**")
            for s in header_context.structs:
                prompt_lines.append(s.raw_decl if s.raw_decl else f"typedef struct {{ ... }} {s.name};")

        if header_context.enums:
            prompt_lines.append("\n**Enums:**")
            for e in header_context.enums:
                members_str = ", ".join([f"{k}={v}" if v is not None else k for k, v in e.members.items()])
                prompt_lines.append(f"typedef enum {{ {members_str} }} {e.name};")

        if header_context.mmio_registers:
            prompt_lines.append("\n**Detected MMIO Registers (Must be mocked!):**")
            for r in header_context.mmio_registers:
                prompt_lines.append(f"- {r.name} = {r.address}")

        if header_context.magic_constants:
            prompt_lines.append("\n**Header Magic Constants:**")
            for k, v in header_context.magic_constants.items():
                prompt_lines.append(f"- {k} = {v}")

        if risk_score and risk_score.memory_operations:
            prompt_lines.append(f"\n**Vulnerability Insights:**")
            prompt_lines.append(f"- Risk Score: {risk_score.risk_score}")
            prompt_lines.append(f"- Analysis: {risk_score.justification}")

        prompt_lines.append("\n### Instructions:")
        prompt_lines.append(f"1. Generate a complete `fuzz_driver.cpp` that fuzzes `{target_api.name}`.")
        prompt_lines.append("2. Implement mock stubs for hardware register read/write functions.")
        prompt_lines.append("3. Properly initialize any context struct, call the target API with fuzzer data, and cleanup.")
        prompt_lines.append("4. Output complete, compilable C++ code.")

        return "\n".join(prompt_lines)

    @staticmethod
    def build_repair_prompt(
        current_code: str,
        error_type: str,
        error_message: str,
        diagnostics: List[Dict[str, str]]
    ) -> str:
        diag_str = "\n".join([f"- Line {d.get('line', '?')}: {d.get('message', '')}" for d in diagnostics]) if diagnostics else error_message

        return f"""### Self-Repair Request: Fuzz Harness Compilation/Runtime Error

The previously synthesized fuzz harness failed verification.

**Error Stage**: `{error_type}`

**Compiler / Runtime Diagnostics**:
```text
{error_message}
```

**Diagnostic Details**:
{diag_str}

**Current Failing Code**:
```cpp
{current_code}
```

### Instructions to Fix:
1. Analyze the exact diagnostic messages, missing types, undeclared symbols, or dynamic crash traces.
2. Correct missing includes, parameter type mismatches, missing mock implementations, or improper memory bounds.
3. Output the completely fixed, compilable C++ code inside a single ```cpp ... ``` block."""
