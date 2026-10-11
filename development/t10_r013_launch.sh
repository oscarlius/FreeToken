set -euo pipefail
CUDA_VISIBLE_DEVICES=0 PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,pathlib
from types import ModuleType
path=pathlib.Path('/data2/FreeToken/runs/dev_D03/t10_stage2_r013_from_r017_d231fe0_87bf525/development/d03_t10_r013_launch.py')
source=path.read_bytes()
assert hashlib.sha256(source).hexdigest()=='87bf52558fcfe462f483bc0d7ee4d05b9223b20387730ed51e799b77a6367b27'
parent=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R017')
assert hashlib.sha256((parent/'round.json').read_bytes()).hexdigest()=='88cbfee4e0cd4f0a12570d5231e5f3516a31ac851c59dd10037c6da25f9900c7'
assert hashlib.sha256((parent/'MANIFEST.sha256').read_bytes()).hexdigest()=='68595988896b31b4f08e545b291396cb9cafb45162b965e0edc48bc296316c38'
m=ModuleType('final_r013_launch');m.__file__=str(path);m.__package__=''
exec(compile(source,str(path),'exec'),m.__dict__)
print('T10_R013_LAUNCHED',json.dumps(m.launch(),sort_keys=True))
PY
