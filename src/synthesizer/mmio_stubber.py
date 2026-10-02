"""
MMIO / Hardware Register Stubbing Module for AeroHarness.

Rebuilt from scratch, Oct 2026 (see FAILURE_TAXONOMY.md: `src/synthesizer/mmio_stubber.py`
was imported by `src/synthesizer/agent.py` and re-exported from `src/synthesizer/__init__.py`
but did not exist anywhere in the repository's git history -- confirmed via a direct
`ModuleNotFoundError` and via `git log --all` showing zero prior commits touching this path).
This is a new, independent implementation satisfying the exact interface `agent.py` already
calls (`MMIOStubber().generate_mmio_stubs(header_context.mmio_registers)` inside
`_generate_deterministic_harness`), written against the real `MMIORegister` Pydantic model in
`src/analyzer/c_ast_extractor.py` rather than copied from the `legacy_v1/` implementation, which
that directory's own README already flags as containing fabricated/stubbed components.

Scope note: this module backs only the deterministic offline-fallback synthesis path in
`HarnessSynthesizerAgent` (used when no Gemini client is configured, or when a live call
raises). It has no bearing on, and makes no claims about, the quality of harnesses that Gemini
itself generates -- those are reviewed/verified by the compiler and smoke-test oracles exactly
like any other candidate.
"""
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from src.analyzer.c_ast_extractor import MMIORegister


class MockStubConfig(BaseModel):
    """Configuration knobs for the generated hardware/RTOS mock layer."""

    registers: List[MMIORegister] = Field(default_factory=list)
    stub_freertos: bool = True
    stub_zephyr: bool = True
    # Per-register-name override: caller-supplied C statement(s) returned verbatim
    # instead of the default heuristic value. Keys match MMIORegister.name.
    custom_stubs: Dict[str, str] = Field(default_factory=dict)


class MMIOStubber:
    """
    Generates minimal, compilable C/C++ mock implementations for the hardware register
    accessors and RTOS primitives that embedded firmware source commonly calls, so that a
    fuzz harness linking against real firmware `.c` files can run host-side under
    libFuzzer/ASan without a live device.

    This is deliberately conservative: it provides just enough state (a "ready" bit pattern
    for unknown/status-looking registers, writable backing storage for recognized
    control/data registers) to let the target function execute past initialization checks
    without hanging, not a full behavioral model of any specific peripheral. The informed,
    per-field MMIO modeling used elsewhere in this project (see `ABLATION_B_V2.md`) is a
    separate, much more detailed mechanism built by the synthesis agent itself; this class
    only underlies the *offline fallback* path when no agent call is available.
    """

    # Values chosen so that firmware code polling a status register for a "ready"/"done"
    # bit with a bitwise-AND test observes it set, regardless of which specific bit the
    # real hardware uses -- the common failure mode without this is an infinite poll loop.
    _DEFAULT_STATUS_VALUE = "0xFFFFFFFFU"
    _DEFAULT_UNKNOWN_VALUE = "0x00000001U"

    def __init__(self, config: Optional[MockStubConfig] = None):
        self.config = config or MockStubConfig()

    def generate_mmio_stubs(self, registers: List[MMIORegister]) -> str:
        """
        Emits `extern "C"` definitions for `hw_read_reg32`/`hw_write_reg32`, the two MMIO
        accessor names the synthesis system prompt (`PromptFactory.get_system_prompt`)
        tells the model it may rely on being mocked. Status-like register names read back
        an all-ones "ready" pattern; control/data-like names get real backing storage so a
        write followed by a read observes the written value; anything else reads back a
        fixed nonzero constant (never zero, since a zero/not-ready readback is the most
        common cause of an infinite hardware-poll loop in a host-side harness).
        """
        reg_names = {r.name for r in registers}
        backing_decls: List[str] = []
        read_cases: List[str] = []
        write_cases: List[str] = []

        for reg in registers:
            override = self.config.custom_stubs.get(reg.name)
            if override is not None:
                read_cases.append(f"        case {reg.name}: {{ {override} }}")
                continue

            upper = reg.name.upper()
            backing_var = f"g_mmio_{reg.name.lower()}"

            if "STATUS" in upper or "READY" in upper or "FLAG" in upper:
                read_cases.append(f"        case {reg.name}: return {self._DEFAULT_STATUS_VALUE};")
            elif "CONTROL" in upper or "CTRL" in upper or "DATA" in upper or "CFG" in upper:
                backing_decls.append(f"static uint32_t {backing_var} = 0x00000000U;")
                read_cases.append(f"        case {reg.name}: return {backing_var};")
                write_cases.append(f"        case {reg.name}: {backing_var} = val; break;")
            else:
                read_cases.append(f"        case {reg.name}: return {self._DEFAULT_UNKNOWN_VALUE};")

        lines: List[str] = [
            "// ===========================================================================",
            "// AeroHarness MMIO stubs (deterministic offline fallback synthesizer)",
            "// ===========================================================================",
        ]
        lines.extend(backing_decls)
        if backing_decls:
            lines.append("")

        lines.append('extern "C" uint32_t hw_read_reg32(uint32_t addr) {')
        lines.append("    switch (addr) {")
        lines.extend(read_cases)
        lines.append("        default:")
        lines.append(f"            return {self._DEFAULT_UNKNOWN_VALUE}; // unknown register: assume active/ready")
        lines.append("    }")
        lines.append("}")
        lines.append("")
        lines.append('extern "C" void hw_write_reg32(uint32_t addr, uint32_t val) {')
        lines.append("    switch (addr) {")
        lines.extend(write_cases)
        lines.append("        default: break;")
        lines.append("    }")
        lines.append("}")

        if not reg_names:
            lines.append("")
            lines.append("// (No MMIO registers were detected in the target header; the switch")
            lines.append("//  statements above are intentionally empty/default-only.)")

        return "\n".join(lines)

    def generate_rtos_stubs(self) -> str:
        """
        Emits no-op host-side replacements for the small set of FreeRTOS/Zephyr kernel
        primitives embedded firmware most commonly calls for timing/yielding (never actual
        scheduling), so that firmware code written for a real RTOS can still link and run
        synchronously inside a single-threaded libFuzzer process. Gated by
        `MockStubConfig.stub_freertos`/`stub_zephyr`.
        """
        blocks: List[str] = [
            "// ===========================================================================",
            "// AeroHarness RTOS kernel stubs (host-compatible, no-op scheduling)",
            "// ===========================================================================",
        ]

        if self.config.stub_freertos:
            blocks.append(
                'extern "C" {\n'
                "    void vTaskDelay(uint32_t ticks) { (void)ticks; }\n"
                "    void taskYIELD(void) {}\n"
                "}"
            )

        if self.config.stub_zephyr:
            blocks.append(
                'extern "C" {\n'
                "    void k_sleep(int32_t ms) { (void)ms; }\n"
                "    void k_yield(void) {}\n"
                "    void k_busy_wait(uint32_t usec) { (void)usec; }\n"
                "}"
            )

        return "\n\n".join(blocks) + "\n"
