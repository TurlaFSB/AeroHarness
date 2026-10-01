
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <assert.h>
#include <string.h>

#define DEVICE_MMIO_RAM
#define BIT(n) (1UL << (n))

struct uart_config {
    int baudrate; int parity; int stop_bits; int data_bits; int flow_ctrl;
};
struct device { void *data; const void *config; };
extern volatile void *mock_regs_ptr;
#define DEVICE_MMIO_GET(dev) (mock_regs_ptr)
#include "../zephyr-src/drivers/serial/uart_pl011_registers.h"
struct pl011_data {
    DEVICE_MMIO_RAM; struct uart_config uart_cfg; bool sbsa; uint32_t clk_freq;
};


static int pl011_err_check(const struct device *dev) {
    volatile struct pl011_regs *uart = get_uart(dev);
    uint32_t rsr = uart->rsr;
    int errors = 0;
    if (rsr & PL011_RSR_OE) errors |= 1;
    if (rsr & PL011_RSR_PE) errors |= 2;
    if (rsr & PL011_RSR_FE) errors |= 4;
    if (rsr & PL011_RSR_BE) errors |= 8;
    uart->rsr = 0; // Clear
    return errors;
}


volatile void *mock_regs_ptr;

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (size < 12) return 0;
    struct pl011_data pl_data; memset(&pl_data, 0, sizeof(pl_data));
    struct pl011_regs regs; memset(&regs, 0, sizeof(regs));
    
    pl_data.clk_freq = data[0] | (data[1] << 8) | (data[2] << 16) | (data[3] << 24);
    regs.cr = data[4];
    regs.fr = data[5];
    regs.rsr = data[6];
    regs.ibrd = data[7];
    regs.fbrd = data[8];
    regs.lcr_h = data[9];
    
    mock_regs_ptr = &regs;
    struct device dev; dev.data = &pl_data;
    
    pl011_err_check(&dev);
    
    return 0;
}
