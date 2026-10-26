#include <iostream>
#include <fstream>
#include <vector>
#include <cstdint>
#include <fuzzer/FuzzedDataProvider.h>

int main(int argc, char** argv) {
    if (argc < 2) return 1;
    std::ifstream file(argv[1], std::ios::binary);
    if (!file) return 2;
    std::vector<uint8_t> data((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
    
    FuzzedDataProvider provider(data.data(), data.size());
    uint32_t offset = provider.ConsumeIntegral<uint32_t>();
    uint8_t length = provider.ConsumeIntegral<uint8_t>();
    std::vector<uint8_t> remaining = provider.ConsumeRemainingBytes<uint8_t>();

    uint32_t sum = offset + length;
    bool sum_le_4096 = (sum <= 4096);

    std::cout << "file: " << argv[1] << "\n"
              << "size: " << data.size() << "\n"
              << "offset: 0x" << std::hex << offset << " (" << std::dec << offset << ")\n"
              << "length: 0x" << std::hex << (int)length << " (" << std::dec << (int)length << ")\n"
              << "offset + length: 0x" << std::hex << sum << " (" << std::dec << sum << ")\n"
              << "sum <= 4096: " << (sum_le_4096 ? "true" : "false") << "\n"
              << "remaining_bytes: " << remaining.size() << "\n";
    return 0;
}
