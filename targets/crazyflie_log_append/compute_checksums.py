import os
import hashlib

files = [
    r"/mnt/d/aeroharness/targets/crazyflie_log_append/crazyflie_log_append.h",
    r"/mnt/d/aeroharness/targets/crazyflie_log_append/log_append_target.c",
    r"/mnt/d/aeroharness/targets/crazyflie_log_append/openrouter_synthesizer_agent.py",
    r"/mnt/d/aeroharness/targets/crazyflie_log_append/run_log_append_self_repair.py",
    r"/mnt/d/aeroharness/targets/crazyflie_log_append/create_seeds.py",
    r"/mnt/d/aeroharness/targets/crazyflie_log_append/run_fuzz_campaign.sh",
    r"/mnt/d/aeroharness/targets/crazyflie_log_append/output/logAppendBlockV2/fuzz_logAppendBlockV2.cpp",
    r"/mnt/d/aeroharness/targets/crazyflie_log_append/output/logAppendBlockV2/fuzz_logAppendBlockV2_bin",
    r"/mnt/d/aeroharness/targets/crazyflie_log_append/output/logAppendBlockV2/repair_record.json",
]

seed_files = [
    r"/mnt/d/aeroharness/targets/crazyflie_log_append/output/logAppendBlockV2/corpus_seeded/seed1_uint8",
    r"/mnt/d/aeroharness/targets/crazyflie_log_append/output/logAppendBlockV2/corpus_seeded/seed2_uint16",
    r"/mnt/d/aeroharness/targets/crazyflie_log_append/output/logAppendBlockV2/corpus_seeded/seed3_uint32",
    r"/mnt/d/aeroharness/targets/crazyflie_log_append/output/logAppendBlockV2/corpus_seeded/seed4_float",
]

all_files = files + seed_files

for f in all_files:
    if os.path.exists(f):
        size = os.path.getsize(f)
        h = hashlib.sha256(open(f, "rb").read()).hexdigest()
        rel = os.path.relpath(f, "/mnt/d/aeroharness")
        print(f"{rel} | {size} | {h}")
