import os

POLL_IN_BASE = """
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

static bool pl011_is_readable(const struct device *dev) {
    struct pl011_data *data = (struct pl011_data *)dev->data;
    volatile struct pl011_regs *uart = get_uart(dev);
    uint32_t cr = uart->cr;
    if (!data->sbsa && (!(cr & PL011_CR_UARTEN) || !(cr & PL011_CR_RXE))) return false;
    return (uart->fr & PL011_FR_RXFE) == 0U;
}

static int pl011_poll_in(const struct device *dev, unsigned char *c) {
    volatile struct pl011_regs *uart = get_uart(dev);
    if (!pl011_is_readable(dev)) return -1;
    *c = (unsigned char)uart->dr;
    return 0;
}

volatile void *mock_regs_ptr;

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (size < 4) return 0;
    struct pl011_data pl_data; memset(&pl_data, 0, sizeof(pl_data));
    struct pl011_regs regs; memset(&regs, 0, sizeof(regs));
    
    // DEFAULT FIXED VALUES
    pl_data.sbsa = 1;
    regs.cr = PL011_CR_UARTEN | PL011_CR_RXE;
    regs.fr = 0;
    regs.dr = 0xAA;
    
    // INJECT FUZZ MUTATIONS
    {INJECTIONS}
    
    mock_regs_ptr = &regs;
    struct device dev; dev.data = &pl_data;
    unsigned char c = 0xFF;
    pl011_poll_in(&dev, &c);
    return 0;
}
"""

POLL_OUT_BASE = """
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

static void pl011_poll_out(const struct device *dev, unsigned char c) {
    volatile struct pl011_regs *uart = get_uart(dev);
    while (uart->fr & PL011_FR_TXFF) {}
    uart->dr = c;
}

volatile void *mock_regs_ptr;

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (size < 4) return 0;
    struct pl011_data pl_data; memset(&pl_data, 0, sizeof(pl_data));
    struct pl011_regs regs; memset(&regs, 0, sizeof(regs));
    
    regs.fr = 0; // Not busy by default
    unsigned char out_char = 0xBB;
    
    {INJECTIONS}
    
    mock_regs_ptr = &regs;
    struct device dev; dev.data = &pl_data;
    pl011_poll_out(&dev, out_char);
    return 0;
}
"""

ISR_BASE = """
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <assert.h>
#include <string.h>

#define DEVICE_MMIO_RAM
#define BIT(n) (1UL << (n))

struct device;
typedef void (*uart_irq_callback_user_data_t)(const struct device *dev, void *user_data);

struct k_spinlock { int lock; };
#define K_SPINLOCK(x) for(int _i=0; _i<1; _i++)

struct uart_config {
    int baudrate; int parity; int stop_bits; int data_bits; int flow_ctrl;
};

struct device {
    void *data; const void *config;
};

extern volatile void *mock_regs_ptr;
#define DEVICE_MMIO_GET(dev) (mock_regs_ptr)
#include "../zephyr-src/drivers/serial/uart_pl011_registers.h"

struct pl011_data {
    DEVICE_MMIO_RAM;
    struct uart_config uart_cfg;
    bool sbsa;
    uint32_t clk_freq;
    uart_irq_callback_user_data_t irq_cb;
    struct k_spinlock irq_cb_lock;
    void *irq_cb_data;
};

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

volatile void *mock_regs_ptr;

static bool cb_called = false;
static void dummy_irq_cb(const struct device *dev, void *user_data) {
    cb_called = true;
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (size < 4) return 0;
    struct pl011_data pl_data; memset(&pl_data, 0, sizeof(pl_data));
    struct pl011_regs regs; memset(&regs, 0, sizeof(regs));
    
    regs.mis = 0;
    regs.imsc = 0;
    pl_data.irq_cb = NULL;
    
    {INJECTIONS}
    
    mock_regs_ptr = &regs;
    struct device dev; dev.data = &pl_data;
    cb_called = false;
    pl011_isr(&dev);
    return 0;
}
"""

TARGETS = [
    # Poll In (5 targets, all 1.0x)
    ("target_poll_in_sbsa", POLL_IN_BASE, "pl_data.sbsa = data[0] & 1;"),
    ("target_poll_in_cr_uarten", POLL_IN_BASE, "pl_data.sbsa = 0; regs.cr = (data[0] & 1) ? PL011_CR_UARTEN : 0; regs.cr |= PL011_CR_RXE;"),
    ("target_poll_in_cr_rxe", POLL_IN_BASE, "pl_data.sbsa = 0; regs.cr = PL011_CR_UARTEN; regs.cr |= (data[0] & 1) ? PL011_CR_RXE : 0;"),
    ("target_poll_in_fr_rxfe", POLL_IN_BASE, "regs.fr = data[0] & PL011_FR_RXFE;"),
    ("target_poll_in_dr", POLL_IN_BASE, "regs.dr = data[0];"),
    
    # Poll Out (2 targets, fr=3.0x, dr=1.0x)
    ("target_poll_out_fr_txff", POLL_OUT_BASE, "regs.fr = (data[0] & 1) ? PL011_FR_TXFF : 0;"),
    ("target_poll_out_dr", POLL_OUT_BASE, "out_char = data[0];"),
    
    # ISR (5 targets, w1c_clobber=3.0x, others 1.0x)
    ("target_isr_ctsmim", ISR_BASE, "regs.mis = (data[0] & 1) ? PL011_IMSC_CTSMIM : 0;"),
    ("target_isr_error", ISR_BASE, "regs.mis = (data[0] & 1) ? PL011_IMSC_ERROR_MASK : 0;"),
    ("target_isr_w1c_clobber", ISR_BASE, "regs.mis = (data[0] & 1) ? (PL011_IMSC_CTSMIM | PL011_IMSC_ERROR_MASK) : 0;"),
    ("target_isr_imsc", ISR_BASE, "regs.imsc = data[0];"),
    ("target_isr_irq_cb", ISR_BASE, "pl_data.irq_cb = (data[0] & 1) ? dummy_irq_cb : NULL;")
]

os.makedirs("targets", exist_ok=True)
for name, base, inj in TARGETS:
    code = base.replace("{INJECTIONS}", inj)
    with open(f"targets/{name}.cpp", "w") as f:
        f.write(code)

with open("build_targets.sh", "w") as f:
    for name, _, _ in TARGETS:
        f.write(f"clang++ -g -fsanitize=fuzzer,address -Iharnesses/include targets/{name}.cpp -o targets/{name}\n")

print("Generated targets.")
