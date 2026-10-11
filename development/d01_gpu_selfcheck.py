"""D01 development checks; outputs are not formal T16/T03 acceptance data."""
import json
import os
from pathlib import Path
import shlex
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request

WT = Path('/data2/FreeToken/wt/e1r008')
OUT = Path('/data2/FreeToken/runs/dev_D01/health_ready_check')
PYTHON = '/data2/FreeToken/venv/bin/python'
LOCK = Path('/data2/_shared/gpu.lock')
TRACE = '/data2/_shared/runs/ft_rounds/E1-R003/trace.json'
COMMIT = 'f91054b'
MODEL = 'Qwen3.8-Flash-Next-NVFP4'


def output(args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs).strip()


def gate():
    with socket.socket() as sock:
        assert sock.connect_ex(('127.0.0.1', 8095)) != 0, '8095 already occupied'
    used = output(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'])
    assert all(int(v) < 1000 for v in used.splitlines()), 'GPU already occupied'
    for line in output(['ps', '-eo', 'pid,args']).splitlines()[1:]:
        pid, _, command = line.strip().partition(' ')
        if int(pid) == os.getpid():
            continue
        assert not any(pattern in command for pattern in (
            'ft serve', 'agent_trace.py replay', 'agent_trace.py generate',
            'ft_probe', 'probe_ft_cold32k', 'cold_eq.py',
        )), f'conflicting process: {line}'
    assert output(['git', '-C', str(WT), 'rev-parse', '--short=7', 'HEAD']) == COMMIT
    assert not output(['git', '-C', str(WT), 'status', '--porcelain', '--untracked-files=no'])


def stop(proc):
    for sig, wait in ((signal.SIGINT, 30), (signal.SIGTERM, 10), (signal.SIGKILL, 10)):
        if proc.poll() is not None:
            return
        os.killpg(proc.pid, sig)
        try:
            proc.wait(timeout=wait)
        except subprocess.TimeoutExpired:
            continue
    raise RuntimeError('owned test process did not stop')


def run_arm(cut):
    gate()
    arm = OUT / ('cut_on' if cut else 'cut_off')
    arm.mkdir(exist_ok=False)
    env = os.environ.copy()
    env.update(PYTHONPATH=str(WT / 'python'), PYTHONUNBUFFERED='1', FT_DEV_D0='1',
               FT_DEV_D0_PATH=str(arm / 'd0'))
    env.pop('FT_DEV_STATE_DUMP', None)
    env.pop('FT_D3_ANCHOR_MODE', None)
    env['PATH'] = '/usr/local/cuda-13.0/bin:/data2/FreeToken/venv/bin:' + env['PATH']
    env['LD_LIBRARY_PATH'] = '/usr/local/cuda-13.0/lib64:' + env.get('LD_LIBRARY_PATH', '')
    assertion = (
        'import freetoken, freetoken.kernel._cpu_moe, freetoken.kernel._pinned_tensor; '
        f'assert freetoken.__file__ == {str(WT / "python/freetoken/__init__.py")!r}; '
        'print(freetoken.__file__)'
    )
    source = output([PYTHON, '-c', assertion], env=env, cwd=WT)
    args = [
        'numactl', '--cpunodebind=0,1', '--interleave=all', '/data2/FreeToken/venv/bin/ft', 'serve',
        '--model-path', '/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay',
        '--served-model-name', MODEL, '--host', '127.0.0.1', '--port', '8095',
        '--memory-ratio', '0.88', '--moe-cache-auto', '--moe-prefill-hit-d2d',
        '--ple-backend', 'pinned', '--moe-strategy', 'offload', '--quant-backend', 'moe.nvfp4=triton',
        '--max-running-requests', '2', '--cuda-graph-max-bs', '2',
        '--kv-reserve-tokens', '49152', '--max-seq-len-override', '49152',
        '--max-prefill-length', '4096', '--enable-cache-report', '--enable-special-token-ckpt',
        '--tool-call-parser', 'qwen3_coder', '--reasoning-parser', 'qwen3', '--prefill-layer-major',
    ]
    if not cut:
        args.append('--no-prefill-anchor-cut')
    (arm / 'SERVE_CMD.txt').write_text(
        'PYTHONPATH=' + shlex.quote(env['PYTHONPATH']) + ' FT_DEV_D0=1 FT_DEV_D0_PATH='
        + shlex.quote(env['FT_DEV_D0_PATH']) + ' PATH=' + shlex.quote(env['PATH'])
        + ' LD_LIBRARY_PATH=' + shlex.quote(env['LD_LIBRARY_PATH']) + ' PYTHONUNBUFFERED=1 '
        + shlex.join(args) + '\n'
    )
    (arm / 'ENV.txt').write_text(time.strftime('%Y-%m-%d %H:%M:%S %Z') + '\n' + source + '\n'
                               + output(['git', '-C', str(WT), 'rev-parse', 'HEAD']) + '\n'
                               + output(['nvidia-smi']) + '\n' + output(['numactl', '-H']) + '\n')
    with (arm / 'serve.log').open('w') as log:
        proc = subprocess.Popen(args, env=env, cwd=WT, stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True)
        try:
            print(f'{arm.name}: started owned service pid={proc.pid}', flush=True)
            deadline = time.monotonic() + 360
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise RuntimeError('owned test service exited during startup')
                try:
                    with urllib.request.urlopen('http://127.0.0.1:8095/health', timeout=3) as r:
                        health = json.load(r)
                        if health.get('status') == 'error':
                            raise RuntimeError(f'backend failed: {health}')
                        if r.status == 200 and health.get('status') == 'ok':
                            break
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(3)
            else:
                raise TimeoutError('owned test service startup exceeded 360 seconds')
            print(f'{arm.name}: service ready', flush=True)
            parsed = [ln for ln in (arm / 'serve.log').read_text().splitlines() if 'ServerArgs(' in ln]
            (arm / 'serve_args.txt').write_text('\n'.join(parsed) + '\n')
            raw = Path('/data2/FreeToken/wt/e1r003/seed_45k.txt').read_text()
            messages = [{'role': 'user' if i % 2 == 0 else 'assistant', 'content': raw[:2000]}
                        for i in range(12)]
            messages.append({'role': 'user', 'content': '只回答：ok'})
            payload = dict(model=MODEL, messages=messages, max_tokens=4, temperature=0, stream=True,
                           chat_template_kwargs={'enable_thinking': False})
            before = (arm / 'serve.log').read_text().count('Prefill batch,')
            req = urllib.request.Request('http://127.0.0.1:8095/v1/chat/completions',
                                         data=json.dumps(payload).encode(),
                                         headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=180) as response:
                body = response.read().decode()
            (arm / 'cold13_request.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2))
            (arm / 'cold13_response.sse').write_text(body)
            time.sleep(1)
            cold_batches = (arm / 'serve.log').read_text().count('Prefill batch,') - before
            print(f'{arm.name}: cold13 prefill_batches={cold_batches}', flush=True)
            replay_env = dict(env, FT_REPLAY_MAX_TOKENS='512')
            replay_cmd = [PYTHON, '/data2/FreeToken/scripts/agent_trace.py', 'replay',
                          '--trace', TRACE, '--out', str(arm / 'replay.json'),
                          '--fresh-note', 'D01 development self-check, not formal acceptance',
                          '--timeout', '120']
            with (arm / 'replay.log').open('w') as replay_log:
                subprocess.run(replay_cmd, env=replay_env, cwd=WT, stdout=replay_log,
                               stderr=subprocess.STDOUT, timeout=480, check=True)
            replay = json.loads((arm / 'replay.json').read_text())
            assert replay['rounds'] and not any(r['error'] for r in replay['rounds']), 'replay error'
            print(f'{arm.name}: replay completed {len(replay["rounds"])} rounds', flush=True)
            time.sleep(3)
        finally:
            stop(proc)
    decode = json.loads((arm / 'd0_decode.json').read_text())
    records = [json.loads(line) for line in (arm / 'd0_prefill.jsonl').read_text().splitlines()]
    cold_records = [r for r in records if any(q['rid'] == records[0]['reqs'][0]['rid']
                                            for q in r['reqs'])] if records and records[0]['reqs'] else []
    return dict(cold_batches=cold_batches, snapshots=decode['anchor_snapshots_taken'],
                cached=[r['cached_tokens'] for r in replay['rounds']],
                messages_sha=[r['messages_sha'] for r in replay['rounds']],
                cold_reasons=[r['seg_reason'] for r in cold_records],
                snapshot_exit_log='D0 anchor_snapshots_taken=' in (arm / 'serve.log').read_text())


def main():
    gate()
    OUT.mkdir(exist_ok=False)
    token = json.dumps(dict(owner='dev_D01', card='D01', since=time.strftime('%Y-%m-%d %H:%M:%S %Z'),
                            pid=os.getpid()))
    fd = os.open(LOCK, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, 'w') as lock:
        lock.write(token)
    try:
        on = run_arm(True)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            used = output(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'])
            if all(int(v) < 1000 for v in used.splitlines()):
                break
            time.sleep(2)
        off = run_arm(False)
        result = dict(commit=COMMIT, trace=TRACE, cut_on=on, cut_off=off,
                      G3=off['cold_batches'] == 1 and 'anchor_cap' not in off['cold_reasons'],
                      G4=on['snapshots'] == off['snapshots'] and on['cached'] == off['cached'],
                      identical_requests=on['messages_sha'] == off['messages_sha'])
        (OUT / 'gpu_selfcheck.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps(result, ensure_ascii=False), flush=True)
    except BaseException as exc:
        (OUT / 'gpu_selfcheck_error.json').write_text(json.dumps(dict(error=repr(exc), commit=COMMIT)))
        raise
    finally:
        if LOCK.exists() and LOCK.read_text() == token:
            LOCK.unlink()


if __name__ == '__main__':
    main()
