set -euo pipefail
directory=/data2/FreeToken/runs/plan_batches
for name in t03_runner.py state_test_runner.py t07_runner.py t08_runner.py t09_runner.py e2_launch.py t03_summarize.py; do
    /data2/FreeToken/venv/bin/python "$directory/$name" --self-test
done
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,pathlib
d=pathlib.Path('/data2/FreeToken/runs/plan_batches')
names=['e2_runtime.py','t03_runner.py','state_test_runner.py','t07_runner.py','t08_runner.py','t09_runner.py','e2_launch.py','t03_summarize.py']
print(json.dumps({n:hashlib.md5((d/n).read_bytes()).hexdigest() for n in names}))
PY
