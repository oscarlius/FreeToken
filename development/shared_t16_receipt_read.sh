set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,pathlib,runpy,sys
stage=pathlib.Path('/data2/FreeToken/runs/dev_D14/shared_t16_fddb430c9607')
receipt=stage/'cpu_validation.json'
assert hashlib.sha256(receipt.read_bytes()).hexdigest()=='052b04f48db1edd8632456961e63160e1782bdb8a2579dede626a31a365bb7b1'
sys.path.insert(0,str(stage))
module=runpy.run_path(str(stage/'t16_candidate_launch_shared.py'),run_name='shared_t16_read_only_verifier')
report=module['receipt'](stage)
print(json.dumps({'stage':str(stage),'passed':report['passed'],'source_files':len(report['files']),
 'receipt_sha256':module['sha'](receipt),'log_sha256':report['log_sha256'],
 'test_output':report['test_output'],'gpu_started':report['gpu_started']},indent=2))
PY
