"""Explicit smoke gate: exactly one passed test and zero skipped tests required."""
import json
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent


def check_result(output, junit, exit_code, expected=1):
    root = ET.fromstring(junit)
    suites = [root] if root.tag == 'testsuite' else list(root.findall('testsuite'))
    totals = {key: sum(int(s.get(key, 0)) for s in suites)
              for key in ('tests', 'failures', 'errors', 'skipped')}
    passed = totals['tests'] - totals['failures'] - totals['errors'] - totals['skipped']
    if (exit_code != 0 or totals['skipped'] != 0 or passed != expected or
            totals['tests'] != expected or not re.search(r'\b' + str(expected) + r' passed\b', output)):
        raise RuntimeError('Smoke requires expected passed count and skipped=0: ' + str(totals))
    return {**totals, 'passed': passed, 'expected_passed': expected}


def main():
    from test_smoke_live import required_environment, validate_owner
    from release_config import ROOT
    from smoke_campaign import attempt
    config = required_environment()
    run_dir = Path(config['RELEASE_SMOKE_RUN_DIR'])
    owner = json.loads(Path(config['RELEASE_SMOKE_OWNER']).read_text())
    validate_owner(owner, config['RELEASE_SMOKE_MODE'], config['RELEASE_SMOKE_BASE'].rstrip('/'),
                   Path(config['RELEASE_SMOKE_SERVE_LOG']), config['RELEASE_SMOKE_EXCLUSIVE_APPROVAL'])
    if run_dir.parent != Path(owner['run_dir']):
        raise ValueError('Smoke artifacts must be in the owned service run')
    campaign = os.environ.get('RELEASE_SMOKE_CAMPAIGN_DIR')
    if not campaign:
        raise ValueError('Explicit smoke requires RELEASE_SMOKE_CAMPAIGN_DIR')
    reference = HERE.parent / 'redeploy_smoke_fix_20261009/redeploy_expected_reference.json'
    reference_sha = hashlib.sha256(reference.read_bytes()).hexdigest() if owner['mode'] == 'release' else None
    junit = run_dir.parent / (run_dir.name + '.junit.xml')
    output_path = run_dir.parent / (run_dir.name + '.pytest.txt')
    if junit.exists() or output_path.exists():
        raise RuntimeError('Never reuse a smoke gate evidence path')
    with attempt(campaign, ROOT / 'runs/production', owner, reference_sha) as current:
        result = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
            '--junitxml=' + str(junit), str(HERE / 'test_smoke_live.py')],
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        output_path.write_text(result.stdout, encoding='utf-8')
        print(result.stdout, end='')
        if (run_dir / 'smoke_invalid.json').is_file():
            first = owner['approval_id'] == Path(campaign).name
            current['outcome'] = 'smoke_invalid' if first else 'failed_second_smoke_invalid'
            print('SMOKE_INVALID: one same-version restart allowed' if first else
                  'FAILED: second smoke_invalid; stop and rollback')
            return 75 if first else 1
        counts = check_result(result.stdout, junit.read_text(encoding='utf-8'), result.returncode)
        with (run_dir / 'smoke_gate.json').open('x', encoding='utf-8') as handle:
            json.dump({'classification': 'passed', **counts}, handle, indent=2)
            handle.write('\n')
        current['outcome'] = 'passed'
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
