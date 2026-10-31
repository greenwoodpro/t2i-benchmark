#!/usr/bin/env bash
# =====================================================================
#  download_models.sh —— 按显卡档位 / 模型组 下载测评所需模型（可在 CPU 机器上先跑）
#
#  用法:
#    bash download_models.sh <profile> [group ...]
#      profile : T4 | A10 | all
#      group   : dit | sdxl | nsfw | all   (默认 all)
#
#  示例:
#    bash download_models.sh T4            # T4 档位全部模型（不含 nsfw）
#    bash download_models.sh A10 dit       # A10 只下 DiT 类（Z-Image/Klein/Krea/Qwen）
#    bash download_models.sh all nsfw      # 只下 NSFW SDXL 模型
#
#  环境变量:
#    COMFY_DIR      ComfyUI 根目录，默认 $PWD/ComfyUI
#    HF_TOKEN       HuggingFace token（下载 FLUX.2 klein 9B 等 gated 模型必需）
#    CIVITAI_TOKEN  Civitai API key（下载 Civitai 模型必需，https://civitai.com/user/account）
#    HF_ENDPOINT    HF 镜像，如 https://hf-mirror.com（国内加速，可选）
#
#  所有链接均于 2026-10 通过 HF API / Civitai API 核实；大小见 01_models/models.json
#  支持断点续传：aria2c 优先，否则 wget -c
# =====================================================================
set -euo pipefail

PROFILE="${1:-all}"; shift || true
GROUPS_SEL="${*:-all}"
COMFY_DIR="${COMFY_DIR:-$PWD/ComfyUI}"
HF="${HF_ENDPOINT:-https://huggingface.co}"
M="$COMFY_DIR/models"
mkdir -p "$M/diffusion_models" "$M/text_encoders" "$M/vae" "$M/checkpoints" "$M/clip"

log(){ printf '\033[1;36m[dl]\033[0m %s\n' "$*"; }
has_group(){ [[ " $GROUPS_SEL " == *" all "* || " $GROUPS_SEL " == *" $1 "* ]]; }
is_profile(){ [[ "$PROFILE" == "all" || "$PROFILE" == "$1" ]]; }

dl(){ # dl <url> <dest> [auth_header]
  local url="$1" dest="$2" hdr="${3:-}"
  if [[ -f "$dest" && ! -f "$dest.aria2" ]]; then log "已存在，跳过: $(basename "$dest")"; return; fi
  log "下载 -> $dest"
  if command -v aria2c >/dev/null 2>&1; then
    aria2c -c -x 16 -s 16 -k 1M --file-allocation=none --console-log-level=warn --summary-interval=30 \
      ${hdr:+--header="$hdr"} -d "$(dirname "$dest")" -o "$(basename "$dest")" "$url"
  else
    wget -c -q --show-progress ${hdr:+--header="$hdr"} -O "$dest" "$url"
  fi
}
hf(){ dl "$HF/$1" "$2" ${HF_TOKEN:+"Authorization: Bearer $HF_TOKEN"}; }
civ(){ # civ <version_id> <dest>
  [[ -z "${CIVITAI_TOKEN:-}" ]] && { echo "!! 需要 CIVITAI_TOKEN 才能下载 Civitai 模型（跳过 $2）"; return; }
  dl "https://civitai.com/api/download/models/$1?type=Model&format=SafeTensor&token=$CIVITAI_TOKEN" "$2"
}

log "profile=$PROFILE groups=$GROUPS_SEL  COMFY_DIR=$COMFY_DIR  HF=$HF"

# ---------------------------------------------------------------- 共用 VAE
if has_group dit; then
  hf Comfy-Org/z_image_turbo/resolve/main/split_files/vae/ae.safetensors            "$M/vae/ae.safetensors"
  hf Comfy-Org/flux2-klein/resolve/main/split_files/vae/flux2-vae.safetensors      "$M/vae/flux2-vae.safetensors"
  hf Comfy-Org/Qwen-Image-2.1/resolve/main/vae/qwen_image_2.1_vae_bf16.safetensors "$M/vae/qwen_image_2.1_vae_bf16.safetensors"

  # ---------------------------------------------------------------- Z-Image-Turbo + FLUX.2 klein 4B（共用 qwen_3_4b 文本编码器）
  hf Comfy-Org/flux2-klein/resolve/main/split_files/diffusion_models/flux-2-klein-4b.safetensors "$M/diffusion_models/flux-2-klein-4b.safetensors"
  if is_profile A10; then
    hf Comfy-Org/z_image_turbo/resolve/main/split_files/diffusion_models/z_image_turbo_bf16.safetensors "$M/diffusion_models/z_image_turbo_bf16.safetensors"
    hf Comfy-Org/z_image_turbo/resolve/main/split_files/text_encoders/qwen_3_4b.safetensors              "$M/text_encoders/qwen_3_4b.safetensors"
  fi
  if is_profile T4; then
    hf Comfy-Org/z_image_turbo/resolve/main/split_files/diffusion_models/z_image_turbo_int8_convrot.safetensors "$M/diffusion_models/z_image_turbo_int8_convrot.safetensors"
    hf Comfy-Org/z_image_turbo/resolve/main/split_files/text_encoders/qwen_3_4b_fp8_mixed.safetensors            "$M/text_encoders/qwen_3_4b_fp8_mixed.safetensors"
    # klein 4B 在 T4 上也用 fp8_mixed 的 qwen_3_4b（同一架构，type=flux2 可加载）
  fi

  # ---------------------------------------------------------------- FLUX.2 klein 9B（仅 A10，gated）
  if is_profile A10; then
    if [[ -n "${HF_TOKEN:-}" ]]; then
      hf black-forest-labs/FLUX.2-klein-9b/resolve/main/flux-2-klein-9b.safetensors                              "$M/diffusion_models/flux-2-klein-9b.safetensors"
      hf Comfy-Org/flux2-klein-9b/resolve/main/split_files/text_encoders/qwen_3_8b_fp8mixed.safetensors         "$M/text_encoders/qwen_3_8b_fp8mixed.safetensors"
    else
      echo "!! 跳过 FLUX.2 klein 9B：需要 HF_TOKEN 且已在 https://huggingface.co/black-forest-labs/FLUX.2-klein-9b 同意许可"
    fi
  fi

  # ---------------------------------------------------------------- FLUX.1 Krea dev（fp8_scaled 两档通用）
  hf Comfy-Org/FLUX.1-Krea-dev_ComfyUI/resolve/main/split_files/diffusion_models/flux1-krea-dev_fp8_scaled.safetensors "$M/diffusion_models/flux1-krea-dev_fp8_scaled.safetensors"
  hf comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors "$M/text_encoders/clip_l.safetensors"
  if is_profile A10; then hf comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp16.safetensors            "$M/text_encoders/t5xxl_fp16.safetensors"; fi
  if is_profile T4;  then hf comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn_scaled.safetensors "$M/text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors"; fi

  # ---------------------------------------------------------------- Qwen-Image 2.1（int8_convrot 两档通用；Turbo 优先）
  hf Comfy-Org/Qwen-Image-2.1/resolve/main/diffusion_models/qwen_image_2.1_turbo_int8_convrot.safetensors "$M/diffusion_models/qwen_image_2.1_turbo_int8_convrot.safetensors"
  hf Comfy-Org/Qwen-Image-2.1/resolve/main/diffusion_models/qwen_image_2.1_int8_convrot.safetensors       "$M/diffusion_models/qwen_image_2.1_int8_convrot.safetensors"
  hf Comfy-Org/Qwen-Image-2.1/resolve/main/text_encoders/qwen3vl_8b_int8_convrot.safetensors              "$M/text_encoders/qwen3vl_8b_int8_convrot.safetensors"
  if is_profile T4; then hf Comfy-Org/Qwen-Image-2.1/resolve/main/text_encoders/qwen3vl_8b_w4a8.safetensors "$M/text_encoders/qwen3vl_8b_w4a8.safetensors"; fi
fi

# ---------------------------------------------------------------- SDXL 二次元
if has_group sdxl; then
  hf cagliostrolab/animagine-xl-4.0/resolve/main/animagine-xl-4.0-opt.safetensors "$M/checkpoints/animagine-xl-4.0-opt.safetensors"
  civ 2883731 "$M/checkpoints/waiIllustriousSDXL_v170.safetensors"
  hf madebyollin/sdxl-vae-fp16-fix/resolve/main/sdxl_vae.safetensors "$M/vae/sdxl_vae_fp16_fix.safetensors"
fi

# ---------------------------------------------------------------- NSFW SDXL
if has_group nsfw; then
  civ 2551619 "$M/checkpoints/pornmaster_proSDXLV8.safetensors"
  hf madebyollin/sdxl-vae-fp16-fix/resolve/main/sdxl_vae.safetensors "$M/vae/sdxl_vae_fp16_fix.safetensors"
fi

log "完成。磁盘占用："
du -sh "$M"/* 2>/dev/null || true
