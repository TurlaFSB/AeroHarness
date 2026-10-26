import os
import glob
import subprocess
import hashlib
import json

ARTIFACTS_DIR = "/mnt/d/aeroharness/targets/crtp_trajectory_write/output/crtpCommanderHighLevelWriteTrajectory/artifacts"
DECODE_BIN = "/mnt/d/aeroharness/targets/crtp_trajectory_write/decode_crash"
CRTP_BIN = "/mnt/d/aeroharness/targets/crtp_trajectory_write/output/crtpCommanderHighLevelWriteTrajectory/fuzz_crtpCommanderHighLevelWriteTrajectory_bin"

def main():
    crash_files = glob.glob(os.path.join(ARTIFACTS_DIR, "crash-*"))
    print(f"Total crash files: {len(crash_files)}")

    results = []
    signatures = {}

    for cf in crash_files:
        p = subprocess.run([DECODE_BIN, cf], capture_output=True, text=True)
        if p.returncode != 0:
            continue
        lines = p.stdout.strip().split("\n")
        parsed = {}
        for line in lines:
            if ": " in line:
                k, v = line.split(": ", 1)
                parsed[k] = v
        
        offset = int(parsed["offset"].split()[0], 16)
        length = int(parsed["length"].split()[0], 16)
        sum_val = int(parsed["offset + length"].split()[0], 16)
        sum_le_4096 = parsed["sum <= 4096"] == "true"
        size = int(parsed["size"])

        # Determine signature
        # Is it the integer overflow bug where offset near 2^32 and sum <= 4096?
        is_overflow = (offset >= 0xFFFFFF00) and sum_le_4096
        
        sig = f"offset_0x{offset:08x}_len_0x{length:02x}_sum_0x{sum_val:08x}"
        if sig not in signatures:
            signatures[sig] = []
        signatures[sig].append((cf, offset, length, sum_val, sum_le_4096, size))

    print(f"Unique (offset, length, sum) signatures: {len(signatures)}")
    
    # Check if ALL crash inputs have sum <= 4096 (which is required to pass the bounds check!)
    all_sum_le_4096 = True
    all_overflow = True
    min_offset = 0xFFFFFFFF
    max_offset = 0

    for sig, occurrences in signatures.items():
        sample = occurrences[0]
        offset, length, sum_val, sum_le_4096, size = sample[1], sample[2], sample[3], sample[4], sample[5]
        if not sum_le_4096:
            all_sum_le_4096 = False
        if offset < 0xFFFF0000:
            all_overflow = False
        if offset < min_offset:
            min_offset = offset
        if offset > max_offset:
            max_offset = offset

    print(f"Do ALL crashes pass the bounds check (sum <= 4096)? {all_sum_le_4096}")
    print(f"Are ALL offsets in the near-UINT32_MAX range? {all_overflow}")
    print(f"Min offset across all crashes: 0x{min_offset:08X} ({min_offset})")
    print(f"Max offset across all crashes: 0x{max_offset:08X} ({max_offset})")

    # Let's inspect the top distinct signatures
    sorted_sigs = sorted(signatures.items(), key=lambda x: len(x[1]), reverse=True)
    print("\nTop 10 distinct signatures by frequency:")
    for sig, occs in sorted_sigs[:10]:
        sample = occs[0]
        cf, offset, length, sum_val, sum_le_4096, size = sample
        with open(cf, "rb") as f:
            raw_bytes = f.read()
        print(f"Signature: {sig} (occurrences: {len(occs)})")
        print(f"  Sample: {os.path.basename(cf)} ({size} bytes, hex: {raw_bytes.hex()})")
        print(f"  Decoded: offset={offset} (0x{offset:08X}), length={length} (0x{length:02X}), sum={sum_val} (0x{sum_val:08X})")

    # Now run a representative crash under ASan to capture full output
    rep_cf = sorted_sigs[0][1][0][0]
    print(f"\nRunning representative crash {os.path.basename(rep_cf)} under ASan:")
    asan_res = subprocess.run([CRTP_BIN, rep_cf], capture_output=True, text=True)
    print("ASan Return Code:", asan_res.returncode)
    print("ASan STDERR:")
    print(asan_res.stderr)

if __name__ == "__main__":
    main()
