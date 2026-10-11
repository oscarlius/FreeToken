set -euo pipefail
CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python - <<'PY'
import datetime, hashlib, json, pathlib, socket, subprocess
d = pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R011')
s = json.loads((d / 'status_batch40.json').read_text())
assert (s['rid'], s['card'], s['batch'], s['batch_pid']) == (d.name, 'T11', 40, 2569357), s
assert s['state'] == 'complete', s
process = pathlib.Path('/proc/2569357/stat')
assert not process.exists() or process.read_text().partition(') ')[2].startswith('Z')
assert not pathlib.Path('/data2/_shared/gpu.lock').exists()
with socket.socket() as sock:
    assert sock.connect_ex(('127.0.0.1', 8095)) != 0
used = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'], text=True).strip()
assert int(used) <= 8, used
source = pathlib.Path('/data2/FreeToken/runs/plan_batches')
expected = {
    'state_measurement_summarize.py': 'd1c0c8bb82ab45d9a3f4339ceb592da660d6486aae600a37a22cce491de311af',
    'initial_measurement_close.py': 'dbfecaee0c31fa1a7057a922e2c8e09944cdb8c51f22fe1e6fb6b8e6b3329835',
}
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
for name, digest in expected.items():
    assert sha(source / name) == digest, name
for name in [*expected, 'poststop_proof.json', 'measurements.json', 'initial_metadata.json']:
    assert not (d / name).exists(), name
proof = {
    'recorded_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'status': s, 'owned_batch_gone': True, 'port8095_free': True,
    'gpu_memory_mib': int(used), 'shared_lock_absent': True,
}
with (d / 'poststop_proof.json').open('x') as f:
    json.dump(proof, f, indent=2)
for name in expected:
    with (d / name).open('xb') as f:
        f.write((source / name).read_bytes())
subprocess.run(['/data2/FreeToken/venv/bin/python', str(d / 'state_measurement_summarize.py'), 'T11', str(d),
                '--out', str(d / 'measurements.json'), '--metadata-out', str(d / 'initial_metadata.json')], check=True)
for name in ['measurements.json', 'initial_metadata.json', 'poststop_proof.json']:
    print(name, sha(d / name))
summary = json.loads((d / 'measurements.json').read_text())
print('T11_SUMMARY', json.dumps(summary, ensure_ascii=False, allow_nan=False))
print('T11 SUMMARY PREPARED; independent metadata review and formal closure pending')
PY
