/*
 * Minimal Cortex-M4 startup for the item 7 Fuzzware target.
 *
 * Just enough to give Fuzzware's auto entry-point/stack-pointer detection
 * (which reads the standard two-word Cortex-M vector table: [initial_sp,
 * reset_handler]) something real to find, and to get .data copied / .bss
 * zeroed before calling into the driver loop. No NVIC/interrupt vectors
 * beyond the reset entry are needed -- pl011_isr() is called directly by
 * app_main(), not dispatched through a real interrupt.
 */
#include <stdint.h>
#include <stddef.h>

extern uint32_t _sidata, _sdata, _edata, _sbss, _ebss, _estack;
extern void app_main(void);

/* -nostdlib/-ffreestanding builds get no libc memcpy; the driver's
 * uart_configure() path needs one for a small struct copy. */
void *memcpy(void *dst, const void *src, size_t n)
{
	unsigned char *d = dst;
	const unsigned char *s = src;

	while (n--) {
		*d++ = *s++;
	}
	return dst;
}

void Reset_Handler(void)
{
	uint32_t *src = &_sidata;
	uint32_t *dst = &_sdata;

	while (dst < &_edata) {
		*dst++ = *src++;
	}

	dst = &_sbss;
	while (dst < &_ebss) {
		*dst++ = 0;
	}

	app_main();

	while (1) {
		/* app_main() never returns; this is unreachable. */
	}
}

void Default_Handler(void)
{
	while (1) {
	}
}

__attribute__((section(".isr_vector")))
void (*const vector_table[])(void) = {
	(void (*)(void))&_estack, /* initial stack pointer */
	Reset_Handler,            /* Reset */
	Default_Handler,          /* NMI */
	Default_Handler,          /* HardFault */
	Default_Handler,          /* MemManage */
	Default_Handler,          /* BusFault */
	Default_Handler,          /* UsageFault */
};
