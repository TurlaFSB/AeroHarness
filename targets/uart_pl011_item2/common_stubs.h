/*
 * Shared host-side stub layer for Work Plan item 2 (Dimension B self-repair
 * statistical rigor, Oct 2 2026).
 *
 * Reused, unmodified, across all 18 new uart_pl011.c self-repair targets.
 * Mirrors exactly the stub convention already established and verified in
 * this project's three existing hand-built pl011 harnesses
 * (harnesses/fuzz_pl011_poll_in.cpp / _poll_out.cpp / _isr.cpp): a
 * mock_regs_ptr global backing DEVICE_MMIO_GET(dev), the real upstream
 * uart_pl011_registers.h included unmodified for struct pl011_regs/get_uart,
 * and a pl011_data struct carrying every field any of the 18 target
 * functions touches (unused fields are harmless per target).
 *
 * This file is NOT generated or repaired by the LLM -- it is pre-built,
 * verbatim-sourced scaffolding, exactly like the established convention for
 * the three existing pl011 harnesses. The LLM only ever writes the
 * LLVMFuzzerTestOneInput wrapper in each target's own harness.cpp.
 */
#ifndef AEROHARNESS_ITEM2_COMMON_STUBS_H_
#define AEROHARNESS_ITEM2_COMMON_STUBS_H_

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <string.h>
#include <errno.h>

/* --- Zephyr primitives these 18 functions' bodies reference --- */
#define DEVICE_MMIO_RAM
#define BIT(n) (1UL << (n))

/* barrier_dmem_fence_full(): a real Zephyr memory-ordering barrier. On a
 * single-threaded host-side libFuzzer run there is nothing else to order
 * against, so this is a behavior-preserving no-op -- the same category of
 * substitution already used for RTOS scheduling primitives elsewhere in
 * this project (see src/synthesizer/mmio_stubber.py's generate_rtos_stubs). */
#define barrier_dmem_fence_full() ((void)0)

struct device;
typedef void (*uart_irq_callback_user_data_t)(const struct device *dev, void *user_data);

struct k_spinlock { int lock; };
#define K_SPINLOCK(x) for (int _i = 0; _i < 1; _i++)

struct uart_config {
    uint32_t baudrate;
    uint8_t parity;
    uint8_t stop_bits;
    uint8_t data_bits;
    uint8_t flow_ctrl;
};

struct device {
    void *data;
    const void *config;
};

/* Real Zephyr uart_rx_stop_reason values (zephyr/drivers/uart.h), needed
 * verbatim by pl011_err_check's return value. */
#define UART_ERROR_OVERRUN (1 << 0)
#define UART_ERROR_PARITY  (1 << 1)
#define UART_ERROR_FRAMING (1 << 2)
#define UART_BREAK         (1 << 3)

extern volatile void *mock_regs_ptr;
#define DEVICE_MMIO_GET(dev) (mock_regs_ptr)

/* Real upstream register map + get_uart() -- unmodified, same file every
 * existing pl011 harness in this project already includes. This header's
 * own `#include <zephyr/device.h>` resolves to an EMPTY stub, not the real
 * Zephyr header, via the include path -- callers of this file MUST compile
 * with `-I<repo>/harnesses/include_isolated` (never `-I<repo>/harnesses/include`,
 * whose non-empty device.h collides with the `struct device` defined above;
 * see harnesses/include_isolated/README.md for the full reproducibility-bug
 * writeup this convention fixes). */
#include "../../zephyr-src/drivers/serial/uart_pl011_registers.h"

/* pl011_data, superset of every field any of the 18 targets touches.
 * Matches the real driver's struct (uart_pl011.c:63-74) field-for-field;
 * unused fields per target are simply left zeroed by memset, exactly as
 * the three existing harnesses already do. */
struct pl011_data {
    DEVICE_MMIO_RAM;
    struct uart_config uart_cfg;
    bool sbsa;
    uint32_t clk_freq;
    volatile bool sw_call_txdrdy;
    uart_irq_callback_user_data_t irq_cb;
    struct k_spinlock irq_cb_lock;
    void *irq_cb_data;
};

#endif /* AEROHARNESS_ITEM2_COMMON_STUBS_H_ */
