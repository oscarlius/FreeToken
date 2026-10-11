set -euo pipefail
CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib, json, pathlib, subprocess
root=pathlib.Path('/data2/FreeToken')
source=root/'wt/e1r003st'
assert subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()=='326749079e163785b8f2ec92c90be18d74969e6d'
assert not subprocess.check_output(['git','-C',str(source),'status','--porcelain','--untracked-files=no'],text=True).strip()
expected={'state_envelope.py':'d542e7dbb26549f01dd6ae8e8f1d5dd6','logits_probe.py':'e66328421bb9b8ae82af5595f9da942a'}
for name,digest in expected.items():
 data=(source/'scripts'/name).read_bytes()
 assert hashlib.md5(data).hexdigest()==digest
 p=root/'scripts'/name
 assert not p.exists() and not p.is_symlink()
for name,digest in expected.items():
 p=root/'scripts'/name
 with p.open('xb') as f: f.write((source/'scripts'/name).read_bytes())
 assert hashlib.md5(p.read_bytes()).hexdigest()==digest
 print('D03_CANDIDATE_CLI_MD5',name,digest)
 subprocess.run([str(root/'venv/bin/python'),str(p),'--help'],check=True,stdout=subprocess.DEVNULL)
print('D03 candidate CLIs synchronized; GPU/default gates remain pending')
PY
