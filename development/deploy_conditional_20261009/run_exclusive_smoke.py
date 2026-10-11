"""Execute the approved official-SDK pytest gate on the already running service."""
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

HERE = Path(__file__).resolve().parent


def main():
    approval = json.loads((HERE / 'DEPLOYMENT_APPROVAL.json').read_text())
    run = Path(approval['run_dir'])
    owner = json.loads((run / 'owner.json').read_text())
    assert owner['approval_id'] == approval['approval_id'] and owner['mode'] == 'release'
    assert (run / 'serving_ready.json').is_file()
    base = 'http://172.16.108.9:8095'
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(base + '/health', timeout=10) as response:
        health = json.loads(response.read())
        assert response.status == 200 and health['status'] == 'ok' and health['maintenance'] == 'serving'
    env = dict(os.environ)
    for key in list(env):
        if key.startswith('RELEASE_SMOKE_'):
            env.pop(key)
    env.update(RELEASE_SMOKE_BASE=base, RELEASE_SMOKE_MODE='release',
               RELEASE_SMOKE_OWNER='/data2/FreeToken/run/production.active.json',
               RELEASE_SMOKE_SERVE_LOG=str(run / 'serve.log'),
               RELEASE_SMOKE_RUN_DIR=str(run / 'smoke_first'),
               RELEASE_SMOKE_EXCLUSIVE_APPROVAL=approval['approval_id'],
               CUDA_VISIBLE_DEVICES='', PYTHONDONTWRITEBYTECODE='1')
    argv = ['/data2/FreeToken/venv/bin/python', '-u', str(Path(approval['ops']) / 'run_smoke.py')]
    invocation = {'approval_id': approval['approval_id'], 'argv': argv, 'started_at': time.time(),
                  'mode': 'release', 'prompts': [512, 8257], 'output_tokens_each': 128,
                  'official_SDK': True, 'generation_readiness_calls': 0}
    with (run / 'smoke_invocation.json').open('x') as handle:
        json.dump(invocation, handle, indent=2)
        handle.write('\n')
    result = subprocess.run(argv, cwd=run, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    with (run / 'smoke_orchestration_output.log').open('xb') as handle:
        handle.write(result.stdout)
    receipt = {'approval_id': approval['approval_id'], 'exit_code': result.returncode,
               'classification': 'passed' if result.returncode == 0 else ('smoke_invalid' if result.returncode == 75 else 'failed'),
               'completed_at': time.time(), 'invocation': invocation}
    with (run / 'smoke_execution_result.json').open('x') as handle:
        json.dump(receipt, handle, indent=2)
        handle.write('\n')
    print(json.dumps(receipt), flush=True)
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
