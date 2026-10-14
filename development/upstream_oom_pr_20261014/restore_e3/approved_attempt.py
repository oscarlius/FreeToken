"""Load the sole restore identity; this package never permits a retry."""
import json
from pathlib import Path
import sys


def load():
    if sys.argv[1:]:
        raise ValueError('night restore permits no retry option')
    source = Path(__file__).with_name('DEPLOYMENT_APPROVAL.json')
    approval = json.loads(source.read_text())
    from deploy_conditional import require_root_final_review
    require_root_final_review(approval)
    if not approval['conditions_met']:
        raise RuntimeError('root final review has not admitted execution')
    return approval
