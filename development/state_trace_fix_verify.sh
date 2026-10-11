set -euo pipefail
cd /data2/FreeToken/runs/plan_batches
/data2/FreeToken/venv/bin/python state_test_runner.py --self-test
/data2/FreeToken/venv/bin/python state_measurement_summarize.py --self-test
/data2/FreeToken/venv/bin/python - <<'PY'
import pathlib,json,hashlib
import state_test_runner as runner
import state_measurement_summarize as summary
root=pathlib.Path('/data2/_shared/runs/ft_rounds')
for p in [root/'E1-R003-v2/trace.json',root/'E1-R003-v2/trace_rev.json',root/'E1-R003/trace.json']:
    actual=runner.trace_map(p)
    interpreted=summary.trace_messages(p)
    assert actual==interpreted,(p,actual,interpreted)
    print('ACTUAL TRACE PASS',str(p),len(actual))
p=root/'E2-R001/A_cut_on_p1/T1_replay.json'
source=root/'E1-R003/trace.json'
runner.validate_replay(source,p)
summary.valid_replay(p,summary.trace_messages(source))
print('ACTUAL LIVE REPLAY PASS',str(p))
for name in ['state_test_runner.py','state_measurement_summarize.py','t03_runner.py','e2_launch.py','t03_summarize.py','production_measurement_summarize.py']:
    print('MD5',name,hashlib.md5(pathlib.Path(name).read_bytes()).hexdigest())
PY
