#!/usr/bin/env bash
# T4 (16G) 启动参数
cd /workspace/ComfyUI || exit 1
exec python main.py --listen 0.0.0.0 --port 8188 \
  --fp16-unet --lowvram --reserve-vram 0.5 --disable-smart-memory --disable-cuda-malloc
