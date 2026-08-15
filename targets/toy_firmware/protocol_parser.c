/**
 * @file protocol_parser.c
 * @brief Implementation of Embedded IoT Protocol Parser with Hardware MMIO Checks
 */

#include "protocol_parser.h"
#include <string.h>
#include <stdlib.h>

int protocol_init(protocol_context_t *ctx, uint32_t session_id) {
    if (!ctx) {
        return -1;
    }
    
    // Interact with MMIO hardware register
    uint32_t status = hw_read_reg32(MMIO_HW_STATUS_REG);
    if (!(status & HW_STATUS_READY_BIT)) {
        // Hardware peripheral not ready
        return -2;
    }

    memset(ctx, 0, sizeof(protocol_context_t));
    ctx->session_id = session_id;
    ctx->is_authenticated = (session_id != 0);
    ctx->rx_packet_count = 0;
    ctx->internal_buffer_len = 0;

    hw_write_reg32(MMIO_HW_CONTROL_REG, 0x01); // ACK peripheral initialization
    return 0;
}

void protocol_reset(protocol_context_t *ctx) {
    if (ctx) {
        ctx->rx_packet_count = 0;
        ctx->internal_buffer_len = 0;
        memset(ctx->internal_buffer, 0, MAX_PAYLOAD_CAPACITY);
    }
}

static uint8_t compute_checksum(const uint8_t *data, size_t len) {
    uint8_t c = 0;
    for (size_t i = 0; i < len; ++i) {
        c ^= data[i];
    }
    return c;
}

int protocol_process_frame(protocol_context_t *ctx, const uint8_t *data, size_t size) {
    if (!ctx || !data) {
        return -1;
    }

    if (size < sizeof(protocol_header_t)) {
        return -2; // Frame too small
    }

    const protocol_header_t *hdr = (const protocol_header_t *)data;

    // Validate magic header bytes
    if (hdr->magic[0] != PROTOCOL_MAGIC_BYTE_1 || hdr->magic[1] != PROTOCOL_MAGIC_BYTE_2) {
        return -3; // Invalid magic
    }

    size_t payload_len = hdr->length;
    if (size < sizeof(protocol_header_t) + payload_len) {
        return -4; // Incomplete payload
    }

    const uint8_t *payload = data + sizeof(protocol_header_t);

    // Verify Checksum
    uint8_t calculated_cs = compute_checksum(payload, payload_len);
    if (calculated_cs != hdr->checksum) {
        return -5; // Checksum failure
    }

    ctx->rx_packet_count++;

    switch (hdr->command) {
        case CMD_PING:
            hw_write_reg32(MMIO_HW_DATA_REG, 0x50494E47); // "PING"
            return 0;

        case CMD_READ_TELEMETRY:
            return 0;

        case CMD_UPDATE_CONFIG:
            if (payload_len <= MAX_PAYLOAD_CAPACITY) {
                memcpy(ctx->internal_buffer, payload, payload_len);
                ctx->internal_buffer_len = payload_len;
                return 0;
            }
            return -6;

        case CMD_COMPLEX_PARSE: {
            /* 
             * INTENTIONAL VULNERABILITY (CWE-119 / CWE-787):
             * Multiple nested TLV sub-records parsed sequentially.
             * The inner loop fails to check cumulative buffer offset against MAX_PAYLOAD_CAPACITY,
             * leading to an Out-of-Bounds memory write / Buffer Overflow!
             */
            size_t offset = 0;
            size_t dest_offset = ctx->internal_buffer_len;

            while (offset + 2 <= payload_len) {
                uint8_t sub_type = payload[offset];
                uint8_t sub_len  = payload[offset + 1];
                offset += 2;

                if (offset + sub_len > payload_len) {
                    break;
                }

                if (sub_type == 0xAA) {
                    // Flawed copy without bound verification against MAX_PAYLOAD_CAPACITY (64 bytes)
                    memcpy(&ctx->internal_buffer[dest_offset], &payload[offset], sub_len);
                    dest_offset += sub_len;
                }
                offset += sub_len;
            }
            ctx->internal_buffer_len = dest_offset;
            return 0;
        }

        default:
            return -7; // Unknown command
    }
}
