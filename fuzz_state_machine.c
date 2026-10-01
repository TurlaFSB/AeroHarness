#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <assert.h>
#include <string.h>

#define EINVAL 22
#define ENOTSUP 95

#define UART_ERROR_OVERRUN (1 << 0)
#define UART_ERROR_PARITY  (1 << 1)
#define UART_ERROR_FRAMING (1 << 2)
#define UART_BREAK         (1 << 3)

#define UART_CFG_PARITY_NONE 0
#define UART_CFG_PARITY_ODD  1
#define UART_CFG_PARITY_EVEN 2
#define UART_CFG_STOP_BITS_1 1
#define UART_CFG_STOP_BITS_2 2
#define UART_CFG_DATA_BITS_5 5
#define UART_CFG_DATA_BITS_6 6
#define UART_CFG_DATA_BITS_7 7
#define UART_CFG_DATA_BITS_8 8
#define UART_CFG_FLOW_CTRL_NONE 0
#define UART_CFG_FLOW_CTRL_RTS_CTS 1

/* Zephyr Mocks and MMIO Stubs */
#define DEVICE_MMIO_RAM
#define DEVICE_MMIO_ROM
#define BIT(n) (1UL << (n))
#define FIELD_PREP(mask, val) (((val) << (__builtin_ctzll(mask))) & (mask))
#define GENMASK(h, l) \
	(((~0UL) - (1UL << (l)) + 1) & (~0UL >> (63 - (h))))

struct uart_config {
    int baudrate; int parity; int stop_bits; int data_bits; int flow_ctrl;
};
struct device { void *data; const void *config; };
extern volatile void *mock_regs_ptr;
#define DEVICE_MMIO_GET(dev) (mock_regs_ptr)
#define DEVICE_MMIO_MAP(dev, flags) do { } while(0)
#define irq_enable(irq)
#define irq_disable(irq)
#define K_SPINLOCK(lock) 
#define k_spin_lock(lock) 0
#define k_spin_unlock(lock, key)
struct k_spinlock {};
typedef void (*uart_irq_config_func_t)(const struct device *dev);
typedef void (*uart_irq_callback_user_data_t)(const struct device *dev, void *user_data);

#define CONFIG_SERIAL_INIT_PRIORITY 50
#define PRE_KERNEL_1 1

#define DT_HAS_COMPAT_STATUS_OKAY(compat) 0
#define DT_ANY_COMPAT_HAS_PROP_STATUS_OKAY(compat, prop) 1
#define IS_ENABLED(config) 0
#define CONFIG_UART_INTERRUPT_DRIVEN 1

#define __maybe_unused
struct uart_driver_api {
    void *poll_in; void *poll_out; void *err_check; void *configure; void *config_get;
    void *fifo_fill; void *fifo_read; void *irq_tx_enable; void *irq_tx_disable;
    void *irq_tx_ready; void *irq_rx_enable; void *irq_rx_disable; void *irq_tx_complete;
    void *irq_rx_ready; void *irq_err_enable; void *irq_err_disable; void *irq_is_pending;
    void *irq_update; void *irq_callback_set;
};
#define DEVICE_API(type, name) struct uart_driver_api name
#define DT_INST_FOREACH_STATUS_OKAY(mac)

#define barrier_dmem_fence_full() do {} while(0)
#define barrier_isync_fence_full() do {} while(0)

static inline int pwr_on_arm_pl011(const struct device *dev) { return 0; }
static inline int clk_enable_arm_pl011(const struct device *dev, uint32_t clk) { return 0; }
static inline void reset_line_toggle_dt(const void *reset) { }
static inline int clock_control_on(const struct device *dev, int id) { return 0; }
static inline int clock_control_get_rate(const struct device *dev, int id, uint32_t *rate) { *rate = 4000000; return 0; }
static inline int pinctrl_apply_state(const void *pincfg, int state) { return 0; }
#define PINCTRL_STATE_DEFAULT 0

/* Included driver code */
#include "uart_pl011_registers.h"
#include "uart_pl011.c"

volatile void *mock_regs_ptr;

// Dummy callback to let ISR proceed past the null check
void dummy_irq_cb(const struct device *dev, void *user_data) {
    // To prevent infinite loop in the ISR, we simulate the app clearing the interrupt condition,
    // or we just break the loop by clearing the mask manually.
    volatile struct pl011_regs *uart = (volatile struct pl011_regs *)mock_regs_ptr;
    uart->imsc &= ~PL011_IMSC_TXIM; // Clear it to avoid infinite loop
}

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (size < 4) return 0;
    
    struct pl011_data pl_data; memset(&pl_data, 0, sizeof(pl_data));
    struct pl011_config pl_config; memset(&pl_config, 0, sizeof(pl_config));
    struct pl011_regs regs; memset(&regs, 0, sizeof(regs));
    
    // TASK 3: Struct-aware mocking with boundary-valid values
    pl_data.sbsa = 0;
    pl_data.clk_freq = 4000000;
    pl_config.fifo_disable = false;
    pl_data.irq_cb = dummy_irq_cb;
    
    mock_regs_ptr = &regs;
    struct device dev; 
    dev.data = &pl_data;
    dev.config = &pl_config;
    
    bool is_initialized = false;
    
    for (size_t i = 0; i < size; i++) {
        uint8_t cmd = data[i] % 4;
        
        if (i + 1 < size) {
            regs.dr = data[i+1];
            regs.fr = data[i+1];
            // clear the TXFF bit to prevent infinite loop in poll_out, so we can fuzz deeper
            regs.fr &= ~PL011_FR_TXFF; 
        }
        
        if (cmd == 0) {
            pl011_init(&dev);
            is_initialized = true;
        } else if (cmd == 1 && is_initialized) {
            if (i + 1 < size) {
                pl011_poll_out(&dev, data[++i]);
            }
        } else if (cmd == 2 && is_initialized) {
            unsigned char c = 0;
            pl011_poll_in(&dev, &c);
        } else if (cmd == 3 && is_initialized) {
            // Also inject MIS / ICR registers for full ISR coverage
            if (i + 1 < size) {
                regs.mis = data[i+1];
                regs.imsc = data[i+1];
            }
            pl011_isr(&dev);
        }
    }
    
    return 0;
}
