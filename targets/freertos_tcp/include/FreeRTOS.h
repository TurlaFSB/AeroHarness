/**
 * @file FreeRTOS.h
 * @brief FreeRTOS core definitions and types for host-based fuzzing
 */

#ifndef INC_FREERTOS_H
#define INC_FREERTOS_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef long              BaseType_t;
typedef unsigned long     UBaseType_t;
typedef uint32_t          TickType_t;

#define pdTRUE            ((BaseType_t) 1)
#define pdFALSE           ((BaseType_t) 0)
#define pdPASS            (pdTRUE)
#define pdFAIL            (pdFALSE)

#define portMAX_DELAY     ((TickType_t) 0xFFFFFFFFUL)

#define ipconfigBYTE_ORDER               pdLITTLE_ENDIAN
#define ipconfigETHERNET_MINIMUM_PACKET_BYTES  60U
#define ipconfigIP_PACKET_MAX_SIZE             1524U

/* Basic queue / task dummy handles */
typedef void* QueueHandle_t;
typedef void* TaskHandle_t;
typedef void* SemaphoreHandle_t;

/* Host memory allocator shims */
void* pvPortMalloc(size_t xSize);
void  vPortFree(void* pv);

#ifdef __cplusplus
}
#endif

#endif /* INC_FREERTOS_H */
