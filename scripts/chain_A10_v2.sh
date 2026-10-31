#!/usr/bin/env bash
# ============================================================
# A10 自动链 v2（MOSS 优先 + 精确大小 + 断线自愈）
#   MOSS 齐 -> moss_image_fast 全量 51
#   krea2 齐 -> SFW 21 + NSFW 32
#   qwen turbo / base 齐 -> NSFW 各 22
#   日志: /workspace/runs/chain_A10_v2.log
# ============================================================
set -u
S=/workspace/ComfyUI/t2i-benchmark-kit/t2i-benchmark-kit/03_scripts
OUT=/workspace/bench_out
L=/workspace/runs
M=/workspace/ComfyUI/models
QB=https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/main
KB=https://huggingface.co/Comfy-Org/Krea-2/resolve/main
MB=https://huggingface.co/Comfy-Org/MOSS-Image/resolve/main
LOG=$L/chain_A10_v2.log
mkdir -p "$L"; : > "$LOG"
cd "$S" || exit 1

# 文件名|URL|目录|精确字节数
meta() {
  case "$1" in
    qwen3.5_9b_int8_convrot.safetensors)      echo "$MB/text_encoders/$1|$M/text_encoders|9748121532" ;;
    krea2_turbo_fp8_scaled.safetensors)       echo "$KB/diffusion_models/$1|$M/diffusion_models|13141730784" ;;
    qwen3vl_8b_int8_convrot.safetensors)      echo "$QB/text_encoders/$1|$M/text_encoders|9350798360" ;;
    qwen_image_2.1_turbo_int8_convrot.safetensors) echo "$QB/diffusion_models/$1|$M/diffusion_models|7256787829" ;;
    qwen_image_2.1_int8_convrot.safetensors)  echo "$QB/diffusion_models/$1|$M/diffusion_models|7256783064" ;;
    moss_image_sft_int8_convrot.safetensors)  echo "$MB/diffusion_models/$1|$M/diffusion_models|5413698958" ;;
    *) echo "$1||0" ;;
  esac
}

waitf() {  # $1=完整路径
  local base url dir size s n=0
  base=$(basename "$1")
  IFS='|' read -r url dir size <<< "$(meta "$base")"
  while :; do
    s=$(stat -c %s "$1" 2>/dev/null || echo 0)
    if [ "$s" -eq "$size" ] && ! pgrep -f "aria2c.*$base" >/dev/null; then
      echo "[$(date -u +%H:%M)] 就绪 $base ($(awk -v c=$s 'BEGIN{printf "%.2f",c/1e9}')G)" | tee -a "$LOG"
      return 0
    fi
    if [ "$s" -lt "$size" ] && ! pgrep -f "aria2c.*$base" >/dev/null; then
      echo "[$(date -u +%H:%M)] 补下 $base $(awk -v c=$s 'BEGIN{printf "%.2f",c/1e9}')G/$size" >>"$LOG"
      aria2c -c -x4 -s4 -k1M --file-allocation=none --max-tries=30 --retry-wait=3 \
        --connect-timeout=20 --timeout=60 --console-log-level=warn --summary-interval=0 \
        -d "$dir" -o "$base" "$url" >>"$LOG" 2>&1 &
    fi
    n=$((n+1)); [ $((n % 20)) -eq 0 ] && echo "[$(date -u +%H:%M)] 等待 $base $(awk -v c=$s 'BEGIN{printf "%.2f",c/1e9}')G/$(awk -v c=$size 'BEGIN{printf "%.2f",c/1e9}')G" >>"$LOG"
    sleep 15
  done
}

run() { echo "[$(date -u +%H:%M)] START $*" | tee -a "$LOG"
        python3 -u run_benchmark.py "$@" >>"$LOG" 2>&1
        echo "[$(date -u +%H:%M)] END rc=$?" | tee -a "$LOG"; }

# --- MOSS 8 步 LoRA 全量 51 ---
waitf "$M/diffusion_models/moss_image_sft_int8_convrot.safetensors"
waitf "$M/text_encoders/qwen3.5_9b_int8_convrot.safetensors"
run --profile A10 --tier standard --models moss_image_fast --out "$OUT"
python3 /workspace/bench_out/build_moss_compare.py >>"$LOG" 2>&1
echo "MOSS_FULL_DONE" | tee -a "$LOG"

# --- krea2 ---
waitf "$M/diffusion_models/krea2_turbo_fp8_scaled.safetensors"
run --profile A10 --tier standard --models krea2_turbo --out "$OUT"
run --profile A10 --tier nsfw_ext --allow-nsfw --clip-retry --models krea2_turbo --out "$OUT"

# --- qwen ---
waitf "$M/text_encoders/qwen3vl_8b_int8_convrot.safetensors"
waitf "$M/diffusion_models/qwen_image_2.1_turbo_int8_convrot.safetensors"
run --profile A10 --tier nsfw_ext --allow-nsfw --clip-retry --models qwen_image_2_1_turbo --out "$OUT"

waitf "$M/diffusion_models/qwen_image_2.1_int8_convrot.safetensors"
run --profile A10 --tier nsfw_ext --allow-nsfw --clip-retry --models qwen_image_2_1 --out "$OUT"

echo "CHAIN_DONE $(date -u)" | tee -a "$LOG"
