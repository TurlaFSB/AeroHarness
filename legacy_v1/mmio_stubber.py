"""
Hardware Abstraction and MMIO Stubbing Module for AeroHarness
Generates C/C++ mock implementations for embedded registers and RTOS functions.
"""
from typing import List, Dict, Optional
from pydantic import BaseModel, Field
from src.analyzer.c_ast_extractor import MMIORegister


class MockStubConfig(BaseModel):
    registers: List[MMIORegister] = Field(default_factory=list)
    stub_freertos: bool = True
    stub_zephyr: bool = True
    custom_stubs: Dict[str, str] = Field(default_factory=dict)


class MMIOStubber:
    """Generates standard C mock implementations for embedded peripheral interactions."""

    def __init__(self, config: Optional[MockStubConfig] = None):
        self.config = config or MockStubConfig()

    def generate_mmio_stubs(self, registers: List[MMIORegister]) -> str:
        """Generates standard hw_read_reg32 / hw_write_reg32 stubs."""
        code = [
            "// ============================================================================",
            "// AeroHarness Auto-Generated MMIO & Hardware Stubs",
            "// ============================================================================",
            "static uint32_t g_mock_hw_status = 0xFFFFFFFF; // Default all flags ready",
            "static uint32_t g_mock_hw_control = 0x00000000;",
            "static uint32_t g_mock_hw_data = 0x00000000;\n",
            "extern \"C\" uint32_t hw_read_reg32(uint32_t addr) {",
            "    switch (addr) {"
        ]

        for reg in registers:
            if "STATUS" in reg.name:
                code.append(f"        case {reg.name}: return g_mock_hw_status;")
            elif "CONTROL" in reg.name:
                code.append(f"        case {reg.name}: return g_mock_hw_control;")
            elif "DATA" in reg.name:
                code.append(f"        case {reg.name}: return g_mock_hw_data;")
            else:
                code.append(f"        case {reg.name}: return 0x00000001;")

        code.extend([
            "        default:",
            "            return 0x00000001; // Return active/ready for unknown registers",
            "    }",
            "}\n",
            "extern \"C\" void hw_write_reg32(uint32_t addr, uint32_t val) {",
            "    switch (addr) {",
            "        case 0x40001004U: g_mock_hw_control = val; break;",
            "        case 0x40001008U: g_mock_hw_data = val; break;",
            "        default: break;",
            "    }",
            "}\n"
        ])

        return "\n".join(code)

    def generate_rtos_stubs(self) -> str:
        """Generates mock stubs for common FreeRTOS / Zephyr primitives."""
        return """
// ============================================================================
// RTOS Kernel Stubs (Host-Compatible)
// ============================================================================
extern "C" {
    void vTaskDelay(uint32_t ticks) { (void)ticks; }
    void taskYIELD(void) {}
    void k_sleep(int32_t ms) { (void)ms; }
    void k_yield(void) {}
}
"""
