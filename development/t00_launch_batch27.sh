set -euo pipefail
/data2/FreeToken/venv/bin/python /data2/FreeToken/runs/plan_batches/t00_runner.py --self-test
/data2/FreeToken/venv/bin/python /data2/FreeToken/runs/plan_batches/t00_runner.py --batch 27
/data2/FreeToken/venv/bin/python - <<'PY'
import pathlib,re,subprocess
root=pathlib.Path('/data2/_shared/runs/ft_rounds')
assert not (root/'E2-R000').exists()
assert not (root/'batch27.log').exists()
numbers=[int(m.group(1)) for p in root.iterdir() if (m:=re.fullmatch(r'batch(\d+)\.log',p.name))]
assert max(numbers)==26
script=pathlib.Path('/data2/FreeToken/runs/plan_batches/batch27_E2-R000_python.sh')
subprocess.run(['bash','-n',str(script)],check=True)
with (root/'batch27.log').open('x') as stream:
    process=subprocess.Popen(['bash',str(script)],stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
print(f'BATCH_PID={process.pid} LOG={root}/batch27.log',flush=True)
PY
