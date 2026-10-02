// BLACKBOX-BASELINE VARIANT (Work Plan item 3, Oct 2 2026).
// See fuzz_pl011_poll_out_blackbox.cpp for the full rationale and explicit
// scope note. Same two removals relative to the blind condition: no
// minimum-size guard (zero-pad instead of reject), no semantic correctness
// assertion (crash-only oracle).
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <string.h>
#include <algorithm>

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
};

// === TARGET FUNCTIONS (byte-for-byte identical to the informed/blind harnesses) ===
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

    *c = (unsigned char)uart->dr;

    return 0;
}

// === LIBFUZZER HARNESS (BLACKBOX: no size guard, no correctness oracle) ===
volatile void *mock_regs_ptr;

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    struct pl011_data pl_data;
    memset(&pl_data, 0, sizeof(pl_data));
    // Software-state byte still consumed from a fixed position (byte 0, bit
    // 0) for the same reason the blind condition did -- a harness has to
    // consume its input in *some* fixed order. This is not a claim that
    // byte 0 was chosen because it's "the important field"; it is simply
    // the first byte in sequential consumption order.
    pl_data.sbsa = (size > 0) ? (data[0] & 1) : 0;

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

    unsigned char c = 0xFF;
    pl011_poll_in(&dev, &c);

    // No correctness assertion -- crash-only oracle (ASan/UBSan).
    return 0;
}
