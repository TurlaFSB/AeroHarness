/**
 * @file FreeRTOS_DNS.c
 * @brief FreeRTOS+TCP DNS Parser Implementation
 */

#include "FreeRTOS_DNS.h"
#include <string.h>
#include <stdlib.h>

static size_t prvSkipDNSName(const uint8_t *pucBuffer, size_t uxOffset, size_t uxBufferLength) {
    while (uxOffset < uxBufferLength) {
        uint8_t ucLen = pucBuffer[uxOffset];
        if (ucLen == 0) {
            return uxOffset + 1;
        }
        if ((ucLen & dnsNAME_IS_OFFSET_MASK) == dnsNAME_IS_OFFSET_MASK) {
            // Compressed pointer (2 bytes)
            return uxOffset + 2;
        }
        uxOffset += (ucLen + 1);
    }
    return uxBufferLength;
}

uint32_t prvParseDNSReply(uint8_t *pucUDPPayloadBuffer, size_t uxBufferLength, BaseType_t xExpectedAddress) {
    (void)xExpectedAddress;

    if (!pucUDPPayloadBuffer || uxBufferLength < sizeof(DNSHeader_t)) {
        return 0;
    }

    const DNSHeader_t *pxDNSHeader = (const DNSHeader_t *)pucUDPPayloadBuffer;
    uint16_t usQuestions = pxDNSHeader->usQuestions;
    uint16_t usAnswers = pxDNSHeader->usAnswers;

    size_t uxOffset = sizeof(DNSHeader_t);

    // Skip question records
    for (uint16_t usQ = 0; usQ < usQuestions; usQ++) {
        uxOffset = prvSkipDNSName(pucUDPPayloadBuffer, uxOffset, uxBufferLength);
        uxOffset += 4; // Skip QTYPE and QCLASS
        if (uxOffset > uxBufferLength) {
            return 0;
        }
    }

    char cExtractedName[128];
    uint32_t ulResolvedIP = 0;

    // Parse answer records
    for (uint16_t usA = 0; usA < usAnswers; usA++) {
        if (uxOffset >= uxBufferLength) {
            break;
        }

        // Decompress DNS label into local buffer
        size_t name_idx = 0;
        while (uxOffset < uxBufferLength && pucUDPPayloadBuffer[uxOffset] != 0) {
            uint8_t ucLabelLen = pucUDPPayloadBuffer[uxOffset++];
            if ((ucLabelLen & dnsNAME_IS_OFFSET_MASK) == dnsNAME_IS_OFFSET_MASK) {
                uxOffset++; // skip pointer byte
                break;
            }
            
            /*
             * INTENTIONAL / HISTORICAL EMBEDDED DNS BUG:
             * Name buffer copy without bound check against cExtractedName (128 bytes)
             */
            memcpy(&cExtractedName[name_idx], &pucUDPPayloadBuffer[uxOffset], ucLabelLen);
            name_idx += ucLabelLen;
            uxOffset += ucLabelLen;
            cExtractedName[name_idx++] = '.';
        }
        if (uxOffset < uxBufferLength && pucUDPPayloadBuffer[uxOffset] == 0) {
            uxOffset++;
        }

        if (uxOffset + 10 > uxBufferLength) {
            break;
        }

        // Skip TYPE (2), CLASS (2), TTL (4)
        uint16_t usType = (pucUDPPayloadBuffer[uxOffset] << 8) | pucUDPPayloadBuffer[uxOffset + 1];
        uint16_t usDataLen = (pucUDPPayloadBuffer[uxOffset + 8] << 8) | pucUDPPayloadBuffer[uxOffset + 9];
        uxOffset += 10;

        if (usType == dnsTYPE_A_HOST && usDataLen == 4) {
            if (uxOffset + 4 <= uxBufferLength) {
                memcpy(&ulResolvedIP, &pucUDPPayloadBuffer[uxOffset], 4);
                return ulResolvedIP;
            }
        }
        uxOffset += usDataLen;
    }

    return ulResolvedIP;
}
