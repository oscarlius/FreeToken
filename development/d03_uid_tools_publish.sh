set -euo pipefail
CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,pathlib,subprocess,sys
root=pathlib.Path('/data2/FreeToken')
dev=root/'runs/dev_D03'
candidate=root/'wt/e1r003st'
md5=lambda p:hashlib.md5(p.read_bytes()).hexdigest()
assert subprocess.check_output(['git','-C',str(candidate),'rev-parse','HEAD'],text=True).strip()=='c30ae0d7003c3bbbf56867ce74da797332fa7ed5'
assert not subprocess.check_output(['git','-C',str(candidate),'status','--porcelain','--untracked-files=no'],text=True).strip()
assert md5(dev/'d03_gpu_selfcheck.py')=='e19337d39e8c8352d1a14da5604cbf0d'
assert md5(dev/'d03_gpu_selfcheck_c30ae0d.py')=='127d0f6108f6a387ae031be5df228c2a'
assert md5(dev/'gate_tools_c30ae0d/t16_runner.py')=='00661195a6df1a6f6456fc938c489381'
global_cli=root/'scripts/state_envelope.py'
assert md5(global_cli)=='d542e7dbb26549f01dd6ae8e8f1d5dd6'
assert md5(candidate/'scripts/state_envelope.py')=='f95a58a588161f15b2b1efabd1a7b842'
archive=dev/'state_envelope_before_uid_selection.py'
with archive.open('xb') as f: f.write(global_cli.read_bytes())
global_cli.write_bytes((candidate/'scripts/state_envelope.py').read_bytes())
(dev/'d03_gpu_selfcheck.py').write_bytes((dev/'d03_gpu_selfcheck_c30ae0d.py').read_bytes())
for path in [global_cli,dev/'d03_gpu_selfcheck.py',dev/'gate_tools_c30ae0d/t16_runner.py']:
 print('D03_CURRENT_TOOL_MD5',path.name,md5(path))
for path in [dev/'d03_gpu_selfcheck.py',dev/'gate_tools_c30ae0d/t16_runner.py']:
 subprocess.run([sys.executable,str(path),'--self-test'],check=True)
subprocess.run([sys.executable,str(global_cli),'--help'],check=True,stdout=subprocess.DEVNULL)
print('D03 tools match current committed candidate; original versions retained')
PY
