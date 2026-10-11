set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,pathlib,subprocess,json
root=pathlib.Path('/data2/FreeToken/runs/dev_D03/continuation_cpu_71f93be/repo')
p=root/'python/freetoken/attention/linear.py'
payload=p.read_bytes()
blob=subprocess.check_output(['git','-C',str(root),'show','c30ae0d7003c3bbbf56867ce74da797332fa7ed5:python/freetoken/attention/linear.py'])
assert payload==blob
print(json.dumps({'linear_runtime_sha256':hashlib.sha256(payload).hexdigest(),'linear_equals_c30_git_blob':True,'length':len(payload)}))
PY
