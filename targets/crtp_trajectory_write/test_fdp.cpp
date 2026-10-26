#include <iostream>
#include <fuzzer/FuzzedDataProvider.h>

int main() {
    uint8_t data[] = {0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77};
    FuzzedDataProvider fdp(data, sizeof(data));
    uint32_t offset = fdp.ConsumeIntegral<uint32_t>();
    uint8_t length = fdp.ConsumeIntegral<uint8_t>();
    std::cout << "offset: 0x" << std::hex << offset << " length: 0x" << (int)length << " remaining: " << std::dec << fdp.remaining_bytes() << std::endl;
    return 0;
}
