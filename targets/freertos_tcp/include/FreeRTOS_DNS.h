/**
 * @file FreeRTOS_DNS.h
 * @brief FreeRTOS+TCP DNS Parser Definitions
 */

#ifndef FREERTOS_DNS_H
#define FREERTOS_DNS_H

#include "FreeRTOS.h"
#include "FreeRTOS_IP.h"

#ifdef __cplusplus
extern "C" {
#endif

#define dnsTYPE_A_HOST             0x0001U
#define dnsCLASS_IN                0x0001U
#define dnsNAME_IS_OFFSET_MASK     0xC0U

#pragma pack(push, 1)
typedef struct xDNS_HEADER {
    uint16_t usIdentifier;
    uint16_t usFlags;
    uint16_t usQuestions;
    uint16_t usAnswers;
    uint16_t usAuthorityRRs;
    uint16_t usAdditionalRRs;
} DNSHeader_t;
#pragma pack(pop)

/* DNS Parser APIs */
uint32_t prvParseDNSReply(uint8_t *pucUDPPayloadBuffer, size_t uxBufferLength, BaseType_t xExpectedAddress);

#ifdef __cplusplus
}
#endif

#endif /* FREERTOS_DNS_H */
