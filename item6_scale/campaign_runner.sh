#!/bin/bash
# Item 6 (vulnerability discovery at scale) campaign driver.
#
# Runs a pinned libFuzzer binary repeatedly against a persistent corpus
# directory until a total wall-clock budget is exhausted, logging every
# iteration. Looping (rather than one single -max_total_time call) matters
# for harnesses with a known near-instant hang (poll_out): a single long
# run would just die on the first hang and never explore further, so this
# restarts after every hang/crash/timeout and keeps accumulating executions
# and corpus growth across the full budget, surfacing any crash TYPE other
# than the already-documented one, not just re-finding the known one once.
set -u

BIN="$1"
CORPUS_DIR="$2"
LOG_DIR="$3"
PER_ITER_SEC="$4"      # -max_total_time per libFuzzer invocation
TOTAL_BUDGET_SEC="$5"  # total wall-clock budget for this target
TIMEOUT_SEC="${6:-5}"  # -timeout per test case

mkdir -p "$CORPUS_DIR" "$LOG_DIR"
START=$(date +%s)
ITER=0

echo "campaign_start=$(date -u +%FT%TZ) bin=$BIN total_budget=${TOTAL_BUDGET_SEC}s per_iter=${PER_ITER_SEC}s timeout=${TIMEOUT_SEC}s" >> "$LOG_DIR/campaign_summary.log"

while true; do
  NOW=$(date +%s)
  ELAPSED=$((NOW - START))
  REMAINING=$((TOTAL_BUDGET_SEC - ELAPSED))
  if [ "$REMAINING" -le 5 ]; then
    break
  fi
  THIS_ITER=$PER_ITER_SEC
  if [ "$REMAINING" -lt "$PER_ITER_SEC" ]; then
    THIS_ITER=$REMAINING
  fi
  ITER=$((ITER + 1))
  ITER_LOG="$LOG_DIR/iter_${ITER}.log"
  "$BIN" -max_total_time="$THIS_ITER" -timeout="$TIMEOUT_SEC" \
      -artifact_prefix="$LOG_DIR/" "$CORPUS_DIR" > "$ITER_LOG" 2>&1
  RC=$?
  LAST_LINE=$(tail -5 "$ITER_LOG" | tr '\n' ' | ')
  echo "iter=$ITER elapsed=${ELAPSED}s rc=$RC tail=[$LAST_LINE]" >> "$LOG_DIR/campaign_summary.log"
  # brief pause to avoid a tight crash-restart loop pegging the CPU on repeated instant crashes
  sleep 1
done

NOW=$(date +%s)
ELAPSED=$((NOW - START))
echo "campaign_end=$(date -u +%FT%TZ) total_elapsed=${ELAPSED}s total_iterations=$ITER corpus_size=$(ls -1 "$CORPUS_DIR" | wc -l)" >> "$LOG_DIR/campaign_summary.log"
