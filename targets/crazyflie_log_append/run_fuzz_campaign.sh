#!/usr/bin/env bash
set -e

DIR="/mnt/d/aeroharness/targets/crazyflie_log_append/output/logAppendBlockV2"
cd "$DIR"

rm -rf artifacts
mkdir -p artifacts

echo "=== Starting 300s fork-mode fuzzing campaign ==="
date

set +e
timeout 300 ./fuzz_logAppendBlockV2_bin \
    -fork=1 \
    -ignore_crashes=1 \
    -max_len=3 \
    -artifact_prefix=artifacts/ \
    corpus_seeded/ 2>&1 | tee fuzz_300s.log
RET=$?
set -e

echo "=== Campaign ended with returncode $RET ==="
date
