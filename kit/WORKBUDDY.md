# WorkBuddy 执行手册 —— 开源文生图模型测评（Cloud Studio T4 / A10）

> 公开版说明：本手册保留完整执行流程，但提示词集已剔除全部成人向条目（16 条），
> 文中涉及 `nsfw` 分档的章节仅作历史流程参考，公开包内无对应用例。
>
> 本文档写给 Cloud Studio 内的 WorkBuddy（或任何在终端中执行的 AI 助手）。
> 目标：按既定清单下载模型、启动 ComfyUI、批量跑 55 条测评提示词、保存所有图片与元数据、按 SFW/NSFW 分类，最后生成对比画廊与汇总表。
> 所有模型文件名、大小、采样参数均已于 2026-10 通过 HuggingFace API、Civitai API 和 Comfy-Org 官方工作流模板核实。**你的职责是执行与排错，不要随意更换模型文件或采样参数**；确需调整时，在 `bench_out/CHANGELOG.md` 中记录原因。

---

## 0. 套件结构

```
t2i-benchmark-kit/
├── WORKBUDDY.md               ← 本文件
├── README.md                  ← 给人看的总览 / 测评方案
├── 01_models/models.json      ← 模型清单：下载链接、目标路径、文本编码器/VAE、采样参数、两档显卡建议
├── 02_prompts/
│   ├── prompts.json           ← 55 条提示词（结构化，脚本读取这个）
│   ├── prompts_sfw.json / prompts_nsfw.json
│   ├── prompts_all.txt / prompts_sfw.txt / prompts_nsfw.txt    ← 人类可读
│   └── list_*.txt             ← 按风格分列的纯文本（手动粘贴到 ComfyUI 用）
├── 03_scripts/
│   ├── setup_comfyui.sh       ← 装 ComfyUI + torch + 启动脚本（CPU 机可跑）
│   ├── download_models.sh     ← 按 T4/A10 档位、按模型组下载（CPU 机可跑，支持断点续传）
│   ├── run_benchmark.py       ← 通过 ComfyUI API 批量跑图，自动记录元数据
│   └── make_report.py         ← 汇总 summary.md/csv + HTML 对比画廊 + 打分表
└── 04_workflows/              ← 可导入 ComfyUI 网页的 API 工作流（由 run_benchmark.py --export-workflows 生成）
```

---

## 1. 模型总表（已核实）

| id | 模型 | 文件（T4 档 / A10 档） | 文本编码器 | VAE | 采样 |
|---|---|---|---|---|---|
| `z_image_turbo` | Z-Image-Turbo 6B（阿里） | `z_image_turbo_int8_convrot` 6.2G / `z_image_turbo_bf16` 12.3G | `qwen_3_4b_fp8_mixed` 5.6G / `qwen_3_4b` 8.0G，CLIPLoader type=`lumina2` | `ae.safetensors` | 8 步, cfg 1, `res_multistep`/`simple`, ModelSamplingAuraFlow shift=3 |
| `flux2_klein_4b` | FLUX.2 [klein] 4B（Apache-2.0） | `flux-2-klein-4b` 7.75G（两档同） | 同上 qwen_3_4b，type=`flux2` | `flux2-vae.safetensors` | 4 步, cfg 1, `euler`, Flux2Scheduler，SamplerCustomAdvanced |
| `flux2_klein_9b` | FLUX.2 [klein] 9B（非商业，gated） | `flux-2-klein-9b` 18.2G，**仅 A10**，UNETLoader weight_dtype=`fp8_e4m3fn` | `qwen_3_8b_fp8mixed` 8.7G，type=`flux2` | `flux2-vae.safetensors` | 同 4B |
| `flux1_krea_dev` | FLUX.1 Krea [dev] 12B | `flux1-krea-dev_fp8_scaled` 11.9G（两档同） | `clip_l` + `t5xxl_fp8_e4m3fn_scaled` 5.2G / `t5xxl_fp16` 9.8G，DualCLIPLoader type=`flux` | `ae.safetensors` | 20 步, cfg 1, `euler`/`simple`, FluxGuidance 3.5 |
| `qwen_image_2_1_turbo` | Qwen-Image 2.1 Turbo 20B | `qwen_image_2.1_turbo_int8_convrot` 7.3G | `qwen3vl_8b_w4a8` 6.3G / `qwen3vl_8b_int8_convrot` 9.4G，type=`qwen_image` | `qwen_image_2.1_vae_bf16` | 8 步, cfg 1, `euler`/`simple` |
| `qwen_image_2_1` | Qwen-Image 2.1 Base | `qwen_image_2.1_int8_convrot` 7.3G | 同上 | 同上 | 25 步, cfg 1, `euler`/`simple` |
| `sdxl_animagine_xl_4` | Animagine XL 4.0 opt | `animagine-xl-4.0-opt` 6.9G | 内置 | 内置 | 28 步, cfg 5, `euler_ancestral`/`normal` |
| `sdxl_wai_illustrious` | WAI-illustrious-SDXL v17 | `waiIllustriousSDXL_v170` 6.5G（Civitai 2883731） | 内置 | 内置 | 28 步, cfg 6, `euler_ancestral`/`normal` |
| `sdxl_pornmaster_pro_v8` | PornMaster Pro SDXL V8（NSFW） | `pornmaster_proSDXLV8` 6.6G（Civitai 2551619） | 内置 | `sdxl_vae_fp16_fix` 外挂 | 30 步, cfg 5, `dpmpp_2m`/`karras` |

完整链接在 `01_models/models.json`。磁盘需求：T4 档全套约 **62 GB**，A10 档全套约 **95 GB**（含 9B）；两档都下约 115 GB（共用文件只算一次）。

### 显卡注意事项（重要）
- **T4（Turing）没有 bf16 / fp8 硬件计算**。ComfyUI 会把 bf16/fp8 权重在加载时转为 fp16 计算，能跑但更慢、更吃显存。因此 T4 档一律选 int8_convrot / fp8 存储格式，并以 `--fp16-unet --lowvram --reserve-vram 1.5` 启动。
- **A10（Ampere）原生 bf16**，fp8 仅可存储不可计算（会上转到 bf16）。24G 显存跑 klein 9B 需 `weight_dtype=fp8_e4m3fn`。
- **两张卡都不支持 nvfp4**，不要下载任何 `*nvfp4*` 文件。
- `int8_convrot` 是 2026 年新量化格式，需要 **ComfyUI ≥ 2026-03**（setup 脚本总是拉最新 master）。若 UNETLoader 报不认识权重格式，先 `git pull` 再装 `requirements.txt`。

---

## 2. 执行流程（分阶段，可在不同机器上做）

### 阶段 A —— CPU 机器：装环境 + 下模型（不需要 GPU）

```bash
# 1) 解压套件到工作区（假设在 /workspace）
cd /workspace && unzip t2i-benchmark-kit.zip && cd t2i-benchmark-kit

# 2) 凭据（按需）。Civitai key: https://civitai.com/user/account → API Keys；HF token 需先在页面同意 FLUX.2-klein-9b 许可
export CIVITAI_TOKEN=xxxxxxxx
export HF_TOKEN=hf_xxxxxxxx
# 国内加速（可选）
# export HF_ENDPOINT=https://hf-mirror.com
# export PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

# 3) 装 ComfyUI（CPU 机也装，之后目录整体复用；若 GPU 机是独立实例，GPU 机上再跑一次即可，秒级完成 git pull）
bash 03_scripts/setup_comfyui.sh /workspace/ComfyUI

# 4) 下载模型 —— 建议拆成几组后台跑，便于失败重试
export COMFY_DIR=/workspace/ComfyUI
nohup bash 03_scripts/download_models.sh T4  dit  > dl_T4_dit.log  2>&1 &
nohup bash 03_scripts/download_models.sh all sdxl > dl_sdxl.log    2>&1 &
nohup bash 03_scripts/download_models.sh all nsfw > dl_nsfw.log    2>&1 &
# A10 档位再补一轮（只会下 T4 没有的那些 bf16/fp16 版本和 9B）
nohup bash 03_scripts/download_models.sh A10 dit  > dl_A10_dit.log 2>&1 &

# 5) 校验：文件大小应与 models.json 的 size_gb 对得上（误差 <1%），且没有 *.aria2 残留
ls -la /workspace/ComfyUI/models/{diffusion_models,text_encoders,vae,checkpoints}
find /workspace/ComfyUI/models -name '*.aria2'
```

> Cloud Studio 工作区磁盘是否随实例迁移，请先在控制台确认。如果 CPU 实例和 GPU 实例不共享磁盘，可选择：(a) 直接在 GPU 实例上下载；(b) 用云存储/对象存储中转。下载本身不吃 GPU，纯看带宽。

### 阶段 B —— GPU 机器：启动 ComfyUI

```bash
cd /workspace/ComfyUI && git pull --ff-only && source venv/bin/activate && pip install -q -r requirements.txt
# T4:
nohup bash start_T4.sh  > comfy.log 2>&1 &
# A10:
nohup bash start_A10.sh > comfy.log 2>&1 &
sleep 20 && tail -30 comfy.log       # 看到 "To see the GUI go to: http://0.0.0.0:8188" 即可
curl -s http://127.0.0.1:8188/system_stats | python3 -m json.tool | head -30
```

Cloud Studio 一般可以在「端口」面板把 8188 转发出来在浏览器打开 ComfyUI；不用网页也行，脚本走 API。

### 阶段 C —— 冒烟测试（每个模型 1~3 张，先验证流水线）

```bash
cd /workspace/t2i-benchmark-kit/03_scripts
pip install -q requests pillow
# 每个模型逐个冒烟，确认能出图、没有节点缺失
P=T4   # 或 A10
for m in z_image_turbo flux2_klein_4b flux1_krea_dev qwen_image_2_1_turbo sdxl_animagine_xl_4 sdxl_wai_illustrious; do
  python run_benchmark.py --profile $P --tier smoke --models $m --out /workspace/bench_out || echo "!!! $m 冒烟失败"
done
```

**常见报错处理：**
| 现象 | 处理 |
|---|---|
| `Node 'TextEncodeQwenImage21' not found` | ComfyUI 太旧 → `git pull`；或临时加 `--qwen-encoder clip` 退回通用编码（结果仍有效但记录到 CHANGELOG） |
| `Flux2Scheduler` / `EmptyFlux2LatentImage` 不存在 | 同上，更新 ComfyUI |
| T4 上 Qwen-Image 2.1 OOM | 文本编码器换 `qwen3vl_8b_w4a8`（脚本 T4 档已默认）；仍 OOM 加 `--max-side 1024`；再不行启动参数加 `--cpu-text-encoder`（新版 ComfyUI 支持，查 `python main.py --help`） |
| T4 上 Krea 20 步极慢（>3 min/张） | 正常，fp8 权重在 T4 上走 fp16；只跑 `--tier quick` 并记录即可 |
| Civitai 下载 401/403 | token 无效或账号未开启 NSFW 显示（Settings → Content Moderation） |
| HF 9B 下载 401 | 需在 HF 网页同意许可后再用 token |
| 出图全黑 / NaN | SDXL 加 fp16 fix VAE（pornmaster 已默认）；DiT 模型检查是否误用了 nvfp4 文件 |
| `res_multistep` 不在采样器列表 | ComfyUI 太旧，更新 |

### 阶段 D —— 正式测评（两档分别跑，输出自动分目录）

```bash
# ---- T4 档（约 4~6 小时，见第 4 节估算）----
python run_benchmark.py --profile T4 --tier standard --out /workspace/bench_out \
  --models z_image_turbo flux2_klein_4b qwen_image_2_1_turbo sdxl_animagine_xl_4 sdxl_wai_illustrious
python run_benchmark.py --profile T4 --tier quick --out /workspace/bench_out --models flux1_krea_dev qwen_image_2_1
# 中文提示词（仅中文模型）
python run_benchmark.py --profile T4 --tier zh --prompt-lang zh --out /workspace/bench_out --models z_image_turbo qwen_image_2_1_turbo
# NSFW（显式开启；会写到 bench_out/T4/nsfw/）
python run_benchmark.py --profile T4 --tier nsfw --allow-nsfw --out /workspace/bench_out --models sdxl_pornmaster_pro_v8 sdxl_wai_illustrious

# ---- A10 档（约 5~8 小时）----
python run_benchmark.py --profile A10 --tier full --out /workspace/bench_out --models all
python run_benchmark.py --profile A10 --tier zh --prompt-lang zh --out /workspace/bench_out --models z_image_turbo qwen_image_2_1_turbo qwen_image_2_1
python run_benchmark.py --profile A10 --tier nsfw --allow-nsfw --out /workspace/bench_out --models sdxl_pornmaster_pro_v8 sdxl_wai_illustrious z_image_turbo flux2_klein_4b
```

脚本特性：
- **断点续跑**：默认跳过 `records.jsonl` 中已完成且图片存在的组合，中断后重跑同一命令即可。
- **按模型顺序执行**，模型切换只发生 N 次，避免反复加载。
- 每张图写入 `records.jsonl` + `records.csv` 一行：GPU、模型 id/文件、文本编码器、VAE、prompt id/类别/标题/考察点、SFW/NSFW、分辨率、seed、步数、cfg、采样器、调度器、shift/guidance、使用的正/负提示词、耗时、是否冷启动、峰值显存、错误信息。
- PNG 内嵌同样的 JSON 元数据（`benchmark` 字段），图片脱离目录也能溯源。
- 用 `nohup python run_benchmark.py ... > run_T4.log 2>&1 &` 后台跑，`tail -f run_T4.log` 看进度。

### 阶段 E —— 汇总与展示

```bash
python make_report.py --out /workspace/bench_out                # 生成 summary.md / summary.csv / scores_template.csv / gallery_sfw.html
python make_report.py --out /workspace/bench_out --include-nsfw  # 额外生成 gallery_nsfw.html（单独文件）
cd /workspace && zip -r bench_out_$(date +%Y%m%d).zip bench_out  # 打包全部图片+记录供下载
```

`gallery_sfw.html` 按 prompt 一行、各模型一列横向对比，顶部可按类别筛选；图片路径为相对路径，整个 `bench_out` 目录打包后在本地双击即可看。

---

## 3. 提示词集说明（55 条）

| 类别 | 条数 | 主要考察 |
|---|---|---|
| portrait 人像 | 5 | 皮肤/眼睛/手部、年龄与种族多样性、多人一致性、布光 |
| landscape 风景 | 4 | 大气透视、水面/雪/雾等材质、时间光线 |
| cinematic 电影 | 4 | 色彩分级、画幅与构图、动态模糊、叙事氛围 |
| scifi 科幻 | 4 | 复杂机械结构、霓虹/体积光、尺度感 |
| anime 二次元 | 5 | 线条/上色、角色设计、动态姿势、多角色 |
| text 文字渲染 | 5 | 英文/中文/多行/字体风格/手写 |
| art 艺术风格 | 5 | 油画/浮世绘/水彩/版画/像素风 的风格保真 |
| fantasy 奇幻 | 3 | 生物设计、魔法特效、场景复杂度 |
| architecture 建筑 | 3 | 透视直线、材质、室内外光 |
| product 产品 | 3 | 棚拍光、玻璃/金属反射、爆炸视图 |
| animal 动物 | 2 | 毛发、拟人化 |
| stress 压力测试 | 4 | 数数、空间关系、否定词、罕见组合（提示词遵循度核心） |
| culture 文化 | 2 | 中式/地域元素准确性 |
| surreal 超现实 | 2 | 概念融合、物理违背的可信度 |
| **nsfw** | **4** | 成年人体解剖、双人交互、二次元成人向（全部限定成年并带年龄护栏负面词） |

每条含 4 种写法：`prompt`（英文自然语言，DiT 模型用）、`prompt_zh`（中文，Z-Image / Qwen 用）、`tags`（danbooru 标签，SDXL 二次元用）、`sdxl_prompt`（写实 SDXL 短句）。脚本按模型 `prompt_field` 自动选用。

分档（`tiers`）：`smoke` 3 条 → `quick` 14 条（每类 1 条）→ `standard` 51 条 SFW×1 seed → `full` 51×2 seeds；`zh` 51 条中文；`nsfw` 4×2 seeds。

---

## 4. 时间估算（单图，1024 级分辨率，warm 状态；实测请以 records.jsonl 为准）

| 模型 | T4 预估 | A10 预估 | 依据 |
|---|---|---|---|
| Z-Image-Turbo 8 步 | 25–45 s | 6–10 s | 6B DiT，T4 走 fp16 无 bf16 加速 |
| FLUX.2 klein 4B 4 步 | 15–30 s | 4–7 s | 4B，4 步 |
| FLUX.2 klein 9B 4 步 | — | 10–18 s | fp8 存储 bf16 计算 |
| FLUX.1 Krea 20 步 | 150–240 s | 30–50 s | 12B，20 步，T4 最慢项 |
| Qwen-Image 2.1 Turbo 8 步 | 60–120 s | 15–25 s | 20B MMDiT int8 |
| Qwen-Image 2.1 Base 25 步 | 180–360 s | 45–75 s | 同上 ×3 步数 |
| SDXL 28–30 步 | 20–35 s | 6–10 s | 成熟架构 |

**总时长粗算**（不含下载与冷启动）：
- T4 `standard`（51 条）：Z-Image 30 min + klein4B 20 min + Qwen-Turbo 75 min + 2×SDXL 50 min ≈ **3 h**；Krea / Qwen-Base 只跑 `quick`（14 条）再 +1.5 h；zh 51×2 模型 ≈ 1.3 h；nsfw 16 张 ≈ 10 min。**合计约 5–6 h**。
- A10 `full`（51×2 seeds = 102 张/模型，9 个模型）：≈ 102×(8+5+14+40+20+60+8+8+8)s ≈ **4.8 h**；加 zh 和 nsfw ≈ **6 h**。
- 下载：按 50 MB/s 计，T4 档 62 GB ≈ 21 min，A10 档 95 GB ≈ 32 min；国内直连 HF 可能慢很多，建议 `HF_ENDPOINT=https://hf-mirror.com`。

冷启动（首张）会多出 30–120 s 模型加载时间，`records.jsonl` 的 `cold_start=true` 行应在统计平均耗时时剔除（`make_report.py` 已处理）。

---

## 5. 公平性约束（必须遵守）

1. 同一 prompt、同一 seed、同一分辨率给所有模型；不要为某个模型单独改提示词。
2. 不使用 Prompt Enhancer / LLM 改写（Qwen 2.1 官方模板里的 TextGenerate 分支保持关闭）。
3. 不加 LoRA、不加 Hires fix、不加 refiner、不做后处理。
4. 采样参数使用各模型**官方推荐值**（见表），不做逐模型调优。
5. NSFW 条目只在 `--allow-nsfw` 下运行，输出到独立 `nsfw/` 目录，画廊单独文件；所有 NSFW 提示词限定成年人，SDXL 负面词含年龄护栏，**不得删除**。
6. 任何偏离（如 T4 上被迫降分辨率）必须记录到 `bench_out/CHANGELOG.md`，并在 records 的 `width/height` 中如实体现。

---

## 6. 交付清单

- [ ] `bench_out/T4/records.jsonl` + `records.csv`
- [ ] `bench_out/A10/records.jsonl` + `records.csv`
- [ ] `bench_out/{T4,A10}/sfw/<model>/*.png`、`bench_out/{T4,A10}/nsfw/<model>/*.png`
- [ ] `bench_out/summary.md`、`summary.csv`
- [ ] `bench_out/gallery_sfw.html`（必）、`gallery_nsfw.html`（可选）
- [ ] `bench_out/scores_template.csv`（供人工打 0–5 分：提示词遵循 / 美学 / 细节 / 文字 / 风格 / 无伪影）
- [ ] `bench_out/CHANGELOG.md`（偏离记录；无偏离也写"无"）
- [ ] 打包 `bench_out_<日期>.zip`
