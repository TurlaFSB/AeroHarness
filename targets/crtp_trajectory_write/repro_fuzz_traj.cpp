#include <stdint.h>
#include <stddef.h>
#include <vector>
#include <fuzzer/FuzzedDataProvider.h>
extern "C" {
#include "crtp_trajectory_write.h"
}
extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    FuzzedDataProvider fdp(data, size);
    uint32_t offset = fdp.ConsumeIntegral<uint32_t>();
    uint8_t  length = fdp.ConsumeIntegral<uint8_t>();   // real caller supplies a uint8_t
    std::vector<uint8_t> buf = fdp.ConsumeRemainingBytes<uint8_t>();
    if (buf.size() < length) buf.resize(length, 0);     // ensure source has >=length bytes
    crtpCommanderHighLevelWriteTrajectory(offset, length, buf.data());
    return 0;
}
