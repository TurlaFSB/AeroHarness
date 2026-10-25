import os
import hashlib

files = [
    r"/mnt/d/aeroharness/targets/crtp_trajectory_write/crtp_trajectory_write.h",
    r"/mnt/d/aeroharness/targets/crtp_trajectory_write/trajectory_write_target.c",
    r"/mnt/d/aeroharness/targets/crtp_trajectory_write/openrouter_synthesizer_agent.py",
    r"/mnt/d/aeroharness/targets/crtp_trajectory_write/run_trajectory_write_self_repair.py",
    r"/mnt/d/aeroharness/targets/crtp_trajectory_write/create_seeds.py",
    r"/mnt/d/aeroharness/targets/crtp_trajectory_write/run_fuzz_campaign.sh",
    r"/mnt/d/aeroharness/targets/crtp_trajectory_write/output/crtpCommanderHighLevelWriteTrajectory/fuzz_crtpCommanderHighLevelWriteTrajectory.cpp",
    r"/mnt/d/aeroharness/targets/crtp_trajectory_write/output/crtpCommanderHighLevelWriteTrajectory/fuzz_crtpCommanderHighLevelWriteTrajectory_bin",
    r"/mnt/d/aeroharness/targets/crtp_trajectory_write/output/crtpCommanderHighLevelWriteTrajectory/repair_record.json",
]

seed_files = [
    r"/mnt/d/aeroharness/targets/crtp_trajectory_write/output/crtpCommanderHighLevelWriteTrajectory/corpus_seeded/seed1_0_10",
    r"/mnt/d/aeroharness/targets/crtp_trajectory_write/output/crtpCommanderHighLevelWriteTrajectory/corpus_seeded/seed2_100_20",
    r"/mnt/d/aeroharness/targets/crtp_trajectory_write/output/crtpCommanderHighLevelWriteTrajectory/corpus_seeded/seed3_2000_50",
    r"/mnt/d/aeroharness/targets/crtp_trajectory_write/output/crtpCommanderHighLevelWriteTrajectory/corpus_seeded/seed4_3000_32",
    r"/mnt/d/aeroharness/targets/crtp_trajectory_write/output/crtpCommanderHighLevelWriteTrajectory/corpus_seeded/seed5_4080_16",
]

all_files = files + seed_files

for f in all_files:
    if os.path.exists(f):
        size = os.path.getsize(f)
        h = hashlib.sha256(open(f, "rb").read()).hexdigest()
        rel = os.path.relpath(f, "/mnt/d/aeroharness")
        print(f"{rel} | {size} | {h}")
