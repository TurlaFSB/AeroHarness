import os
import struct

corpus_dir = "/mnt/d/aeroharness/targets/crazyflie_log_append/output/logAppendBlockV2/corpus_seeded"
os.makedirs(corpus_dir, exist_ok=True)

# 4 valid seeds based on log.h named constants (1, 2, 3, 7)
seeds = [
    ("seed1_uint8", 1, 0x0001),   # LOG_UINT8 = 1, id = 1
    ("seed2_uint16", 2, 0x0002),  # LOG_UINT16 = 2, id = 2
    ("seed3_uint32", 3, 0x0003),  # LOG_UINT32 = 3, id = 3
    ("seed4_float", 7, 0x0004),   # LOG_FLOAT = 7, id = 4
]

for name, log_type, var_id in seeds:
    payload = struct.pack("<BH", log_type, var_id)
    assert len(payload) == 3
    filepath = os.path.join(corpus_dir, name)
    with open(filepath, "wb") as f:
        f.write(payload)
    print(f"Wrote {name}: size={len(payload)}, logType={log_type}, id={var_id}, hex={payload.hex()}")
