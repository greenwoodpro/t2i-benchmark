#!/usr/bin/env python3
"""
build_site.py —— 从测评工程包生成静态站点（支持 SFW 公开版 / 全量私有版）。

用法:
    python tools/build_site.py --src /path/to/pkg --variant public  --out ../t2i-benchmark
    python tools/build_site.py --src /path/to/pkg --variant private --out ../t2i-benchmark-private

variant:
    public  仅 SFW：723 张图 / 51 条提示词，可直接公开部署
    private 全量：1107 张图 / 67 条提示词（含 16 条成人向），默认遮蔽，需确认后查看

输入（--src 指向解压后的工程包根目录）:
    bench_out/<GPU>/records.jsonl
    bench_out/<GPU>/sfw/<model>/*.png · bench_out/<GPU>/nsfw/<model>/*.png
    kit/t2i-benchmark-kit/02_prompts/prompts.json

输出:
    <out>/*.html  assets/  data/  thumbs/  README.md  LICENSE ...
"""
import argparse, csv, json, shutil, statistics, sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = (HERE / "template") if (HERE / "template").exists() else (HERE.parent / "template")

# ---------------------------------------------------------------- 模型元信息
# name, maker, family, note, license, intro, strengths
META = {
    "z_image_turbo": (
        "Z-Image Turbo", "阿里 Tongyi-MAI", "Z-Image", "6B DiT · 8 步蒸馏 · 中文原生", "Apache-2.0",
        "6B 的蒸馏 DiT，用 Qwen3-4B 做文本编码、16 通道 ae VAE。8 步、cfg 1，是全表里少数原生支持中文提示词的模型；"
        "文字渲染（招牌、海报）是它的强项。T4 上峰值 14.9G，属于「刚好塞得下」。",
        ["中文提示词", "文字渲染", "8 步"]),
    "flux2_klein_4b": (
        "FLUX.2 klein 4B", "Black Forest Labs", "FLUX.2", "4B 蒸馏 · 4 步 · Apache-2.0", "Apache-2.0",
        "FLUX.2 系列的小参数蒸馏版，4 步出图，共享 Qwen3-4B 文本编码器与 flux2-vae。"
        "T4 定版批次中位 13.1 秒，是同卡最快；代价是显存贴顶，必须 lowvram。",
        ["T4 最快", "4 步", "可商用"]),
    "flux1_krea_dev": (
        "FLUX.1 Krea [dev]", "Krea × BFL", "FLUX.1", "12B · 20 步 · 写实调优", "非商业许可",
        "Krea 与 BFL 合作的 12B 写实模型，卖点是「去 AI 感」——皮肤、胶片颗粒、镜头语言更接近摄影。"
        "权重 11.9G，在 16G 卡上反复换入换出，T4 单张 111 秒，是全表最慢。",
        ["写实摄影", "去 AI 感", "12B"]),
    "qwen_image_2_1": (
        "Qwen-Image 2.1", "阿里 Qwen", "Qwen-Image", "20B MMDiT · 25 步", "研究许可",
        "20B 级 MMDiT，原生 2K，文本编码器是 Qwen3-VL-8B。中文排版与长文本理解是它最能打的地方。"
        "T4 跑不动，只在 A10 上测；25 步单张 66 秒。",
        ["20B", "中文排版", "长文本"]),
    "qwen_image_2_1_turbo": (
        "Qwen-Image 2.1 Turbo", "阿里 Qwen", "Qwen-Image", "20B 蒸馏 · 8 步", "研究许可",
        "同一底模的 8 步蒸馏版，画质略降、速度约 2.7 倍。24G 卡上做中文海报的首选："
        "8 步 24.1 秒，比 Base 版省三分之二时间。",
        ["8 步", "中文", "性价比"]),
    "flux3_klein": (
        "FLUX.3 klein", "Black Forest Labs", "FLUX.3", "16 步 · bf16 · 仅 A10", "见模型页",
        "FLUX.3 系列的小参数版本，16 步、cfg 1。在 T4 上因 bf16 转 fp16 数值溢出产出全黑图，"
        "本轮改为 A10 原生 bf16 重跑，13.0 秒一张，是 A10 最快。",
        ["A10 最快", "新代", "16 步"]),
    "krea2_turbo": (
        "Krea 2 Turbo", "Krea", "Krea 2", "8 步 · 峰值 18.8G", "见模型页",
        "Krea 2 的蒸馏加速版，8 步、cfg 1，文本编码器 Qwen3-VL-4B。峰值显存 18.8G，"
        "是全场最高——16G 卡完全无法承载，属于 24G 卡的专属项目。",
        ["8 步", "高显存", "美学"]),
    "moss_image": (
        "MOSS-Image（50 步）", "OpenMOSS", "MOSS", "5B DiT · 真 CFG · 50 步", "见模型页",
        "5B DiT，走 FLUX.2 latent，文本编码器 Qwen3.5-9B，用真正的负面提示词与 cfg 3.0。"
        "50 步单张 197 秒，是全表最慢；换来的是可控性，适合版面类实验而非批量生产。",
        ["真 CFG", "50 步", "布局"]),
    "moss_image_fast": (
        "MOSS-Image 8 步", "OpenMOSS", "MOSS", "DMD 蒸馏 · 无 CFG", "见模型页",
        "在 SFT 权重上挂 8 步 DMD LoRA，去掉 CFG。同一底模从 197 秒压到 18.1 秒，"
        "代价是负面提示词失效——和 50 步基线不是同一口径，分开统计。",
        ["8 步", "DMD", "快 11 倍"]),
    "moss_image_base_fast": (
        "MOSS-Image Base 8 步", "OpenMOSS", "MOSS", "Base 权重 + DMD", "见模型页",
        "换成 Base 权重再挂 DMD，峰值显存降到 13.4G，是 A10 上最省显存的一个。"
        "与 SFT 版不是同一个底模，不能直接比画质。",
        ["最省显存", "8 步", "Base"]),
    "sdxl_animagine_xl_4": (
        "Animagine XL 4.0", "Cagliostro Lab", "SDXL", "二次元 · danbooru 标签", "RAIL++-M",
        "SDXL 二次元的标准参照，用 danbooru 标签体系、28 步 cfg 5。显存只要 12G，"
        "是 16G 卡上最从容的一档；代价是提示词必须按标签写。",
        ["二次元", "低显存", "标签体系"]),
    "sdxl_wai_illustrious": (
        "WAI-illustrious v17", "Civitai 社区", "SDXL", "Illustrious 合并模型", "见模型页",
        "Illustrious 系下载量最高的合并模型，28 步 cfg 6。线条与上色比 Animagine 更「现代」，"
        "但同样依赖标签写法，且 CLIP 有 77 token 的硬边界。",
        ["二次元", "合并模型", "28 步"]),
    "sdxl_pornmaster_pro_v8": (
        "PornMaster Pro V8", "Civitai 社区", "SDXL", "写实 SDXL · R18 调优", "见模型页",
        "写实向 SDXL 调优模型，本轮只取其 SFW 输出参与横评，用于观察写实 SDXL 在通用题上的表现。"
        "30 步 dpmpp_2m，单张 30.1 秒。",
        ["写实", "SDXL", "仅 SFW 参与"]),
}

ORDER = ["z_image_turbo", "flux2_klein_4b", "flux1_krea_dev",
         "sdxl_animagine_xl_4", "sdxl_wai_illustrious", "sdxl_pornmaster_pro_v8",
         "flux3_klein", "krea2_turbo", "moss_image", "moss_image_fast",
         "moss_image_base_fast", "qwen_image_2_1", "qwen_image_2_1_turbo"]

CATS = [
    ("portrait",     "人像",     "皮肤纹理、手部、多人属性绑定、年龄与族群", 0),
    ("landscape",    "风景",     "大气透视、水面雪雾、光照一致性", 0),
    ("cinematic",    "电影",     "镜头语言、调色、年代质感", 0),
    ("scifi",        "科幻",     "硬表面结构、设计密度、尺度感", 0),
    ("anime",        "二次元",   "风格一致性、角色设计、双人互动", 0),
    ("text",         "文字渲染", "招牌、书法、多行排版、双语菜单、手写", 0),
    ("art",          "艺术风格", "笔触与流派还原", 0),
    ("fantasy",      "奇幻",     "生物设计、魔法特效、场景复杂度", 0),
    ("architecture", "建筑",     "透视直线、材质、室内外光", 0),
    ("product",      "产品",     "棚拍光、玻璃金属反射、爆炸视图", 0),
    ("animal",       "动物",     "毛发、眼神、拟人化", 0),
    ("stress",       "压力测试", "计数、空间关系、镜面反射、罕见材质", 0),
    ("culture",      "文化",     "中式与地域元素准确性", 0),
    ("surreal",      "超现实",   "概念融合、物理违背的可信度", 0),
    ("nsfw",         "成人向",   "成年人体解剖与布料质感（仅私有版）", 1),
    ("nsfw_extreme", "成人向·极端", "极端姿势与交互（仅私有版）", 1),
    ("nsfw_dark",    "成人向·黑暗", "暗黑主题与氛围（仅私有版）", 1),
    ("nsfw_guro",    "成人向·猎奇", "猎奇身体改造（仅私有版）", 1),
]


def load_jsonl(p: Path):
    out = []
    if not p.exists():
        return out
    for line in p.open(encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def hours(sec: float) -> str:
    return f"{sec / 3600:.1f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="解压后的工程包根目录")
    ap.add_argument("--out", required=True, help="输出目录（仓库根）")
    ap.add_argument("--variant", choices=["public", "private"], default="public")
    ap.add_argument("--no-thumbs", action="store_true")
    ap.add_argument("--thumb-size", type=int, default=720)
    ap.add_argument("--thumb-quality", type=int, default=82)
    ap.add_argument("--gpt-src", default=None,
                    help="GPT 对照素材目录，含 gpt.js 与 img/*.jpg；默认找 <src>/gpt")
    a = ap.parse_args()

    src, out = Path(a.src), Path(a.out)
    private = a.variant == "private"
    data_dir = out / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------ 载入并去重
    recs = load_jsonl(src / "bench_out/T4/records.jsonl") + load_jsonl(src / "bench_out/A10/records.jsonl")
    if not recs:
        sys.exit("没有找到 records.jsonl")

    latest = {}
    for r in recs:
        key = (r["gpu_profile"], r["model_id"], r["prompt_id"], r["seed"], r["prompt_lang"])
        if key not in latest or r["timestamp"] > latest[key]["timestamp"]:
            latest[key] = r
    all_rows = [r for r in latest.values() if not r["error"] and r.get("image_path")]
    rows = all_rows if private else [r for r in all_rows if not r["nsfw"]]

    sfw = [r for r in rows if not r["nsfw"]]
    nsfw = [r for r in rows if r["nsfw"]]

    # ------------------------------------------------ 模型统计
    by_model = defaultdict(list)      # 展示 / 计数 / 累计耗时：按 variant
    timing = defaultdict(list)        # 速度 / 显存：始终用全量，避免两版口径不一致
    for r in rows:
        by_model[(r["gpu_profile"], r["model_id"])].append(r)
    for r in all_rows:
        timing[(r["gpu_profile"], r["model_id"])].append(r)

    models, gallery = [], []
    for key, rs in by_model.items():
        profile, mid = key
        trs = timing[key]
        dates = sorted({r["timestamp"][:10] for r in trs})
        # 取最近一个样本量足够的批次（>=8 条），避免最后那批只有两三条时回退到全量
        final_date, final = "all", trs
        for d in reversed(dates):
            batch = [r for r in trs if r["timestamp"][:10] == d]
            if len(batch) >= 8:
                final_date, final = d, batch
                break

        def med(batch):
            d = [r["duration_sec"] for r in batch if not r["cold_start"]] or [r["duration_sec"] for r in batch]
            return statistics.median(d)

        def p90(batch):
            d = sorted(r["duration_sec"] for r in batch if not r["cold_start"]) or sorted(r["duration_sec"] for r in batch)
            return d[max(int(len(d) * 0.9) - 1, 0)]

        name, maker, family, note, lic, intro, strengths = META.get(mid, (mid, "?", "?", "", "见模型页", "", []))
        r0 = rs[0]
        total = sum(r["duration_sec"] for r in rs)
        models.append(dict(
            id=mid, name=name, maker=maker, family=family, note=note, license=lic,
            intro=intro, strengths=strengths,
            profile=profile,
            steps=r0["steps"], cfg=r0["cfg"],
            sampler=r0["sampler"], scheduler=r0.get("scheduler") or "",
            file=r0["model_file"] or "", te=r0["text_encoder"] or "内置",
            vae=r0["vae"] or "内置",
            n=len(rs), prompts=len({r["prompt_id"] for r in rs}),
            seeds=sorted({r["seed"] for r in rs}),
            median_all=round(med(trs), 1), median_final=round(med(final), 1),
            p90_final=round(p90(final), 1),
            vram_mb=max((r["peak_vram_mb"] for r in trs if r["peak_vram_mb"]), default=0),
            total_sec=round(total, 1),
            avg_sec=round(total / len(rs), 1),
            final_date=final_date, final_n=len(final),
            first_date=dates[0], last_date=dates[-1],
            nsfw_n=sum(1 for r in rs if r["nsfw"]),
            chinese=(mid in ("z_image_turbo", "qwen_image_2_1", "qwen_image_2_1_turbo")),
        ))

        for r in rs:
            stem = Path(r["image_path"]).stem
            sub = "nsfw" if r["nsfw"] else "sfw"
            rel = f'thumbs/{profile}/{"" if not r["nsfw"] else "nsfw/"}{mid}/{stem}.jpg'
            gallery.append(dict(
                p=profile, m=mid, id=r["prompt_id"], t=r["title_zh"], c=r["category"],
                a=r["aspect"], w=r["width"], h=r["height"], s=r["seed"],
                d=round(r["duration_sec"], 1), v=r["peak_vram_mb"] or 0,
                i=rel, lang=r["prompt_lang"], n=1 if r["nsfw"] else 0,
                st=r["steps"], cf=r["cfg"], sa=r["sampler"],
                sub=sub,
            ))

    rank = {m: i for i, m in enumerate(ORDER)}
    models.sort(key=lambda m: (rank.get(m["id"], 99), m["profile"]))
    gallery.sort(key=lambda g: (g["n"], g["m"], g["id"], g["s"]))

    # ------------------------------------------------ 提示词
    pd = json.loads((src / "kit/t2i-benchmark-kit/02_prompts/prompts.json").read_text(encoding="utf-8"))
    prompts = []
    for p in pd["prompts"]:
        if p.get("nsfw") and not private:
            continue
        prompts.append(dict(
            id=p["id"], category=p["category"], title=p["title_zh"], aspect=p["aspect"],
            evaluates=p.get("evaluates") or [], prompt=p["prompt"],
            prompt_zh=p.get("prompt_zh", ""), tags=p.get("tags", ""), sdxl=p.get("sdxl_prompt", ""),
            nsfw=1 if p.get("nsfw") else 0,
        ))

    cat_count = Counter(p["category"] for p in prompts)
    img_count = Counter(g["c"] for g in gallery)
    categories = [dict(key=k, zh=zh, desc=desc, nsfw=bool(nf),
                       count=cat_count.get(k, 0), images=img_count.get(k, 0))
                  for k, zh, desc, nf in CATS if private or not nf]

    # ------------------------------------------------ 汇总
    t4 = [m for m in models if m["profile"] == "T4"]
    a10 = [m for m in models if m["profile"] == "A10"]
    fastest_t4 = min(t4, key=lambda m: m["median_final"])
    slowest_t4 = max(t4, key=lambda m: m["median_final"])
    fastest_a10 = min(a10, key=lambda m: m["median_final"])
    flux2 = next((m for m in models if m["id"] == "flux2_klein_4b"), None)

    total_sec = sum(r["duration_sec"] for r in rows)
    t4_sec = sum(r["duration_sec"] for r in rows if r["gpu_profile"] == "T4")
    a10_sec = total_sec - t4_sec

    by_date = defaultdict(lambda: dict(n=0, sec=0.0))
    for r in rows:
        d = by_date[r["timestamp"][:10]]
        d["n"] += 1
        d["sec"] += r["duration_sec"]
    timeline = [dict(date=k, n=v["n"], hours=round(v["sec"] / 3600, 2))
                for k, v in sorted(by_date.items())]

    data = dict(
        variant=a.variant,
        kit=dict(
            name="开源文生图模型测评",
            en="T2I BENCHMARK",
            date="2026-10-27",
            desc=("同一套 51 条 SFW 提示词、同一套记录协议，在 Tesla T4 16G 与 NVIDIA A10 24G 上跑 13 个模型配置。"
                  if not private else
                  "同一套 67 条提示词（含 16 条成人向）、同一套记录协议，在 Tesla T4 16G 与 NVIDIA A10 24G 上跑 13 个模型配置。"),
        ),
        counts=dict(
            images=len(rows), sfw=len(sfw), nsfw=len(nsfw),
            models=len(models), prompts=len(prompts), categories=len(categories),
            t4=sum(1 for r in rows if r["gpu_profile"] == "T4"),
            a10=sum(1 for r in rows if r["gpu_profile"] == "A10"),
            total_sec=round(total_sec, 1), total_hours=round(total_sec / 3600, 1),
            t4_hours=round(t4_sec / 3600, 1), a10_hours=round(a10_sec / 3600, 1),
            avg_sec=round(total_sec / len(rows), 1),
            records=len(rows),
        ),
        models=models, prompts=prompts, categories=categories, timeline=timeline,
        highlight=dict(
            fastest_t4=dict(id=fastest_t4["id"], name=fastest_t4["name"], sec=fastest_t4["median_final"]),
            slowest_t4=dict(id=slowest_t4["id"], name=slowest_t4["name"], sec=slowest_t4["median_final"]),
            fastest_a10=dict(id=fastest_a10["id"], name=fastest_a10["name"], sec=fastest_a10["median_final"]),
            speedup=round(slowest_t4["median_final"] / fastest_t4["median_final"], 1),
            flux2_all=flux2["median_all"] if flux2 else None,
            flux2_final=flux2["median_final"] if flux2 else None,
            vram_ceiling=max(m["vram_mb"] for m in t4) if t4 else 0,
        ),
        aspect=pd["_meta"]["aspect_to_resolution"],
        scoring=pd["_meta"]["scoring_dimensions"],
        sources=dict(records=len(rows), batches=sorted(by_date.keys())),
    )

    (data_dir / "site-data.js").write_text(
        "window.BENCH = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    (data_dir / "site-data.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    (data_dir / "gallery.js").write_text(
        "window.GALLERY = " + json.dumps(gallery, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")

    with (data_dir / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        cols = ["gpu_profile", "model_id", "images", "sfw", "nsfw", "prompts_covered",
                "median_all_sec", "median_final_sec", "p90_final_sec", "peak_vram_mb",
                "total_sec", "total_hours", "avg_sec", "steps", "cfg", "sampler",
                "final_batch", "final_batch_n", "model_file"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for m in models:
            w.writerow(dict(
                gpu_profile=m["profile"], model_id=m["id"], images=m["n"],
                sfw=m["n"] - m["nsfw_n"], nsfw=m["nsfw_n"], prompts_covered=m["prompts"],
                median_all_sec=m["median_all"], median_final_sec=m["median_final"],
                p90_final_sec=m["p90_final"], peak_vram_mb=m["vram_mb"],
                total_sec=m["total_sec"], total_hours=hours(m["total_sec"]),
                avg_sec=m["avg_sec"], steps=m["steps"], cfg=m["cfg"],
                sampler=m["sampler"], final_batch=m["final_date"],
                final_batch_n=m["final_n"], model_file=m["file"]))

    # ------------------------------------------------ 模板与页面
    if not TEMPLATE.exists():
        sys.exit(f"模板目录不存在: {TEMPLATE}")
    for item in TEMPLATE.iterdir():
        if item.name in ("README-public.md", "README-private.md"):
            continue
        dst = out / item.name
        if item.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(item, dst)
        else:
            shutil.copy2(item, dst)

    readme_src = TEMPLATE / ("README-private.md" if private else "README-public.md")
    if readme_src.exists():
        shutil.copy2(readme_src, out / "README.md")

    for f in ["index.html", "gallery.html", "report.html", "models.html", "gpt.html", "disclaimer.html"]:
        p = out / f
        s = p.read_text(encoding="utf-8")
        s = s.replace("__VARIANT__", a.variant)
        head_extra = '<meta name="robots" content="noindex,nofollow">\n' if private else ""
        s = s.replace("<!--HEAD-EXTRA-->\n", head_extra)
        p.write_text(s, encoding="utf-8")

    # ------------------------------------------------ 缩略图
    if not a.no_thumbs:
        from PIL import Image
        made = missing = 0
        for g in gallery:
            sub = "nsfw" if g["n"] else "sfw"
            src_img = src / "bench_out" / g["p"] / sub / g["m"] / (Path(g["i"]).stem + ".png")
            dst = out / g["i"]
            if not src_img.exists():
                missing += 1
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            im = Image.open(src_img).convert("RGB")
            w, h = im.size
            scale = a.thumb_size / max(w, h)
            if scale < 1:
                im = im.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
            im.save(dst, "JPEG", quality=a.thumb_quality, optimize=True, progressive=True)
            made += 1
        print(f"缩略图: 生成 {made}（{a.thumb_size}px q{a.thumb_quality}），缺失 {missing}")

    # ------------------------------------------------ GPT 对照（可选）
    gpt_src = Path(a.gpt_src) if a.gpt_src else (src / "gpt")
    gpt_js, gpt_img = gpt_src / "gpt.js", gpt_src / "img"
    if gpt_js.exists():
        shutil.copy2(gpt_js, data_dir / "gpt.js")
        n = 0
        if gpt_img.exists():
            dst_dir = out / "assets/gpt"
            dst_dir.mkdir(parents=True, exist_ok=True)
            for f in sorted(gpt_img.glob("*.jpg")):
                shutil.copy2(f, dst_dir / f.name)
                n += 1
        print(f"GPT 对照: data/gpt.js + {n} 张图")
    else:
        print("GPT 对照: 未提供素材（--gpt-src），页面会显示为全空缺")

    print(f"[{a.variant}] {len(models)} 配置 / {len(prompts)} 提示词 / {len(rows)} 张图"
          f"（SFW {len(sfw)} + NSFW {len(nsfw)}）")
    print(f"[{a.variant}] 总耗时 {hours(total_sec)} 小时（T4 {hours(t4_sec)} / A10 {hours(a10_sec)}），"
          f"平均 {total_sec / len(rows):.1f} 秒 / 张")
    print(f"[{a.variant}] 输出到 {out}")


if __name__ == "__main__":
    main()
