#!/usr/bin/env python3
"""
run_benchmark.py —— 通过 ComfyUI HTTP API 批量跑测评，自动保存图片 + 元数据。

依赖: Python 3.9+, requests (pip install requests)；Pillow 可选（写 PNG 元数据）。
前提: ComfyUI 已启动（默认 http://127.0.0.1:8188），模型已按 01_models/models.json 放好。

常用示例:
  # 冒烟（3 条 prompt）验证流水线
  python run_benchmark.py --profile T4 --tier smoke --models z_image_turbo
  # T4 标准测评（51 条 SFW × 1 seed）
  python run_benchmark.py --profile T4 --tier standard --models z_image_turbo flux2_klein_4b flux1_krea_dev qwen_image_2_1_turbo sdxl_animagine_xl_4 sdxl_wai_illustrious
  # A10 全量
  python run_benchmark.py --profile A10 --tier full --models all
  # NSFW（需显式允许）
  python run_benchmark.py --profile A10 --tier nsfw --allow-nsfw --models sdxl_pornmaster_pro_v8 sdxl_wai_illustrious
  # 中文提示词测试（仅 Z-Image / Qwen）
  python run_benchmark.py --profile A10 --tier zh --prompt-lang zh --models z_image_turbo qwen_image_2_1_turbo
  # 只导出工作流 JSON（可拖进 ComfyUI 网页），不跑图
  python run_benchmark.py --profile A10 --models all --export-workflows ../04_workflows/exported

输出目录结构 (默认 ./bench_out):
  bench_out/<profile>/sfw/<model>/<prompt_id>__s<seed>.png
  bench_out/<profile>/nsfw/<model>/...
  bench_out/<profile>/records.jsonl   每图一行完整元数据
  bench_out/<profile>/records.csv     同上，表格
"""
import argparse, csv, json, os, subprocess, sys, threading, time, uuid, urllib.parse
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("缺少 requests: pip install requests")

HERE = Path(__file__).resolve().parent
KIT = HERE.parent
MODELS_JSON = KIT / "01_models" / "models.json"
PROMPTS_JSON = KIT / "02_prompts" / "prompts.json"

# ------------------------------------------------------------------ 模型运行配置（文件名需与 download_models.sh 一致）
def model_configs(profile: str):
    t4 = profile == "T4"
    return {
        "z_image_turbo": dict(
            kind="zimage",
            unet="z_image_turbo_int8_convrot.safetensors" if t4 else "z_image_turbo_bf16.safetensors",
            clip="qwen_3_4b_fp8_mixed.safetensors" if t4 else "qwen_3_4b.safetensors", clip_type="lumina2",
            vae="ae.safetensors", steps=8, cfg=1.0, sampler="res_multistep", scheduler="simple", shift=3.0,
            prompt_field="prompt", zh=True),
        "flux2_klein_4b": dict(
            kind="flux2",
            unet="flux-2-klein-4b.safetensors",
            clip="qwen_3_4b_fp8_mixed.safetensors" if t4 else "qwen_3_4b.safetensors", clip_type="flux2",
            vae="flux2-vae.safetensors", steps=4, cfg=1.0, sampler="euler", prompt_field="prompt"),
        "flux2_klein_9b": dict(
            kind="flux2", unet="flux-2-klein-9b.safetensors", unet_dtype="fp8_e4m3fn",
            clip="qwen_3_8b_fp8mixed.safetensors", clip_type="flux2",
            vae="flux2-vae.safetensors", steps=4, cfg=1.0, sampler="euler", prompt_field="prompt", a10_only=True),
        "flux3_klein": dict(
            kind="flux3",
            unet="flux3-image-klein-bf16.safetensors",
            clip="qwen3vl_4b_int8_convrot.safetensors", clip_type="flux3",
            vae="flux2-vae.safetensors", steps=16, cfg=1.0, sampler="euler", scheduler="simple",
            shift=2.77259, prompt_field="prompt",
            note="FLUX.3 klein distilled；官方模板：16步 cfg1 euler simple，ModelSamplingFlux max_shift=base_shift=ln(16)≈2.77259，空负面。T4 用 bf16 权重(自动转fp16计算)：int8_convrot 在 T4 无原生算子支持，走 emulated fp32 路径触发 CUBLAS_STATUS_NOT_INITIALIZED，详见 bench_out/CHANGELOG.md"),
        "flux1_krea_dev": dict(
            kind="flux1",
            unet="flux1-krea-dev_fp8_scaled.safetensors",
            t5="t5xxl_fp8_e4m3fn_scaled.safetensors" if t4 else "t5xxl_fp16.safetensors", clip_l="clip_l.safetensors",
            vae="ae.safetensors", steps=20, cfg=1.0, sampler="euler", scheduler="simple", guidance=3.5,
            prompt_field="prompt"),
        "qwen_image_2_1_turbo": dict(
            kind="qwen21",
            unet="qwen_image_2.1_turbo_int8_convrot.safetensors",
            clip="qwen3vl_8b_w4a8.safetensors" if t4 else "qwen3vl_8b_int8_convrot.safetensors", clip_type="qwen_image",
            vae="qwen_image_2.1_vae_bf16.safetensors", steps=8, cfg=1.0, sampler="euler", scheduler="simple",
            prompt_field="prompt", zh=True),
        "qwen_image_2_1": dict(
            kind="qwen21",
            unet="qwen_image_2.1_int8_convrot.safetensors",
            clip="qwen3vl_8b_w4a8.safetensors" if t4 else "qwen3vl_8b_int8_convrot.safetensors", clip_type="qwen_image",
            vae="qwen_image_2.1_vae_bf16.safetensors", steps=25, cfg=1.0, sampler="euler", scheduler="simple",
            prompt_field="prompt", zh=True),
        "moss_image": dict(
            kind="moss",
            unet="moss_image_sft_int8_convrot.safetensors",
            clip="qwen3.5_9b_int8_convrot.safetensors", clip_type="moss_image",
            vae="flux2-vae.safetensors", steps=50, cfg=3.0, sampler="euler", scheduler="simple",
            prompt_field="prompt", zh=True,
            note="MOSS-Image SFT (OpenMOSS 5B DiT, FLUX.2 latent, Qwen3.5-9B TE)。官方建议 ≥50步 / cfg3 / shift5（shift 由 sampling_settings 自动施加），真实负面提示词"),
        "krea2_turbo": dict(
            kind="krea2",
            unet="krea2_turbo_fp8_scaled.safetensors",
            clip="qwen3vl_4b_fp8_scaled.safetensors", clip_type="krea2",
            vae="qwen_image_vae.safetensors", steps=8, cfg=1.0, sampler="euler", scheduler="simple",
            prompt_field="prompt", zh=True, a10_only=True,
            note="Krea 2 Turbo fp8_scaled 12.2G（本地已有，models/unet/diffusion_models）。官方建议 8步 cfg1 euler simple，shift1.15 由 sampling_settings 施加；latent 为 Wan21(16ch)，用 EmptySD3LatentImage"),
        "moss_image_fast": dict(
            kind="moss_fast",
            unet="moss_image_sft_int8_convrot.safetensors",
            clip="qwen3.5_9b_int8_convrot.safetensors", clip_type="moss_image",
            vae="flux2-vae.safetensors", steps=8, cfg=1.0, sampler="euler", scheduler="simple",
            lora="MOSS-8steps-dmd-latest.safetensors", lora_strength=0.7,
            prompt_field="prompt", zh=True,
            note="MOSS-Image + 8 步 DMD 蒸馏 LoRA（lodestones/MOSS-Image-SFT-8-steps-dmd，Apache-2.0）。"
                 "8 步 / 无 CFG，与官方 50 步基线不可混比，报告里单列 moss_image_fast"),
        # ---- MOSS 原模型（Base）加速档：为 T4 16G 设计 ----
        # 权重：base_int8 DiT 5.41G + qwen3.5_9b_w4a8 TE 7.34G + vae_small 0.25G ≈ 13.0G，
        # 两个卡统一用这一套（同一 model id 才能跨卡对比），T4 需 --lowvram 兜底。
        "moss_image_base_fast": dict(
            kind="moss_fast",
            unet="moss_image_base_int8_convrot.safetensors",
            clip="qwen3.5_9b_w4a8_gptq.safetensors", clip_type="moss_image",
            vae="flux2-vae_small.safetensors", steps=8, cfg=1.0, sampler="euler", scheduler="simple",
            lora="MOSS-Base-8steps-dmd.safetensors", lora_strength=0.7,
            prompt_field="prompt", zh=True,
            note="MOSS-Image **Base 原模型** + 8 步 DMD LoRA（lodestones/MOSS-Image-Base-8-steps-dmd）"
                 "+ 4bit TE(w4a8) + small VAE：权重约 13G，目标 T4 16G。与 SFT 版 moss_image_fast 是不同基模，不可混算"),
        "moss_image_base": dict(
            kind="moss",
            unet="moss_image_base_int8_convrot.safetensors",
            clip="qwen3.5_9b_w4a8_gptq.safetensors", clip_type="moss_image",
            vae="flux2-vae_small.safetensors", steps=50, cfg=3.0, sampler="euler", scheduler="simple",
            prompt_field="prompt", zh=True,
            note="MOSS-Image Base 原模型官方口径（50步/cfg3），仅作 moss_image_base_fast 的质量对照组，同 TE/VAE 便于 A/B"),
        "sdxl_animagine_xl_4": dict(
            kind="sdxl", ckpt="animagine-xl-4.0-opt.safetensors",
            steps=28, cfg=5.0, sampler="euler_ancestral", scheduler="normal",
            prefix="masterpiece, high score, great score, absurdres, ",
            negative="lowres, bad anatomy, bad hands, text, error, missing finger, extra digits, fewer digits, cropped, worst quality, low quality, low score, bad score, average score, signature, watermark, username, blurry",
            prompt_field="tags", nsfw_ok=True),
        "sdxl_wai_illustrious": dict(
            kind="sdxl", ckpt="waiIllustriousSDXL_v170.safetensors",
            steps=28, cfg=6.0, sampler="euler_ancestral", scheduler="normal",
            prefix="masterpiece, best quality, amazing quality, very aesthetic, absurdres, ",
            negative="bad quality, worst quality, worst detail, sketch, censor, lowres, bad anatomy, bad hands, watermark, signature",
            prompt_field="tags", nsfw_ok=True),
        "sdxl_pornmaster_pro_v8": dict(
            kind="sdxl", ckpt="pornmaster_proSDXLV8.safetensors", vae_override="sdxl_vae_fp16_fix.safetensors",
            steps=30, cfg=5.0, sampler="dpmpp_2m", scheduler="karras",
            prefix="photorealistic, RAW photo, 8k uhd, detailed skin texture, ",
            negative="cartoon, anime, 3d, painting, lowres, bad anatomy, bad hands, deformed, extra limbs, watermark, text, blurry, child, kid, teen, young girl",
            prompt_field="sdxl_prompt", nsfw_ok=True, nsfw_model=True),
    }

# ------------------------------------------------------------------ 构建 ComfyUI API 格式工作流
def build_graph(cfg, pos, neg, w, h, seed, prefix):
    g, n = {}, [0]
    def add(cls, **inputs):
        n[0] += 1; k = str(n[0]); g[k] = {"class_type": cls, "inputs": inputs}; return k
    kind = cfg["kind"]
    if kind == "sdxl":
        ck = add("CheckpointLoaderSimple", ckpt_name=cfg["ckpt"])
        model, clip, vae = [ck, 0], [ck, 1], [ck, 2]
        if cfg.get("vae_override"):
            vae = [add("VAELoader", vae_name=cfg["vae_override"]), 0]
        p = add("CLIPTextEncode", text=pos, clip=clip)
        ng = add("CLIPTextEncode", text=neg, clip=clip)
        lat = add("EmptyLatentImage", width=w, height=h, batch_size=1)
        ks = add("KSampler", model=model, seed=seed, steps=cfg["steps"], cfg=cfg["cfg"], sampler_name=cfg["sampler"],
                 scheduler=cfg["scheduler"], denoise=1.0, positive=[p, 0], negative=[ng, 0], latent_image=[lat, 0])
        dec = add("VAEDecode", samples=[ks, 0], vae=vae)
    elif kind == "zimage":
        un = add("UNETLoader", unet_name=cfg["unet"], weight_dtype=cfg.get("unet_dtype", "default"))
        cl = add("CLIPLoader", clip_name=cfg["clip"], type=cfg["clip_type"], device="default")
        va = add("VAELoader", vae_name=cfg["vae"])
        ms = add("ModelSamplingAuraFlow", model=[un, 0], shift=cfg["shift"])
        p = add("CLIPTextEncode", text=pos, clip=[cl, 0])
        ng = add("ConditioningZeroOut", conditioning=[p, 0])
        lat = add("EmptySD3LatentImage", width=w, height=h, batch_size=1)
        ks = add("KSampler", model=[ms, 0], seed=seed, steps=cfg["steps"], cfg=cfg["cfg"], sampler_name=cfg["sampler"],
                 scheduler=cfg["scheduler"], denoise=1.0, positive=[p, 0], negative=[ng, 0], latent_image=[lat, 0])
        dec = add("VAEDecode", samples=[ks, 0], vae=[va, 0])
    elif kind == "flux1":
        un = add("UNETLoader", unet_name=cfg["unet"], weight_dtype="default")
        cl = add("DualCLIPLoader", clip_name1=cfg["t5"], clip_name2=cfg["clip_l"], type="flux", device="default")
        va = add("VAELoader", vae_name=cfg["vae"])
        p0 = add("CLIPTextEncode", text=pos, clip=[cl, 0])
        p = add("FluxGuidance", conditioning=[p0, 0], guidance=cfg["guidance"])
        ng = add("ConditioningZeroOut", conditioning=[p0, 0])
        lat = add("EmptySD3LatentImage", width=w, height=h, batch_size=1)
        ks = add("KSampler", model=[un, 0], seed=seed, steps=cfg["steps"], cfg=cfg["cfg"], sampler_name=cfg["sampler"],
                 scheduler=cfg["scheduler"], denoise=1.0, positive=[p, 0], negative=[ng, 0], latent_image=[lat, 0])
        dec = add("VAEDecode", samples=[ks, 0], vae=[va, 0])
    elif kind == "flux2":
        un = add("UNETLoader", unet_name=cfg["unet"], weight_dtype=cfg.get("unet_dtype", "default"))
        cl = add("CLIPLoader", clip_name=cfg["clip"], type=cfg["clip_type"], device="default")
        va = add("VAELoader", vae_name=cfg["vae"])
        p = add("CLIPTextEncode", text=pos, clip=[cl, 0])
        ng = add("ConditioningZeroOut", conditioning=[p, 0])
        lat = add("EmptyFlux2LatentImage", width=w, height=h, batch_size=1)
        noise = add("RandomNoise", noise_seed=seed)
        samp = add("KSamplerSelect", sampler_name=cfg["sampler"])
        guider = add("CFGGuider", model=[un, 0], positive=[p, 0], negative=[ng, 0], cfg=cfg["cfg"])
        sig = add("Flux2Scheduler", steps=cfg["steps"], width=w, height=h)
        ks = add("SamplerCustomAdvanced", noise=[noise, 0], guider=[guider, 0], sampler=[samp, 0], sigmas=[sig, 0], latent_image=[lat, 0])
        dec = add("VAEDecode", samples=[ks, 0], vae=[va, 0])
    elif kind == "flux3":
        # FLUX.3 klein（官方 workflows/flux3_klein_int8_t2i.json 模板：KSampler + ModelSamplingFlux(ln(steps))）
        un = add("UNETLoader", unet_name=cfg["unet"], weight_dtype=cfg.get("unet_dtype", "default"))
        cl = add("CLIPLoader", clip_name=cfg["clip"], type=cfg["clip_type"], device="default")
        va = add("VAELoader", vae_name=cfg["vae"])
        p = add("CLIPTextEncode", text=pos, clip=[cl, 0])
        ng = add("CLIPTextEncode", text=neg or "", clip=[cl, 0])  # 官方模板：空字符串负面而非 ConditioningZeroOut
        ms = add("ModelSamplingFlux", model=[un, 0], max_shift=cfg["shift"], base_shift=cfg["shift"], width=w, height=h)
        lat = add("EmptyFlux2LatentImage", width=w, height=h, batch_size=1)
        ks = add("KSampler", model=[ms, 0], seed=seed, steps=cfg["steps"], cfg=cfg["cfg"], sampler_name=cfg["sampler"],
                 scheduler=cfg["scheduler"], denoise=1.0, positive=[p, 0], negative=[ng, 0], latent_image=[lat, 0])
        dec = add("VAEDecode", samples=[ks, 0], vae=[va, 0])
    elif kind == "qwen21":
        un = add("UNETLoader", unet_name=cfg["unet"], weight_dtype="default")
        cl = add("CLIPLoader", clip_name=cfg["clip"], type=cfg["clip_type"], device="default")
        va = add("VAELoader", vae_name=cfg["vae"])
        if cfg.get("qwen_encoder", "qwen21") == "qwen21":
            # 官方模板节点：输出 positive / negative / latent；本脚本只用前两个
            # 新版 ComfyUI（2026-10）必填 resolution（参考图缩放用，纯 t2i 传 1024），images 可留空
            enc = add("TextEncodeQwenImage21", clip=[cl, 0], vae=[va, 0], prompt=pos, negative_prompt=neg or "", resolution=1024)
            pcond, ncond = [enc, 0], [enc, 1]
        else:  # 兜底：通用编码
            p = add("CLIPTextEncode", text=pos, clip=[cl, 0])
            pcond = [p, 0]; ncond = [add("ConditioningZeroOut", conditioning=[p, 0]), 0]
        lat = add("EmptyLatentImage", width=w, height=h, batch_size=1)
        ks = add("KSampler", model=[un, 0], seed=seed, steps=cfg["steps"], cfg=cfg["cfg"], sampler_name=cfg["sampler"],
                 scheduler=cfg["scheduler"], denoise=1.0, positive=pcond, negative=ncond, latent_image=[lat, 0])
        dec = add("VAEDecode", samples=[ks, 0], vae=[va, 0])
    elif kind == "moss_fast":
        # MOSS-Image + 8 步 DMD LoRA：无 CFG（cfg=1，负面不参与），其余与 moss 一致
        un = add("UNETLoader", unet_name=cfg["unet"], weight_dtype=cfg.get("unet_dtype", "default"))
        if cfg.get("lora"):
            un = add("LoraLoaderModelOnly", model=[un, 0], lora_name=cfg["lora"],
                     strength_model=cfg.get("lora_strength", 1.0))
        cl = add("CLIPLoader", clip_name=cfg["clip"], type=cfg["clip_type"], device="default")
        va = add("VAELoader", vae_name=cfg["vae"])
        p = add("CLIPTextEncode", text=pos, clip=[cl, 0])
        ng = add("CLIPTextEncode", text=neg or "", clip=[cl, 0])
        lat = add("EmptyFlux2LatentImage", width=w, height=h, batch_size=1)
        ks = add("KSampler", model=[un, 0], seed=seed, steps=cfg["steps"], cfg=cfg["cfg"],
                 sampler_name=cfg["sampler"], scheduler=cfg["scheduler"], denoise=1.0,
                 positive=[p, 0], negative=[ng, 0], latent_image=[lat, 0])
        dec = add("VAEDecode", samples=[ks, 0], vae=[va, 0])
    elif kind == "krea2":
        # Krea 2：Wan21 latent(16ch)，8步 cfg1 euler simple
        un = add("UNETLoader", unet_name=cfg["unet"], weight_dtype=cfg.get("unet_dtype", "default"))
        cl = add("CLIPLoader", clip_name=cfg["clip"], type=cfg["clip_type"], device="default")
        va = add("VAELoader", vae_name=cfg["vae"])
        p = add("CLIPTextEncode", text=pos, clip=[cl, 0])
        ng = add("CLIPTextEncode", text=neg or "", clip=[cl, 0])
        lat = add("EmptySD3LatentImage", width=w, height=h, batch_size=1)
        ks = add("KSampler", model=[un, 0], seed=seed, steps=cfg["steps"], cfg=cfg["cfg"], sampler_name=cfg["sampler"],
                 scheduler=cfg["scheduler"], denoise=1.0, positive=[p, 0], negative=[ng, 0], latent_image=[lat, 0])
        dec = add("VAEDecode", samples=[ks, 0], vae=[va, 0])
    elif kind == "moss":
        # MOSS-Image：FLUX.2 latent 空间 + 真实负面（官方 cfg3 / ≥50步 / shift5 由 sampling_settings 施加）
        un = add("UNETLoader", unet_name=cfg["unet"], weight_dtype=cfg.get("unet_dtype", "default"))
        cl = add("CLIPLoader", clip_name=cfg["clip"], type=cfg["clip_type"], device="default")
        va = add("VAELoader", vae_name=cfg["vae"])
        p = add("CLIPTextEncode", text=pos, clip=[cl, 0])
        ng = add("CLIPTextEncode", text=neg or "", clip=[cl, 0])
        lat = add("EmptyFlux2LatentImage", width=w, height=h, batch_size=1)
        ks = add("KSampler", model=[un, 0], seed=seed, steps=cfg["steps"], cfg=cfg["cfg"], sampler_name=cfg["sampler"],
                 scheduler=cfg["scheduler"], denoise=1.0, positive=[p, 0], negative=[ng, 0], latent_image=[lat, 0])
        dec = add("VAEDecode", samples=[ks, 0], vae=[va, 0])
    else:
        raise ValueError(kind)
    add("SaveImage", images=[dec, 0], filename_prefix=prefix)
    return g

# ------------------------------------------------------------------ VRAM 采样线程
class VramMonitor(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True); self.peak = -1; self.stop = threading.Event()
    def run(self):
        while not self.stop.is_set():
            try:
                out = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], timeout=5)
                self.peak = max(self.peak, int(out.decode().strip().splitlines()[0]))
            except Exception:
                pass
            time.sleep(0.5)

def gpu_name():
    try:
        return subprocess.check_output(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], timeout=5).decode().strip().splitlines()[0]
    except Exception:
        return "unknown"

# ------------------------------------------------------------------ ComfyUI API
def comfy_run(server, graph, timeout=1800):
    cid = str(uuid.uuid4())
    r = requests.post(f"{server}/prompt", json={"prompt": graph, "client_id": cid}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"ComfyUI 拒绝工作流: {r.status_code} {r.text[:800]}")
    pid = r.json()["prompt_id"]
    t0 = time.time()
    while True:
        h = requests.get(f"{server}/history/{pid}", timeout=60).json()
        if pid in h:
            item = h[pid]
            st = item.get("status", {})
            if st.get("status_str") == "error":
                msgs = [m for m in st.get("messages", []) if m[0] == "execution_error"]
                raise RuntimeError(f"执行错误: {json.dumps(msgs, ensure_ascii=False)[:1200]}")
            imgs = []
            for node_out in item.get("outputs", {}).values():
                imgs += node_out.get("images", [])
            return pid, imgs
        if time.time() - t0 > timeout:
            raise TimeoutError("等待超时")
        time.sleep(1.0)

def comfy_fetch(server, img):
    q = urllib.parse.urlencode({"filename": img["filename"], "subfolder": img.get("subfolder", ""), "type": img.get("type", "output")})
    r = requests.get(f"{server}/view?{q}", timeout=120); r.raise_for_status(); return r.content

def write_png_with_meta(path: Path, data: bytes, meta: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image, PngImagePlugin
        import io
        im = Image.open(io.BytesIO(data)); info = PngImagePlugin.PngInfo()
        info.add_text("benchmark", json.dumps(meta, ensure_ascii=False))
        info.add_text("prompt", meta["prompt_used"]); im.save(path, pnginfo=info)
    except Exception:
        path.write_bytes(data)

# ------------------------------------------------------------------ 主流程
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--server", default=os.environ.get("COMFY_SERVER", "http://127.0.0.1:8188"))
    ap.add_argument("--profile", required=True, choices=["T4", "A10"])
    ap.add_argument("--models", nargs="+", required=True, help="模型 id 列表或 all")
    ap.add_argument("--tier", default="standard", choices=["smoke", "quick", "top20", "round2", "standard", "full", "nsfw", "nsfw_ext", "zh", "custom"])
    ap.add_argument("--prompt-ids", nargs="*", default=[], help="tier=custom 时指定 prompt id")
    ap.add_argument("--seeds", nargs="*", type=int, default=None, help="覆盖 tier 默认 seeds")
    ap.add_argument("--prompt-lang", default="auto", choices=["auto", "en", "zh"], help="auto: 模型按其 prompt_field；zh 仅对支持中文的模型生效")
    ap.add_argument("--allow-nsfw", action="store_true")
    ap.add_argument("--out", default="./bench_out")
    ap.add_argument("--no-resume", action="store_true", help="默认跳过已存在的图；加此参数强制重跑")
    ap.add_argument("--qwen-encoder", default="qwen21", choices=["qwen21", "clip"], help="Qwen-Image 2.1 文本编码节点；若 TextEncodeQwenImage21 不存在改用 clip")
    ap.add_argument("--export-workflows", metavar="DIR", help="仅导出每个模型的 API 工作流 JSON，不跑图")
    ap.add_argument("--max-side", type=int, default=0, help="限制最长边（如 T4 跑 Qwen 爆显存时设 1024），0=不限制")
    ap.add_argument("--clip-retry", action="store_true",
                    help="CLIP 编码报 CUBLAS_STATUS_NOT_INITIALIZED 时，从 negative 末尾逐段删除后重试（最多 5 次，"
                         "年龄护栏词在开头不会被裁；截断次数记在 extra.clip_retry_neg_truncated）")
    a = ap.parse_args()

    cfgs = model_configs(a.profile)
    prompts_doc = json.load(open(PROMPTS_JSON, encoding="utf-8"))
    meta, prompts = prompts_doc["_meta"], {p["id"]: p for p in prompts_doc["prompts"]}
    asp = meta["aspect_to_resolution"]

    model_ids = list(cfgs) if a.models == ["all"] else a.models
    for m in model_ids:
        if m not in cfgs: sys.exit(f"未知模型 id: {m}，可选: {', '.join(cfgs)}")
    if a.profile == "T4":
        skipped = [m for m in model_ids if cfgs[m].get("a10_only")]
        if skipped: print(f"[warn] T4 档位跳过仅 A10 模型: {skipped}"); model_ids = [m for m in model_ids if m not in skipped]
    if not a.allow_nsfw:
        model_ids = [m for m in model_ids if not cfgs[m].get("nsfw_model")]

    for m in model_ids: cfgs[m]["qwen_encoder"] = a.qwen_encoder

    if a.export_workflows:
        d = Path(a.export_workflows); d.mkdir(parents=True, exist_ok=True)
        for m in model_ids:
            c = cfgs[m]
            g = build_graph(c, "a cinematic photo of a red fox in snow", c.get("negative", ""), 1024, 1024, 42, f"bench/{m}")
            (d / f"{a.profile}_{m}_api.json").write_text(json.dumps(g, ensure_ascii=False, indent=2), encoding="utf-8")
            print("导出", d / f"{a.profile}_{m}_api.json")
        return

    tier = meta["tiers"].get(a.tier)
    if a.tier == "custom":
        pids, seeds = a.prompt_ids, (a.seeds or meta["default_seeds"][:1])
    else:
        pids, seeds = tier["prompt_ids"], (a.seeds or tier["seeds"])
    if not pids: sys.exit("没有选中任何 prompt")

    out = Path(a.out) / a.profile; out.mkdir(parents=True, exist_ok=True)
    jsonl, csvp = out / "records.jsonl", out / "records.csv"
    done = set()
    if jsonl.exists() and not a.no_resume:
        for line in jsonl.open(encoding="utf-8"):
            try:
                r = json.loads(line); done.add((r["model_id"], r["prompt_id"], r["seed"], r["prompt_lang"]))
            except Exception: pass
    gname = gpu_name()
    try:
        requests.get(f"{a.server}/system_stats", timeout=10).raise_for_status()
    except Exception as e:
        sys.exit(f"无法连接 ComfyUI {a.server}: {e}")

    total = len(model_ids) * len(pids) * len(seeds); k = 0
    print(f"GPU={gname} profile={a.profile} tier={a.tier} models={model_ids} prompts={len(pids)} seeds={seeds} => {total} 张")
    for m in model_ids:
        c = cfgs[m]; warm = False
        for pid in pids:
            p = prompts.get(pid)
            if not p: print("[skip] 未知 prompt", pid); continue
            if p["nsfw"] and not a.allow_nsfw: print("[skip] NSFW 需 --allow-nsfw:", pid); continue
            if p["nsfw"] and not c.get("nsfw_ok") and c["kind"] == "sdxl":
                print(f"[skip] {m} 不适合 NSFW 条目 {pid}"); continue
            lang = "en"
            if a.prompt_lang == "zh":
                if c.get("zh") and p.get("prompt_zh"): lang = "zh"
                else: print(f"[skip] {m} 不支持中文 prompt 或条目无中文: {pid}"); continue
            field = "prompt_zh" if lang == "zh" else c["prompt_field"]
            text = p.get(field) or p["prompt"]
            if c["kind"] == "sdxl":
                # T4 上 SDXL 的 CLIP 对括号权重语法敏感（含 "(xxx)" 的 danbooru 词会触发 cublasSgemm 崩溃），
                # 统一去掉括号保留词本身，例如 "charcoal (medium)" -> "charcoal medium"
                text = text.replace("(", " ").replace(")", " ").replace("  ", " ")
            pos = c.get("prefix", "") + text
            neg = c.get("negative", "")
            if p.get("negative_extra") and c["kind"] == "sdxl": neg = (neg + ", " + p["negative_extra"]).strip(", ")
            w, h = asp[p["aspect"]]
            if a.max_side and max(w, h) > a.max_side:
                s = a.max_side / max(w, h); w, h = int(w * s) // 16 * 16, int(h * s) // 16 * 16
            neg_base = neg          # 每个 seed 都从完整 negative 开始，避免上一次截断污染后续 seed
            for seed in seeds:
                k += 1
                neg = neg_base
                key = (m, pid, seed, lang)
                sub = "nsfw" if p["nsfw"] else "sfw"
                img_path = out / sub / m / f"{pid}__s{seed}{'_zh' if lang=='zh' else ''}.png"
                if key in done and img_path.exists():
                    print(f"[{k}/{total}] 已有，跳过 {m} {pid} s{seed}"); continue
                g = build_graph(c, pos, neg, w, h, seed, f"bench/{a.profile}/{m}/{pid}_s{seed}")
                mon = VramMonitor(); mon.start(); t0 = time.time(); err = ""; clip_retry = 0
                neg_cur = neg
                for attempt in range(6):
                    try:
                        cpid, imgs = comfy_run(a.server, g)
                        dur = time.time() - t0
                        data = comfy_fetch(a.server, imgs[0]) if imgs else b""
                        err = ""
                        break
                    except Exception as e:
                        dur = time.time() - t0; err = str(e); data = b""; cpid = ""
                        # 已知缺陷：negative 过长（token 数跨过 77）会让 SDXL 的 CLIP 在 T4 上 cublas 崩溃。
                        # 处理：从 negative 末尾逐段删除后重试；年龄护栏词都在最前面，不会被裁掉。
                        if a.clip_retry and "CUBLAS_STATUS_NOT_INITIALIZED" in err:
                            segs = [s for s in neg_cur.split(",") if s.strip()]
                            if len(segs) > 1:
                                neg_cur = ", ".join(s.strip() for s in segs[:-1])
                                g = build_graph(c, pos, neg_cur, w, h, seed, f"bench/{a.profile}/{m}/{pid}_s{seed}")
                                clip_retry += 1
                                continue
                        break
                if clip_retry:
                    neg = neg_cur
                mon.stop.set(); mon.join(timeout=2)
                rec = dict(
                    timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"), gpu_profile=a.profile, gpu_name=gname,
                    model_id=m, model_kind=c["kind"], model_file=c.get("unet") or c.get("ckpt"),
                    text_encoder=c.get("clip") or (c.get("t5") and f"{c['t5']}+{c['clip_l']}") or "builtin",
                    vae=c.get("vae") or c.get("vae_override") or "builtin",
                    prompt_id=pid, category=p["category"], title_zh=p["title_zh"], nsfw=p["nsfw"], tags_eval=p["evaluates"],
                    aspect=p["aspect"], width=w, height=h, seed=seed, steps=c["steps"], cfg=c["cfg"],
                    sampler=c["sampler"], scheduler=c.get("scheduler", "flux2_scheduler" if c["kind"] == "flux2" else ""),
                    extra=dict(shift=c.get("shift"), flux_guidance=c.get("guidance"),
                               unet_dtype=c.get("unet_dtype", "default"),
                               **({"clip_retry_neg_truncated": clip_retry} if clip_retry else {})),
                    prompt_lang=lang, prompt_field=field, prompt_used=pos, negative_used=neg,
                    duration_sec=round(dur, 2), cold_start=not warm, peak_vram_mb=mon.peak,
                    image_path=str(img_path.relative_to(out.parent)) if data else "", comfy_prompt_id=cpid, error=err[:500])
                if data: write_png_with_meta(img_path, data, rec)
                with jsonl.open("a", encoding="utf-8") as f: f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                new = not csvp.exists()
                with csvp.open("a", newline="", encoding="utf-8") as f:
                    wr = csv.DictWriter(f, fieldnames=list(rec)); new and wr.writeheader()
                    wr.writerow({kk: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v) for kk, v in rec.items()})
                warm = True
                status = "ERR " + err[:120] if err else f"{dur:.1f}s  vram {mon.peak}MB"
                print(f"[{k}/{total}] {m} {pid} s{seed} {w}x{h} -> {status}")
    print("完成。记录:", jsonl)

if __name__ == "__main__":
    main()
