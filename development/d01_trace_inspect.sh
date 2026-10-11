set -eu
/data2/FreeToken/venv/bin/python - <<'PY'
import json
from pathlib import Path
for filename in ('/data2/_shared/runs/ft_rounds/E1-R003/trace.json', '/data2/_shared/runs/ft_rounds/E1-R003-v2/trace.json'):
    doc = json.loads(Path(filename).read_text())
    print(filename, 'keys=', list(doc), 'meta=', doc.get('meta'))
    for key, value in doc.items():
        if isinstance(value, list):
            print(key, 'count=', len(value), 'first_keys=', list(value[0]) if value and isinstance(value[0], dict) else '')
            if value and isinstance(value[0], dict):
                print('first_scalars=', {k:v for k,v in value[0].items() if isinstance(v, (str,int,float,bool)) and len(str(v)) < 200})
PY
