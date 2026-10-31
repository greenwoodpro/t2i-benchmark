#!/usr/bin/env bash
# ============================================================
# A10 收尾：等链跑完 -> 校验 -> 报告 -> 站点 -> 同步仓库包 -> 三个 zip
#   日志: /workspace/runs/finish_A10.log
# ============================================================
set -u
B=/workspace/bench_out
KIT=/workspace/ComfyUI/t2i-benchmark-kit/t2i-benchmark-kit/03_scripts
L=/workspace/runs
LOG=$L/finish_A10.log
: > "$LOG"
say() { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$LOG"; }

# 1) 等链结束
say "等待 CHAIN_DONE ..."
for i in $(seq 1 480); do
  grep -q "CHAIN_DONE" "$L/chain_A10_v2.log" 2>/dev/null && break
  sleep 15
done
grep -q "CHAIN_DONE" "$L/chain_A10_v2.log" || { say "超时未完成，退出"; exit 1; }
say "链已结束"

# 1.5) 等 MOSS 8 步加速档 NSFW 补完
say "等待 FAST_NSFW_DONE ..."
for i in $(seq 1 240); do
  grep -q "FAST_NSFW_DONE" "$L/fast_nsfw.log" 2>/dev/null && break
  sleep 15
done
grep -q "FAST_NSFW_DONE" "$L/fast_nsfw.log" 2>/dev/null || { say "fast NSFW 未完成，退出"; exit 1; }
say "fast NSFW 已完成"

# 2) 完整性校验（不合格直接退出，避免打出脏包）
say "校验记录完整性"
python3 - "$B" <<'PY' >>"$LOG" 2>&1
import json, sys, os, glob
B=sys.argv[1]
tot=0
for prof in ("T4","A10"):
    f=os.path.join(B,prof,"records.jsonl")
    rows=[json.loads(l) for l in open(f)]
    miss=[r for r in rows if not os.path.exists(os.path.join(B,r["image_path"]))]
    blank=[r for r in rows if os.path.exists(os.path.join(B,r["image_path"])) and os.path.getsize(os.path.join(B,r["image_path"]))<50000]
    err=[r for r in rows if r.get("error")]
    png=len(glob.glob(os.path.join(B,prof,"**","*.png"),recursive=True))
    print(f"{prof}: 记录 {len(rows)} PNG {png} 缺图 {len(miss)} 空白 {len(blank)} 失败 {len(err)}")
    if miss or blank or err or png<len(rows):
        print("!! 校验不通过"); sys.exit(3)
    tot+=len(rows)
print("TOTAL",tot)
PY
rc=$?
if [ "$rc" -ne 0 ]; then say "校验失败($rc)，中止"; exit 3; fi
say "校验通过"

# 3) 报告与站点
cd "$KIT" && say "make_report" && python3 make_report.py --out "$B" >>"$LOG" 2>&1
cd "$B" || exit 1
for s in build_site.py build_report.py build_disclaimer.py build_moss_compare.py; do
  say "run $s"; python3 "$s" >>"$LOG" 2>&1 || say "!! $s 失败"
done

# 4) 同步 GitHub 仓库包（保留 .gitignore/.nojekyll）
say "同步 github_repo"
cp -a "$B"/site/assets "$B"/site/data "$B"/site/thumbs "$B"/github_repo/ 2>>"$LOG"
cp -f "$B"/site/*.html "$B"/github_repo/ 2>>"$LOG"
cp -f "$B"/site/README.md "$B"/site/LICENSE "$B"/site/DISCLAIMER.md "$B"/github_repo/ 2>>"$LOG"
du -sh "$B/github_repo" >>"$LOG"

# 5) 打包
say "make_pkg"
python3 "$B/make_pkg.py" >>"$LOG" 2>&1
say "FINISH_DONE"
ls -lh /workspace/*.zip >>"$LOG" 2>&1
