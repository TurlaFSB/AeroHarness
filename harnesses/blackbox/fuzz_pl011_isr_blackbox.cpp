// BLACKBOX-BASELINE VARIANT (Work Plan item 3, Oct 2 2026).
// See fuzz_pl011_poll_out_blackbox.cpp for the full rationale and explicit
// scope note. Same two removals relative to the blind condition: no
// minimum-size guard (zero-pad instead of reject), no semantic correctness
// assertion (crash-only oracle).
//
// One necessary, explicitly-flagged exception: `irq_cb` is a function
// pointer. Raw-memcpy'ing fuzzer-controlled garbage directly onto it would
// make the harness jump to an arbitrary address on a non-NULL byte pattern
// -- a harness memory-safety artifact, not a signal about the target
// function. Exactly like the blind condition, a single fixed bit (byte 0,
// bit 0) chooses between NULL and one fixed dummy callback. This is a
// safety-driven exception, not a reintroduction of per-field reasoning:
// the position is fixed arbitrarily (first byte), not selected because
// it is known to be behaviorally significant.
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <string.h>
#include <algorithm>

struct device;
typedef void (*uart_irq_callback_user_data_t)(const struct device *dev, void *user_data);

struct k_spinlock { int lock; };
#define K_SPINLOCK(x) for(int _i=0; _i<1; _i++)

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

#include "../../zephyr-src/drivers/serial/uart_pl011_registers.h"

struct pl011_data {
    DEVICE_MMIO_RAM;
    struct uart_config uart_cfg;
    bool sbsa;
    uint32_t clk_freq;

    uart_irq_callback_user_data_t irq_cb;
    struct k_spinlock irq_cb_lock;
    void *irq_cb_data;
};

// === TARGET FUNCTION (byte-for-byte identical to the informed/blind harnesses) ===
static void pl011_isr(const struct device *dev)
{
    struct pl011_data *data = (struct pl011_data *)dev->data;
    volatile struct pl011_regs *uart = get_uart(dev);

    if (uart->mis & PL011_IMSC_CTSMIM) {
        uart->icr = PL011_IMSC_CTSMIM;
        uart->imsc &= ~PL011_IMSC_CTSMIM;
    }

    if (uart->mis & PL011_IMSC_ERROR_MASK) {
        uart->icr = uart->mis & PL011_IMSC_ERROR_MASK;
    }

    if (data->irq_cb) {
        K_SPINLOCK(&data->irq_cb_lock) {
            data->irq_cb(dev, data->irq_cb_data);
        }
    }
}

// === LIBFUZZER HARNESS (BLACKBOX: no size guard, no correctness oracle) ===
volatile void *mock_regs_ptr;

static void dummy_irq_cb(const struct device *dev, void *user_data) {
    (void)dev;
    (void)user_data;
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    struct pl011_data pl_data;
    memset(&pl_data, 0, sizeof(pl_data));

    // Memory-safety exception explained in the file header above.
    pl_data.irq_cb = (size > 0 && (data[0] & 1)) ? dummy_irq_cb : nullptr;

    struct pl011_regs regs;
    memset(&regs, 0, sizeof(regs));

    size_t avail = (size > 1) ? (size - 1) : 0;
    size_t reg_bytes = std::min(avail, sizeof(regs));
    if (reg_bytes > 0) {
        memcpy(&regs, data + 1, reg_bytes);
    }

    mock_regs_ptr = &regs;

    struct device dev;
    dev.data = &pl_data;

    pl011_isr(&dev);

    // No correctness assertion -- crash-only oracle (ASan/UBSan).
    return 0;
}
