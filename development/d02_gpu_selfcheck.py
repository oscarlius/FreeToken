"""D02 development checks. These measurements are not formal T16/T05 acceptance."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shlex
import signal
import socket
import statistics
import subprocess
import threading
import time
import urllib.error
import urllib.request

WT = Path('/data2/FreeToken/wt/e1ms')
OUT = Path('/data2/FreeToken/runs/dev_D02/gpu_selfcheck_23f2e2c')
PYTHON = '/data2/FreeToken/venv/bin/python'
LOCK = Path('/data2/_shared/gpu.lock')
COMMIT = '23f2e2c'
MODEL = 'Qwen3.8-Flash-Next-NVFP4'
LOCK_TOKEN = None


def output(args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs).strip()


def gate():
    if LOCK.exists():
        assert LOCK_TOKEN and LOCK.read_text() == LOCK_TOKEN, 'GPU lock belongs to someone else'
    with socket.socket() as sock:
        assert sock.connect_ex(('127.0.0.1', 8095)) != 0, '8095 already occupied'
    used = output(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'])
    assert all(int(v) < 1000 for v in used.splitlines()), 'GPU already occupied'
    for line in output(['ps', '-eo', 'pid,args']).splitlines()[1:]:
        pid, _, command = line.strip().partition(' ')
        if int(pid) == os.getpid():
            continue
        assert not any(pattern in command for pattern in (
            'ft serve', 'agent_trace.py replay', 'agent_trace.py generate', 'ft_probe',
            'probe_ft_cold32k', 'cold_eq.py', 'batchNN_',
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


def stream_request(arm, label, messages, max_tokens, barrier=None):
    payload = dict(model=MODEL, messages=messages, max_tokens=max_tokens, temperature=0,
                   ignore_eos=True, stream=True, stream_options={'include_usage': True},
                   chat_template_kwargs={'enable_thinking': False})
    (arm / (label + '_request.json')).write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    request = urllib.request.Request('http://127.0.0.1:8095/v1/chat/completions',
                                     data=json.dumps(payload).encode(),
                                     headers={'Content-Type': 'application/json'})
    if barrier:
        barrier.wait(timeout=5)
    t0 = time.perf_counter()
    first_wire = first_real = last_real = None
    usage = None
    content = []
    with urllib.request.urlopen(request, timeout=180) as response, (arm / (label + '_response.sse')).open('wb') as raw:
        for line in response:
            raw.write(line)
            if not line.startswith(b'data: '):
                continue
            if first_wire is None:
                first_wire = time.perf_counter() - t0
            if line.strip() == b'data: [DONE]':
                break
            event = json.loads(line[6:])
            assert 'error' not in event, event
            if event.get('usage'):
                usage = event['usage']
            for choice in event.get('choices', []):
                text = choice.get('delta', {}).get('content')
                if text:
                    elapsed = time.perf_counter() - t0
                    first_real = elapsed if first_real is None else first_real
                    last_real = elapsed
                    content.append(text)
    assert usage and usage['completion_tokens'] == max_tokens, f'incomplete generation: {usage}'
    assert first_real is not None and last_real is not None, 'no real content'
    result = dict(first_wire_s=first_wire, first_real_s=first_real, last_real_s=last_real,
                  first_real_at=t0 + first_real, last_real_at=t0 + last_real,
                  total_s=time.perf_counter() - t0, usage=usage,
                  content_sha256=hashlib.sha256(''.join(content).encode()).hexdigest())
    (arm / (label + '_client.json')).write_text(json.dumps(result, indent=2))
    return result


def verify_telemetry(arm, timeline):
    log = (arm / 'serve.log').read_text()
    batch_tokens = [int(x) for x in re.findall(r'Prefill batch,.*?#new-token: (\d+)', log)]
    prefill = [json.loads(line) for line in (arm / 'd0_prefill.jsonl').read_text().splitlines()]
    assert len(prefill) == len(batch_tokens), (len(prefill), len(batch_tokens))
    assert [sum(q['new_tokens'] for q in row['reqs']) for row in prefill] == batch_tokens
    assert all(row['t_start'] <= row['t_end'] and row['reqs'] for row in prefill)
    assert prefill[-1]['chunk'] == len(prefill) - 1
    steps = [json.loads(line) for line in (arm / 'd0_decode_steps.jsonl').read_text().splitlines()]
    assert steps and [row['step'] for row in steps] == list(range(len(steps)))
    assert all(len(row['rids']) == row['bs'] and sum(row['missing_per_layer']) == row['missing_total']
               for row in steps)
    assert any(row['bs'] == 2 for row in steps), 'concurrent decode was not exercised'
    assert any(row['missing_total'] > 0 and row['h2d_bytes'] > 0 for row in steps)
    aggregate = json.loads((arm / 'd0_decode.json').read_text())
    assert 'sm_clock_mhz' in aggregate
    tl = None
    if timeline:
        assert 'D0 TIMELINE: cuda graph disabled' in log
        path = arm / 'd0_decode_timeline.jsonl'
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        assert len(rows) == min(8, len(steps)), 'timeline cap is wrong'
        command = [PYTHON, '/data2/FreeToken/scripts/d0_timeline_summary.py', str(path), '--json']
        summary = json.loads(output(command))
        (arm / 'timeline_summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False))
        text = output(command[:-1])
        (arm / 'timeline_summary.txt').write_text(text + '\n')
        tl = dict(steps=len(rows), layers=len(summary['layers']), overall=summary['overall'])
    else:
        assert not (arm / 'd0_decode_timeline.jsonl').exists()
        assert 'D0 TIMELINE: cuda graph disabled' not in log
        assert 'Start capturing CUDA graphs with sizes: [1, 2]' in log
    return dict(prefill_records=len(prefill), prefill_batches=len(batch_tokens),
                prefill_new_tokens= batch_tokens, decode_steps=len(steps),
                bs2_steps=sum(row['bs'] == 2 for row in steps),
                moe_layers=len(steps[0]['missing_per_layer']),
                missing_total=sum(row['missing_total'] for row in steps),
                h2d_bytes=sum(row['h2d_bytes'] for row in steps),
                sm_clock_mhz=aggregate['sm_clock_mhz'], timeline=tl)


def run_arm(name, d0, timeline=False):
    gate()
    arm = OUT / name
    arm.mkdir(exist_ok=False)
    env = os.environ.copy()
    for key in ('FT_DEV_STATE_DUMP', 'FT_D3_ANCHOR_MODE', 'FT_DEV_D0_TIMELINE', 'FT_DEV_D0_TIMELINE_STEPS'):
        env.pop(key, None)
    env.update(PYTHONPATH=str(WT / 'python'), PYTHONUNBUFFERED='1', FT_DEV_D0='1' if d0 else '0',
               FT_DEV_D0_PATH=str(arm / 'd0'))
    if timeline:
        env.update(FT_DEV_D0_TIMELINE='1', FT_DEV_D0_TIMELINE_STEPS='8')
    env['PATH'] = '/usr/local/cuda-13.0/bin:/data2/FreeToken/venv/bin:' + env['PATH']
    env['LD_LIBRARY_PATH'] = '/usr/local/cuda-13.0/lib64:' + env.get('LD_LIBRARY_PATH', '')
    assertion = ('import freetoken, freetoken.kernel._cpu_moe, freetoken.kernel._pinned_tensor; '
                 f'assert freetoken.__file__ == {str(WT / "python/freetoken/__init__.py")!r}; '
                 'print(freetoken.__file__)')
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
    selected = ['PYTHONPATH', 'PYTHONUNBUFFERED', 'FT_DEV_D0', 'FT_DEV_D0_PATH', 'PATH', 'LD_LIBRARY_PATH']
    if timeline:
        selected += ['FT_DEV_D0_TIMELINE', 'FT_DEV_D0_TIMELINE_STEPS']
    (arm / 'SERVE_CMD.txt').write_text(' '.join(k + '=' + shlex.quote(env[k]) for k in selected)
                                    + ' ' + shlex.join(args) + '\n')
    (arm / 'ENV.txt').write_text(time.strftime('%Y-%m-%d %H:%M:%S %Z') + '\n' + source + '\n'
                               + output(['git', '-C', str(WT), 'rev-parse', 'HEAD']) + '\n'
                               + output(['nvidia-smi']) + '\n' + output(['numactl', '-H']) + '\n')
    with (arm / 'serve.log').open('w') as log:
        proc = subprocess.Popen(args, env=env, cwd=WT, stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True)
        try:
            print(f'{name}: service pid={proc.pid}, D0={d0}, timeline={timeline}', flush=True)
            deadline = time.monotonic() + 360
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise RuntimeError('owned service exited during startup')
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
                raise TimeoutError('startup exceeded 360 seconds')
            print(f'{name}: ready', flush=True)
            if name != 'off_A1':
                base_log = OUT / 'off_A1' / 'serve.log'
                command = [PYTHON, '/data2/FreeToken/scripts/serve_args_diff.py', str(base_log), str(arm / 'serve.log')]
                difference = output(command)
                (arm / 'serve_args_diff.txt').write_text(difference + '\n')
                parser = runpy.run_path('/data2/FreeToken/scripts/serve_args_diff.py')['parse']
                left, right = parser(str(base_log)), parser(str(arm / 'serve.log'))
                assert set(left) == set(right)
                # ServerArgs declares its per-process IPC suffix as '.pid=<PID>'.
                # Validate that exact generated form before normalizing PID identity;
                # any actual configuration difference still stops this development run.
                assert re.fullmatch(r"'\.pid=\d+'", left['_unique_suffix']), difference
                assert right['_unique_suffix'] == repr('.pid=' + str(proc.pid)), difference
                assert all(left[k] == right[k] for k in left if k not in {'pid', '_unique_suffix'}), difference
            seed = Path('/data2/FreeToken/wt/e1r003/seed_45k.txt').read_text()
            first_messages = [{'role': 'user' if i % 2 == 0 else 'assistant', 'content': seed[:2000]}
                              for i in range(12)] + [{'role': 'user', 'content': '请详细介绍模型推理。'}]
            first = stream_request(arm, 'first_shot', first_messages, 1 if timeline else 16)
            barrier = threading.Barrier(2)
            pair_messages = [[{'role': 'user', 'content': f'独立任务{index}。' + seed[2000:3500]
                               + '请连续详细解释这段资料。'}] for index in range(2)]
            with ThreadPoolExecutor(max_workers=2) as pool:
                jobs = [pool.submit(stream_request, arm, f'pair_{i}', pair_messages[i],
                                    16 if timeline else 128, barrier) for i in range(2)]
                clients = [job.result() for job in jobs]
            elapsed = max(r['last_real_at'] for r in clients) - min(r['first_real_at'] for r in clients)
            decode_tokens = sum(r['usage']['completion_tokens'] - 1 for r in clients)
            result = dict(arm=name, d0=d0, timeline=timeline, first_shot=first, clients=clients,
                          decode_window_s=elapsed, decode_tokens=decode_tokens,
                          decode_tok_s=decode_tokens / elapsed)
            time.sleep(3)
            # Verify final prefill publication while the process is STILL alive.
            if d0:
                result['telemetry'] = verify_telemetry(arm, timeline)
            else:
                assert not list(arm.glob('d0*')), 'disabled D0 created telemetry'
            print(f'{name}: decode {result["decode_tok_s"]:.3f} tok/s, telemetry={result.get("telemetry")}', flush=True)
        finally:
            stop(proc)
    (arm / 'selfcheck.json').write_text(json.dumps(result, indent=2, allow_nan=False))
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        used = output(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'])
        if all(int(v) < 1000 for v in used.splitlines()):
            return result
        time.sleep(2)
    raise RuntimeError('GPU memory did not release after owned process stopped')


def main():
    global LOCK_TOKEN
    gate()
    OUT.mkdir(exist_ok=False)
    LOCK_TOKEN = json.dumps(dict(owner='dev_D02_23f2e2c', card='D02',
                                 since=time.strftime('%Y-%m-%d %H:%M:%S %Z'), pid=os.getpid()))
    with os.fdopen(os.open(LOCK, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644), 'w') as lock:
        lock.write(LOCK_TOKEN)
    try:
        results = [run_arm(name, d0) for name, d0 in (
            ('off_A1', False), ('on_B1', True), ('off_A2', False), ('on_B2', True))]
        timeline = run_arm('timeline', True, timeline=True)
        off = [r['decode_tok_s'] for r in results if not r['d0']]
        on = [r['decode_tok_s'] for r in results if r['d0']]
        paired_drop = [100 * (1 - on[i] / off[i]) for i in range(2)]
        result = dict(commit=COMMIT, mode='development_selfcheck_not_acceptance',
                      sequence=[r['arm'] for r in results], arms=results, timeline=timeline,
                      off_median_tok_s=statistics.median(off), on_median_tok_s=statistics.median(on),
                      median_drop_pct=100 * (1 - statistics.median(on) / statistics.median(off)),
                      paired_drop_pct=paired_drop, paired_drop_range_pct=[min(paired_drop), max(paired_drop)])
        (OUT / 'gpu_selfcheck.json').write_text(json.dumps(result, indent=2, allow_nan=False))
        print(json.dumps({k: v for k, v in result.items() if k not in ('arms', 'timeline')}), flush=True)
    except BaseException as exc:
        (OUT / 'gpu_selfcheck_error.json').write_text(json.dumps(dict(error=repr(exc), commit=COMMIT)))
        raise
    finally:
        if LOCK.exists() and LOCK.read_text() == LOCK_TOKEN:
            LOCK.unlink()
        files = sorted(p for p in OUT.rglob('*') if p.is_file() and p.name != 'MANIFEST.sha256')
        (OUT / 'MANIFEST.sha256').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()
                                                 + '  ' + str(p.relative_to(OUT)) + '\n' for p in files))


if __name__ == '__main__':
    main()
