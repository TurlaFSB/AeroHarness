#ifndef FREERTOS_STUBS_H_
#define FREERTOS_STUBS_H_

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <string.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Real Crazyflie Syslink Packet Constants */
#define SYSLINK_RADIO_RAW            0x00
#define SYSLINK_RADIO_RSSI           0x04
#define SYSLINK_RADIO_RAW_BROADCAST  0x06
#define SYSLINK_RADIO_P2P_BROADCAST  0x0A
#define SYSLINK_RADIO_READY          0x0B
#define SYSLINK_MTU                  64

/* Verbatim struct layouts from cf/src/hal/interface/syslink.h and radiolink.h */
typedef struct _SyslinkPacket
{
  uint8_t type;
  uint8_t length;
  char data[64];     // SYSLINK_MTU
} __attribute__((packed)) SyslinkPacket;

typedef struct _P2PPacket
{
  uint8_t size;
  uint8_t rssi;
  union {
    struct {
      uint8_t port;
      uint8_t data[60];   // P2P_MAX_DATA_SIZE
    };
    uint8_t raw[61];
  };
} __attribute__((packed)) P2PPacket;

/* FreeRTOS and driver primitive types and definitions */
typedef void* xQueueHandle;
typedef long BaseType_t;
typedef uint32_t TickType_t;

#define pdPASS  1
#define pdFAIL  0
#define pdTRUE  1
#define pdFALSE 0
#define M2T(x)  (x)

typedef void (*P2PCallback)(P2PPacket *p2pp);
typedef struct { int dummy; } ledseq_t;

/* Stub declarations for runtime */
TickType_t xTaskGetTickCount(void);
BaseType_t xQueueSend(xQueueHandle q, const void *item, TickType_t wait);
BaseType_t xQueueReceive(xQueueHandle q, void *dest, TickType_t wait);
void ledseqRun(const ledseq_t *sequence);
void syslinkSendPacket(SyslinkPacket *slp);

#ifdef __cplusplus
}
#endif

#endif /* FREERTOS_STUBS_H_ */
