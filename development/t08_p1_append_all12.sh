set -euo pipefail
CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,pathlib,subprocess,sys
root=pathlib.Path('/data2/FreeToken')
d=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R009')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(d/'round.json')=='44778560e9d62cfcb4e9ebdc4b4e50cc0f54d0bdc8051b45b6db4d2a11cdf137'
assert sha(d/'MANIFEST.sha256')=='d0b8ef2a7597c438fb0cda68fd89d30d287280b6f9c965d7ef95007cf68c4fca'
old=(d/'round.json').read_bytes()
totals={}; sources={}
for name in ['agent_coldfirst','agent_warm','agent_edit']:
 path=d/'P1'/f'{name}.json'; rows=json.loads(path.read_text())['rounds']
 assert len(rows)==12 and {r['round'] for r in rows}==set(range(12))
 assert all(r['error'] is None and r['dry_run'] is False for r in rows)
 times=[r['ttft_any_s'] for r in rows]
 totals[name]={'n':12,'sum_ttft_s':sum(times),'mean_ttft_s':sum(times)/12,'max_ttft_s':max(times),
 'first_request_ttft_s':times[0],'prompt_total':sum(r['prompt_tokens'] for r in rows),
 'cached_total':sum(r['cached_tokens'] for r in rows),'recomputed_total':sum(r['recomputed_tokens'] for r in rows)}
 sources[name]=sha(path)
patch={'results':{'agent_all12':totals},'diagnostics':{'agent_all12_scope':{
 'definition':'whole 12-request trace, including its first request; original indices1..11 steady measurements remain unchanged',
 'source_sha256':sources}}}
path=root/'runs/dev_D04/t08_p1_all12_append.json'
with path.open('x',encoding='utf-8') as f: json.dump(patch,f,indent=2);f.write('\n')
subprocess.run([sys.executable,str(root/'scripts/round_json_append.py'),str(d),'add','--json',str(path)],check=True)
subprocess.run([sys.executable,str(root/'scripts/round_json_append.py'),str(d),'check'],check=True)
after=json.loads((d/'round.json').read_text())
assert after['results'].pop('agent_all12')==totals
assert after['diagnostics'].pop('agent_all12_scope')==patch['diagnostics']['agent_all12_scope']
assert after==json.loads(old)
assert (d/'round_history/round.v001.json').read_bytes()==old
assert sha(d/'MANIFEST.sha256')=='d0b8ef2a7597c438fb0cda68fd89d30d287280b6f9c965d7ef95007cf68c4fca'
assert all(not p.stat().st_mode&0o222 for p in [d,*d.rglob('*')])
for name in ['round.json','round_history/round.v001.json','round_history/round.v002.json','round_history/SHA256SUMS']:
 print('T08_P1_ALL12_APPEND_SHA256',name,sha(d/name))
print('T08_P1_ALL12_PATCH_SHA256',sha(path))
print('T08 all12 trace totals appended; old results, first-shots, verdict, and manifest preserved')
PY
