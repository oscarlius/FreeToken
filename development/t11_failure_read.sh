set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import collections, hashlib, json, pathlib, socket, subprocess
d=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R007')
for rel in ['admission.json','status_batch35.json','failure.json','runner_sha256.txt','batch.sh','S_A_trace/replay.json','S_A_trace/serve_args.txt','S_A_trace/dump/index.jsonl']:
 p=d/rel
 print('ARTIFACT',rel,hashlib.sha256(p.read_bytes()).hexdigest())
 if rel in ['admission.json','failure.json']:
  print(p.read_text())
replay=json.loads((d/'S_A_trace/replay.json').read_text())
row=next(r for r in replay['rounds'] if r.get('round')==7)
print('ROUND7',json.dumps({k:v for k,v in row.items() if k not in ['text','parts']},ensure_ascii=False))
index=[json.loads(l) for l in (d/'S_A_trace/dump/index.jsonl').read_text().splitlines() if l]
print('DUMP_KINDS',json.dumps(dict(collections.Counter(r['kind'] for r in index))))
print('TARGET_INDEX',json.dumps([{k:r.get(k) for k in ['seq','uid','kind','length','note']} for r in index if str(r.get('uid'))=='7']))
log=(d/'S_A_trace/serve.log').read_text(errors='replace').splitlines()
for i,line in enumerate(log):
 if 'resuming req 7 ' in line:
  print('TARGET_SERVE_LINES',i+1,json.dumps(log[max(0,i-2):i+7]))
print('ORIGINAL_BATCHLOG_SHA256',hashlib.sha256(pathlib.Path('/data2/_shared/runs/ft_rounds/batch35.log').read_bytes()).hexdigest())
print('OWNED_BATCH',subprocess.run(['ps','-p','1934776','-o','pid,ppid,stat,etime,args'],capture_output=True,text=True).stdout)
print('CURRENT_GPU',subprocess.run(['nvidia-smi','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader'],capture_output=True,text=True).stdout)
PY
