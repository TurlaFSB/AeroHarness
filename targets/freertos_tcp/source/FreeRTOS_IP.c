/**
 * @file FreeRTOS_IP.c
 * @brief FreeRTOS+TCP Packet Parser Implementation
 */

#include "FreeRTOS_IP.h"
#include <string.h>
#include <stdlib.h>

/* Memory allocator shims */
void* pvPortMalloc(size_t xSize) {
    return malloc(xSize);
}

void vPortFree(void* pv) {
    if (pv) {
        free(pv);
    }
}

BaseType_t FreeRTOS_IPInit(
    const uint8_t *ucIPAddress,
    const uint8_t *ucNetMask,
    const uint8_t *ucGatewayAddress,
    const uint8_t *ucDNSServerAddress,
    const uint8_t *ucMACAddress
) {
    if (!ucIPAddress || !ucMACAddress) {
        return pdFAIL;
    }
    return pdPASS;
}

BaseType_t prvProcessIPPacket(IPPacket_t *pxIPPacket, NetworkBufferDescriptor_t *pxNetworkBuffer) {
    if (!pxIPPacket || !pxNetworkBuffer) {
        return pdFAIL;
    }

    if (pxNetworkBuffer->xDataLength < sizeof(IPPacket_t)) {
        return pdFAIL;
    }

    const IPHeader_t *pxIPHeader = &(pxIPPacket->xIPHeader);
    uint8_t ucVersion = (pxIPHeader->ucVersionAndHeaderLength) >> 4;
    uint8_t ucHeaderLength = ((pxIPHeader->ucVersionAndHeaderLength) & 0x0FU) << 2;

    if (ucVersion != 4 || ucHeaderLength < sizeof(IPHeader_t)) {
        return pdFAIL;
    }

    switch (pxIPHeader->ucProtocol) {
        case ipPROTOCOL_UDP:
            return xProcessReceivedUDPPacket(pxNetworkBuffer);

        case ipPROTOCOL_TCP:
            return pdPASS;

        case ipPROTOCOL_ICMP:
            return pdPASS;

        default:
            return pdFAIL;
    }
}

BaseType_t xProcessReceivedUDPPacket(NetworkBufferDescriptor_t *pxNetworkBuffer) {
    if (!pxNetworkBuffer || !pxNetworkBuffer->pucEthernetBuffer) {
        return pdFAIL;
    }

    if (pxNetworkBuffer->xDataLength < sizeof(UDPPacket_t)) {
        return pdFAIL;
    }

    const UDPPacket_t *pxUDPPacket = (const UDPPacket_t *)pxNetworkBuffer->pucEthernetBuffer;
    uint16_t usLength = pxUDPPacket->xUDPHeader.usLength;

    if (usLength < sizeof(UDPHeader_t) || usLength > pxNetworkBuffer->xDataLength) {
        return pdFAIL;
    }

    /* Process payload */
    const uint8_t *pucPayload = pxNetworkBuffer->pucEthernetBuffer + sizeof(UDPPacket_t);
    size_t uxPayloadLength = pxNetworkBuffer->xDataLength - sizeof(UDPPacket_t);

    if (uxPayloadLength > 0 && pucPayload[0] == 0xFF) {
        // Special test handler
        return pdPASS;
    }

    return pdPASS;
}
