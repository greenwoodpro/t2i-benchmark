#!/usr/bin/env bash
# T4 (15.36G) 性能优先配置：
#  - fp16-unet：SDXL/Flux 原生 fp16，避免 bf16→fp32 显存翻倍
#  - lowvram：12G 级模型（krea_dev fp8→fp16 实际 24G）必须分块，否则 OOM
#  - reserve-vram 0.5：只留 0.5G 给系统，其余交给模型缓存
#  - 不再加 --disable-smart-memory：同模型连续跑时权重常驻显存，省掉每张图的 12G 重载
#  - disable-cuda-malloc：T4 上走 native 分配，避免 cudaMallocAsync 兼容问题
cd /workspace/ComfyUI || exit 1
exec python main.py --listen 0.0.0.0 --port 8188 \
  --fp16-unet --lowvram --reserve-vram 0.5 --disable-cuda-malloc
