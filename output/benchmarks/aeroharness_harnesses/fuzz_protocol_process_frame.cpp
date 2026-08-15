#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdlib.h>
#include <vector>
#include <fuzzer/FuzzedDataProvider.h>
#include "protocol_parser.h"

// ============================================================================
// AeroHarness Auto-Generated MMIO & Hardware Stubs
// ============================================================================
static uint32_t g_mock_hw_status = 0xFFFFFFFF; // Default all flags ready
static uint32_t g_mock_hw_control = 0x00000000;
static uint32_t g_mock_hw_data = 0x00000000;

extern "C" uint32_t hw_read_reg32(uint32_t addr) {
    switch (addr) {
        case MMIO_HW_STATUS_REG: return g_mock_hw_status;
        case MMIO_HW_CONTROL_REG: return g_mock_hw_control;
        case MMIO_HW_DATA_REG: return g_mock_hw_data;
        default:
            return 0x00000001; // Return active/ready for unknown registers
    }
}

extern "C" void hw_write_reg32(uint32_t addr, uint32_t val) {
    switch (addr) {
        case 0x40001004U: g_mock_hw_control = val; break;
        case 0x40001008U: g_mock_hw_data = val; break;
        default: break;
    }
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (size < 4) {
        return 0;
    }

    protocol_process_frame(size);

    return 0;
}