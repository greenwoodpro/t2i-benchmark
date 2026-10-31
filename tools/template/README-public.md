# 开源文生图模型测评 · T2I Benchmark 2026

**13 个模型配置 · 2 张显卡 · 723 张 SFW 有效图 · 每张 32 项参数留痕**

同一套 51 条 SFW 提示词、六种画幅、统一记录协议，在 **Tesla T4 16G** 与 **NVIDIA A10 24G** 上逐张跑，
记录分辨率、步数、CFG、采样器、耗时与峰值显存。不改提示词、不加 LoRA、不做后处理。

![图库预览](assets/cover-public.jpg)

> **在线浏览：https://greenwoodpro.github.io/t2i-benchmark/**
>
> 数据快照 **2026-10-27**。本仓库是 **SFW 公开版**：只有非成人向结果。
> 原始测评另有 16 条成人向提示词与 384 张图，只在私有版本中，不在此仓库。
> 模型权重不随仓库分发。

---

## 先看站点

无需构建，双击 `index.html` 即可打开：

| 页面 | 内容 |
|---|---|
| [`index.html`](index.html) | 总览：五条结论、**生成总耗时面板**、T4/A10 排行榜、**速度×显存散点**、模型图鉴 |
| [`gallery.html`](gallery.html) | 图库：723 张图，按显卡 / 模型 / 类别 / 关键词筛选，点击看大图与完整参数 |
| [`report.html`](report.html) | 报告：方法口径、总耗时、速度与显存、架构家族、稳定性、选型结论 |
| [`models.html`](models.html) | 模型：13 个配置的图鉴、参数、31 个权重文件、许可归类 |
| [`gpt.html`](gpt.html) | GPT 对照：同一套 51 条提示词，ChatGPT 跑了 30 条，按编号排成宫格，空缺留白 |
| [`disclaimer.html`](disclaimer.html) | 范围与许可：数据口径、已知误差、CC BY-NC 说明 |

本地预览（灯箱与筛选都能用）：

```bash
python -m http.server 8000
# http://127.0.0.1:8000
```

---

## 关键数字

| 项 | T4 16G | A10 24G |
|---|---|---|
| 配置数 | 6 | 7 |
| 有效图 | 366 | 357 |
| 最快单张（定版批次中位） | **13.1s** FLUX.2 klein 4B | **13.0s** FLUX.3 klein |
| 最慢单张 | **111.3s** FLUX.1 Krea [dev] | **196.7s** MOSS-Image 50 步 |
| 峰值显存 | 14907 MB / 15360 MB | 18853 MB / 24564 MB |

**五条结论**（推导过程见 [`report.html`](report.html)）：

1. **T4 最快与最慢差 8.5 倍**，差距主要来自显存——三个大模型峰值都在 14901–14907 MB，只剩约 450 MB，必须分块换入换出。
2. **一个启动参数值 3.3 倍**：去掉 `--disable-smart-memory` 后 FLUX.2 klein 4B 从 43.4s 降到 13.1s。
3. **SDXL 的 CLIP 有硬边界**：negative 超过 77 token（约 300 字符）必崩 `cublasSgemm`，与语义无关；用末尾裁词重试规避。
4. **FLUX.3 在 T4 上不可用**：bf16 转 fp16 数值溢出，产出纯黑图；int8 权重在 Turing 上无原生算子。最终改 A10 原生 bf16 重跑。
5. **A10 买到的是容量**：Krea 2 峰值 18.8G，Qwen 20B 与 MOSS 50 步都只有 24G 卡能承载。

---

## 数据

```
data/site-data.js     模型 / 提示词 / 类别 / 统计（前端直接消费）
data/gallery.js       723 条图库记录（GPU / 模型 / 题号 / 分辨率 / 耗时 / 显存）
data/summary.csv      每模型统计：定版中位、全量中位、P90、累计耗时、峰值显存
thumbs/<GPU>/<模型>/  723 张 720px 缩略图（JPEG q82）
```

口径说明：

- **定版中位**取该模型最近一个运行批次（同批启动参数一致）；**全量中位**跨所有批次，会把早期慢配置算进去。
- **累计耗时**是该模型全部出图的墙钟时间之和，含首张的模型加载，不等于「中位 × 张数」。
- 首张 `cold_start` 不计入中位；显存取 `nvidia-smi` 每 0.5s 采样峰值。
- 失败记录隔离在原始包的 `records_failed_quarantine.jsonl`，不进入统计。

---

## 目录

```
.
├── index.html  gallery.html  report.html  models.html  disclaimer.html
├── assets/          site.css / site.js / cover.jpg
├── data/            site-data.js / gallery.js / summary.csv
├── thumbs/          723 张缩略图
├── kit/             测评套件：prompts.json（51 条 SFW）/ models.json / 跑图与汇总脚本 / 16 份工作流
├── scripts/         T4/A10 启动脚本、模型自检、断点续跑
├── docs/            CHANGELOG（19 条偏离记录）、OPERATIONS、HANDOVER、MODELS（权重清单）
├── LICENSE          MIT（代码）+ CC BY-NC 4.0（数据与图片）
└── .nojekyll
```

## 重建站点

构建脚本与页面模板在本仓库 `tools/`，改完数据原地重建：

```bash
python tools/build_site.py --src <解压后的工程包> --variant public --out .
# 只重建数据、不动缩略图：加 --no-thumbs
```

`--src` 指向包含 `bench_out/` 与 `kit/` 的工程包根目录。

---

## 部署到 GitHub Pages

```bash
git init && git add . && git commit -m "T2I benchmark: 13 configs on T4/A10 (SFW)"
git remote add origin https://github.com/<你的账号>/t2i-benchmark.git
git push -u origin main
```

仓库 **Settings → Pages → Source: Deploy from a branch → `main` / `/ (root)`**，
一两分钟后访问 https://greenwoodpro.github.io/t2i-benchmark/。仓库已带 `.nojekyll`。

- 仓库约 48 MB（主要是 723 张缩略图），在 GitHub 建议的 1 GB 以内。
- 原始 PNG 全量约 1.5 GB，**不入库**；需要原图请从跑图产物另存，或用 release 附件。
- 免费账号的 Pages 只支持公开仓库；私密仓库发布需要 Pro/Team。

---

## 许可与范围

- 代码（HTML / CSS / JS / Python）：**MIT**
- 评测数据与生成图片（`data/`、`thumbs/`）：**CC BY-NC 4.0**
- 模型权重与商标：归各自作者所有，本仓库不分发

仅用于技术研究与模型能力对比，不构成采购或性能担保。已知限制（批次混合、样本量、单机墙钟）
写在 [`disclaimer.html`](disclaimer.html)。
