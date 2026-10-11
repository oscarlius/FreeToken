set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import json,pathlib,re
r=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R001')
a=r/'A_cut_on_p1'
for p in sorted(a.glob('*')):
    if p.is_file():print(p.name,p.stat().st_size)
for p in a.rglob('d0_prefill.jsonl'):
    for line in p.read_text().splitlines():
        row=json.loads(line)
        reqs=row.get('requests',row.get('reqs',[]))
        if any(q.get('rid',q.get('uid'))==26 for q in reqs):
            print('D0 REQUEST26',json.dumps({k:v for k,v in row.items() if k in ['reqs','requests','idx','chunk','chunk_idx','seg_reason','t_start','t_end','new_tokens','cached_tokens','prompt_tokens']}))
lines=(a/'serve.log').read_text(errors='replace').splitlines()
for i,line in enumerate(lines):
    if '26:' in line or 'anchor_snapshots' in line:print('LOG', '\n'.join(lines[i:i+3]))
for p in a.glob('tax*.json'):
    print(p.name,p.read_text()[:3500])
for p in a.glob('P*.json'):print(p.name,p.read_text())
PY
