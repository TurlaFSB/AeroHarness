#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdlib.h>
#include <vector>
#include <fuzzer/FuzzedDataProvider.h>
#include "clk_enable_arm_pl011.h"

// ===========================================================================
// AeroHarness MMIO stubs (deterministic offline fallback synthesizer)
// ===========================================================================
extern "C" uint32_t hw_read_reg32(uint32_t addr) {
    switch (addr) {
        default:
            return 0x00000001U; // unknown register: assume active/ready
    }
}

extern "C" void hw_write_reg32(uint32_t addr, uint32_t val) {
    switch (addr) {
        default: break;
    }
}

// (No MMIO registers were detected in the target header; the switch
//  statements above are intentionally empty/default-only.)
extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (size < 4) {
        return 0;
    }

    clk_enable_arm_pl011((const struct device *)0, 0);

    return 0;
}