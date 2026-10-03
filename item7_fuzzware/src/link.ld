/*
 * Linker script for the item 7 Fuzzware target.
 * Must match item7_fuzzware/config/config.yml's memory_map exactly.
 */
MEMORY
{
	FLASH (rx) : ORIGIN = 0x00000000, LENGTH = 0x00040000  /* 256K */
	RAM   (rwx): ORIGIN = 0x20000000, LENGTH = 0x00010000  /* 64K  */
}

ENTRY(Reset_Handler)

SECTIONS
{
	.isr_vector :
	{
		KEEP(*(.isr_vector))
	} > FLASH

	.text :
	{
		*(.text*)
		*(.rodata*)
		*(.ARM.exidx*)
		*(.ARM.extab*)
	} > FLASH

	.data : AT (ADDR(.text) + SIZEOF(.text))
	{
		_sdata = .;
		*(.data*)
		_edata = .;
	} > RAM

	_sidata = LOADADDR(.data);

	.bss :
	{
		_sbss = .;
		*(.bss*)
		*(COMMON)
		_ebss = .;
	} > RAM

	. = ALIGN(8);
	_estack = ORIGIN(RAM) + LENGTH(RAM);
}
