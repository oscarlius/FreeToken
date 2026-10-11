set -euo pipefail
CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python - <<'PY'
import datetime, hashlib, importlib.util, json, os, pathlib, socket, subprocess
d = pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R017').resolve(strict=True)
stage = pathlib.Path('/data2/FreeToken/runs/dev_D03/r017_close_inputs')
helper = pathlib.Path('/data2/FreeToken/runs/dev_D03/phase2_close_r017_a52e39e/development/d03_phase2_prepare_r017.py')
closer = pathlib.Path('/data2/FreeToken/runs/plan_batches/initial_measurement_close.py')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
helper_bytes, closer_bytes = helper.read_bytes(), closer.read_bytes()
assert hashlib.sha256(helper_bytes).hexdigest() == 'a52e39e95cf002aa3909b860ff084ff7c85f3d91261d1c75baa9e74a38671581'
assert hashlib.sha256(closer_bytes).hexdigest() == 'dbfecaee0c31fa1a7057a922e2c8e09944cdb8c51f22fe1e6fb6b8e6b3329835'
review_bytes = (stage / 'review_raw_measurements.json').read_bytes()
assert hashlib.sha256(review_bytes).hexdigest() == '292a8262f211da3dc758bff786b7c04f7055388bb7336f1efc7e599e31b2d4ed'
review = json.loads(review_bytes)
assert (review['rid'], review['batch'], review['verdict']) == (d.name, 44, 'PASS')
assert review['integrity']['run_manifest_sha256'] == sha(d / 'RUN_MANIFEST.sha256') == '10f57ef07f85c772e8d01063b47776fb2d4d8f84e9654ea5dca962f0bd257b94'
assert review['integrity']['admission_sha256'] == sha(d / 'admission.json') == 'e3efca3828bdb87eb8f073ed5ea17feda73130c247a549da979dd53b105e09a3'
assert review['integrity']['status_sha256'] == sha(d / 'status_batch44.json') == '0f5aa67254e03831f4ba924d43bfdff06989f7daa28c1879a776fbc15009b382'
for pid in [2786369, 2786510, 2786758, 2816854, 2817086, 2847692, 2847884]:
    proc = pathlib.Path(f'/proc/{pid}/stat')
    assert not proc.exists() or proc.read_text().partition(') ')[2][0] == 'Z', pid
assert not pathlib.Path('/data2/_shared/gpu.lock').exists()
with socket.socket() as sock:
    assert sock.connect_ex(('127.0.0.1', 8095)) != 0
used = subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],text=True).strip()
assert int(used) <= 8, used
for name in ('round.json','round_history','MANIFEST.sha256','initial_metadata.json','review_raw_measurements.json','poststop_proof.json','d03_phase2_prepare_r017.py','initial_measurement_close.py'):
    assert not (d / name).exists(), name
for name, data in {'review_raw_measurements.json': review_bytes, 'd03_phase2_prepare_r017.py': helper_bytes, 'initial_measurement_close.py': closer_bytes}.items():
    with (d / name).open('xb') as stream:
        stream.write(data)
proof = {'recorded_at': datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z'),
         'rid': d.name, 'batch':44, 'all_owned_batch_service_engine_pids_terminal': True,
         'owned_pids':[2786369,2786510,2786758,2816854,2817086,2847692,2847884],
         'port8095_free':True,'shared_lock_absent':True,'gpu_memory_mib':int(used)}
with (d / 'poststop_proof.json').open('x',encoding='utf-8') as stream:
    json.dump(proof,stream,indent=2); stream.write('\n')
from types import ModuleType
module = ModuleType('reviewed_r017_metadata'); module.__file__ = str(helper)
exec(compile(helper_bytes,str(helper),'exec'),module.__dict__)
result = module.prepare(d,44,d / 'review_raw_measurements.json')
result['poststop_sha256'] = sha(d / 'poststop_proof.json')
result['metadata_sha256'] = sha(d / 'initial_metadata.json')
result['raw_review_sha256'] = sha(d / 'review_raw_measurements.json')
result['state'] = 'initial_metadata_prepared_pending_independent_review'
print(json.dumps(result,sort_keys=True))
PY
