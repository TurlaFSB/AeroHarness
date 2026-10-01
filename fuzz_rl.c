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



#include <stdio.h>
#include <math.h>
#include <stdlib.h>

extern uint8_t __start___sancov_cntrs[] __attribute__((weak));
extern uint8_t __stop___sancov_cntrs[] __attribute__((weak));
size_t get_coverage() {
    size_t cov = 0;
    if (__start___sancov_cntrs) {
        for (uint8_t *p = __start___sancov_cntrs; p < __stop___sancov_cntrs; p++) {
            if (*p) cov++;
        }
    }
    return cov;
}

#define NUM_STATES 100 // 2 (is_init) * 5 (prev_cmd) * 10 (step)
#define NUM_ACTIONS 4  // 0=init, 1=poll_in, 2=poll_out, 3=isr
#define MAX_STEPS 10

static float Q[NUM_STATES][NUM_ACTIONS] = {0};
static int N_s[NUM_STATES] = {0};
static int N_sa[NUM_STATES][NUM_ACTIONS] = {0};
static float V[NUM_STATES][NUM_ACTIONS] = {0}; // empirical mean reward

// Uncertainty weights from Stage 3 data (approximate based on prompt logic)
// init: cr, imsc, icr, dmacr, ifls -> high uncertainty
// poll_in: dr, fr -> moderate
// poll_out: dr, fr -> moderate
// isr: mis, icr, imsc -> high
static const float U_weights[4] = {0.8, 0.4, 0.4, 0.7};

static unsigned long long total_executions = 0;

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (size < 1) return 0;
    
    struct pl011_data pl_data; memset(&pl_data, 0, sizeof(pl_data));
    struct pl011_config pl_config; memset(&pl_config, 0, sizeof(pl_config));
    struct pl011_regs regs; memset(&regs, 0, sizeof(regs));
    
    pl_data.sbsa = 0;
    pl_data.clk_freq = 4000000;
    pl_config.fifo_disable = false;
    pl_data.irq_cb = dummy_irq_cb;
    
    mock_regs_ptr = &regs;
    struct device dev; 
    dev.data = &pl_data;
    dev.config = &pl_config;
    
    bool is_initialized = false;
    int last_cmd = 0; // 0=none, 1=init, 2=read, 3=write, 4=isr
    size_t data_idx = 0;
    
    total_executions++;
    
    for (int step = 0; step < MAX_STEPS; step++) {
        int state = (is_initialized ? 1 : 0) * 50 + last_cmd * 10 + step;
        uint8_t cmd;
        
        static bool seeded = false;
        if (!seeded) {
            char *env_seed = getenv("AGENT_SEED");
            if (env_seed) srand(atoi(env_seed));
            seeded = true;
        }
        
#ifdef MODE_RANDOM
        cmd = rand() % 4;
#elif defined(MODE_CONSTRAINED_RANDOM)
        if (!is_initialized) {
            cmd = 0;
        } else {
            cmd = rand() % 4;
        }
#elif defined(MODE_QLEARNING)
        float epsilon = 1.0f / (1.0f + (total_executions / 1000.0f));
        if ((rand() % 10000) / 10000.0f < epsilon) {
            cmd = rand() % 4;
        } else {
            cmd = 0; float best_q = Q[state][0];
            for (int a = 1; a < 4; a++) {
                if (Q[state][a] > best_q) { best_q = Q[state][a]; cmd = a; }
            }
        }
#elif defined(MODE_UCB1)
        if (N_s[state] < 4) {
            cmd = N_s[state]; // Try each action once
        } else {
            cmd = 0; float best_ucb = -1e9;
            for (int a = 0; a < 4; a++) {
                float ucb = V[state][a] + 1.0f * sqrtf(logf(N_s[state]) / (N_sa[state][a]));
                if (ucb > best_ucb) { best_ucb = ucb; cmd = a; }
            }
        }
#endif
        
        // Supply payload data from fuzzer input
        if (data_idx + 1 < size) {
            regs.dr = data[data_idx];
            regs.fr = data[data_idx];
            regs.fr &= ~PL011_FR_TXFF; 
            data_idx++;
        }
        
        size_t features_before = get_coverage();
        
        if (cmd == 0) {
            pl011_init(&dev);
            is_initialized = true;
            last_cmd = 1;
        } else if (cmd == 1) {
            if (is_initialized) { unsigned char c = 0; pl011_poll_in(&dev, &c); }
            last_cmd = 2;
        } else if (cmd == 2) {
            if (is_initialized && data_idx < size) { pl011_poll_out(&dev, data[data_idx++]); }
            last_cmd = 3;
        } else if (cmd == 3) {
            if (is_initialized && data_idx + 1 < size) {
                regs.mis = data[data_idx];
                regs.imsc = data[data_idx];
                data_idx++;
            }
            if (is_initialized) { pl011_isr(&dev); }
            last_cmd = 4;
        }
        
        size_t features_after = get_coverage();
        long long delta = (long long)features_after - (long long)features_before;
        if (delta < 0) delta = 0; // Prevent underflow from 8-bit coverage counter wrap-around
        float reward = (float)delta * (1.0f + U_weights[cmd]);
        
        // Prerequisite violation penalty!
        if (!is_initialized && cmd != 0) {
            reward = -1.0f;
        }
        
        static size_t max_cov = 0;
        if (features_after > max_cov) {
            max_cov = features_after;
            printf("MAX_COV: %zu\n", max_cov);
        }
        
#ifdef MODE_QLEARNING
        float next_max_q = 0;
        if (step + 1 < MAX_STEPS) {
            int next_state = (is_initialized ? 1 : 0) * 50 + last_cmd * 10 + (step + 1);
            next_max_q = Q[next_state][0];
            for(int a=1; a<4; a++) if (Q[next_state][a] > next_max_q) next_max_q = Q[next_state][a];
        }
        Q[state][cmd] += 0.1f * (reward + 0.9f * next_max_q - Q[state][cmd]);
#elif defined(MODE_UCB1)
        N_s[state]++;
        N_sa[state][cmd]++;
        V[state][cmd] += (reward - V[state][cmd]) / N_sa[state][cmd];
#endif
    }
    
    return 0;
}
