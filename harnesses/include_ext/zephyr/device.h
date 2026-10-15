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

/*
 * EXTENDED MOCK (Oct 15 2026, labeled variant "mock-headers ext" -- NOT the frozen v1 mock).
 * Found by Ablation G with DeepSeek on prompt v3: 98/100 attempt-1 failures and about three
 * quarters of the final failures were not model mistakes but names real Zephyr provides and
 * this mock did not: mm_reg_t / mem_addr_t / mmio_addr_t, ARG_UNUSED, and an integer
 * mmio base (real Zephyr stores the MMIO address as an integer, so models write
 * `dev.mmio_base = (uintptr_t)&regs`, which a plain `void *` member rejects). This file adds:
 *  - the integer address typedefs (all uintptr_t, as in Zephyr),
 *  - ARG_UNUSED(),
 *  - `mmio_base` as a small C++ wrapper that accepts BOTH conventions (pointer or integer
 *    assignment) and converts to any pointer type or uintptr_t, so DEVICE_MMIO_GET(dev) still
 *    works in the real uart_pl011_registers.h cast.
 * Nothing about register semantics or the target functions changes.
 */
typedef uintptr_t mm_reg_t;
typedef uintptr_t mem_addr_t;
typedef uintptr_t mmio_addr_t;
#ifndef ARG_UNUSED
#define ARG_UNUSED(x) (void)(x)
#endif

#ifdef __cplusplus
struct mmio_ref {
	void *p;
	mmio_ref() : p(0) {}
	mmio_ref(void *v) : p(v) {}
	mmio_ref(uintptr_t v) : p((void *)v) {}
	template <class T> operator T *() const { return (T *)p; }
	operator uintptr_t() const { return (uintptr_t)p; }
};
#endif

struct device {
	const void *config;
	void *data;
#ifdef __cplusplus
	mmio_ref mmio_base;
#else
	void *mmio_base;
#endif
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
