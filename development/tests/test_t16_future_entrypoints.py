import hashlib
from pathlib import Path

DEV=Path(__file__).parents[1]
CURRENT=DEV/'t16_candidate_runner_full_tail.py'

def test_compat_runners_pin_the_current_runtime():
    digest=hashlib.sha256(CURRENT.read_bytes()).hexdigest()
    for name in ('t16_candidate_runner.py','t16_candidate_runner_d07.py'):
        source=(DEV/name).read_text()
        assert 't16_candidate_runner_full_tail.py' in source and digest in source

def test_obsolete_launchers_fail_closed_without_a_current_receipt():
    for name in ('t16_candidate_launch.py','t16_candidate_launch_d07.py','t16_candidate_launch_full_tail.py'):
        assert 'exact current full-tail stage and CPU receipt' in (DEV/name).read_text()
