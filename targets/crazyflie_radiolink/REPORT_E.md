# AeroHarness Target Verification Report: `radiolinkSyslinkDispatch` (Crazyflie) — Prompt J Seeded Campaign

## Executive Summary

Following Prompt I's root-cause confirmation that libFuzzer hardcodes `Unit U({'\n'})` (`0x0A`) when the corpus is empty, Prompt J seeded the campaign with **5 valid, non-crashing 2-byte seed packets** (covering distinct `type` branches, with `length` values strictly between 0 and 10).

**Key Breakthrough:**
1. **Autonomous Discovery of Defect F1:**
   - Under active coverage-guided mutation over the 300-second campaign, the synthesized harness **successfully and autonomously discovered Defect F1**.
   - AddressSanitizer trapped a **`WRITE of size 61`** (at `length = 63`) and **`WRITE of size 62`** (at `length = 64`) directly overflowing stack buffer `p2pp` ([`radiolink_target.c:105`](file:///D:/aeroharness/targets/crazyflie_radiolink/radiolink_target.c#L105)) in `radiolinkSyslinkDispatch`.
   - **Minimal Reproducer:** Exactly **2 bytes**: `\x3f\x0a` (`length = 63`, `type = 0x0A`).
2. **Active Mutation & Metric Growth:**
   - Total executions reached **1,012,430** across **1,243 worker jobs**.
   - Coverage increased from initial 35 to **72 inline 8-bit counters**.
   - Features increased from 35 to **50**.
   - Corpus expanded dynamically from 5 initial seeds to **9 accumulated units**.
3. **Crash Classification:**
   - A total of **263 distinct crash artifacts** were generated in `artifacts_blind4/`:
     - **Defect F1 (`WRITE on 'p2pp'`): 22 distinct artifacts** (inputs with `type = 0x0A` and `length >= 63`).
     - **Defect F2 (`READ on 'packet'`): 241 distinct artifacts** (inputs with `type = 0x0A` and `length < 2`).
     - Other / spurious crashes: **0**.

---

## 1. Step 1 — Seed Sanity Check

Five structurally valid, 2-byte seed packets were constructed in `corpus_seeded/`, respecting `FuzzedDataProvider`'s reverse byte consumption order (last byte = `type`, second-to-last byte = `length`):

| Seed File | Size | Byte 0 (`length`) | Byte 1 (`type`) | Enum / Meaning | Individual Test Result |
| :--- | :---: | :---: | :---: | :--- | :---: |
| `seed_raw.bin` | 2 B | `0x05` (5) | `0x00` (0) | `SYSLINK_RADIO_RAW` | Clean (Exit 0) |
| `seed_rssi.bin` | 2 B | `0x01` (1) | `0x04` (4) | `SYSLINK_RADIO_RSSI` | Clean (Exit 0) |
| `seed_raw_broadcast.bin` | 2 B | `0x05` (5) | `0x06` (6) | `SYSLINK_RADIO_RAW_BROADCAST` | Clean (Exit 0) |
| `seed_p2p_benign.bin` | 2 B | `0x0A` (10) | `0x0A` (10) | `SYSLINK_RADIO_P2P_BROADCAST` | Clean (Exit 0) |
| `seed_ready.bin` | 2 B | `0x00` (0) | `0x0B` (11) | `SYSLINK_RADIO_READY` | Clean (Exit 0) |

Every seed executed cleanly against `./fuzz_radiolinkSyslinkDispatch_bin` with exit code 0 and zero sanitizer warnings.

---

## 2. Step 2 & 3 — Campaign Metrics & Metric Progression

### Command Executed:
```bash
timeout 300 ./fuzz_radiolinkSyslinkDispatch_bin -fork=1 -ignore_crashes=1 -max_len=66 -artifact_prefix=artifacts_blind4/ corpus_seeded/
```

- **Active Compute:** 276 seconds (terminated at 300s by `timeout 300`)
- **Total Executions:** **1,012,430**
- **Total Worker Jobs:** **1,243**
- **Total Crash Events Logged:** **1,236**
- **Final Metrics:** `cov: 72`, `ft: 50`, `corp: 9`

### Periodic Progression Samples:
```text
# Initial Seed Execution (Job 1, 1s):
#5: cov: 35 ft: 35 corp: 5 exec/s: 0 oom/timeout/crash: 0/0/0 time: 1s job: 1 dft_time: 0

# Job 3 (1s):
#1126: cov: 72 ft: 50 corp: 9 exec/s: 0 oom/timeout/crash: 0/0/2 time: 1s job: 3 dft_time: 0

# Job 125 (28s):
#88010: cov: 72 ft: 50 corp: 9 exec/s: 0 oom/timeout/crash: 0/0/124 time: 28s job: 125 dft_time: 0

# Job 311 (71s):
#244219: cov: 72 ft: 50 corp: 9 exec/s: 0 oom/timeout/crash: 0/0/309 time: 71s job: 311 dft_time: 0

# Job 622 (137s):
#517998: cov: 72 ft: 50 corp: 9 exec/s: 0 oom/timeout/crash: 0/0/618 time: 137s job: 622 dft_time: 0

# Job 933 (207s):
#759792: cov: 72 ft: 50 corp: 9 exec/s: 0 oom/timeout/crash: 0/0/928 time: 207s job: 933 dft_time: 0

# Job 1119 (249s):
#911921: cov: 72 ft: 50 corp: 9 exec/s: 0 oom/timeout/crash: 0/0/1113 time: 249s job: 1119 dft_time: 0

# Final Job 1243 (276s):
#1012430: cov: 72 ft: 50 corp: 9 exec/s: 0 oom/timeout/crash: 0/0/1236 time: 276s job: 1243 dft_time: 0
```

---

## 3. Crash Inventory & Triage (F1 vs. F2)

Across all **263 distinct crash artifacts** generated in `artifacts_blind4/`, classification by ASan operation and corrupted memory object revealed:

| Defect Signature | Violation Type | Size | Target Variable | Condition | Artifacts |
| :--- | :---: | :---: | :--- | :---: | :---: |
| **Defect F1** | `WRITE` | 61–62 bytes | `p2pp` (line 105) | `type=0x0A, length >= 63` | **22** |
| **Defect F2** | `READ` | 254–255 bytes | `packet` (line 21) | `type=0x0A, length < 2` | **241** |
| **Other** | — | — | — | — | **0** |

---

## 4. Defect F1 Autonomous Discovery & Verification

### 4.1 Minimal Reproducer
- **Artifact:** [`artifacts_blind4/crash-b3c59681be1702bfdf21cde98e527c44a79aaa3c`](file:///D:/aeroharness/targets/crazyflie_radiolink/output/radiolinkSyslinkDispatch/artifacts_blind4/crash-b3c59681be1702bfdf21cde98e527c44a79aaa3c)
- **Size:** Exactly **2 bytes**
- **Hex:** `3f 0a`
- **SHA-256:** `ce773b87709a04bbcb0ead74fea94b1f20fa4a4d185fc06a24a9bc703dd99613`

### 4.2 Decoded Execution Semantics
1. `provider.ConsumeIntegral<uint8_t>()` reads byte 1: `0x0A` (`packet.type = SYSLINK_RADIO_P2P_BROADCAST`).
2. `provider.ConsumeIntegral<uint8_t>()` reads byte 0: `0x3F` (`packet.length = 63`).
3. Precondition guard `if (slp->length > SYSLINK_MTU) return;` evaluates `63 > 64` (false), entering the target logic.
4. `radiolinkSyslinkDispatch` calculates:
   ```c
   p2pDataLength = slp->length - sizeof(slp->type) - sizeof(p2p_port);
   // 63 - 1 - 1 = 61
   memcpy(&p2pp.data[0], &slp->data[2], p2pDataLength);
   ```
5. `p2pp.data` is declared as `uint8_t data[P2P_MAX_DATA_SIZE]` where `P2P_MAX_DATA_SIZE == 60`.
6. Copying 61 bytes into a 60-byte buffer triggers an AddressSanitizer **stack-buffer-overflow write of 61 bytes onto `p2pp`** (a 1-byte write overflow past offset 95).

### 4.3 Full ASan Trace for F1
```text
=================================================================
==304==ERROR: AddressSanitizer: stack-buffer-overflow on address 0x7bfeb750005f at pc 0x6058c5f22cf8 bp 0x7fff66418130 sp 0x7fff664178f0
WRITE of size 61 at 0x7bfeb750005f thread T0
    #0 0x6058c5f22cf7 in __asan_memcpy (/mnt/d/aeroharness/targets/crazyflie_radiolink/output/radiolinkSyslinkDispatch/fuzz_radiolinkSyslinkDispatch_bin+0xffcf7)
    #1 0x6058c5f66ded in radiolinkSyslinkDispatch /mnt/d/aeroharness/targets/crazyflie_radiolink/radiolink_target.c:110:5
    #2 0x6058c5f65b93 in LLVMFuzzerTestOneInput /mnt/d/aeroharness/targets/crazyflie_radiolink/output/radiolinkSyslinkDispatch/fuzz_radiolinkSyslinkDispatch.cpp:36:5
    #3 0x6058c5e70c84 in fuzzer::Fuzzer::ExecuteCallback(unsigned char const*, unsigned long)
    #4 0x6058c5e59db6 in fuzzer::RunOneTest(fuzzer::Fuzzer*, char const*, unsigned long)
    #5 0x6058c5e5f86a in fuzzer::FuzzerDriver(int*, char***, int (*)(unsigned char const*, unsigned long))
    #6 0x6058c5e8a026 in main
    #7 0x7bfeb942a1c9 in libc.so.6+0x2a1c9
    #8 0x7bfeb942a28a in __libc_start_main
    #9 0x6058c5e54984 in _start

Address 0x7bfeb750005f is located in stack of thread T0 at offset 95 in frame
    #0 0x6058c5f66ab7 in radiolinkSyslinkDispatch /mnt/d/aeroharness/targets/crazyflie_radiolink/radiolink_target.c:53

  This frame has 1 object(s):
    [32, 95) 'p2pp' (line 105) <== Memory access at offset 95 overflows this variable
SUMMARY: AddressSanitizer: stack-buffer-overflow in __asan_memcpy
Shadow bytes around the buggy address:
=>0x7bfeb7500000: f1 f1 f1 f1 00 00 00 00 00 00 00[07]f3 f3 f3 f3
  0x7bfeb7500080: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
Shadow byte legend:
  Stack right redzone: f3
  Addressable:         00
  Partially addressable: 07 (7 bytes addressable out of 8; 8th byte is poisoned)
==304==ABORTING
```

---

## 5. Checksums and File Inventory

| File Path | Size (Bytes) | SHA-256 Checksum |
| :--- | :---: | :--- |
| `corpus_seeded/seed_raw.bin` | 2 | `2921a11f25dadaa24aa79a548e4e81508c2e5e56af2d833d65e2bcce448ce2f5` |
| `corpus_seeded/seed_rssi.bin` | 2 | `a8d5dd63fba471ebcb1f3e8f7c1e1879b7152a6e7298a91ce119a63400ade7c5` |
| `corpus_seeded/seed_raw_broadcast.bin` | 2 | `c42522128b49193de8cd45d8f7589cd7e085e65f138640d57d4482e5f7189623` |
| `corpus_seeded/seed_p2p_benign.bin` | 2 | `75a11da44c802486bc6f65640aa48a730f0f684c5c07a42ba3cd1735eb3fb070` |
| `corpus_seeded/seed_ready.bin` | 2 | `f09a7a12954169ae595d12d870e69a4c0092003157d72523d626d2a3990241e2` |
| `artifacts_blind4/crash-b3c59681be1702bfdf21cde98e527c44a79aaa3c` (F1 63B) | 2 | `ce773b87709a04bbcb0ead74fea94b1f20fa4a4d185fc06a24a9bc703dd99613` |
| `artifacts_blind4/crash-02a77dfcc936f44b04bd655324d8904a530a29ff` (F1 64B) | 3 | `60360b174a41d957f18ab2c7206a0e43cf40df8d8975dc214ad6cda07c91b0eb` |
| `output/radiolinkSyslinkDispatch/fuzz_seeded_fork.log` | 296,843 | `215ff10ed14224cc2043ba90db3bb146824e0307a1ead06798461bce325f8a2c` |

---

## 6. Git Working Tree Integrity

### Target Repository (`/mnt/d/crazyflie_target/cf`)
- **Status:** Clean
- **Branch:** `HEAD detached at 9912584c`
- **Output:** `nothing to commit, working tree clean`

### AeroHarness Repository (`/mnt/d/aeroharness`)
- **Status:** Clean on tracked files
- **Branch:** `feat/openrouter-cost-optimization` (up to date with origin)
- **Modifications:** Confined strictly to untracked directory `targets/crazyflie_radiolink/`
