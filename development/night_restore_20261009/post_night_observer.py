"""Enter the task-owned, read-only overnight observer after a successful smoke."""
import json
import subprocess
import sys
from pathlib import Path
from deploy_conditional import require_root_final_review

HERE = Path(__file__).resolve().parent

def main():
    approval = json.loads((HERE / 'DEPLOYMENT_APPROVAL.json').read_text())
    require_root_final_review(approval)
    run = Path(approval['run_dir'])
    smoke = json.loads((run / 'smoke_execution_result.json').read_text())
    if smoke.get('exit_code') != 0:
        raise RuntimeError('observer is forbidden until the sole RESTORE481 smoke passes')
    return subprocess.run([sys.executable, str(HERE / 'observe_overnight.py'), '--run-dir', str(run),
                           '--out-dir', str(run / 'overnight_observation'),
                           '--until', approval['observation_until']]).returncode

if __name__ == '__main__':
    raise SystemExit(main())
