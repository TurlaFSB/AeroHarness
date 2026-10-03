/*
 * Item 7 (Fuzzware head-to-head benchmark) -- bare-metal driver loop.
 *
 * This mirrors the API sequence AeroHarness's own Stage 6 dispatcher
 * harness (fuzz_state_machine.c) exercises -- init, poll_out, poll_in,
 * isr -- but instead of a fuzz byte-stream choosing which call to make
 * next and what mock register value to inject, this firmware calls all
 * four unconditionally in a fixed sequence on real hardware-mapped
 * registers. Fuzzware's MMIO-region fuzzing (config.yml's mmio_pl011
 * region) supplies the register *values* the AFL-driven Unicorn emulator
 * returns for each load, which is what actually varies between runs and
 * drives the driver down different branches.
 *
 * There is no notion of "the fuzz input selects command N" here, because
 * Fuzzware does not hand the firmware a buffer to parse -- it fuzzes the
 * hardware's answers to the firmware's own memory accesses. This is the
 * fundamental methodological difference documented in RESULTS.md: the two
 * tools fuzz the same driver code through two different input channels.
 */

#include <stdint.h>
#include <stdbool.h>

/* Declarations from firmware_driver.c (the real uart_pl011.c, unmodified
 * apart from the MMIO-address macro, concatenated in by the build). */
struct device;
extern struct device pl011_dev_instance;

int pl011_init(const struct device *dev);
int pl011_poll_in(const struct device *dev, unsigned char *c);
void pl011_poll_out(const struct device *dev, unsigned char c);
void pl011_isr(const struct device *dev);

/* dummy_irq_cb clears PL011_IMSC_TXIM the same way fuzz_state_machine.c's
 * does, to avoid an infinite loop inside pl011_isr when the fuzzed MIS/IMSC
 * values would otherwise keep the "pending" condition asserted forever. */
void dummy_irq_cb(const struct device *dev, void *user_data);

/* Fuzzware's native AFL forkserver harness restarts emulation from the
 * entry point for every test case (same model as a real power-on reset),
 * so an unbounded loop here is safe: each run is cut off by AFL's own
 * per-testcase timeout, exactly as it would be for a real firmware's
 * infinite main loop. */
void app_main(void)
{
	unsigned char c;

	pl011_init(&pl011_dev_instance);

	while (1) {
		pl011_poll_out(&pl011_dev_instance, 'A');
		(void)pl011_poll_in(&pl011_dev_instance, &c);
		pl011_isr(&pl011_dev_instance);
	}
}
