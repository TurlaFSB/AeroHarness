# Reproducing the Crazyflie findings (Work Plan Item 4)

Each finding is reproducible from the committed target source (the verbatim
extracted function + host stubs) plus an independent libFuzzer harness
(`repro_fuzz_*.cpp`). Each harness is seeded only with **valid, non-crashing**
packets and then fuzzed **blind**: the coverage-guided fuzzer rediscovers the
defect on its own, with no hand-crafted triggering input. Verified with
Clang 18.1.3 on x86-64; any recent Clang with the libFuzzer/ASan/UBSan runtime
works. These are host-level results (host-mocked, sanitizer-based); none is
confirmed on physical STM32F405/nRF51 hardware.

## 1. radiolinkSyslinkDispatch — 1-byte stack-buffer overflow (and length<2 underflow)

```bash
cd crazyflie_radiolink
clang++ -g -O1 -fsanitize=fuzzer,address,undefined -I. \
    repro_fuzz_radiolink.cpp radiolink_target.c -o fuzz_radiolink_bin
mkdir -p corpus && printf '\x05\x00' > corpus/s1 && printf '\x05\x0a' > corpus/s2   # valid, non-crashing
./fuzz_radiolink_bin -fork=1 -ignore_crashes=1 -max_len=70 -artifact_prefix=artifacts/ corpus/
```
Expect `AddressSanitizer: stack-buffer-overflow ... WRITE of size 61` in
`radiolink_target.c` for a `type=0x0A`, `length>=63` input (the 60-byte
`P2PPacket.data` overflow). Inputs with `length<2` trigger the separate
underflow (harness-scope only; blocked upstream by the nRF51 on real hardware).

## 2. crtpCommanderHighLevelWriteTrajectory — CWE-190 wraparound

```bash
cd crtp_trajectory_write
clang++ -g -O1 -fsanitize=fuzzer,address,undefined -I. \
    repro_fuzz_traj.cpp trajectory_write_target.c -o fuzz_traj_bin
# seed with in-bounds writes (offset+length < 4096), 4-byte LE offset + 1-byte length:
mkdir -p corpus && python3 -c "import struct;open('corpus/s','wb').write(struct.pack('<I',0)+bytes([10]))"
./fuzz_traj_bin -fork=1 -ignore_crashes=1 -max_len=66 -artifact_prefix=artifacts/ corpus/
```
Expect a crash where the decoded `offset` is near `2^32` and
`(offset+length) mod 2^32 <= 4096` (e.g. `offset=0xFFFFFFFF, length=255` →
`254`), i.e. the bounds check passes but the `memcpy` writes far out of bounds.

## 3. logAppendBlockV2 — CWE-125 out-of-bounds table read

```bash
cd crazyflie_log_append
clang++ -g -O1 -fsanitize=fuzzer,address,undefined -I. \
    repro_fuzz_log.cpp log_append_target.c -o fuzz_log_bin
# seed with valid logType 1..8 (3 bytes: 1-byte logType + 2-byte id):
mkdir -p corpus && python3 -c "import struct;open('corpus/s','wb').write(struct.pack('<BH',1,1))"
./fuzz_log_bin -fork=1 -ignore_crashes=1 -max_len=3 -artifact_prefix=artifacts/ corpus/
```
Expect `UndefinedBehaviorSanitizer: index <9..15> out of bounds for type
'const uint8_t[9]'` at the `typeLength[... & LOG_TYPE_MASK]` access, with an
ASan `global-buffer-overflow READ` — reached when the `logType` low nibble is
9–15 (the `0x0f` mask permits 0–15 but the table only defines 1–8).
