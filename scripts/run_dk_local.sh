#!/usr/bin/env bash
# Run the domain-knowledge (DK) condition for all 4 cricket formats
# (CricBench/IPL, ODI, T20I, Test) against a local open-source model, one
# format at a time.

set -uo pipefail
cd "$(dirname "$0")" || exit 1

MODEL="${1:?Usage: ./run_dk_local.sh <model-slug>}"
LOG="outputs/dk_local_run_${MODEL//[:\/]/_}.log"

# benchmark:target_instances
JOBS=(
  "cricbench:922"
  "odi:256"
  "t20i:779"
  "test:676"
)

echo "=== RUN start: model=$MODEL $(date '+%F %T') ===" | tee -a "$LOG"

# --- Step 0: confirm the local server is reachable before spending any time ---
python run_eval.py --benchmark cricbench --dry-run --resume --limit 1 \
  --dk --client local --model-slug "$MODEL" >> "$LOG" 2>&1
if [ $? -ne 0 ]; then
  echo "FAIL: dry-run wiring check failed. See $LOG" | tee -a "$LOG"
  exit 1
fi
echo "OK: dry-run wiring check passed for all formats (schema/prompts load fine)." | tee -a "$LOG"

# --- Step 1: wipe the dry-run's stub records so --resume doesn't skip real work ---
for job in "${JOBS[@]}"; do
  IFS=':' read -r benchmark target <<< "$job"
  rm -f "outputs/raw/${MODEL}_${benchmark}_dk.jsonl" "outputs/records/${MODEL}_${benchmark}_dk.json"
done
echo "Cleaned dry-run artifacts for model=$MODEL" | tee -a "$LOG"

# --- Step 2: real runs, one format at a time, looped until complete ---
for job in "${JOBS[@]}"; do
  IFS=':' read -r benchmark target <<< "$job"
  echo "=== JOB start: benchmark=$benchmark target=$target $(date '+%F %T') ===" >> "$LOG"
  for pass in $(seq 1 40); do
    echo "--- pass $pass start $(date '+%F %T') ---" >> "$LOG"
    python run_eval.py --benchmark "$benchmark" --resume --dk \
      --client local --model-slug "$MODEL" >> "$LOG" 2>&1
    n=$(python count_genuine.py --model "$MODEL" --benchmark "$benchmark" --dk)
    echo "--- pass $pass done: ${n}/${target} genuine ($(date '+%T')) ---" | tee -a "$LOG"
    if [ "${n:-0}" -ge "$target" ]; then
      echo "JOB DONE: $benchmark at pass $pass" | tee -a "$LOG"
      break
    fi
    sleep 10
  done

  # Per-condition summary CSV
  python summarize_condition.py \
    --records "outputs/records/${MODEL}_${benchmark}_dk.json" \
    --model "$MODEL" --benchmark "$benchmark" --dk >> "$LOG" 2>&1
done

echo "=== ALL DK JOBS FINISHED for model=$MODEL $(date '+%F %T') ===" | tee -a "$LOG"
echo "Per-condition results are in outputs/results/${MODEL}_*_dk_results.csv"
echo "Full log: $LOG"
