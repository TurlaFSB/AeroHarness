#ifndef ZEPHYR_DRIVERS_UART_H_
#define ZEPHYR_DRIVERS_UART_H_

#include <stdint.h>

/*
 * Minimal mock of Zephyr's public UART config API (real:
 * zephyr-src/include/zephyr/drivers/uart.h), added Oct 2026 — the
 * pl011_runtime_configure_internal target body uses struct uart_config and
 * all four of these enums, and none were available anywhere in the harness
 * build, so every attempt failed with "undeclared identifier" before any
 * model-written code was even evaluated. Field names/values mirror the
 * real header exactly.
 */

enum uart_config_parity {
	UART_CFG_PARITY_NONE,
	UART_CFG_PARITY_ODD,
	UART_CFG_PARITY_EVEN,
	UART_CFG_PARITY_MARK,
	UART_CFG_PARITY_SPACE,
};

enum uart_config_stop_bits {
	UART_CFG_STOP_BITS_0_5,
	UART_CFG_STOP_BITS_1,
	UART_CFG_STOP_BITS_1_5,
	UART_CFG_STOP_BITS_2,
};

enum uart_config_data_bits {
	UART_CFG_DATA_BITS_5,
	UART_CFG_DATA_BITS_6,
	UART_CFG_DATA_BITS_7,
	UART_CFG_DATA_BITS_8,
	UART_CFG_DATA_BITS_9,
};

enum uart_config_flow_control {
	UART_CFG_FLOW_CTRL_NONE,
	UART_CFG_FLOW_CTRL_RTS_CTS,
	UART_CFG_FLOW_CTRL_DTR_DSR,
	UART_CFG_FLOW_CTRL_RS485,
};

struct uart_config {
	uint32_t baudrate;
	uint8_t parity;
	uint8_t stop_bits;
	uint8_t data_bits;
	uint8_t flow_ctrl;
};

#endif /* ZEPHYR_DRIVERS_UART_H_ */
