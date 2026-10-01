/**
 * @file FreeRTOS_IP.h
 * @brief FreeRTOS+TCP Network Stack Definitions
 */

#ifndef FREERTOS_IP_H
#define FREERTOS_IP_H

#include "FreeRTOS.h"

#ifdef __cplusplus
extern "C" {
#endif

#define ipTYPE_IPv4               0x0800U
#define ipTYPE_ARP                0x0806U
#define ipPROTOCOL_UDP            17U
#define ipPROTOCOL_TCP            6U
#define ipPROTOCOL_ICMP           1U

#pragma pack(push, 1)

typedef struct xMAC_ADDRESS {
    uint8_t ucBytes[6];
} MACAddress_t;

typedef struct xETHERNET_HEADER {
    MACAddress_t xDestinationAddress;
    MACAddress_t xSourceAddress;
    uint16_t     usFrameType;
} EthernetHeader_t;

typedef struct xIP_HEADER {
    uint8_t  ucVersionAndHeaderLength;
    uint8_t  ucDifferentiatedServicesCode;
    uint16_t usLength;
    uint16_t usIdentification;
    uint16_t usFragmentOffset;
    uint8_t  ucTimeToLive;
    uint8_t  ucProtocol;
    uint16_t usHeaderChecksum;
    uint32_t ulSourceIPAddress;
    uint32_t ulDestinationIPAddress;
} IPHeader_t;

typedef struct xUDP_HEADER {
    uint16_t usSourcePort;
    uint16_t usDestinationPort;
    uint16_t usLength;
    uint16_t usChecksum;
} UDPHeader_t;

typedef struct xIP_PACKET {
    EthernetHeader_t xEthernetHeader;
    IPHeader_t       xIPHeader;
} IPPacket_t;

typedef struct xUDP_PACKET {
    EthernetHeader_t xEthernetHeader;
    IPHeader_t       xIPHeader;
    UDPHeader_t      xUDPHeader;
} UDPPacket_t;

#pragma pack(pop)

typedef struct xNETWORK_BUFFER {
    uint8_t     *pucEthernetBuffer;
    size_t       xDataLength;
    uint32_t     ulIPAddress;
    uint16_t     usPort;
} NetworkBufferDescriptor_t;

/* API Prototypes */
BaseType_t FreeRTOS_IPInit(const uint8_t *ucIPAddress, const uint8_t *ucNetMask, const uint8_t *ucGatewayAddress, const uint8_t *ucDNSServerAddress, const uint8_t *ucMACAddress);
BaseType_t prvProcessIPPacket(IPPacket_t *pxIPPacket, NetworkBufferDescriptor_t *pxNetworkBuffer);
BaseType_t xProcessReceivedUDPPacket(NetworkBufferDescriptor_t *pxNetworkBuffer);

#ifdef __cplusplus
}
#endif

#endif /* FREERTOS_IP_H */
