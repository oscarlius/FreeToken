set -euo pipefail
r=/data2/_shared/runs/ft_rounds/E2-R027-diagnostic-T17
find "$r" -type f -name '*.pt' -printf '%P\n' | sort
printf '%s\n' '--- diagnostic keys ---'
/data2/FreeToken/venv/bin/python - <<'PY'
import json
p='/data2/_shared/runs/ft_rounds/E2-R027-diagnostic-T17/diagnostic_batch55.json'
x=json.load(open(p))
print(x.keys())
for k,v in x.items():
 if isinstance(v,dict):print(k,v.keys())
PY