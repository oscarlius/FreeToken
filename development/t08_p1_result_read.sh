set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,pathlib
d=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R009')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
values=json.loads((d/'P1/measurements.json').read_text())
print('T08_P1_MEASUREMENTS',json.dumps(values,ensure_ascii=False))
for name in ['agent_coldfirst','agent_warm','agent_edit']:
 doc=json.loads((d/'P1'/f'{name}.json').read_text()); rows=doc['rounds']; vals=[r['ttft_any_s'] for r in rows]
 print('T08_P1_ALL12',json.dumps({'arm':name,'n':len(rows),'first':vals[0],'sum':sum(vals),'mean':sum(vals)/len(vals),'max':max(vals),
 'prompt_total':sum(r['prompt_tokens'] for r in rows),'cached_total':sum(r['cached_tokens'] for r in rows),'recomputed_total':sum(r['recomputed_tokens'] for r in rows),
 'dry_count':sum(r['dry_run'] for r in rows)},ensure_ascii=False))
print('T08_P1_BATCH_LOG_SHA256',sha(d.parent/'batch36.log'))
print('T08_P1_CLOSED_AT',json.loads((d/'round.json').read_text())['closed_at'])
PY
