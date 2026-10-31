#!/usr/bin/env bash
# T4 断点续跑（随时可停，重跑本脚本自动跳过已有图）
# 内容：WAI 补 8 条 SFW -> krea_dev 补剩余 SFW -> 出报告 + 刷新看板
set -u
S=/workspace/ComfyUI/t2i-benchmark-kit/t2i-benchmark-kit/03_scripts
OUT=/workspace/bench_out
LOG=/workspace/chain_T4_resume.log
cd "$S" || exit 1

curl -s -m 5 http://127.0.0.1:8188/system_stats >/dev/null || { echo "ComfyUI 未在线（先 bash /workspace/start_comfy_T4.sh）"; exit 1; }

step() { local n=$1; shift
  echo "=== [$(date -u +%H:%M:%S)] START $n" >> "$LOG"
  "$@" >> "$LOG" 2>&1
  echo "=== [$(date -u +%H:%M:%S)] END $n rc=$?" >> "$LOG"
}

echo "resume begin $(date -u)" > "$LOG"

step "wai standard" python3 -u run_benchmark.py --profile T4 --tier standard \
  --models sdxl_wai_illustrious --out "$OUT"

step "krea_dev standard" python3 -u run_benchmark.py --profile T4 --tier standard \
  --models flux1_krea_dev --out "$OUT"

# 清理失败/无图记录（保留审计副本）
python3 - <<'PY'
import json,csv,os
p='/workspace/bench_out/T4/records.jsonl'
rows=[json.loads(l) for l in open(p)]
bad=[r for r in rows if r.get('error') or not r.get('image_path') or not os.path.exists(os.path.join('/workspace/bench_out',r['image_path']))]
ok=[r for r in rows if r not in bad]
if bad:
    with open('/workspace/bench_out/T4/records_failed_quarantine.jsonl','a') as f:
        for r in bad: f.write(json.dumps(r,ensure_ascii=False)+'\n')
    with open(p,'w') as f:
        for r in ok: f.write(json.dumps(r,ensure_ascii=False)+'\n')
    with open('/workspace/bench_out/T4/records.csv','w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(ok[0])); w.writeheader()
        for r in ok: w.writerow({k:(json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v) for k,v in r.items()})
print('清理',len(bad),'条，保留',len(ok))
PY

python3 make_report.py --out "$OUT" >> "$LOG" 2>&1
python3 /workspace/bench_out/gen_dashboard.py >> "$LOG" 2>&1
echo "RESUME_DONE $(date -u)" >> "$LOG"
