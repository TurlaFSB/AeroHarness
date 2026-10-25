#ifndef CRAZYFLIE_LOG_APPEND_H
#define CRAZYFLIE_LOG_APPEND_H

#include <stdint.h>
#include <stdbool.h>

#define LOG_UINT8  1
#define LOG_UINT16 2
#define LOG_UINT32 3
#define LOG_INT8   4
#define LOG_INT16  5
#define LOG_INT32  6
#define LOG_FLOAT  7
#define LOG_FP16   8

#define LOG_TYPE_MASK (0x0f)
#define LOG_MAX_LEN 26
#define FIXED_BLOCK_ID 42

struct ops_setting_v2 {
    uint8_t logType;
    uint16_t id;
} __attribute__((packed));

#ifdef __cplusplus
extern "C" {
#endif

int logAppendBlockV2(int id, struct ops_setting_v2 * settings, int len);

#ifdef __cplusplus
}
#endif

#endif // CRAZYFLIE_LOG_APPEND_H
