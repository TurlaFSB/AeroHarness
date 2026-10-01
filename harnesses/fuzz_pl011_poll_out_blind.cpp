// BLIND-BASELINE VARIANT (Section B item 2 ablation, Oct 1 2026).
// See fuzz_pl011_poll_in_blind.cpp for the full rationale. Same change here:
// the informed harness bitextracts PL011_FR_TXFF into data[0]; this variant
// raw-memcpy's the whole register struct with no field-level reasoning.
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <assert.h>
#include <string.h>

// === ZEPHYR STUBS ===
#define DEVICE_MMIO_RAM
#define BIT(n) (1UL << (n))

struct uart_config {
    int baudrate;
    int parity;
    int stop_bits;
    int data_bits;
    int flow_ctrl;
};

struct device {
    void *data;
    const void *config;
};

extern volatile void *mock_regs_ptr;
#define DEVICE_MMIO_GET(dev) (mock_regs_ptr)

// === INCLUDE REGISTERS ===
#include "../zephyr-src/drivers/serial/uart_pl011_registers.h"

// === PL011 STRUCTS ===
struct pl011_data {
    DEVICE_MMIO_RAM;
    struct uart_config uart_cfg;
    bool sbsa;
    uint32_t clk_freq;
};

// === TARGET FUNCTIONS (byte-for-byte identical to the informed harness) ===
static void pl011_poll_out(const struct device *dev, unsigned char c)
{
    volatile struct pl011_regs *uart = get_uart(dev);

    /* Wait for space in FIFO */
    while (uart->fr & PL011_FR_TXFF) {
        ; /* Wait */
    }

    /* Send a character */
    uart->dr = (uint32_t)c;
}

// === LIBFUZZER HARNESS (BLIND MMIO CONSTRUCTION) ===
volatile void *mock_regs_ptr;

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    // sizeof(struct pl011_regs) raw bytes for the register blob + 1 byte for
    // the function-argument character `c` (a Stage-1 signature fact shared
    // by both conditions, not a Stage 2/3 MMIO model).
    if (size < sizeof(struct pl011_regs) + 1) {
        return 0;
    }

    // 1. Mock software state
    struct pl011_data pl_data;
    memset(&pl_data, 0, sizeof(pl_data));

    // 2. BLIND hardware MMIO registers: raw memcpy, no per-field model.
    //    NOTE: because PL011_FR_TXFF (bit 5 of byte 0 of `regs`, since fr is
    //    the second word after dr+union+reserved_0[4]) is now fuzzer-
    //    controlled with no isolation hint, libFuzzer must *discover* via
    //    coverage feedback alone that this single bit gates an infinite
    //    busy-wait loop -- exactly the discovery cost the informed harness's
    //    bitextract model was built to avoid.
    struct pl011_regs regs;
    memcpy(&regs, data, sizeof(regs));

    mock_regs_ptr = &regs;

    struct device dev;
    dev.data = &pl_data;

    // 3. Call Target
    unsigned char c = data[sizeof(regs)];
    pl011_poll_out(&dev, c);

    // 4. Sanity Behavior Assertion (unchanged)
    assert(regs.dr == (uint32_t)c);

    return 0;
}
