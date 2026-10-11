set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,pathlib,subprocess,tarfile
stage=pathlib.Path('/data2/FreeToken/runs/dev_D06/cpu_23f2e2c')
repo=stage/'repo'
archive=stage/'d06_server_cpu_e2e552b30920.tar'
assert hashlib.sha256(archive.read_bytes()).hexdigest()=='3f0bf504cf8562931f5621e85c0078211ee0448ac2c33b5a0f28e4240bdcd660'
assert subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()=='23f2e2caa3395837c9474735ffc83321f3b9b5a1'
with tarfile.open(archive) as tf:
    manifest=json.loads(tf.extractfile('MANIFEST.json').read())
    assert set(tf.getnames())=={'MANIFEST.json',*manifest['files']}
    for name,digest in manifest['files'].items():
        assert not pathlib.PurePosixPath(name).is_absolute() and '..' not in pathlib.PurePosixPath(name).parts
        blob=tf.extractfile(name).read()
        assert hashlib.sha256(blob).hexdigest()==digest
        dest=repo/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(blob)
log=stage/'d06_server_cpu_e2e552b30920.log'
assert not log.exists()
cmd=['/data2/FreeToken/venv/bin/python','-m','pytest','-q','tests/scheduler/test_dev_pause.py','tests/server/test_dev_pause_api.py','tests/server/test_generation_accounting.py','tests/server/test_message_wire.py']
with log.open('xb') as output:
    result=subprocess.run(cmd,cwd=repo,stdout=output,stderr=subprocess.STDOUT)
report={'scope':'Linux CPU only; CUDA_VISIBLE_DEVICES empty; no model service','archive_sha256':'3f0bf504cf8562931f5621e85c0078211ee0448ac2c33b5a0f28e4240bdcd660','manifest':manifest,'command':cmd,'returncode':result.returncode,'log':str(log),'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
receipt=stage/'d06_server_cpu_e2e552b30920.json'
with receipt.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2);f.write('\n')
print(log.read_text()[-10000:])
print(json.dumps({'report':str(receipt),'returncode':result.returncode,'log_sha256':report['log_sha256']}))
raise SystemExit(result.returncode)
PY
