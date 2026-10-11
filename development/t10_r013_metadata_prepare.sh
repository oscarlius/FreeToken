set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import datetime, hashlib, json, os, pathlib, socket, subprocess
from types import ModuleType
d = pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R013').resolve(strict=True)
stage = pathlib.Path('/data2/FreeToken/runs/dev_D03/r013_close_inputs_ab48676')
helper = pathlib.Path('/data2/FreeToken/runs/dev_D03/phase2_close_r017_a52e39e/development/d03_phase2_prepare_r017.py')
closer = pathlib.Path('/data2/FreeToken/runs/plan_batches/initial_measurement_close.py')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
helper_bytes, closer_bytes = helper.read_bytes(), closer.read_bytes()
if hashlib.sha256(helper_bytes).hexdigest() != 'a52e39e95cf002aa3909b860ff084ff7c85f3d91261d1c75baa9e74a38671581':
    raise ValueError('reviewed metadata preparer changed')
if hashlib.sha256(closer_bytes).hexdigest() != 'dbfecaee0c31fa1a7057a922e2c8e09944cdb8c51f22fe1e6fb6b8e6b3329835':
    raise ValueError('reviewed initial closer changed')
review_bytes = (stage / 'review_raw_measurements.json').read_bytes()
if hashlib.sha256(review_bytes).hexdigest() != 'ab48676fb3f2660959527f9c8e589206ef822816378e9c6d67d1446e2cd6c8a6':
    raise ValueError('independent raw review changed')
review = json.loads(review_bytes)
if (review['rid'], review['batch'], review['verdict']) != (d.name, 45, 'PASS'):
    raise ValueError('raw review identity is invalid')
for name, digest in review['integrity'].items():
    if sha(d / name) != digest:
        raise ValueError('reviewed producer artifact changed: ' + name)
module = ModuleType('r013_reviewed_metadata'); module.__file__ = str(helper)
exec(compile(helper_bytes,str(helper),'exec'),module.__dict__)
module.assert_owned(d)
status, _ = module.validate_status(d,module.SPECS[d.name],45)
_metadata, arms, _results, _nonfinite, _files = module.validate_measurement(d,module.SPECS[d.name])
pids = {status['batch_pid']}
pgids = set()
for arm, record in arms.items():
    pids.add(record['owned_service_pid']); pgids.add(record['owned_service_pgid'])
    capture = json.loads((d / arm / 'capture.json').read_text())
    pids.add(capture['capture_pid'])
if not all(module.terminal(pid) for pid in pids):
    raise ValueError('owned batch, service or capture PID remains live')
for proc in pathlib.Path('/proc').iterdir():
    if not proc.name.isdigit():
        continue
    try:
        fields = proc.joinpath('stat').read_text().partition(') ')[2].split()
        if int(fields[2]) in pgids and fields[0] != 'Z':
            raise ValueError('owned service process group remains live: ' + proc.name)
    except FileNotFoundError:
        pass
if pathlib.Path('/data2/_shared/gpu.lock').exists():
    raise ValueError('GPU lock remains held before poststop proof')
with socket.socket() as sock:
    if sock.connect_ex(('127.0.0.1',8095)) == 0:
        raise ValueError('8095 remains occupied before poststop proof')
used = subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],text=True).strip()
if int(used) > 8:
    raise ValueError('GPU not released before poststop proof')
new_files = {'review_raw_measurements.json':review_bytes,
             'd03_phase2_prepare_r017.py':helper_bytes,'initial_measurement_close.py':closer_bytes}
for name in (*new_files,'round.json','round_history','MANIFEST.sha256','initial_metadata.json','poststop_proof.json'):
    if (d / name).exists():
        raise ValueError('initial metadata artifact already exists: ' + name)
for name, data in new_files.items():
    with (d / name).open('xb') as stream:
        stream.write(data)
proof = {'recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
         'rid':d.name,'batch':45,'all_owned_batch_service_engine_pids_terminal':True,
         'owned_pids':sorted(pids),'owned_service_pgids':sorted(pgids),'all_owned_groups_terminal':True,
         'port8095_free':True,'shared_lock_absent':True,'gpu_memory_mib':int(used)}
with (d/'poststop_proof.json').open('x') as stream:
    stream.write(json.dumps(proof,indent=2)+'\n')
result = module.prepare(d,45,d/'review_raw_measurements.json')
result.update(poststop_sha256=sha(d/'poststop_proof.json'), metadata_sha256=sha(d/'initial_metadata.json'),
              raw_review_sha256=sha(d/'review_raw_measurements.json'),state='initial_metadata_prepared_pending_independent_review')
print(json.dumps(result,sort_keys=True))
PY
