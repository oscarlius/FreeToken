set -euo pipefail
CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,pathlib,subprocess,sys
out=pathlib.Path('/data2/FreeToken/runs/dev_D03/phase2_tools_c30ae0d')
hashes={
 't04_logits_phase2.py':'c61e749ccd45ff04846641e337a37b10b207f2f50919055e309538b353cd52d1',
 't10_raw_phase1.py':'b86900137665b97817d1a8e5620c2e250ef1cf61bc11698e432b6a9f75d07d52',
 't10_logits_stage2.py':'fe883d11c8dcf2e37ceac97597e4cbad848cc1cb54e449135fecff15ecafe829',
 'tests/test_phase2_guards.py':'d5c201438b16a17957a5784ec16a33a11155c5f62f6a5ed8359aaaf07574a009',
}
for name,expected in hashes.items():
    path=out/name;actual=hashlib.sha256(path.read_bytes()).hexdigest()
    assert actual==expected,(name,actual)
    print('PHASE2_DELIVERY_SHA256',name,actual)
subprocess.run([sys.executable,'-m','py_compile',*[str(out/name) for name in hashes]],check=True)
for name in list(hashes)[:3]: subprocess.run([sys.executable,str(out/name),'--self-test'],check=True)
log=out/'cpu_guards.log'
with log.open('x') as f:
    result=subprocess.run([sys.executable,'-m','pytest','--noconftest',str(out/'tests/test_phase2_guards.py'),'-q'],
                          cwd=out,stdout=f,stderr=subprocess.STDOUT)
print(log.read_text())
assert result.returncode==0
record={'candidate_commit':'c30ae0d7003c3bbbf56867ce74da797332fa7ed5','tool_sha256':hashes,
        'cpu_log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'reviewer':'/root/d00_audit',
        'independent_code_review':'PASS','gpu_measurement_status':'not_started'}
with (out/'delivery.json').open('x') as f: json.dump(record,f,indent=2);f.write('\n')
print('PHASE2_SERVER_CPU_DELIVERY_PASS')
PY
