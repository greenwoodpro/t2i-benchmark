# 文生图测评 · 操作手册（T4 / A10）

> 最后更新：2026-10-18。新会话或换卡后先读本文档，再执行对应命令。

## 0. 一句话现状

- **T4 档**：top20 代表性测试进行中（7 模型串行，已跑自动跳过）；Z-Image standard 51 条已完成 41 条。
- **A10 档**：待跑（Qwen-Image 2.1 Base/Turbo 20B、可选 FLUX.2 klein 9B、Krea-2、FLUX.3 bf16 高质量重跑）。
- 结果全部在 `/workspace/bench_out/`，每张图完成即写盘，断点续跑零丢失。

## 1. 环境

| 项 | 值 |
|---|---|
| ComfyUI 路径 | `/workspace/ComfyUI`（git master，2026-10-16 版 5cc4b870，ComfyUI 0.41.0） |
| Python | 系统 pyenv 3.11.1（**不要用 venv**，venv 是半装状态没有 torch） |
| torch | 2.10.0+cu128（系统 python 已装） |
| 测评套件 | `/workspace/ComfyUI/t2i-benchmark-kit/t2i-benchmark-kit/`（解压后双层目录） |
| 运行依赖 | `pip install -r /workspace/ComfyUI/requirements.txt`（含 comfy_kitchen，跑 int8_convrot 必需） |

### 启动 ComfyUI（T4，16G）

```bash
cd /workspace/ComfyUI
nohup python main.py --listen 0.0.0.0 --port 8188 \
  --fp16-unet --lowvram --reserve-vram 1.5 --disable-smart-memory \
  > /workspace/comfy.log 2>&1 &
# 验证：
curl -s http://127.0.0.1:8188/system_stats | head -c 200
# 日志出现 "Device: cuda:0 Tesla T4 : native"（不是 cudaMallocAsync）即正确
```

### 启动 ComfyUI（A10，24G）

```bash
cd /workspace/ComfyUI
nohup python main.py --listen 0.0.0.0 --port 8188 > /workspace/comfy.log 2>&1 &
```

## 2. 模型清单（T4 已下载，全部就位）

| 用途 | 文件 | 位置 |
|---|---|---|
| Z-Image-Turbo | `z_image_turbo_int8_convrot.safetensors` 5.8G | models/diffusion_models |
| Z-Image TE | `qwen_3_4b_fp8_mixed.safetensors` 5.3G | models/text_encoders |
| FLUX.2 klein 4B | `flux-2-klein-4b.safetensors` 7.3G | models/diffusion_models |
| FLUX.3 klein（**bf16**） | `flux3-image-klein-bf16.safetensors` 11G | models/diffusion_models |
| FLUX.3 TE | `qwen3vl_4b_int8_convrot.safetensors` 4.6G | models/text_encoders |
| FLUX.1 Krea dev | `flux1-krea-dev_fp8_scaled.safetensors` 12G | models/diffusion_models |
| Krea TE | `t5xxl_fp8_e4m3fn_scaled.safetensors` 4.9G + `clip_l.safetensors` | models/text_encoders |
| Qwen 2.1 Base/Turbo | `qwen_image_2.1_int8_convrot` 6.8G / `_turbo_int8_convrot` 6.8G | models/diffusion_models |
| Qwen 2.1 TE | `qwen3vl_8b_w4a8.safetensors` 5.9G（T4）/ `qwen3vl_8b_int8_convrot.safetensors` 8.8G（A10） | models/text_encoders |
| SDXL 二次元 | `animagine-xl-4.0-opt` 6.5G / `waiIllustriousSDXL_v170` 6.5G | models/checkpoints |
| SDXL NSFW | `pornmaster_proSDXLV8` 6.7G | models/checkpoints |
| VAE | `ae` (Z-Image/Krea) / `flux2-vae` (FLUX.2/3) / `qwen_image_2.1_vae_bf16` / `sdxl_vae_fp16_fix` | models/vae |

## 3. 测试集（prompts.json 的 _meta.tiers）

| tier | 内容 | 用途 |
|---|---|---|
| `smoke` | 3 条 | 冒烟 |
| `top20` | **20 条：14 个 SFW 类别 + 1 条 NSFW(P52) × seed 42** | 当前 T4 主测（性价比最高） |
| `standard` | 51 条 SFW × 1 seed | 完整档（Z-Image 已跑 41） |
| `nsfw_ext` | 16 条 NSFW（原4 + 用户12条 P56-P67 极端/黑暗/猎奇）× 2 seeds | 二轮 NSFW |
| `zh` | 51 条中文 × 1 seed | 仅 Z-Image / Qwen |

## 4. 跑图命令（断点续跑：直接重跑同一命令即可）

```bash
cd /workspace/ComfyUI/t2i-benchmark-kit/t2i-benchmark-kit/03_scripts

# T4 当前主测（20 条 × 7 模型，串行，跑过的自动跳过）
nohup python3 run_benchmark.py --profile T4 --tier top20 --allow-nsfw \
  --models z_image_turbo flux2_klein_4b sdxl_animagine_xl_4 sdxl_wai_illustrious \
           sdxl_pornmaster_pro_v8 flux3_klein flux1_krea_dev \
  --out /workspace/bench_out > /workspace/run_T4_top20.log 2>&1 &

# T4 第二轮（NSFW 全套，16条×2seeds）
python3 run_benchmark.py --profile T4 --tier nsfw_ext --allow-nsfw \
  --models sdxl_pornmaster_pro_v8 sdxl_wai_illustrious z_image_turbo flux2_klein_4b flux3_klein \
  --out /workspace/bench_out

# A10：Qwen 2.1（20B，T4 跑不动的）
python3 run_benchmark.py --profile A10 --tier top20 --allow-nsfw \
  --models qwen_image_2_1_turbo qwen_image_2_1 --out /workspace/bench_out

# 汇总报告 + 画廊
python3 make_report.py --out /workspace/bench_out
```

## 5. 结果与字段

- `bench_out/T4/records.jsonl` + `records.csv`：每图一行
  字段：timestamp / gpu_profile / gpu_name / model_id / model_kind / model_file / text_encoder / vae /
  prompt_id / category / title_zh / nsfw / tags_eval / aspect / width / height / seed / steps / cfg /
  sampler / scheduler / extra(shift等) / prompt_lang / prompt_used / negative_used / duration_sec /
  cold_start / peak_vram_mb / image_path / comfy_prompt_id / error
- `bench_out/T4/sfw/<model>/*.png`、`bench_out/T4/nsfw/<model>/*.png`（PNG 内嵌同款 JSON 元数据）
- `bench_out/CHANGELOG.md`：所有偏离记录
- `bench_out/OPERATIONS.md`：本文档

## 6. 已知坑（务必避免）

1. **不要用 venv**：`/workspace/ComfyUI/venv` 是半装状态（无 torch），用系统 `python`。
2. **pkill 自匹配**：`pkill -f "run_benchmark.py"` 会匹配到执行命令的 shell 自身导致命令中断。必须用正则断字：`pkill -f "run_benchmar[k]"`、`pkill -f "mai[n].py"`。
3. **FLUX.3 int8 在 T4 不可用**：int8_convrot 的量化算子在 Turing 无原生支持 → emulated fp32 → CUBLAS_STATUS_NOT_INITIALIZED。T4 必须用 `flux3-image-klein-bf16.safetensors`（自动转 fp16 计算）。
4. **TextEncodeQwenImage21 新版必填 `resolution`**（已在脚本里传 1024）；`images` 可留空。
5. **--disable-cuda-malloc**：T4 上建议加（日志显示 `native`），避免 cudaMallocAsync 兼容问题。
6. **磁盘**：根分区 256G，剩约 20G。`models/` 里还有可删的旧文件（GGUF UC ×4=27.8G、krea2 13G、ace_step 7.2G、hunyuan3d 4.6G、sd1.5 2G、qwen3vl_8b_fp8_heretic 8.8G、3个实验 LoRA 2.8G）——**用户要求暂不删**，空间紧张时再清。
7. 监控命令不要用长 `sleep`（工具会超时断开，虽然后台任务不受影响）；用 60-120 秒轮询。

## 7. A10 阶段待办

1. 启动 ComfyUI（默认参数，A10 原生 bf16）
2. Qwen-Image 2.1 Base(25步) + Turbo(8步) 跑 top20（T4 因 20B 太慢已排除）
3. 可选：FLUX.2 klein 9B（18.2G，需 HF_TOKEN + 同意许可，已在 models.json 有配置但未下载）
4. 可选：Krea-2（`/workspace/ComfyUI/models/unet/diffusion_models/krea2_turbo_fp8_scaled.safetensors` 13G 本地已有，需 qwen3vl_4b_fp8_scaled TE + qwen_image_vae，均在 models/text_encoders 和 models/vae）
5. 可选：FLUX.3 bf16 在 A10 上更高质量重跑（对比 T4 fp16）
6. 汇总：`make_report.py` 生成 T4 vs A10 对比

## 8. 进度快照（2026-10-18 更新：T4 阶段完成）

**T4 最终：256 张有效图，0 空白，图片数与记录数一一对应（PornMaster top20 已补齐）。**

| 模型 | 完成 | 平均耗时 | 峰值显存 | 参数 |
|---|---|---|---|---|
| flux1_krea_dev | 40 | 141.2s | 12487MB | 20步/cfg1/euler/simple |
| flux2_klein_4b | 40 | 31.2s | 14901MB | 4步/cfg1/euler/Flux2Scheduler |
| sdxl_animagine_xl_4 | 39 | 34.4s | 12085MB | 28步/cfg5/euler_ancestral |
| sdxl_pornmaster_pro_v8 | 21 | 43.1s | 5701MB | 30步/cfg5/dpmpp_2m/karras |
| sdxl_wai_illustrious | 40 | 34.5s | 10603MB | 28步/cfg6/euler_ancestral |
| z_image_turbo | 58 | 68.7s | 14899MB | 8步/cfg1/res_multistep |
| flux3_klein | 0（作废） | — | — | T4 硬件不支持，A10 跑 |

缺失：P59（Animagine/PornMaster 各 1 条，该极端提示词触发 CLIP bug，已确认重启无效）。

报告文件：summary.md / summary.csv / scores_template.csv / gallery_sfw.html。

**A10 启动：`bash /workspace/run_A10.sh`**（自动启 ComfyUI + 跑 top20 的 Qwen Turbo → Qwen Base → FLUX.3，约 45 分钟）。
A10 所需 7 个模型文件已全部就位，无需下载。

8. **CUDA context 污染**：任何一次 CUBLAS 报错后，后续所有请求都会失败（看起来像“模型坏了”，其实是 context 坏了）。**处理：重启 ComfyUI 进程**，然后断点续跑。
9. **T4 + bf16 权重**：需要 `model_management.py: unet_manual_cast` 的 fp16 补丁（已在 2026-10-18 应用），否则 bf16→fp32 显存翻倍。
10. **保留模型与磁盘**：删除的文件会进入 `/root/.local/share/Trash`（平台 safe-delete，du 仍显示占用但 df 不释放），清空被保护机制拦截；当前 20G 可用足够 T4 剩余测试。

## 9. 第二轮加测（round2）与终端监控

- tier round2（20 条 = 11 条新 SFW + 9 条 NSFW 代表，seed 42）
  - SFW: P03 多人 / P04 儿童 / P08 江南雨 / P12 动作 / P16 机械 / P19 动态 / P25 多行文字 / P30 水彩 / P41 爆炸图 / P46 镜面 / P47 罕见材质
  - NSFW: P56/P57/P58/P59（极端）+ P60/P61/P62（黑暗）+ P64/P65（猎奇）
- 命令:
  python3 run_benchmark.py --profile T4 --tier round2 --allow-nsfw --models z_image_turbo flux2_klein_4b sdxl_animagine_xl_4 sdxl_wai_illustrious sdxl_pornmaster_pro_v8 flux1_krea_dev --out /workspace/bench_out
- 终端监控: tmux attach -t bench  （面板每 10 秒刷新；Ctrl+B D 脱离不影响）
- 速查: bash /workspace/watch_progress.sh

## 10. 已知修复（2026-10-18）

| 问题 | 修复 |
|---|---|
| PornMaster 全崩 CLIPTextEncode | negative 去掉 (…:1.5) 权重语法，安全词保留 |
| FLUX.3 T4 全空白 | bf16→fp16 溢出；T4 放弃，改 A10 |
| bf16 权重 fp32 计算爆显存 | model_management.py unet_manual_cast 强制 fp16（已打补丁） |
| tier 白名单 | 新增 tier 时必须同步改 run_benchmark.py 的 --tier choices |
