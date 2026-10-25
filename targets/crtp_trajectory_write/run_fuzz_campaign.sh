#!/usr/bin/env bash
set -e

DIR="/mnt/d/aeroharness/targets/crtp_trajectory_write/output/crtpCommanderHighLevelWriteTrajectory"
cd "$DIR"

rm -rf artifacts
mkdir -p artifacts

echo "=== Starting 300s fork-mode fuzzing campaign ==="
date

# Run fork mode with 300s timeout
set +e
timeout 300 ./fuzz_crtpCommanderHighLevelWriteTrajectory_bin \
    -fork=1 \
    -ignore_crashes=1 \
    -max_len=66 \
    -artifact_prefix=artifacts/ \
    corpus_seeded/ 2>&1 | tee fuzz_300s.log
RET=$?
set -e

echo "=== Campaign ended with returncode $RET ==="
date
