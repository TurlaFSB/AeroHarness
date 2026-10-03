#!/bin/bash
# Builds the bare-metal PL011 firmware used for the Fuzzware head-to-head
# benchmark (item 7). Produces firmware.elf and firmware.bin in this dir.
set -eu
cd "$(dirname "$0")"

CC=arm-none-eabi-gcc
OBJCOPY=arm-none-eabi-objcopy

CFLAGS="-mcpu=cortex-m4 -mthumb -ffreestanding -fno-builtin -nostdlib \
    -fno-stack-protector -Os -Wall -Wno-unused-function -Isrc \
    -I../fake_zephyr"

$CC $CFLAGS -c src/startup.c -o startup.o
$CC $CFLAGS -c src/main.c -o main.o
$CC $CFLAGS -c src/firmware_driver.c -o firmware_driver.o

$CC $CFLAGS -T src/link.ld -nostartfiles -Wl,--gc-sections -Wl,-Map=firmware.map \
    startup.o main.o firmware_driver.o -lgcc -o firmware.elf

$OBJCOPY -O binary firmware.elf firmware.bin

arm-none-eabi-size firmware.elf
cp firmware.bin config/firmware.bin
echo "[+] Built firmware.elf / firmware.bin (copied into config/ for Fuzzware)"
