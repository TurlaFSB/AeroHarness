#ifndef ZEPHYR_DRIVERS_SERIAL_UART_PL011_REGISTERS_SHIM_H_
#define ZEPHYR_DRIVERS_SERIAL_UART_PL011_REGISTERS_SHIM_H_

/*
 * Forwarding shim, added Oct 2026 (Ablation B v2 scaffolding audit).
 *
 * Every target's prompt tells the model it can use
 * "zephyr-src/drivers/serial/uart_pl011_registers.h" (quoted, no
 * zephyr/ prefix) -- that's where this repo actually keeps the real
 * driver source on disk. But harnesses/include/zephyr/device.h and
 * harnesses/include/zephyr/drivers/uart.h both use the real upstream
 * Zephyr convention (<zephyr/...>), which is what a model trained on
 * real Zephyr source naturally reaches for by analogy -- and multiple
 * smoke tests showed exactly that: the model correctly used
 * <zephyr/device.h> and <zephyr/drivers/uart.h>, then guessed
 * <zephyr/drivers/serial/uart_pl011_registers.h> for this one too,
 * and failed on a "file not found" that has nothing to do with its
 * actual coding ability.
 *
 * This shim makes both paths resolve to the identical, unmodified real
 * header, removing that inconsistency without changing the task.
 */
#include "zephyr-src/drivers/serial/uart_pl011_registers.h"

#endif /* ZEPHYR_DRIVERS_SERIAL_UART_PL011_REGISTERS_SHIM_H_ */
