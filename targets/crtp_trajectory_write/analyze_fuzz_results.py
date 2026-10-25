import os
import glob
import struct
import subprocess
import hashlib
import re

LOG_FILE = "/mnt/d/aeroharness/targets/crtp_trajectory_write/output/crtpCommanderHighLevelWriteTrajectory/fuzz_300s.log"
ARTIFACTS_DIR = "/mnt/d/aeroharness/targets/crtp_trajectory_write/output/crtpCommanderHighLevelWriteTrajectory/artifacts"
BIN_PATH = "/mnt/d/aeroharness/targets/crtp_trajectory_write/output/crtpCommanderHighLevelWriteTrajectory/fuzz_crtpCommanderHighLevelWriteTrajectory_bin"

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
        
        # Sample across time: every ~30s or evenly across list
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
    for cf in crash_files:
        with open(cf, "rb") as f:
            data = f.read()
        if len(data) >= 5:
            offset = struct.unpack("<I", data[:4])[0]
            length = struct.unpack("<B", data[4:5])[0]
            sum_val = (offset + length) & 0xFFFFFFFF
            # signature can be categorized by crash type/property
            sig_key = (f"offset_high_{offset >= 0xFFFF0000}", f"sum_wraparound_{sum_val <= 4096}")
            if sig_key not in signatures:
                signatures[sig_key] = []
            signatures[sig_key].append((cf, offset, length, sum_val, data))
        else:
            sig_key = ("short_input", len(data))
            if sig_key not in signatures:
                signatures[sig_key] = []
            signatures[sig_key].append((cf, None, None, None, data))

    print(f"Distinct crash groups: {len(signatures)}")
    for k, v in signatures.items():
        print(f"Group {k}: {len(v)} occurrences")
        sample = v[0]
        cf, offset, length, sum_val, data = sample
        print(f"  Sample file: {os.path.basename(cf)}")
        print(f"  Data hex ({len(data)} bytes): {data.hex()}")
        if offset is not None:
            print(f"  offset = {offset} (0x{offset:08X}), length = {length} (0x{length:02X})")
            print(f"  offset + length (32-bit wrapped) = {sum_val} (<= 4096: {sum_val <= 4096})")
        
        # Run sample against binary to get ASan output
        res = subprocess.run([BIN_PATH, cf], capture_output=True, text=True)
        print("  Sanitizer returncode:", res.returncode)
        print("  Sanitizer stderr (first 25 lines):")
        for line in res.stderr.splitlines()[:25]:
            print("    ", line)

if __name__ == "__main__":
    analyze_log()
    analyze_crashes()
