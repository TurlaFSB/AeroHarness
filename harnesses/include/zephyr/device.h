#ifndef ZEPHYR_DEVICE_H_
#define ZEPHYR_DEVICE_H_

#include <stdint.h>
#include <stddef.h>

/*
 * Minimal mock of Zephyr's device model, for compiling real Zephyr driver
 * headers (e.g. drivers/serial/uart_pl011_registers.h) standalone, outside
 * a full Zephyr build (no devicetree, no Kconfig).
 *
 * Root-caused Oct 2026 (Ablation B v2 evidence follow-up): this file was
 * previously empty, so every harness that included the real
 * uart_pl011_registers.h (as every target's prompt explicitly suggests)
 * failed with "use of undeclared identifier 'DEVICE_MMIO_GET'"/'BIT'" at
 * compile time, 100% of the time, regardless of model or code quality.
 * That was a scaffolding bug, not a model-capability floor effect.
 *
 * - `config`   mirrors the real struct device field: a driver-specific
 *              config struct pointer (e.g. cast to `struct pl011_config *`).
 * - `data`     mirrors the real struct device field: driver runtime state
 *              (e.g. cast to `struct pl011_data *`).
 * - `mmio_base` is NOT in the real struct device; it's this mock's stand-in
 *              for Zephyr's real MMIO-region indirection (DEVICE_MMIO_ROM/RAM,
 *              normally populated by devicetree). Point it at your mock
 *              register struct before calling the target function.
 */
struct device {
	const void *config;
	void *data;
	void *mmio_base;
};

#define DEVICE_MMIO_GET(dev) ((dev)->mmio_base)

#ifndef BIT
#define BIT(n) (1UL << (n))
#endif

#ifndef GENMASK
#define GENMASK(h, l) \
	(((~0UL) << (l)) & (~0UL >> (sizeof(unsigned long) * 8 - 1 - (h))))
#endif

#endif /* ZEPHYR_DEVICE_H_ */
