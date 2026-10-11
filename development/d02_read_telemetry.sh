set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import collections,json,pathlib
p=pathlib.Path('/data2/FreeToken/runs/dev_D02/gpu_selfcheck_23f2e2c/on_B1')
rows=[json.loads(s) for s in (p/'d0_prefill.jsonl').read_text().splitlines()]
steps=[json.loads(s) for s in (p/'d0_decode_steps.jsonl').read_text().splitlines()]
print(json.dumps({'prefill':[
 {'chunk':r['chunk'],'reason':r['seg_reason'],'new_tokens':sum(q['new_tokens'] for q in r['reqs']),
  'reqs':r['reqs'],'h2d_bytes':r['h2d_bytes'],'d2d_bytes':r['d2d_bytes'],
  'wall_s':r['wall_s'],'layer_entries':len(r['layers']),
  'distinct_layers':len({q['layer'] for q in r['layers']}),'start':r['t_start'],'end':r['t_end']}
 for r in rows], 'decode_bs_hist':dict(collections.Counter(r['bs'] for r in steps)),
 'decode_rids': sorted({q for r in steps for q in r['rids']}),
 'missing_layers': sorted({len(r['missing_per_layer']) for r in steps}),
 'first_step':steps[0]['step'],'last_step':steps[-1]['step']},ensure_ascii=False))
PY
