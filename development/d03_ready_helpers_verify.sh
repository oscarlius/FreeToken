set -euo pipefail
CUDA_VISIBLE_DEVICES='' PHASE2_REPO_ROOT=/data2/FreeToken /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,pathlib,subprocess,sys
out=pathlib.Path('/data2/FreeToken/runs/dev_D03/phase2_tools_c30ae0d_ready')
hashes={
 'd03_gpu_selfcheck.py':'4cf751a93457ef28a88fc175004c86d12130b84943193cb43c55254c2e0fb453',
 't04_logits_phase2.py':'d7226c466e5922ecc4e80d80dc2b634592e1449538587d3232d4f3b9176723eb',
 't10_raw_phase1.py':'b86900137665b97817d1a8e5620c2e250ef1cf61bc11698e432b6a9f75d07d52',
 't10_logits_stage2.py':'d6e01dee6fd39e59976f5b9f90b798b27dded4a7e516bb97debe10e237c2e2e9',
 'tests/test_phase2_guards.py':'4a62066b345ee741e48da2da15290fd5ed58b0de7c4f43f9ca084c47d8a00d4f',
}
for name,expected in hashes.items():
    path=out/name;actual=hashlib.sha256(path.read_bytes()).hexdigest()
    assert actual==expected,(name,actual)
    print('READY_HELPER_SHA256',name,actual)
writer=pathlib.Path('/data2/FreeToken/scripts/round_json_append.py')
assert hashlib.md5(writer.read_bytes()).hexdigest()=='88178a9a3c83dec204e90e6dcf8c4db9'
subprocess.run([sys.executable,'-m','py_compile',*[str(out/name) for name in hashes]],check=True)
for name in list(hashes)[:4]: subprocess.run([sys.executable,str(out/name),'--self-test'],check=True)
log=out/'cpu_guards.log'
with log.open('x') as f:
    result=subprocess.run([sys.executable,'-m','pytest','--noconftest',str(out/'tests/test_phase2_guards.py'),'-q'],
                          cwd=out,stdout=f,stderr=subprocess.STDOUT)
print(log.read_text());assert result.returncode==0
assert (out/'d03_gpu_selfcheck.py').read_bytes()==(out.parent/'d03_gpu_selfcheck.py').read_bytes()
record={'candidate_commit':'c30ae0d7003c3bbbf56867ce74da797332fa7ed5','tool_sha256':hashes,
        'cpu_log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'cpu_guards':'PASS',
        'gpu_measurement_status':'not_started','writer_md5':'88178a9a3c83dec204e90e6dcf8c4db9',
        'selfcheck_output':'/data2/FreeToken/runs/dev_D03/gpu_selfcheck_c30ae0d_urlfix'}
with (out/'delivery.json').open('x') as f: json.dump(record,f,indent=2);f.write('\n')
print('READY_HELPERS_SERVER_CPU_PASS')
PY
