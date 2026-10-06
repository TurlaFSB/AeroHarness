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
        header_filename: str,
        externally_linked: bool = False,
        mmio_convention_note: Optional[str] = None
    ) -> str:
        """
        `externally_linked` (added Oct 2 2026, Work Plan item 2): set this True when the
        target function is a `static`-at-source-but-externally-relinked real driver
        function that will be compiled as its own separate translation unit and linked
        against the harness, rather than something the LLM is expected to define itself.
        Without this, the model has no way to know the function already exists elsewhere,
        and Ablation B v2 already documented this exact failure mode: the model attempting
        to define the target function itself, which the project treats as a genuine compile
        failure (symbol redefinition) rather than something to silently work around -- this
        flag only reduces how often that avoidable failure mode occurs, it does not suppress
        it as a scored outcome if the model does it anyway.

        `mmio_convention_note` (added Oct 2 2026, Work Plan item 2): this system prompt's
        default MMIO guidance (bullet 2, below) steers the model toward writing standalone
        `hw_read_reg32`/`hw_write_reg32`-style accessor functions. That is the wrong
        convention for a target whose real body already calls a fixed accessor like
        `get_uart(dev)` that dereferences a specific global the harness must set, rather
        than calling functions the harness defines -- an externally-linked real function
        cannot be redirected to call whatever mock functions the LLM invents. When set,
        this string is appended verbatim as its own instruction so the actual convention
        in force can be stated exactly (which global, what struct, how to point it) instead
        of silently relying on the generic guidance below, which does not apply.
        """
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
            raw_decl = target_api.raw_declaration or ""
            target_parts = [p.lower() for p in target_api.name.split("_") if len(p) > 2]
            relevant_constants = {
                k: v for k, v in header_context.magic_constants.items()
                if k in raw_decl or any(part in k.lower() for part in target_parts)
            }
            items_to_show = relevant_constants if relevant_constants else dict(list(header_context.magic_constants.items())[:15])
            for k, v in items_to_show.items():
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
        if externally_linked:
            prompt_lines.append(
                f"5. `{target_api.name}` is a real, already-implemented function that will be "
                f"COMPILED SEPARATELY and LINKED against your harness. Do NOT write a body for "
                f"it, and do NOT write your own forward declaration of it either -- the "
                f"`#include \"{header_filename}\"` directive above already declares it with the "
                f"correct signature and linkage, so writing any additional declaration of "
                f"`{target_api.name}` (with or without `extern \"C\"`) will conflict with that "
                f"header declaration and fail to compile. Simply include the header (as "
                f"instructed above) and call `{target_api.name}` directly. Writing your own "
                f"implementation of this function will cause a symbol-redefinition link error."
            )
        if mmio_convention_note:
            prompt_lines.append(f"6. MMIO convention override for this target: {mmio_convention_note}")

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
