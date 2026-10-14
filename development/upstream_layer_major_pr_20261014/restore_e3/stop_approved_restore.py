"""Stop RESTORE481 through the frozen controller and require its stopped receipt."""
import json
from pathlib import Path
import subprocess

from deploy_conditional import require_root_final_review

HERE = Path(__file__).resolve().parent

def main():
    approval = json.loads((HERE / 'DEPLOYMENT_APPROVAL.json').read_text())
    require_root_final_review(approval)
    ops = Path(approval['frozen_ops']['path'])
    run = Path(approval['run_dir'])
    active = Path('/data2/FreeToken/run/production.active.json')
    if not active.exists():
        if (run / 'stopped.json').exists():
            return 0
        raise RuntimeError('restore owner absent without stopped receipt; inspect before rollback')
    owner = json.loads(active.read_text())
    if owner.get('approval_id') != approval['approval_id'] or owner.get('commit') != approval['restore_commit']:
        raise RuntimeError('refuse to stop a foreign production owner')
    result = subprocess.run(['/data2/FreeToken/venv/bin/python', str(ops / 'release_control.py'),
                             '--stop', '--approval-id', approval['approval_id']])
    if result.returncode:
        return result.returncode
    if not (run / 'stopped.json').is_file():
        raise RuntimeError('frozen controller returned success without RESTORE481 stopped.json')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
