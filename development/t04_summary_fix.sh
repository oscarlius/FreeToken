set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,pathlib,subprocess
d=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R002')
source=pathlib.Path('/data2/FreeToken/runs/plan_batches/state_measurement_summarize.py')
assert hashlib.md5(source.read_bytes()).hexdigest()=='4cc3e8c951649009e5f6837165088ac9'
subprocess.run(['/data2/FreeToken/venv/bin/python',str(source),'--self-test'],check=True)
archived=d/'state_measurement_summarize_v2.py'
with archived.open('xb') as f:
    f.write(source.read_bytes())
subprocess.run(['/data2/FreeToken/venv/bin/python',str(archived),'T04',str(d),
                '--out',str(d/'t04_summary_v2.json'),'--metadata-out',str(d/'measurements_v2.json')],check=True)
old=json.loads((d/'t04_summary.json').read_text())
new=json.loads((d/'t04_summary_v2.json').read_text())
for name in ['eq_B_vs_R4096.txt','eq_R4096_vs_R8192.txt','eq_R4096_vs_RLM.txt']:
    assert old['diagnostics'][name]==new['diagnostics'][name],name
    print(name,json.dumps(new['diagnostics'][name],ensure_ascii=False))
assert new['diagnostics']['comparability_gate']['observed']==12
assert new['results']['comparable_length_records']==36
print('results',json.dumps(new['results'],ensure_ascii=False))
print('comparability_gate',json.dumps(new['diagnostics']['comparability_gate'],ensure_ascii=False))
for name in ['state_measurement_summarize_v2.py','t04_summary_v2.json','measurements_v2.json']:
    print(name,hashlib.sha256((d/name).read_bytes()).hexdigest())
print('T04 DERIVED SUMMARY V2 READY; ORIGINAL OUTPUTS AND RAW STATE EVIDENCE RETAINED')
PY
