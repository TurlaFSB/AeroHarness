#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <assert.h>
#include <string.h>

// === ZEPHYR STUBS ===
#define DEVICE_MMIO_RAM
#define BIT(n) (1UL << (n))

struct device;
typedef void (*uart_irq_callback_user_data_t)(const struct device *dev, void *user_data);

struct k_spinlock { int lock; };
#define K_SPINLOCK(x) for(int _i=0; _i<1; _i++)

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
    
    // Extra fields for IRQ
    uart_irq_callback_user_data_t irq_cb;
    struct k_spinlock irq_cb_lock;
    void *irq_cb_data;
};

// === TARGET FUNCTIONS ===
static void pl011_isr(const struct device *dev)
{
    struct pl011_data *data = (struct pl011_data *)dev->data;
    volatile struct pl011_regs *uart = get_uart(dev);

    /* Clear CTS modem status interrupt and disable it */
    if (uart->mis & PL011_IMSC_CTSMIM) {
        uart->icr = PL011_IMSC_CTSMIM;
        uart->imsc &= ~PL011_IMSC_CTSMIM;
    }

    /* Clear error interrupts (OE, BE, PE, FE) so they don't
     * re-fire endlessly.  The error status is still available
     * via uart_err_check() which reads RSR.
     */
    if (uart->mis & PL011_IMSC_ERROR_MASK) {
        uart->icr = uart->mis & PL011_IMSC_ERROR_MASK;
    }

    /* Verify if the callback has been registered */
    if (data->irq_cb) {
        K_SPINLOCK(&data->irq_cb_lock) {
            data->irq_cb(dev, data->irq_cb_data);
        }
    }
}

// === LIBFUZZER HARNESS ===
volatile void *mock_regs_ptr;

// Global to verify callback execution
static bool cb_called = false;
static void dummy_irq_cb(const struct device *dev, void *user_data) {
    cb_called = true;
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (size < 3) {
        return 0;
    }

    struct pl011_data pl_data;
    memset(&pl_data, 0, sizeof(pl_data));
    
    if (data[0] & 1) {
        pl_data.irq_cb = dummy_irq_cb;
    } else {
        pl_data.irq_cb = NULL;
    }
    
    struct pl011_regs regs;
    memset(&regs, 0, sizeof(regs));
    regs.mis = data[1] & (PL011_IMSC_CTSMIM | PL011_IMSC_ERROR_MASK);
    regs.imsc = data[2];
    
    mock_regs_ptr = &regs;

    struct device dev;
    dev.data = &pl_data;

    cb_called = false;

    pl011_isr(&dev);

    if (pl_data.irq_cb != NULL) {
        assert(cb_called == true);
    } else {
        assert(cb_called == false);
    }

    if (regs.mis & PL011_IMSC_CTSMIM) {
        // Due to two separate direct assignments to uart->icr in the driver,
        // the second one clobbers the first in our static struct mock.
        // On real hardware (W1C), two writes work perfectly, but here we only see the last write.
        if (!(regs.mis & PL011_IMSC_ERROR_MASK)) {
            assert(regs.icr & PL011_IMSC_CTSMIM);
        }
        assert((regs.imsc & PL011_IMSC_CTSMIM) == 0);
    }

    return 0;
}
