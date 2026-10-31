# 交接文档 —— T4 结项 · A10 待补

> 更新：2026-10-27（A10 主线结项，MOSS 官方口径补跑中）

## 0. 一句话现状

**T4 已结项：6 个模型 × (SFW 51 + NSFW 32) 全部跑满，558 张。**
**A10 已结项：549 张 —— 4 个模型 83/83 满覆盖 + MOSS 三条口径（详见下表）。**
**合计 1107 张，0 失败、0 缺图、0 空白图。**
**下一站：T4 上跑 MOSS Base 加速档实测（工作流与权重已就绪，见下节）。**
静态站点已重新生成：`/workspace/bench_out/site/`（12 个模型配置，983 张缩略图）。

## 1. 数据总览

| 卡 | 模型 | 张数 | SFW 51 | NSFW 32 | 状态 |
|---|---|---|---|---|---|
| T4 | z_image_turbo | 103 | 51/51 | 32/32 | ✅ |
| T4 | flux2_klein_4b | 93 | 51/51 | 32/32 | ✅ |
| T4 | sdxl_animagine_xl_4 | 93 | 51/51 | 32/32 | ✅ |
| T4 | sdxl_wai_illustrious | 93 | 51/51 | 32/32 | ✅ |
| T4 | sdxl_pornmaster_pro_v8 | 93 | 51/51 | 32/32 | ✅ |
| T4 | flux1_krea_dev | 83 | 51/51 | 32/32 | ✅ |
| A10 | qwen_image_2_1_turbo | 83 | 51/51 | 32/32 | ✅ |
| A10 | qwen_image_2_1 | 83 | 51/51 | 32/32 | ✅ |
| A10 | flux3_klein | 83 | 51/51 | 32/32 | ✅ |
| A10 | krea2_turbo | 83 | 51/51 | 32/32 | ✅ |
| A10 | moss_image_fast（8 步 DMD LoRA） | 83 | 51/51 | 32/32 | ✅ |
| A10 | moss_image（50 步官方，SFT 基模） | 67 | 51/51 | 16/32 | ✅ 单 seed，与 SFT-8步 67 组对拍 |
| A10 | moss_image_base_fast（Base 原模型 + 8 步） | 67 | 51/51 | 16/32 | ✅ 单 seed，峰值仅 12.2G，T4 可跑 |

### MOSS 三条口径（不可混统计）

| model_id | 基模 | 采样 | 张数 | 热态 | 峰值显存 |
|---|---|---|---|---|---|
| `moss_image` | SFT | 50 步 / cfg 3 / 真负面 | 67 | 198.6s | 16.1G |
| `moss_image_fast` | SFT | 8 步 / cfg 1 + DMD LoRA@0.7 | 83 | 18.0s | 16.1G |
| `moss_image_base_fast` | **Base** | 8 步 / cfg 1 + Base DMD LoRA@0.7 + **4bit TE(w4a8)** + small VAE | 67 | 19.1s | **12.5G** |

> `moss_image_base_fast` 是为 **T4 16G** 准备的组合：权重约 13G（Base DiT 5.41G + w4a8 TE 7.34G + small VAE 0.25G + LoRA 1.19G），
> 峰值实测 12.5G，T4（15.36G 可用）余量近 3G。文字渲染经验证正常（P23 招牌、P24 中文书法均正确）。
> 同 8 步下与 SFT 版有 **67 组同 prompt 对拍**：`site/moss_compare.html` 第三节。

## 2. A10 任务清单 → 见 `/workspace/A10_TASKS.md`

**2026-10-27 实际执行结果（本轮已完成）：**

| 阶段 | 内容 | 结果 |
|---|---|---|
| 0 | `check_models.py A10` 自检 | 缺 6 个 / 49.8G，全量下载（curl 6MB/s → 换 aria2c 4×4 连接后 24–35MB/s） |
| A | flux3 NSFW 22 | ✅ 83（13s/张） |
| B | krea2 SFW 21 + NSFW 32 | ✅ 83（18s/张，峰值 18.8G） |
| C | qwen turbo NSFW 22 + base NSFW 22 | ✅ 各 83（turbo 24s、base 66s） |
| D | MOSS 8 步 DMD LoRA 全量 51（用户决定跳过试点直接全量） | ✅ 83，热态 **18.0s** |
| E | MOSS 50 步官方口径（进行中） | SFW 41 + NSFW 16（单 seed），约 3.2h |

A10 启动**不要**加 `--lowvram --fp16-unet`（那是 T4 参数）。
本轮新增脚本：`dl_A10_moss_first.sh`（MOSS 优先下载）、`chain_A10_v2.sh`（权重一到就开跑 + 断线自愈）、
`run_fast_nsfw.sh`、`finish_A10.sh`、`moss_official.sh`、`finish_final.sh`。

以下是早前的详细估算（供参考）：

## 2.1 A10 剩余：约 110 分钟（含下载 52G，用 MOSS 8 步 LoRA）

> 详细方案见 **`/workspace/A10_PLAN.md`**（盘点、下载清单、时间预算、存储清理、风险与备选）

MOSS 官方 50 步补 41 条要 **136 分钟**，装不进 2.5 小时窗口，因此改用
**8 步 DMD 蒸馏 LoRA**（`lodestones/MOSS-Image-SFT-8-steps-dmd`，1.2G，Apache-2.0），
新增模型 id `moss_image_fast`（8 步 / cfg 1 / LoRA 强度 1.0），**与 50 步基线单列，不混统计**。
已有的 10 条 50 步与 fast 版同 prompt，可做成对对比（画质/文字准确率差异）。

执行顺序：`check_models.py A10` → `dl_A10_all.sh`（52G）→ `run_A10_finish.sh`（SFW 段 40min）
→ `run_A10_nsfw.sh`（NSFW 段 70min，用户执行）→ 报告 + 站点 + 打包。

| 任务 | 张数 | 耗时 |
|---|---|---|
| krea2 补 SFW（30→51） | 21 | ~6 min |
| qwen turbo NSFW | 22 | ~9 min |
| qwen base NSFW | 22 | ~24 min |
| flux3 NSFW | 22 | ~5 min |
| krea2 NSFW（全 32） | 32 | ~10 min |
| 模型切换 | — | ~5 min |
| **合计** | **119 张** | **≈ 60 min** |

⚠️ **切 A10 前必须自检权重**：`python3 /workspace/check_models.py A10`
上次实测缺 6 个文件约 **49.8G**（qwen×2、qwen3vl_8b、krea2、moss、qwen3.5_9b），换卡后模型不跟随工作区。

A10 启动（24G，默认参数即可）：
```bash
cd /workspace/ComfyUI && setsid nohup python main.py --listen 0.0.0.0 --port 8188 > /workspace/comfy.log 2>&1 &
```
补 SFW：
```bash
cd /workspace/ComfyUI/t2i-benchmark-kit/t2i-benchmark-kit/03_scripts
python3 run_benchmark.py --profile A10 --tier standard --models krea2_turbo --out /workspace/bench_out
```
补 NSFW（4 模型，不含 moss）：
```bash
python3 run_benchmark.py --profile A10 --tier nsfw_ext --allow-nsfw \
  --models qwen_image_2_1_turbo qwen_image_2_1 flux3_klein krea2_turbo \
  --out /workspace/bench_out --clip-retry
```

## 3. T4 定版配置（别改）

```bash
bash /workspace/start_comfy_T4_fast.sh
# --fp16-unet --lowvram --reserve-vram 0.5 --disable-cuda-malloc
```
- **绝对不要加 `--disable-smart-memory`**：会让每张图重载权重，flux2 从 12s 退到 44s
- **不要用默认 `python main.py`**：krea_dev 会 OOM

## 4. 站点（已生成，可直接部署）

```
/workspace/bench_out/site/
├── index.html    总览（KPI、结论、横评表、模型卡片）
├── gallery.html  图库（显卡/模型/类别/比例/seed/关键词筛选，NSFW 默认隐藏）
├── report.html   测评报告（方法、结果、家族对比、结论、复现）
├── assets/       style.css / data.js / app.js
├── data/         records.json + 4 个 csv
└── thumbs/       781 张 520px 缩略图
```
重建：`python3 /workspace/bench_out/build_site.py && python3 /workspace/bench_out/build_report.py`

部署：`cd site && git init && git add -A && git commit -m init && git push`（Pages 选 main / root）
**注意**：私密仓库发布 Pages 需 Pro；公开部署前建议剔除 NSFW（`load()` 里加 `if r["nsfw"]: continue` 后重建）。

## 5. 工程包（可下载）

| 包 | 大小 | 内容 |
|---|---|---|
| `/workspace/T4_benchmark_full_20261027.zip` | 1.6GB | 站点 + T4 558 张 + A10 549 张原图 + records + kit + 脚本 + 文档 |
| `/workspace/T4_benchmark_lite_20261027.zip` | 48MB | 同上去掉原图 |
| `/workspace/T4_benchmark_github_20261027.zip` | 48MB | **GitHub 仓库包**：解压即仓库根（含 README / DISCLAIMER / LICENSE / .nojekyll） |

另含 `MODELS.md` / `models_manifest.json`：31 个权重文件（159G）的大小与 HF 下载源，换实例后可直接比对重下。

> 文件名沿用 `T4_` 前缀（与历史链接一致），内容已含 A10 全部数据。

站点已含**免责声明页** `disclaimer.html`（18+ 分级、模型许可、数据准确性、平台合规、责任限制），并接入三个页面的导航与页脚。
仓库根另有 `DISCLAIMER.md` / `LICENSE`（代码 MIT、数据 CC BY-NC 4.0）/ `.gitignore`。

## 6. 关键结论（写报告可直接引用）

1. T4 最快：`flux2_klein_4b` 热态 **12.1s**（4 步）；最慢：`flux1_krea_dev` **139.4s**（12B，显存贴顶被迫分块）。
2. 去掉 `--disable-smart-memory` 带来 **20–70%** 提速（flux2 44.1→12.1s）。
3. T4 显存天花板：三个模型峰值 14.9G/15.36G，只剩 400–500MB。
4. SDXL CLIP 内核级缺陷：negative 超 **77 token** 必崩 `cublasSgemm`；解法 `--clip-retry`（negative 末尾裁词重试，护栏词在开头不受影响）。
5. A10 价值在“装得下”：Qwen 20B、Krea2（18.8G）、MOSS（50 步）T4 无法承载。
6. MOSS 单张 **198.6s**（50 步 + cfg3 真 CFG），是唯一支持布局 JSON 的模型。
7. **MOSS 8 步 DMD LoRA 可用**：热态 **18.0s**，比 50 步快 **11 倍**（18.0 vs 198.6s）。同 prompt 对拍（`site/moss_compare.html`，10 组）显示：
   构图/排版/光照/文字渲染（P23 招牌、P24 中文书法）都保住，损失集中在**高频细节**——雨丝基本消失（P12）、布纹与纸纹颗粒变平（P30）、人像皮肤质感略糊。
   结论：海报/版式/文案类可用加速档，质感类素材仍建议 50 步。
8. A10 主线耗时（热态中位）：flux3 13.0s、krea2 18.1s（峰值 18.8G）、moss_fast 18.0s、qwen turbo 24.1s、qwen base 66.3s。
9. 下载教训：HF 单线程 curl 会退化到 1.5–6MB/s；换 `aria2c -x4 -s4` 后 24–35MB/s，49.8G 从 2 小时降到约 25 分钟。
   `ready()` 判定必须用 **content-length 精确比对**（TE 9B 实际 9.75G，早前脚本写的 9.6G 阈值差点死等）。

## 7. 已知坑（新会话务必先看）

1. `pkill -f "main.py"` 会杀掉执行命令的 shell → 用 `pkill -f "mai[n].py"`。
2. `--tier zh` 必须配 `--prompt-lang zh`，否则按英文跑、全部跳过。
3. `nsfw_model` 类模型（PornMaster）不加 `--allow-nsfw` 会被静默过滤成 `models=[]`，0 张直接退出。
4. `rm` 不释放空间（进 Trash），要回收用 `truncate -s 0`。
5. 中断后 ComfyUI 可能仍算完旧任务，导致新记录计时失真（出现过 1.0s 假记录）。
6. 换卡后权重不同步，先跑 `check_models.py`。
7. SDXL tags 里的括号（`charcoal (medium)`）也会触发同类崩溃，代码已自动去括号。
