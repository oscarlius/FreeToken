set -euo pipefail
PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib, json, pathlib, subprocess
stage = pathlib.Path('/data2/FreeToken/runs/dev_D03/t16_launcher_241cbcc')
source = stage / 't16_candidate_launch.py'
if source.is_symlink() or hashlib.sha256(source.read_bytes()).hexdigest() != '241cbccc21ee34fe61e64af48530117b8cf243b979ad1d577563f77d2bee0d0e':
    raise ValueError('final launcher differs from reviewed bytes')
report = json.loads((stage/'cpu_validation.json').read_text())
log = stage/'cpu_validation.log'
expected = '58620a3490ddf3cb7091b8f0f6c4a1913b112845365ee8eb92b0b189fb15437d'
if (report['files']['t16_candidate_launch.py'] != '241cbccc21ee34fe61e64af48530117b8cf243b979ad1d577563f77d2bee0d0e'
        or report['log_sha256'] != expected or hashlib.sha256(log.read_bytes()).hexdigest() != expected
        or len(report['steps']) != 2 or any(step['returncode'] for step in report['steps'])):
    raise ValueError('final launcher exact-source Linux CPU proof changed')
source.chmod(0o444)
subprocess.run(['/data2/FreeToken/venv/bin/python','-u',str(source),'--case','D06'],check=True,timeout=180)
PY
