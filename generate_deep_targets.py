import os

BASE = """
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

{TARGET_FUNC}

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
    
    {INVOCATION}
    
    return 0;
}
"""

TARGET_SET_BAUDRATE = """
static int pl011_set_baudrate(const struct device *dev, uint32_t baudrate) {
    struct pl011_data *data = (struct pl011_data *)dev->data;
    volatile struct pl011_regs *uart = get_uart(dev);
    uint32_t clk = data->clk_freq;
    if (baudrate == 0) return -1;
    uint32_t baud_div = (clk * 4) / baudrate;
    if (baud_div == 0) return -1;
    uart->ibrd = baud_div >> 6;
    uart->fbrd = baud_div & 0x3F;
    uart->lcr_h |= PL011_LCRH_FEN;
    return 0;
}
"""

TARGET_ERR_CHECK = """
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
"""

TARGET_FIFO_FILL = """
static int pl011_fifo_fill(const struct device *dev, const uint8_t *tx_data, int size) {
    volatile struct pl011_regs *uart = get_uart(dev);
    int num_tx = 0;
    while ((size - num_tx) > 0) {
        if (uart->fr & PL011_FR_TXFF) break;
        uart->dr = tx_data[num_tx++];
    }
    return num_tx;
}
"""

os.makedirs("deep_targets", exist_ok=True)
import shutil

shutil.copy("harnesses/fuzz_pl011_poll_in.cpp", "deep_targets/fuzz_pl011_poll_in.cpp")
shutil.copy("harnesses/fuzz_pl011_poll_out.cpp", "deep_targets/fuzz_pl011_poll_out.cpp")
shutil.copy("harnesses/fuzz_pl011_isr.cpp", "deep_targets/fuzz_pl011_isr.cpp")

with open("deep_targets/fuzz_pl011_set_baudrate.cpp", "w") as f:
    f.write(BASE.replace("{TARGET_FUNC}", TARGET_SET_BAUDRATE).replace("{INVOCATION}", "pl011_set_baudrate(&dev, data[10] | (data[11] << 8));"))

with open("deep_targets/fuzz_pl011_err_check.cpp", "w") as f:
    f.write(BASE.replace("{TARGET_FUNC}", TARGET_ERR_CHECK).replace("{INVOCATION}", "pl011_err_check(&dev);"))

with open("deep_targets/fuzz_pl011_fifo_fill.cpp", "w") as f:
    f.write(BASE.replace("{TARGET_FUNC}", TARGET_FIFO_FILL).replace("{INVOCATION}", "pl011_fifo_fill(&dev, data + 10, size - 10);"))

with open("build_deep_targets.sh", "w") as f:
    for name in ["poll_in", "poll_out", "isr", "set_baudrate", "err_check", "fifo_fill"]:
        f.write(f"clang++ -g -fsanitize=fuzzer,address -Iharnesses/include deep_targets/fuzz_pl011_{name}.cpp -o deep_targets/target_{name}\n")

print("Generated deep targets.")
