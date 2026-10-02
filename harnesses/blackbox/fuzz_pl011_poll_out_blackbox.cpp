// BLACKBOX-BASELINE VARIANT (Work Plan item 3, Oct 2 2026).
//
// Distinct from fuzz_pl011_poll_out_blind.cpp (the Oct 1 "informed vs blind"
// ablation, which removed per-field MMIO modeling but kept two things that
// still encode domain knowledge: a minimum-input-size guard, and a
// semantic correctness assertion). This variant removes those two as well,
// leaving the absolute minimum of engineering judgment this project's
// infrastructure can support while still calling the real, unmodified
// target function:
//   - No minimum-size guard. Short inputs are zero-padded, not rejected --
//     a true blackbox fuzzer has no way to know how many bytes "matter".
//   - No semantic/behavioral correctness assertion. The only oracle is
//     ASan/UBSan crash detection, exactly as a fuzzer with no model of
//     "correct" output would operate.
//   - Register construction remains whole-struct memcpy (inherited from
//     the blind condition -- this project's infrastructure cannot call
//     the real, unmodified driver source without *some* backing memory for
//     its struct-typed register accesses, so this is the practical floor,
//     not a remaining semantic choice).
//
// Explicit scope note: this is the closest feasible approximation of a
// "no semantic harness" baseline with this project's current, per-function
// harness infrastructure -- NOT a literal zero-knowledge fuzzer that
// doesn't even know which function to call. A fully faithful blackbox
// baseline (fuzzing the compiled firmware with generic MMIO stubbing, no
// source-level target selection at all) is a materially larger undertaking
// and is explicitly scoped separately as the Fuzzware head-to-head
// (Work Plan item 7), not claimed here.
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <string.h>
#include <algorithm>

// === ZEPHYR STUBS (structural necessity to compile the real driver source
// unmodified -- not a semantic model of valid input, same as every other
// condition in this project) ===
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

// === INCLUDE REGISTERS (real, unmodified) ===
#include "../../zephyr-src/drivers/serial/uart_pl011_registers.h"

struct pl011_data {
    DEVICE_MMIO_RAM;
    struct uart_config uart_cfg;
    bool sbsa;
    uint32_t clk_freq;
};

// === TARGET FUNCTION (byte-for-byte identical to the informed/blind harnesses) ===
static void pl011_poll_out(const struct device *dev, unsigned char c)
{
    volatile struct pl011_regs *uart = get_uart(dev);

    while (uart->fr & PL011_FR_TXFF) {
        ; /* Wait */
    }

    uart->dr = (uint32_t)c;
}

// === LIBFUZZER HARNESS (BLACKBOX: no size guard, no correctness oracle) ===
volatile void *mock_regs_ptr;

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    // Zero-init is a memory-safety requirement (uninitialized-read ASan
    // noise would just be a harness artifact), not a semantic model.
    struct pl011_data pl_data;
    memset(&pl_data, 0, sizeof(pl_data));

    struct pl011_regs regs;
    memset(&regs, 0, sizeof(regs));

    // No minimum-size rejection: copy whatever is available (possibly 0
    // bytes), zero-padding the rest.
    size_t reg_bytes = std::min(size, sizeof(regs));
    memcpy(&regs, data, reg_bytes);

    mock_regs_ptr = &regs;

    struct device dev;
    dev.data = &pl_data;

    // Argument `c`: next byte after the register blob if available, else 0.
    unsigned char c = (size > sizeof(regs)) ? data[sizeof(regs)] : 0;

    pl011_poll_out(&dev, c);

    // No correctness assertion -- crash-only oracle (ASan/UBSan).
    return 0;
}
