set -euo pipefail
PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,pathlib,subprocess
stage=pathlib.Path('/data2/FreeToken/runs/dev_D06/t16_full_tail_launcher_7e1c05a_289327f')
source=stage/'t16_candidate_launch_full_tail.py'
expected='7e1c05a79b856b6a99c3f8d9422afd7013b9ef0215c78e17427d205f78384dcf'
log_sha='6d70cd37dcaedef1cfdfac0ffe72fa484353c889da62578bc67bd0be7a237e1f'
if source.is_symlink() or hashlib.sha256(source.read_bytes()).hexdigest()!=expected:
 raise ValueError('reviewed full-tail launcher changed')
report=json.loads((stage/'cpu_validation.json').read_text())
if (report['files']['t16_candidate_launch_full_tail.py']!=expected
    or report['log_sha256']!=log_sha
    or hashlib.sha256((stage/'cpu_validation.log').read_bytes()).hexdigest()!=log_sha
    or len(report['steps'])!=3 or any(step['returncode'] for step in report['steps'])
    or report['gpu_started'] is not False):
 raise ValueError('exact full-tail launcher Linux proof changed')
prior=pathlib.Path('/proc/3715805/stat')
if prior.exists() and prior.read_text().rpartition(') ')[2].split()[0]!='Z':
 raise ValueError('previous development selfcheck is still live; do not restart it')
subprocess.run(['/data2/FreeToken/venv/bin/python','-u',str(source),'--case','D06'],check=True,timeout=180)
PY
