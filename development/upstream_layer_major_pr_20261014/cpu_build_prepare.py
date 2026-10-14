"""Prepare only the isolated upstream contribution build; no GPU/service actions."""
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "ops", HERE.parent / "r067c_retry2_production_control_20261009/ssh_ops.py"
)
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)
client = ops.connect()
try:
    ops.run(client, r'''
import datetime, json, os, pathlib, subprocess
root = pathlib.Path('/data2/FreeToken/development/upstream_layer_major_pr_20261014')
env = os.environ.copy()
env.update(CUDA_VISIBLE_DEVICES='', CUDA_HOME='/usr/local/cuda-13.0',
           PATH='/usr/local/cuda-13.0/bin:' + env['PATH'], MAX_JOBS='2',
           OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
launch = root / 'native_build_launch.json'
if launch.exists():
    raise RuntimeError('Build already has a launch receipt; inspect before retrying')
argv = ['nice', '-n', '19', 'ionice', '-c', '3', str(root/'main-venv/bin/python'),
        'setup.py', 'build_ext', '--inplace']
with (root/'native_build.log').open('xb') as log:
    child = subprocess.Popen(argv, cwd=root/'candidate_63858fa', env=env,
                             stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
ticks = pathlib.Path(f'/proc/{child.pid}/stat').read_text().split()[21]
receipt = {'at': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
           'pid': child.pid, 'start_ticks': ticks, 'argv': argv,
           'cuda_visible_devices': '', 'production_untouched': True}
launch.write_text(json.dumps(receipt, indent=2)+'\n')
print(json.dumps(receipt, indent=2))
prod = pathlib.Path('/data2/FreeToken/runs/production/RELEASE-E3-20261012-02')
print('Production package top-level files:', sorted(p.name for p in prod.iterdir()))
print('Production package scripts:', [str(p.relative_to(prod)) for p in prod.rglob('*.py')][:30])
''')
    sftp = client.open_sftp()
    sftp.get('/data2/FreeToken/development/upstream_layer_major_pr_20261014/native_build_launch.json',
             str(HERE/'native_build_launch.json'))
    sftp.close()
finally:
    client.close()
