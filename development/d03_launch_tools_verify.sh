set -euo pipefail
CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,pathlib,subprocess,sys
root=pathlib.Path('/data2/FreeToken/runs/dev_D03')
hashes={'d03_phase2_launch.py':'6c403cc8ea2c8719c22c8a6be86de23ad266d138d31e5af63fcb02dcb2a588fe',
        'd03_t16_prepare.py':'802e5a80f4e05b5fd863289a0a55009afa1059ab72390e77b1fdfb9823c440da'}
for name,expected in hashes.items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==expected,name
subprocess.run([sys.executable,'-m','py_compile',*[str(root/name) for name in hashes]],check=True)
subprocess.run([sys.executable,str(root/'d03_t16_prepare.py'),'--self-test'],check=True)
subprocess.run([sys.executable,str(root/'d03_phase2_launch.py'),'--help'],check=True)
subprocess.run(['bash','-n',str(root/'d03_t16_launch.sh')],check=True)
hashes['d03_t16_launch.sh']=hashlib.sha256((root/'d03_t16_launch.sh').read_bytes()).hexdigest()
with (root/'reviewed_launch_tools.json').open('x') as f:
    json.dump({'sha256':hashes,'reviewer':'/root/d00_audit','code_review':'PASS','runtime_measurements':'pending'},f,indent=2);f.write('\n')
print('D03_REVIEWED_LAUNCH_TOOLS_CPU_PASS',json.dumps(hashes))
PY
