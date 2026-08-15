/**
 * @file protocol_parser.h
 * @brief Embedded IoT Protocol Parser with MMIO Hardware Interface
 */

#ifndef PROTOCOL_PARSER_H
#define PROTOCOL_PARSER_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Hardware MMIO Register Addresses */
#define MMIO_HW_STATUS_REG       0x40001000U
#define MMIO_HW_CONTROL_REG      0x40001004U
#define MMIO_HW_DATA_REG         0x40001008U

#define HW_STATUS_READY_BIT      (1U << 0)
#define HW_STATUS_ERROR_BIT      (1U << 1)

#define PROTOCOL_MAGIC_BYTE_1    0xA5
#define PROTOCOL_MAGIC_BYTE_2    0x5A

#define MAX_PAYLOAD_CAPACITY     64

typedef enum {
    CMD_PING           = 0x01,
    CMD_READ_TELEMETRY = 0x02,
    CMD_UPDATE_CONFIG  = 0x03,
    CMD_COMPLEX_PARSE  = 0x04
} protocol_cmd_t;

#pragma pack(push, 1)
typedef struct {
    uint8_t  magic[2];
    uint8_t  command;
    uint16_t length;
    uint8_t  checksum;
} protocol_header_t;
#pragma pack(pop)

typedef struct {
    uint32_t session_id;
    bool     is_authenticated;
    uint32_t rx_packet_count;
    uint8_t  internal_buffer[MAX_PAYLOAD_CAPACITY];
    size_t   internal_buffer_len;
} protocol_context_t;

/* MMIO hardware hook prototypes (to be stubbed on host) */
uint32_t hw_read_reg32(uint32_t addr);
void     hw_write_reg32(uint32_t addr, uint32_t val);

/* Protocol API */
int  protocol_init(protocol_context_t *ctx, uint32_t session_id);
int  protocol_process_frame(protocol_context_t *ctx, const uint8_t *data, size_t size);
void protocol_reset(protocol_context_t *ctx);

#ifdef __cplusplus
}
#endif

#endif /* PROTOCOL_PARSER_H */
