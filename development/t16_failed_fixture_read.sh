set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,pathlib,re
root=pathlib.Path('/data2/_shared/runs/ft_rounds'); result={}
event=re.compile(r'#new-seq: (\d+), #new-token: (\d+), #cached-token: (\d+)')
for rid,batch in [('E2-R019-gate-D06',47),('E2-R021-gate-D14',49)]:
 directory=root/rid; item={'batch':batch,'arms':{},'sources':{}}
 for name in ['PARENT_b'+str(batch),'NEW_b'+str(batch)]:
  arm=directory/name; log=arm/'serve.log'; raw=arm/'d0_prefill.jsonl'
  item['sources'][name]={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (log,raw)}
  rows=[json.loads(x) for x in raw.read_text().splitlines() if x]
  item['arms'][name]={'events':[list(map(int,x)) for x in event.findall(log.read_text())],
                      'rows':[{k:r[k] for k in ('chunk','h2d_bytes','d2d_bytes','seg_reason','t_start','t_end','reqs')} for r in rows]}
 result[rid]=item
print(json.dumps(result,sort_keys=True))
PY
