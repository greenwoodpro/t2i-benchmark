#!/usr/bin/env python3
"""
make_report.py —— 把 bench_out 中的 records.jsonl 汇总成:
  * summary.csv / summary.md     每模型 × 档位：平均耗时、峰值显存、成功率、各类别张数
  * gallery_sfw.html             SFW 对比画廊（按 prompt 横向排列各模型）
  * gallery_nsfw.html            NSFW 画廊（单独文件，默认不生成，需 --include-nsfw）
  * scores_template.csv          人工打分表（每图一行，预留 6 个维度）

用法:
  python make_report.py --out ./bench_out            # 汇总 T4 + A10 全部
  python make_report.py --out ./bench_out --include-nsfw
"""
import argparse, csv, html, json, statistics
from collections import defaultdict
from pathlib import Path

DIMS = ["prompt_adherence", "aesthetics", "detail_fidelity", "text_render", "style_match", "artifact_free"]

def load(out: Path):
    recs = []
    for prof in ("T4", "A10"):
        f = out / prof / "records.jsonl"
        if f.exists():
            for line in f.open(encoding="utf-8"):
                line = line.strip()
                if line:
                    try: recs.append(json.loads(line))
                    except Exception: pass
    # 同 key 多次运行只保留最后一次
    latest = {}
    for r in recs: latest[(r["gpu_profile"], r["model_id"], r["prompt_id"], r["seed"], r["prompt_lang"])] = r
    return list(latest.values())

def summarize(recs):
    g = defaultdict(list)
    for r in recs: g[(r["gpu_profile"], r["model_id"])].append(r)
    rows = []
    for (prof, m), rs in sorted(g.items()):
        ok = [r for r in rs if not r["error"] and r["image_path"]]
        warm = [r["duration_sec"] for r in ok if not r["cold_start"]] or [r["duration_sec"] for r in ok]
        vram = [r["peak_vram_mb"] for r in ok if r["peak_vram_mb"] and r["peak_vram_mb"] > 0]
        cats = defaultdict(int)
        for r in ok: cats[r["category"]] += 1
        rows.append(dict(
            gpu_profile=prof, gpu_name=rs[0]["gpu_name"], model_id=m, model_file=rs[0]["model_file"],
            text_encoder=rs[0]["text_encoder"], steps=rs[0]["steps"], cfg=rs[0]["cfg"], sampler=rs[0]["sampler"],
            images_ok=len(ok), images_failed=len(rs) - len(ok),
            sfw=sum(1 for r in ok if not r["nsfw"]), nsfw=sum(1 for r in ok if r["nsfw"]),
            avg_sec_warm=round(statistics.mean(warm), 1) if warm else "",
            median_sec_warm=round(statistics.median(warm), 1) if warm else "",
            first_image_sec=next((r["duration_sec"] for r in ok if r["cold_start"]), ""),
            peak_vram_mb=max(vram) if vram else "",
            categories=json.dumps(dict(cats), ensure_ascii=False),
            first_error=next((r["error"] for r in rs if r["error"]), "")))
    return rows

def md_table(rows):
    if not rows: return "_无数据_"
    cols = ["gpu_profile", "model_id", "images_ok", "images_failed", "avg_sec_warm", "median_sec_warm", "first_image_sec", "peak_vram_mb", "steps", "cfg", "sampler"]
    s = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    for r in rows: s += "| " + " | ".join(str(r[c]) for c in cols) + " |\n"
    return s

def gallery(recs, out: Path, title: str, nsfw: bool):
    recs = [r for r in recs if r["nsfw"] == nsfw and r["image_path"]]
    if not recs: return None
    models = sorted({(r["gpu_profile"], r["model_id"]) for r in recs})
    byp = defaultdict(dict)
    for r in recs: byp[(r["prompt_id"], r["seed"], r["prompt_lang"])][(r["gpu_profile"], r["model_id"])] = r
    cats = sorted({r["category"] for r in recs})
    css = """body{font-family:system-ui,sans-serif;background:#111;color:#eee;margin:0;padding:16px}
    h1{font-size:20px}h2{font-size:15px;margin:28px 0 6px;color:#9cf}.meta{font-size:12px;color:#aaa;margin-bottom:6px;max-width:1200px}
    .row{display:flex;gap:8px;overflow-x:auto;padding-bottom:10px}.cell{flex:0 0 300px;background:#1c1c1c;border-radius:6px;padding:6px}
    .cell img{width:100%;height:auto;border-radius:4px;display:block}.cell .cap{font-size:11px;color:#ccc;margin-top:4px;line-height:1.5}
    .cell .cap b{color:#fff}.filter{position:sticky;top:0;background:#111;padding:8px 0;z-index:2;font-size:13px}
    .filter button{margin:2px;background:#222;color:#ddd;border:1px solid #444;border-radius:4px;padding:3px 8px;cursor:pointer}
    .filter button.on{background:#2a6fdb;border-color:#2a6fdb;color:#fff}.hidden{display:none}"""
    js = """const btns=[...document.querySelectorAll('.filter button')];btns.forEach(b=>b.onclick=()=>{btns.forEach(x=>x.classList.remove('on'));b.classList.add('on');
    document.querySelectorAll('section').forEach(s=>s.classList.toggle('hidden',b.dataset.c!=='all'&&s.dataset.c!==b.dataset.c));});"""
    parts = [f"<!doctype html><html lang=zh><meta charset=utf-8><title>{html.escape(title)}</title><style>{css}</style><body><h1>{html.escape(title)}</h1>",
             f"<div class=meta>{len(recs)} 张图 · {len(byp)} 个 prompt×seed · 模型: {', '.join(f'{p}/{m}' for p, m in models)}</div>",
             "<div class=filter>类别: <button class=on data-c=all>全部</button>" + "".join(f"<button data-c='{c}'>{c}</button>" for c in cats) + "</div>"]
    for (pid, seed, lang), mm in sorted(byp.items()):
        any_r = next(iter(mm.values()))
        parts.append(f"<section data-c='{any_r['category']}'><h2>{html.escape(pid)} · seed {seed}{' · 中文' if lang=='zh' else ''} — {html.escape(any_r['title_zh'])}</h2>")
        parts.append(f"<div class=meta>考察: {html.escape(' / '.join(any_r['tags_eval']))}<br>Prompt: {html.escape(any_r['prompt_used'][:400])}</div><div class=row>")
        for key in models:
            r = mm.get(key)
            if not r: parts.append(f"<div class=cell><div class=cap><b>{key[0]} / {key[1]}</b><br>（无）</div></div>"); continue
            ex = {k: v for k, v in (r.get("extra") or {}).items() if v not in (None, "default")}
            parts.append(f"<div class=cell><a href='{html.escape(r['image_path'])}' target=_blank><img loading=lazy src='{html.escape(r['image_path'])}'></a>"
                         f"<div class=cap><b>{key[0]} / {key[1]}</b><br>{r['width']}×{r['height']} · {r['steps']}步 cfg{r['cfg']} {html.escape(r['sampler'])} {html.escape(str(r.get('scheduler','')))}"
                         f"{(' · '+html.escape(json.dumps(ex,ensure_ascii=False))) if ex else ''}<br>耗时 {r['duration_sec']}s{' (冷启动)' if r['cold_start'] else ''} · 峰值显存 {r['peak_vram_mb']}MB</div></div>")
        parts.append("</div></section>")
    parts.append(f"<script>{js}</script></body></html>")
    p = out / ("gallery_nsfw.html" if nsfw else "gallery_sfw.html")
    p.write_text("\n".join(parts), encoding="utf-8"); return p

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default="./bench_out"); ap.add_argument("--include-nsfw", action="store_true")
    a = ap.parse_args(); out = Path(a.out)
    recs = load(out)
    if not recs: raise SystemExit(f"{out} 下没有 records.jsonl")
    rows = summarize(recs)
    with (out / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    md = ["# 测评汇总", "", f"记录总数: {len(recs)}（SFW {sum(1 for r in recs if not r['nsfw'])} / NSFW {sum(1 for r in recs if r['nsfw'])}）", "",
          "## 性能", "", md_table(rows), "", "## 失败", ""]
    errs = [r for r in recs if r["error"]]
    md += [f"- {r['gpu_profile']}/{r['model_id']} {r['prompt_id']} s{r['seed']}: {r['error'][:200]}" for r in errs] or ["无"]
    (out / "summary.md").write_text("\n".join(md), encoding="utf-8")
    with (out / "scores_template.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["gpu_profile", "model_id", "prompt_id", "seed", "category", "nsfw", "image_path"] + DIMS + ["notes"])
        for r in sorted(recs, key=lambda r: (r["nsfw"], r["prompt_id"], r["seed"], r["gpu_profile"], r["model_id"])):
            if r["image_path"]: w.writerow([r["gpu_profile"], r["model_id"], r["prompt_id"], r["seed"], r["category"], r["nsfw"], r["image_path"]] + [""] * (len(DIMS) + 1))
    g1 = gallery(recs, out, "开源文生图测评 · SFW 对比画廊", False)
    g2 = gallery(recs, out, "开源文生图测评 · NSFW 画廊（仅成年人内容）", True) if a.include_nsfw else None
    print("生成:", out / "summary.md", out / "summary.csv", out / "scores_template.csv", g1, g2 or "(未生成 NSFW 画廊)")

if __name__ == "__main__":
    main()
