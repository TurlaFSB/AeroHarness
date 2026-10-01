// BLIND-BASELINE VARIANT (Section B item 2 ablation, Oct 1 2026).
// Identical to fuzz_pl011_poll_in.cpp in every respect EXCEPT how the MMIO
// register struct is populated: the informed harness uses Stage 2/3's
// verified per-field models (passthrough for DR, bitextract for FR/CR bits
// that gate branches). This variant has NO semantic understanding of the
// register layout at all -- it raw-memcpy's fuzzer bytes directly onto the
// whole struct, exactly what an engineer with zero hardware-semantic
// analysis (no Stage 1-3) would write. Same software-state mocking and same
// correctness assertions as the informed harness, so the only thing being
// measured is the effect of informed vs. blind register-value construction.
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
static bool pl011_is_readable(const struct device *dev)
{
    struct pl011_data *data = (struct pl011_data *)dev->data;
    volatile struct pl011_regs *uart = get_uart(dev);
    uint32_t cr = uart->cr;

    if (!data->sbsa &&
        (!(cr & PL011_CR_UARTEN) || !(cr & PL011_CR_RXE))) {
        return false;
    }

    return (uart->fr & PL011_FR_RXFE) == 0U;
}

static int pl011_poll_in(const struct device *dev, unsigned char *c)
{
    volatile struct pl011_regs *uart = get_uart(dev);

    if (!pl011_is_readable(dev)) {
        return -1;
    }

    /* got a character */
    *c = (unsigned char)uart->dr;

    return 0;
}

// === LIBFUZZER HARNESS (BLIND MMIO CONSTRUCTION) ===
volatile void *mock_regs_ptr;

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    // 1 byte for software-state (sbsa) + sizeof(struct pl011_regs) raw bytes
    // for the entire register blob, no field-level reasoning at all.
    if (size < 1 + sizeof(struct pl011_regs)) {
        return 0;
    }

    // 1. Mock software state (unchanged from informed harness -- this is
    //    Stage-1 AST-level struct knowledge, not a Stage 2/3 MMIO model,
    //    so it is not part of what this ablation is testing).
    struct pl011_data pl_data;
    memset(&pl_data, 0, sizeof(pl_data));
    pl_data.sbsa = (data[0] & 1);

    // 2. BLIND hardware MMIO registers: raw memcpy, no per-field model.
    struct pl011_regs regs;
    memcpy(&regs, data + 1, sizeof(regs));

    mock_regs_ptr = &regs;

    struct device dev;
    dev.data = &pl_data;

    // 3. Call Target
    unsigned char c = 0xFF; // Sentinel value
    int ret = pl011_poll_in(&dev, &c);

    // 4. Sanity Behavior Assertion (unchanged -- tests driver correctness,
    //    not the register model, so it must hold under blind inputs too).
    if (ret == 0) {
        assert(c == (unsigned char)regs.dr);
    } else {
        assert(ret == -1);
        assert(c == 0xFF);
    }

    return 0;
}
