#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""开卡自检：检查当前实例上各 profile 所需模型是否齐全（切卡后先跑这个）。
用法: python3 /workspace/check_models.py [T4|A10]
"""
import sys, os
from pathlib import Path

M = Path("/workspace/ComfyUI/models")

NEED = {
    "T4": [
        ("diffusion_models/z_image_turbo_int8_convrot.safetensors", 5.8),
        ("text_encoders/qwen_3_4b_fp8_mixed.safetensors", 5.2),
        ("vae/ae.safetensors", 0.32),
        ("diffusion_models/flux-2-klein-4b.safetensors", 7.3),
        ("text_encoders/qwen_3_4b_fp8_mixed.safetensors", 5.2),
        ("vae/flux2-vae.safetensors", 0.32),
        ("diffusion_models/flux1-krea-dev_fp8_scaled.safetensors", 11.1),
        ("text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors", 5.0),
        ("text_encoders/clip_l.safetensors", 0.24),
        ("checkpoints/animagine-xl-4.0-opt.safetensors", 6.5),
        ("checkpoints/waiIllustriousSDXL_v170.safetensors", 6.5),
        ("checkpoints/pornmaster_proSDXLV8.safetensors", 6.6),
    ],
    "A10": [
        ("diffusion_models/qwen_image_2.1_turbo_int8_convrot.safetensors", 6.8),
        ("diffusion_models/qwen_image_2.1_int8_convrot.safetensors", 6.8),
        ("text_encoders/qwen3vl_8b_int8_convrot.safetensors", 8.8),
        ("vae/qwen_image_2.1_vae_bf16.safetensors", 0.65),
        ("diffusion_models/flux3-image-klein-bf16.safetensors", 11.0),
        ("text_encoders/qwen3vl_4b_int8_convrot.safetensors", 4.6),
        ("vae/flux2-vae.safetensors", 0.32),
        ("diffusion_models/krea2_turbo_fp8_scaled.safetensors", 12.2),
        ("text_encoders/qwen3vl_4b_fp8_scaled.safetensors", 5.24),
        ("vae/qwen_image_vae.safetensors", 0.25),
        ("diffusion_models/moss_image_sft_int8_convrot.safetensors", 5.41),
        ("text_encoders/qwen3.5_9b_int8_convrot.safetensors", 9.75),
        ("loras/MOSS-8steps-dmd.safetensors", 1.1),
        ("loras/MOSS-8steps-dmd-latest.safetensors", 1.1),
    ],
}

def check(prof):
    print(f"=== {prof} 所需模型自检 ===")
    miss, ok = [], 0
    seen = set()
    for rel, exp in NEED[prof]:
        if rel in seen:
            continue
        seen.add(rel)
        p = M / rel
        # 兼容旧路径：diffusion_models 的权重可能放在 models/unet/diffusion_models/
        ALT = {"diffusion_models/": "unet/diffusion_models/"}
        if not p.exists():
            for k, v in ALT.items():
                if rel.startswith(k):
                    cand = M / (v + rel[len(k):])
                    if cand.exists():
                        p = cand
                        break
        if not p.exists():
            miss.append((rel, exp, "缺失"))
            print(f"  ✗ {rel:62s} 缺失")
            continue
        gb = p.stat().st_size / 1e9
        if gb < exp * 0.92:
            miss.append((rel, exp, f"不完整 {gb:.1f}/{exp:.1f}G"))
            print(f"  ! {rel:62s} {gb:.1f}G < {exp:.1f}G（不完整）")
        else:
            ok += 1
            print(f"  ✓ {rel:62s} {gb:.1f}G")
    print(f"\n{prof}: 齐全 {ok}，缺失/不完整 {len(miss)}，需下载约 {sum(e for _, e, _ in miss):.1f}G")
    return miss

if __name__ == "__main__":
    profs = sys.argv[1:] or ["T4", "A10"]
    for p in profs:
        check(p)
        print()
