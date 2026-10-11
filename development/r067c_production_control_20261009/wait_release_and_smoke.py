"""Wait for release readiness, then run the unchanged approved smoke once."""
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request


def main():
    from approved_attempt import load
    approval = load()
    assert approval['conditions_met']
    run = Path(approval['run_dir'])
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + 1800
    while time.monotonic() < deadline:
        if (run / 'stopped.json').exists():
            raise RuntimeError('Release supervisor stopped before readiness')
        health = None
        try:
            with opener.open('http://172.16.108.9:8095/health', timeout=5) as response:
                health = json.loads(response.read())
        except Exception:
            pass
        if health and health.get('status') == 'ok' and health.get('maintenance') == 'serving':
            with (run / 'serving_ready.json').open('x') as handle:
                json.dump({'at': time.time(), 'health': health,
                           'generation_readiness_calls': 0}, handle, indent=2)
                handle.write('\n')
            return subprocess.call(
                ['/data2/FreeToken/venv/bin/python', '-u',
                 str(Path(__file__).with_name('run_exclusive_smoke.py'))] + (['--retry1'] if approval['approval_id'].endswith('-retry1') else []),
                env={**os.environ, 'CUDA_VISIBLE_DEVICES': '', 'PYTHONDONTWRITEBYTECODE': '1'})
        time.sleep(10)
    raise RuntimeError('Release readiness exceeded 1800 seconds')


if __name__ == '__main__':
    raise SystemExit(main())
