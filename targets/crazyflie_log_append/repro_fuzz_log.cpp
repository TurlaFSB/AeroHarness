#include <stdint.h>
#include <stddef.h>
#include <string.h>
extern "C" {
#include "crazyflie_log_append.h"
}
#define FIXED_BLOCK_ID 42
extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (size < 3) return 0;                 // need one full 3-byte ops_setting_v2
    struct ops_setting_v2 s;
    s.logType = data[0];
    memcpy(&s.id, data + 1, sizeof(s.id));  // 2 bytes, packed
    logAppendBlockV2(FIXED_BLOCK_ID, &s, 1);
    return 0;
}
