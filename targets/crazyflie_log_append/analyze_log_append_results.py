import os
import glob
import struct
import subprocess
import re

LOG_FILE = "/mnt/d/aeroharness/targets/crazyflie_log_append/output/logAppendBlockV2/fuzz_300s.log"
ARTIFACTS_DIR = "/mnt/d/aeroharness/targets/crazyflie_log_append/output/logAppendBlockV2/artifacts"
BIN_PATH = "/mnt/d/aeroharness/targets/crazyflie_log_append/output/logAppendBlockV2/fuzz_logAppendBlockV2_bin"

def analyze_log():
    print("=== Analyzing Fuzzing Log ===")
    status_lines = []
    with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if re.search(r"#\d+:\s+cov:\s+\d+", line):
                status_lines.append(line.strip())
    
    print(f"Total status lines found: {len(status_lines)}")
    if status_lines:
        print("First 3 status lines:")
        for l in status_lines[:3]:
            print("  ", l)
        
        step = max(1, len(status_lines) // 8)
        print("\nEvenly spaced samples:")
        for i in range(0, len(status_lines), step):
            print("  ", status_lines[i])
        print("Last status line:")
        print("  ", status_lines[-1])

def analyze_crashes():
    print("\n=== Analyzing Crash Artifacts ===")
    crash_files = glob.glob(os.path.join(ARTIFACTS_DIR, "crash-*"))
    print(f"Total crash files: {len(crash_files)}")

    signatures = {}
    index_distribution = {}

    for cf in crash_files:
        with open(cf, "rb") as f:
            data = f.read()
        if len(data) >= 3:
            log_type, var_id = struct.unpack("<BH", data[:3])
            masked_type = log_type & 0x0F
            sig_key = f"masked_type_{masked_type}_raw_{log_type}"
            if sig_key not in signatures:
                signatures[sig_key] = []
            signatures[sig_key].append((cf, log_type, masked_type, var_id, data))

            index_distribution[masked_type] = index_distribution.get(masked_type, 0) + 1
        else:
            sig_key = f"short_input_{len(data)}"
            if sig_key not in signatures:
                signatures[sig_key] = []
            signatures[sig_key].append((cf, None, None, None, data))

    print(f"Distinct (masked_type, raw_logType) signatures: {len(signatures)}")
    print("\nDistribution across out-of-bounds indices (typeLength has 9 elements, indices 0..8):")
    for idx in sorted(index_distribution.keys()):
        print(f"  Index {idx} (offset {idx-8} bytes past end): {index_distribution[idx]} crashes")

    # Group by masked_type (which directly maps to out-of-bounds index into typeLength)
    by_index = {}
    for cf, log_type, masked_type, var_id, data in [item for group in signatures.values() for item in group]:
        if masked_type not in by_index:
            by_index[masked_type] = []
        by_index[masked_type].append((cf, log_type, var_id, data))

    print("\nDistinct bug signatures by out-of-bounds index:")
    for idx in sorted(by_index.keys()):
        samples = by_index[idx]
        sample = samples[0]
        cf, log_type, var_id, data = sample
        print(f"\nSignature: Out-of-bounds index {idx} into typeLength (raw logType=0x{log_type:02X}, id={var_id})")
        print(f"  Occurrences: {len(samples)}")
        print(f"  Sample file: {os.path.basename(cf)} ({len(data)} bytes, hex: {data.hex()})")
        print(f"  Decoded: logType = 0x{log_type:02X} (masked & 0x0F = {idx}), id = {var_id} (0x{var_id:04X})")

    # Run one representative crash under ASan
    rep_cf = crash_files[0]
    print(f"\nRepresentative ASan output for {os.path.basename(rep_cf)}:")
    res = subprocess.run([BIN_PATH, rep_cf], capture_output=True, text=True)
    print("Exit code:", res.returncode)
    for line in res.stderr.splitlines():
        if "ERROR:" in line or "runtime error:" in line or "SUMMARY:" in line or "is located" in line or "READ of size" in line:
            print("  ", line)

if __name__ == "__main__":
    analyze_log()
    analyze_crashes()
