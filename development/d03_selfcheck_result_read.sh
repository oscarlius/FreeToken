set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,pathlib,re,subprocess
root=pathlib.Path('/data2/FreeToken/runs/dev_D03/gpu_selfcheck_c30ae0d_urlfix')
for name in ['selfcheck.json','selfcheck_error.json','g5_logits_compare.log','candidate_boundary/terminal_binding.json']:
    p=root/name
    if not p.exists():continue
    print('D03_RESULT_FILE',name,'SHA256',hashlib.sha256(p.read_bytes()).hexdigest())
    lines=p.read_text().splitlines()
    doc=json.loads(lines[-1]) if name.endswith('.log') else json.loads(p.read_text())
    print(json.dumps(doc,ensure_ascii=False))
binding=root/'candidate_boundary/terminal_binding.json'
if binding.exists():
    doc=json.loads(binding.read_text()); p=pathlib.Path(doc['path'])
    token=json.loads(p.read_text())
    print('D03_G4_TERMINAL_SUMMARY',json.dumps({k:token.get(k) for k in ['schema','uid','pid','prompt_length','finish_reason','matched_stop','prompt_ids_sha256_int32le','generated_ids_sha256_int32le']}),
          'generated_length',len(token['generated_ids']),'sha256',hashlib.sha256(p.read_bytes()).hexdigest())
rounds=pathlib.Path('/data2/_shared/runs/ft_rounds')
numbers=[int(m.group(1)) for p in rounds.iterdir() if (m:=re.fullmatch(r'batch(\d+)\.log',p.name))]
print('NEXT_BATCH',max(numbers)+1)
print('ROUND_EXISTS',json.dumps({rid:(rounds/rid).exists() for rid in ['E2-R002-gate-D03','E2-R014','E2-R012','E2-R013','E2-R010','E2-R011']}))
PY
