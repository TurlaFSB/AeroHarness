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

// === TARGET FUNCTIONS ===
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

// === LIBFUZZER HARNESS ===
volatile void *mock_regs_ptr;

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (size < 2) {
        return 0; // Need at least 2 bytes of entropy
    }

    // 1. Mock software state
    struct pl011_data pl_data;
    memset(&pl_data, 0, sizeof(pl_data));
    
    // 2. Mock hardware MMIO registers
    struct pl011_regs regs;
    memset(&regs, 0, sizeof(regs));
    
    // FR Model: bitextract for TXFF flag (bit 5)
    // NOTE: Because this is a static mock structure, if TXFF is set (1),
    // the target function will infinite loop. LibFuzzer will quickly timeout
    // on such inputs and learn to provide inputs where TXFF is 0.
    regs.fr = data[0] & PL011_FR_TXFF;
    
    mock_regs_ptr = &regs;

    struct device dev;
    dev.data = &pl_data;

    // 3. Call Target
    unsigned char c = data[1];
    pl011_poll_out(&dev, c);

    // 4. Sanity Behavior Assertion
    // For a write path, the character c should be written exactly to the DR register.
    assert(regs.dr == (uint32_t)c);

    return 0;
}
