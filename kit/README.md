# 开源文生图模型全方位测评套件（Cloud Studio T4 16G / A10 24G）

一套开箱即用的测评包：**模型清单（已核实）+ 51 条 SFW 提示词 + 下载/跑图/汇总脚本 + 执行手册**。

> 公开版说明：原始提示词集 67 条中的 16 条成人向条目已移除，本目录只保留 51 条 SFW。
> 本次实测额外接入了 FLUX.3 klein、Krea 2、MOSS-Image 五个配置，相关改动见 `../docs/CHANGELOG.md`。
所有链接、文件名、大小、采样参数在 2026-10 通过 HuggingFace API、Civitai API、Comfy-Org 官方工作流模板逐一核对。

## 测什么

| 阵营 | 模型 | 为什么选它 |
|---|---|---|
| 新一代开源 DiT | **Z-Image-Turbo**（阿里，6B，Apache-2.0） | 2025-11 发布后开源榜单第一梯队，8 步出图，中英文文字渲染强，T4 可跑 |
| | **FLUX.2 [klein] 4B / 9B**（BFL） | FLUX.2 系列的小参数蒸馏版，4 步出图；4B Apache-2.0 可商用，9B 画质更好但 gated 且需 A10 |
| | **FLUX.1 Krea [dev]**（Krea × BFL，12B） | 专门调优"去 AI 感"的写实美学，是摄影类对照组 |
| | **Qwen-Image 2.1**（阿里，20B，Base + Turbo） | 当前开源文字渲染/中文理解最强，原生 2K；int8 版 T4 也能跑 |
| SDXL 二次元 | **Animagine XL 4.0 opt** | Cagliostro 官方系列，danbooru 标签体系的标准参照 |
| | **WAI-illustrious-SDXL v17** | Civitai 下载量最高的 Illustrious 系合并模型，兼顾 SFW/NSFW |
| SDXL 写实 NSFW | **PornMaster Pro SDXL V8**（用户指定参考） | 写实 NSFW SDXL 代表 |

未纳入但可加测：NoobAI-XL V-Pred（需特殊 v-pred 工作流）、Pony V6（提示词体系不同）、Krea 2（2026-10 新发，仅 A10）、FLUX.3 image klein（刚发布）。详见 `01_models/models.json → alternatives_not_included`。

## 提示词集（51 条 SFW）

51 条 SFW，覆盖 **人像 / 风景 / 电影 / 科幻 / 二次元 / 文字渲染 / 艺术风格 / 奇幻 / 建筑 / 产品 / 动物 / 压力测试 / 文化 / 超现实** 14 个类别。
每条提供 4 种写法（英文自然语言、中文、danbooru 标签、SDXL 写实短句）、画幅比例、考察维度与中文标题。
分档：`smoke`(3) / `quick`(14) / `standard`(51) / `full`(51×2 seeds) / `zh`(51 中文) / `top20`(20)。

## 快速开始（三步）

```bash
unzip t2i-benchmark-kit.zip && cd t2i-benchmark-kit
bash 03_scripts/setup_comfyui.sh /workspace/ComfyUI                      # 装环境（CPU 机可做）
COMFY_DIR=/workspace/ComfyUI bash 03_scripts/download_models.sh T4       # 下模型（CPU 机可做；A10 换参数）
bash /workspace/ComfyUI/start_T4.sh &                                     # GPU 机启动 ComfyUI
python 03_scripts/run_benchmark.py --profile T4 --tier smoke --models all # 冒烟
python 03_scripts/run_benchmark.py --profile T4 --tier standard --models all
python 03_scripts/make_report.py --out ./bench_out                        # 汇总 + 画廊
```

详细步骤、时间估算、排错表、公平性约束 → **`WORKBUDDY.md`**（直接把这份文件交给 Cloud Studio 的 WorkBuddy 执行）。

## 输出

```
bench_out/
├── T4/  ├── sfw/<model>/<prompt>__s<seed>.png     ← 图片内嵌完整元数据
│        ├── records.jsonl  records.csv             ← 每图：型号/参数/耗时/分辨率/提示词/标签/显存
├── A10/ └── 同上
├── summary.md  summary.csv                          ← 每模型平均耗时、峰值显存、成功率
├── gallery_sfw.html                                 ← 横向对比画廊（按类别筛选）
└── scores_template.csv                              ← 人工 0–5 打分表（6 个维度）
```

## 评分维度

提示词遵循度 · 美学/构图 · 细节与物理合理性 · 文字渲染（text 类） · 风格匹配 · 无伪影 ——各 0–5 分，另记单图耗时与峰值显存。

## 法律与安全

公开版只含 SFW 内容。原始测评另跑了成人向条目用于观察护栏行为，未随本仓库分发。请遵守 Cloud Studio 平台规定与所在地法律；FLUX.1 Krea / FLUX.2 klein 9B / Qwen-Image 为非商业或研究许可，测评结果用于商业前请自查。
