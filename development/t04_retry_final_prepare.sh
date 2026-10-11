set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import pathlib
base = pathlib.Path('/data2/FreeToken/runs/dev_D03')
target = base / 't04_retry_r015_71d4846'
previous = base / 't04_retry_r015_ready'
assert not target.exists()
(target / 'development/tests').mkdir(parents=True)
(target / 'development/e2d03/scripts').mkdir(parents=True)
for name in ['development/t04_logits_phase2.py', 'development/d03_phase2_launch.py',
             'development/e2d03/scripts/logits_probe.py',
             'development/tests/test_t04_logits_retry.py', 'development/tests/test_d03_t04_retry_launch.py']:
    with (target / name).open('xb') as stream:
        stream.write((previous / name).read_bytes())
print('Final T04 candidate prepared; preceding bundle preserved, not a launch')
PY
