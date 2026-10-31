#!/usr/bin/env bash
# T4 收尾（tmux 托管）：WAI 8 条 -> krea_dev 10 条 -> Z-Image 中文档 51 条 -> 报告/看板
set -u
S=/workspace/ComfyUI/t2i-benchmark-kit/t2i-benchmark-kit/03_scripts
OUT=/workspace/bench_out
LOG=/workspace/chain_T4_finish.log
cd "$S" || exit 1

step() { local n=$1; shift
  echo "=== [$(date -u +%H:%M:%S)] START $n" >> "$LOG"
  "$@" >> "$LOG" 2>&1
  echo "=== [$(date -u +%H:%M:%S)] END $n rc=$?" >> "$LOG"
}

echo "finish begin $(date -u)" > "$LOG"

step "wai standard" python3 -u run_benchmark.py --profile T4 --tier standard \
  --models sdxl_wai_illustrious --out "$OUT"

step "krea_dev standard" python3 -u run_benchmark.py --profile T4 --tier standard \
  --models flux1_krea_dev --out "$OUT"

step "z_image zh51" python3 -u run_benchmark.py --profile T4 --tier zh \
  --models z_image_turbo --out "$OUT"

echo "FINISH_DONE $(date -u)" >> "$LOG"
python3 make_report.py --out "$OUT" >> "$LOG" 2>&1
python3 /workspace/bench_out/gen_dashboard.py >> "$LOG" 2>&1
echo "REPORT_DONE $(date -u)" >> "$LOG"
