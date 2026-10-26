#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <fuzzer/FuzzedDataProvider.h>
extern "C" {
#include "crazyflie_radiolink.h"
}
extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    FuzzedDataProvider provider(data, size);
    SyslinkPacket packet;
    memset(&packet, 0, sizeof(packet));
    packet.type   = provider.ConsumeIntegral<uint8_t>();
    packet.length = provider.ConsumeIntegral<uint8_t>();
    // Fill the data region from any remaining fuzzer bytes (bounded to the struct)
    std::vector<uint8_t> rest = provider.ConsumeRemainingBytes<uint8_t>();
    size_t n = rest.size() < sizeof(packet.data) ? rest.size() : sizeof(packet.data);
    if (n) memcpy(packet.data, rest.data(), n);
    radiolinkSyslinkDispatch(&packet);
    return 0;
}
