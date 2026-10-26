#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdlib.h>
#include <vector>
#include <fuzzer/FuzzedDataProvider.h>
#include "pl011_enable.h"

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

    struct pl011_data dev_data;
    memset(&dev_data, 0, sizeof(dev_data));
    struct pl011_regs dev_regs;
    memset(&dev_regs, 0, sizeof(dev_regs));
    mock_regs_ptr = &dev_regs;
    struct device dev_obj;
    memset(&dev_obj, 0, sizeof(dev_obj));
    dev_obj.data = &dev_data;

    pl011_enable(&dev_obj);

    return 0;
}