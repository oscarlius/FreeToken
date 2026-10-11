set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib, importlib.util, json, pathlib, socket, subprocess
directory = pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R013')
helper = pathlib.Path('/data2/FreeToken/runs/dev_D03/phase2_close_r017_a52e39e/development/d03_phase2_prepare_r017.py')
if hashlib.sha256(helper.read_bytes()).hexdigest() != 'a52e39e95cf002aa3909b860ff084ff7c85f3d91261d1c75baa9e74a38671581':
    raise ValueError('reviewed prepare helper changed')
spec = importlib.util.spec_from_file_location('phase2_validate_only', helper)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.assert_owned(directory)
admission, _ = module.validate_admission(directory, module.SPECS[directory.name], 45)
status, _ = module.validate_status(directory, module.SPECS[directory.name], 45)
manifest_sha, declared = module.verify_manifest(directory)
metadata, arms, values, nonfinite, files = module.validate_measurement(directory, module.SPECS[directory.name])
result_path = directory / 'stage2_results.json'
result = json.loads(result_path.read_text()) if result_path.is_file() else {}
with socket.socket() as sock:
    port_free = sock.connect_ex(('127.0.0.1', 8095)) != 0
summary = {'rid': directory.name, 'batch': 45, 'batch_terminal': module.terminal(status['batch_pid']),
    'metadata_status': metadata['status'], 'manifest_sha256': manifest_sha,
    'manifest_files': len(declared), 'validated_arms': len(arms), 'validated_files': len(files),
    'finite_statistics': values, 'nonfinite_statistics': nonfinite,
    'result_top_keys': sorted(result), 'gpu_lock_present': pathlib.Path('/data2/_shared/gpu.lock').exists(),
    'integrity': {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                  for name in ('admission.json', 'status_batch45.json', 'round_metadata.json',
                               'stage2_results.json', 'RUN_MANIFEST.sha256')},
    'port_8095_free': port_free,
    'gpu_memory_mib': subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],text=True).strip()}
print(json.dumps(summary, allow_nan=False))
PY
