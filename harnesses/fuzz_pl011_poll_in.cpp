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

// === LIBFUZZER HARNESS ===
volatile void *mock_regs_ptr;

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (size < 4) {
        return 0; // Need at least 4 bytes of entropy
    }

    // 1. Mock software state
    struct pl011_data pl_data;
    memset(&pl_data, 0, sizeof(pl_data));
    pl_data.sbsa = (data[0] & 1);
    
    // 2. Mock hardware MMIO registers based on verified Stage 2/3 models
    struct pl011_regs regs;
    memset(&regs, 0, sizeof(regs));
    
    // DR Model: passthrough (raw fuzzer byte)
    regs.dr = data[1];
    
    // FR Model: bitextract for RXFE flag (bit 4)
    regs.fr = data[2] & PL011_FR_RXFE;
    
    // CR Model: bitextract for UARTEN (bit 0) and RXE (bit 9)
    // We construct the value from data[3] ensuring we only control the relevant bits
    regs.cr = (data[3] & 1) ? PL011_CR_UARTEN : 0;
    regs.cr |= (data[3] & 2) ? PL011_CR_RXE : 0;
    
    mock_regs_ptr = &regs;

    struct device dev;
    dev.data = &pl_data;

    // 3. Call Target
    unsigned char c = 0xFF; // Sentinel value
    int ret = pl011_poll_in(&dev, &c);

    // 4. Sanity Behavior Assertion
    if (ret == 0) {
        // If the function reports success, the character read should exactly match
        // the lower 8 bits of our passthrough DR register.
        assert(c == (unsigned char)regs.dr);
    } else {
        // If it failed, c should remain untouched
        assert(ret == -1);
        assert(c == 0xFF);
    }

    return 0;
}
