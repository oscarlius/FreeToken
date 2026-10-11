"""T16 executor. Source trees and historical artifacts are read-only inputs."""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import runpy
import shlex
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path('/data2/FreeToken')
ROUNDS = Path('/data2/_shared/runs/ft_rounds')
PY = str(ROOT / 'venv/bin/python')
FT = str(ROOT / 'venv/bin/ft')
SCR = ROOT / 'scripts'
LOCK = Path('/data2/_shared/gpu.lock')
MODEL = 'Qwen3.8-Flash-Next-NVFP4'
TOOL_MD5 = {
    'cold_eq.py': '7141f874c41c310ac20d2da72490eccb',
    'probe_ft_cold32k.py': 'de5ccb4f2fee8c5d5eb1881a9fb11674',
    'ft_probe_ckpt_tax.py': '728d4a99123c333d18b5fc51fdf16392',
    'serve_args_diff.py': 'ce123cb0af201d99baac91f7f8e4f8c7',
}
EVENT = re.compile(r'#new-seq: (\d+), #new-token: (\d+), #cached-token: (\d+)')
D03_PARENT_COMMIT = '23f2e2caa3395837c9474735ffc83321f3b9b5a1'
D03_CANDIDATE_COMMIT = 'c30ae0d7003c3bbbf56867ce74da797332fa7ed5'



def command(argv, **kwargs):
    return subprocess.check_output(argv, text=True, **kwargs).strip()


def write_new(path, value):
    with path.open('x', encoding='utf-8') as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def rows(path):
    result = [json.loads(line) for line in path.read_text().splitlines()]
    if not result:
        raise ValueError(f'empty telemetry: {path}')
    return result


def events(path):
    result = [tuple(map(int, match)) for match in EVENT.findall(path.read_text())]
    if not result:
        raise ValueError(f'empty prefill events: {path}')
    return result


def strict_args(left, right, allowed_new):
    required = {'model_path', 'server_port', 'special_token_ckpt', '_unique_suffix'}
    for side, values in (('parent', left), ('new', right)):
        if required - values.keys():
            raise ValueError(f'{side} missing parsed arguments: {required - values.keys()}')
        suffix = ast.literal_eval(values['_unique_suffix'])
        if not isinstance(suffix, str) or not re.fullmatch(r'\.pid=\d+', suffix):
            raise ValueError(f'{side} invalid generated PID suffix: {suffix!r}')
    differences = {}
    for key in left.keys() | right.keys():
        a, b = left.get(key), right.get(key)
        if a == b:
            continue
        if key == '_unique_suffix':
            differences[key] = [a, b]
            continue
        if a is None and key in allowed_new and b == allowed_new[key]:
            differences[key] = [a, b]
            continue
        raise ValueError(f'configuration changed: {key}: {a!r} -> {b!r}')
    return differences


def check_det(paths, target, max_tokens):
    data = [json.loads(path.read_text()) for path in paths]
    inputs = []
    for record in data:
        r = record['record']
        if (not record['text'] or record['events'] <= 0 or r['built_tokens'] != target
                or r['cached_tokens'] != 0 or r['prompt_tokens'] <= 0
                or abs(r['prompt_tokens'] - target) >= 2000
                or not 0 < r['completion_tokens'] <= max_tokens
                or r['ttft_s'] is None):
            raise ValueError(f'invalid cold sample: {r}')
        inputs.append(tuple(r[key] for key in ('cold_id', 'built_tokens', 'prompt_tokens', 'cached_tokens')))
    if len(set(inputs)) != 1:
        raise ValueError(f'cold inputs differ: {inputs}')
    if data[0]['text'] != data[1]['text']:
        raise ValueError('TEXT DIFF')
    return {'input': inputs[0], 'text_sha256': hashlib.sha256(data[0]['text'].encode()).hexdigest(),
            'content_chars': len(data[0]['text']), 'records': [d['record'] for d in data]}


def prefill_tail_contract(arm):
    proof = json.loads((arm / 'prefill_while_alive.json').read_text())
    value = proof.get('includes_terminal_prefill')
    if type(value) is not bool:
        raise ValueError('explicit terminal-prefill coverage required: ' + str(arm))
    return value


def check_prefill(parent, new, tail_fix=True, parent_tail_fix=True):
    old_events, new_events = events(parent / 'serve.log'), events(new / 'serve.log')
    if old_events != new_events:
        raise ValueError('full prefill event sequence differs')
    a, b = rows(parent / 'd0_prefill.jsonl'), rows(new / 'd0_prefill.jsonl')
    expected_old = len(old_events) - (0 if parent_tail_fix else 1)
    expected_new = len(new_events) - (0 if tail_fix else 1)
    if len(a) != expected_old or len(b) != expected_new:
        raise ValueError(f'prefill count mismatch: old={len(a)}/{expected_old}, new={len(b)}/{expected_new}')
    for i, old in enumerate(a):
        fresh = b[i]
        if any(old[key] != fresh[key] for key in ('h2d_bytes', 'd2d_bytes')):
            raise ValueError(f'H2D/D2D DIFF at row {i}')
    for side, records, side_events, complete in (
            ('parent', a, old_events, parent_tail_fix), ('new', b, new_events, tail_fix)):
        for i, record in enumerate(records):
            if record['chunk'] != i:
                raise ValueError(f'chunk index mismatch at row {i}')
            for key in ('h2d_bytes', 'd2d_bytes'):
                if type(record[key]) is not int or record[key] < 0:
                    raise ValueError(f'invalid {key} at row {i}')
            if 'reqs' in record:
                requests = record['reqs']
                actual = (len(requests), sum(r['new_tokens'] for r in requests),
                          sum(r['cached_tokens'] for r in requests))
                if not requests or actual != side_events[i]:
                    raise ValueError(f'{side} request metadata mismatch at row {i}: {actual} != {side_events[i]}')
            elif complete:
                raise ValueError(f'D02 request metadata missing at row {i}')
            if complete:
                if (record['seg_reason'] not in ('anchor_cap', 'token_budget', 'layer_major_whole', 'continuation', 'other')
                        or not math.isfinite(record['t_start']) or not math.isfinite(record['t_end'])
                        or record['t_end'] < record['t_start']):
                    raise ValueError(f'invalid D02 metadata at row {i}')
    return {'h2d': 'SAME', 'parent_rows': len(a), 'new_rows': len(b),
            'all_prefill_events': len(old_events), 'tail_aligned': bool(tail_fix),
            'parent_tail_aligned': bool(parent_tail_fix)}


def has_d02_prefill_tail(wt):
    """Return whether this source tree publishes the final D0 prefill segment."""
    path = Path(wt) / 'python/freetoken/moe/offload_cache.py'
    try:
        source = path.read_text(encoding='utf-8')
    except OSError as exc:
        raise RuntimeError(f'cannot inspect D0 prefill source: {path}') from exc
    return bool(re.search(r'def\s+end_prefill\s*\([^)]*\)(?:\s*->[^:]+)?\s*:\s*.*?\b_d0_flush_chunk\s*\(',
                          source, re.DOTALL))


class Runner:
    def __init__(self, options):
        with socket.socket() as private:
            private.bind(('127.0.0.1', 0))
            self.port = private.getsockname()[1]
        if self.port == 8095:
            raise RuntimeError('private service cannot use 8095')
        self.options = options
        self.directory = ROUNDS / options.rid
        self.token = None
        self.lock_inode = None
        self.proc = None
        self.parser = runpy.run_path(str(SCR / 'serve_args_diff.py'))['parse']
        self.status = self.directory / f'status_batch{options.batch}.json'
        self.allowed = {'prefill_anchor_cut': 'True'} if options.gate == 'D01' else {}
        self.d03_extensions = None
        if options.gate == 'D00':
            self.allowed = {'prefill_anchor_cut': 'True', 'mamba_host_slots': '0'}

    def environment(self, wt, arm=None, d0=False):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith(('FT_DEV_', 'FT_D3_')):
                env.pop(key)
        env.update(PYTHONPATH=str(wt / 'python'), PYTHONUNBUFFERED='1',
                   VIRTUAL_ENV=str(ROOT / 'venv'))
        env['PATH'] = '/usr/local/cuda-13.0/bin:' + str(ROOT / 'venv/bin') + ':' + env.get('PATH', '')
        env['LD_LIBRARY_PATH'] = '/usr/local/cuda-13.0/lib64:' + env.get('LD_LIBRARY_PATH', '')
        if d0:
            env.update(FT_DEV_D0='1', FT_DEV_D0_PATH=str(arm / 'd0'))
        return env

    def set_status(self, **values):
        temporary = self.status.with_suffix('.tmp')
        temporary.write_text(json.dumps({'gate': self.options.gate, 'batch': self.options.batch,
                                        'batch_pid': os.getpid(), 'updated_at': time.strftime('%F %T %Z'),
                                        **values}, ensure_ascii=False, indent=2))
        os.replace(temporary, self.status)

    def gate(self, wt, commit):
        if LOCK.exists() and not (self.token and LOCK.read_text() == self.token
                                 and LOCK.stat().st_ino == self.lock_inode):
            raise RuntimeError('foreign GPU lock exists')
        # Admission reads resources; it never probes another listening service.
        gpu = command(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'])
        if not gpu or any(int(v) >= 1000 for v in gpu.splitlines()):
            raise RuntimeError(f'GPU occupied: {gpu}')
        for line in command(['ps', '-eo', 'pid,args']).splitlines()[1:]:
            pid, _, text = line.strip().partition(' ')
            if int(pid) == os.getpid():
                continue
            if re.search(r'ft serve\b|agent_trace\.py (?:replay|generate)\b|ft_probe|probe_ft_cold32k|cold_eq\.py|batch\d+_|t16_runner\.py.*--run', text):
                raise RuntimeError(f'competing GPU/test process: {line}')
        actual_commit = command(['git', '-C', str(wt), 'rev-parse', 'HEAD'])
        if (len(commit) == 40 and actual_commit != commit) or (len(commit) != 40 and actual_commit[:7] != commit):
            raise RuntimeError(f'source commit does not match: {actual_commit} != {commit}')
        if command(['git', '-C', str(wt), 'status', '--porcelain', '--untracked-files=no']):
            raise RuntimeError('tracked source tree is dirty')
        env = self.environment(wt)
        source = command([PY, '-c', 'import freetoken,torch,freetoken.kernel._cpu_moe,freetoken.kernel._pinned_tensor;'
                          f'assert freetoken.__file__ == {str(wt / "python/freetoken/__init__.py")!r};'
                          'print(freetoken.__file__,torch.__version__,torch.version.cuda)'], env=env, cwd=wt)
        print(f'GATE PASS wt={wt} commit={commit} gpu={gpu} source={source}', flush=True)
        return source

    def compiled_extensions(self, wt):
        """Fingerprint the extensions actually imported from the shared virtualenv."""
        script = (
            'import hashlib,json; import freetoken.kernel._cpu_moe as cpu; '
            'import freetoken.kernel._pinned_tensor as pinned; '
            'mods={"_cpu_moe":cpu,"_pinned_tensor":pinned}; '
            'paths={k:v.__file__ for k,v in mods.items()}; '
            'assert all(p and p.endswith(".so") for p in paths.values()), paths; '
            'print(json.dumps({k:{"path":paths[k],"sha256":hashlib.sha256(open(paths[k],"rb").read()).hexdigest()} '
            'for k in sorted(paths)},sort_keys=True))'
        )
        return json.loads(command([PY, '-c', script], env=self.environment(wt), cwd=wt))

    def lock_take(self):
        self.token = json.dumps({'owner': self.options.rid, 'card': 'T16', 'pid': os.getpid(),
                                 'since': time.strftime('%F %T %Z')})
        descriptor = os.open(LOCK, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(descriptor, 'w') as handle:
            handle.write(self.token)
        self.lock_inode = LOCK.stat().st_ino

    def lock_release(self):
        if self.token and LOCK.exists() and LOCK.stat().st_ino == self.lock_inode and LOCK.read_text() == self.token:
            LOCK.unlink()

    def owned_lifecycle(self):
        source = Path(__file__).with_name('d07_g3g4_prepare.py')
        spec = importlib.util.spec_from_file_location('t16_private_d07', source)
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        return helper.load_owned_lifecycle()

    def private_probe_bootstrap(self, name):
        # Existing verified clients build the exact same requests; only their
        # module URL is supplied by the owner of this private service.
        url = f'http://127.0.0.1:{self.port}/v1/chat/completions'
        probe, client = SCR / 'probe_ft_cold32k.py', SCR / name
        return (
            'import importlib.util,runpy,sys;'
            f'spec=importlib.util.spec_from_file_location("probe_ft_cold32k",{str(probe)!r});'
            'mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);'
            f'mod.URL={url!r};sys.modules["probe_ft_cold32k"]=mod;'
            f'sys.argv=[{str(client)!r}]+sys.argv[1:];'
            f'ns=runpy.run_path({str(client)!r},run_name="ft_private_client");'
            f'ns["main"].__globals__["URL"]={url!r};ns["main"]()'
        )

    def stop(self):
        if self.proc is None:
            return
        proc = self.proc
        lifecycle = self.owned_lifecycle()
        current = lifecycle.process_identity(proc.pid)
        if current is not None and any(current[k] != self.service_birth[k] for k in ('pid', 'start_ticks', 'pgid', 'session')):
            raise RuntimeError('owned service birth changed; preserve lock')
        lifecycle.stop_owned_process(proc)
        if lifecycle.owned_group_alive(proc.pid):
            raise RuntimeError('owned process group remains; preserve lock')
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            gpu = command(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'])
            if gpu and all(int(v) < 1000 for v in gpu.splitlines()):
                self.proc = None
                print(f'STOP PASS owned_pid={proc.pid} gpu={gpu}', flush=True)
                return
            time.sleep(2)
        raise RuntimeError('owned service did not release GPU/port')

    def ready(self, arm):
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError('service died during startup')
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{self.port}/health', timeout=5) as response:
                    health = json.load(response)
                if health.get('status') == 'error':
                    raise RuntimeError(f'backend error: {health}')
                if health.get('status') == 'ok':
                    write_new(arm / 'health.json', health)
                    break
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(5)
        else:
            raise TimeoutError('service readiness exceeded 600s')
        payload = {'model': MODEL, 'messages': [{'role': 'user', 'content': 'say ok'}],
                   'max_tokens': 2, 'temperature': 0, 'chat_template_kwargs': {'enable_thinking': False}}
        request = urllib.request.Request(f'http://127.0.0.1:{self.port}/v1/chat/completions',
                                         data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=25) as response:
            result = json.load(response)
        if 'error' in result or not result.get('choices') or not result['choices'][0]['message'].get('content'):
            raise RuntimeError(f'readiness request failed: {result}')
        write_new(arm / 'ready_sayok.json', result)

    def run_arm(self, name, wt, commit, d0, layer_major=True, compare_to=None, cases=None):
        source = self.gate(wt, commit)
        arm = self.directory / name
        arm.mkdir(exist_ok=False)
        env = self.environment(wt, arm, d0)
        argv = ['numactl', '--cpunodebind=0,1', '--interleave=all', FT, 'serve',
                '--model-path', str(ROOT / 'models/Qwen3.8-Flash-Next-NVFP4-overlay'),
                '--served-model-name', MODEL, '--host', '127.0.0.1', '--port', str(self.port),
                '--memory-ratio', '0.88', '--moe-cache-auto', '--moe-prefill-hit-d2d', '--ple-backend', 'pinned',
                '--moe-strategy', 'offload', '--quant-backend', 'moe.nvfp4=triton',
                '--max-running-requests', '2', '--cuda-graph-max-bs', '2', '--kv-reserve-tokens', '49152',
                '--max-seq-len-override', '49152', '--max-prefill-length', '4096', '--enable-cache-report',
                '--enable-special-token-ckpt', '--tool-call-parser', 'qwen3_coder', '--reasoning-parser', 'qwen3']
        if layer_major:
            argv.append('--prefill-layer-major')
        selected = ['PYTHONPATH', 'PYTHONUNBUFFERED', 'VIRTUAL_ENV', 'PATH', 'LD_LIBRARY_PATH']
        if d0:
            selected += ['FT_DEV_D0', 'FT_DEV_D0_PATH']
        (arm / 'SERVE_CMD.txt').write_text('env ' + ' '.join(k + '=' + shlex.quote(env[k]) for k in selected)
                                         + ' ' + shlex.join(argv) + '\n')
        (arm / 'ENV.txt').write_text(time.strftime('%F %T %Z') + '\n' + source + '\n'
                                   + command(['git', '-C', str(wt), 'log', '-1', '--format=%H %s']) + '\n'
                                   + command(['nvidia-smi']) + '\n' + command(['numactl', '-H']) + '\n'
                                   + command(['ps', '-eo', 'pid,pcpu,pmem,comm', '--sort=-pcpu']).split('\n')[0]
                                   + '\n' + '\n'.join(command(['ps', '-eo', 'pid,pcpu,pmem,comm', '--sort=-pcpu']).split('\n')[1:9]) + '\n')
        if getattr(self.options, 'file_dry_run', False):
            # These are the actual arm directory and client output filenames in
            # a separate dry-run tree. No model data or acceptance is produced.
            labels = [case[0] for case in cases or [('det', '', 32052, 128)]]
            names = ['serve.log', 'serve_args.txt', 'owned_process.json', 'health.json',
                     'ready_sayok.json', 'args_checked.json', 'markers.json',
                     'tax.log', 'tax.json', 'business_prefill_events.json', 'prefill_seq.txt']
            names += [label + suffix for label in labels for suffix in ('.json', '.stdout', '.err')]
            if d0:
                names += ['d0_prefill.jsonl', 'prefill_while_alive.json']
            for filename in names:
                path = arm / filename
                with path.open('x', encoding='utf-8') as stream:
                    stream.write('CPU FILE WRITABILITY PROBE ONLY\n')
                with path.open('a', encoding='utf-8') as stream:
                    stream.write('append verified\n')
                if not os.access(path, os.W_OK):
                    raise RuntimeError('dry-run output is not writable: ' + str(path))
            bootstraps = {client: self.private_probe_bootstrap(client)
                          for client in ('cold_eq.py', 'ft_probe_ckpt_tax.py')}
            for client, script in bootstraps.items():
                compile(script, client + '-private-bootstrap', 'exec')
            write_new(arm / 'file_dry_run.json', {
                'source': source, 'port': self.port, 'output_files': names,
                'bootstrap_sha256': {key: hashlib.sha256(value.encode()).hexdigest()
                                     for key, value in bootstraps.items()},
                'service_started': False, 'requests_sent': False,
            })
            return arm
        with (arm / 'serve.log').open('x') as log:
            self.proc = subprocess.Popen(argv, env=env, cwd=wt, stdout=log, stderr=subprocess.STDOUT,
                                         start_new_session=True)
            self.set_status(state='loading', arm=name, service_pid=self.proc.pid)
            print(f'START {name} SPID={self.proc.pid}', flush=True)
            try:
                self.service_birth = self.owned_lifecycle().process_identity(self.proc.pid)
                if self.service_birth is None or self.service_birth['pgid'] != self.proc.pid or self.service_birth['session'] != self.proc.pid:
                    raise RuntimeError('service lacks owned private PGID/session')
                write_new(arm / 'owned_process.json', {'birth': self.service_birth, 'port': self.port})
                self.ready(arm)
                parsed = self.parser(str(arm / 'serve.log'))
                if parsed['_unique_suffix'] != repr('.pid=' + str(self.proc.pid)):
                    raise RuntimeError('parsed service PID identity differs from owned process')
                text = (arm / 'serve.log').read_text()
                position = text.index('Parsed arguments')
                (arm / 'serve_args.txt').write_text('\n'.join(text[position:].splitlines()[:2]) + '\n')
                if compare_to is not None:
                    differences = strict_args(self.parser(str(compare_to / 'serve.log')), parsed, self.allowed)
                    write_new(arm / 'args_checked.json', differences)
                p0 = len(events(arm / 'serve.log'))
                write_new(arm / 'markers.json', {'ready_prefill_count': p0})
                self.set_status(state='probing', arm=name, service_pid=self.proc.pid)
                selected_cases = cases or [('det', self.options.rid + '-det', 32052, 128)]
                for label, cold_id, target, tokens in selected_cases:
                    with (arm / (label + '.stdout')).open('x') as stdout, (arm / (label + '.err')).open('x') as stderr:
                        subprocess.run([PY, '-c', self.private_probe_bootstrap('cold_eq.py'), cold_id, str(arm / (label + '.json')),
                                        str(target), str(tokens)], env=env, cwd=wt, stdout=stdout, stderr=stderr,
                                       check=True, timeout=1800)
                    check_det([arm / (label + '.json')] * 2, target, tokens)
                    if compare_to is not None:
                        check_det([compare_to / (label + '.json'), arm / (label + '.json')], target, tokens)
                with (arm / 'tax.log').open('x') as stdout:
                    subprocess.run([PY, '-c', self.private_probe_bootstrap('ft_probe_ckpt_tax.py'), str(arm / 'tax.json'), name],
                                   env=env, cwd=wt, stdout=stdout, stderr=subprocess.STDOUT, check=True, timeout=1800)
                tax = json.loads((arm / 'tax.json').read_text())
                if tax['reps'] != 5 or any(len(tax[k]) != 5 or any(not isinstance(v, (float, int))
                      or not math.isfinite(v) or v <= 0 for v in tax[k]) for k in ('single', 'multi')):
                    raise ValueError('invalid checkpoint probe output')
                all_events = events(arm / 'serve.log')
                write_new(arm / 'business_prefill_events.json', all_events[p0:])
                (arm / 'prefill_seq.txt').write_text(''.join(f'#new-seq: {bs}, #new-token: {new}, #cached-token: {cached}\n'
                                                           for bs, new, cached in all_events[p0:]))
                if self.proc.poll() is not None:
                    raise RuntimeError('service exited before live telemetry verification')
                if d0:
                    telemetry = rows(arm / 'd0_prefill.jsonl')
                    complete_tail = has_d02_prefill_tail(wt)
                    expected = len(all_events) if complete_tail else len(all_events) - 1
                    if len(telemetry) != expected:
                        raise ValueError(f'prefill telemetry count {len(telemetry)} != {expected}')
                    write_new(arm / 'prefill_while_alive.json', {'service_pid': self.proc.pid,
                              'process_alive': self.proc.poll() is None, 'events': len(all_events), 'rows': len(telemetry),
                              'includes_terminal_prefill': complete_tail,
                              'last_row': telemetry[-1]})
                    if compare_to is not None:
                        check_prefill(compare_to, arm, tail_fix=complete_tail,
                                      parent_tail_fix=prefill_tail_contract(compare_to))
                else:
                    full_log = (arm / 'serve.log').read_text()
                    if list(arm.glob('d0*')) or any(token in full_log for token in ('GDN bank:', 'D0 seg:', 'D0 prefill', 'D0 instrumentation enabled')):
                        raise RuntimeError('default path bank/D0 leakage')
                if compare_to is not None and (compare_to / 'prefill_seq.txt').read_bytes() != (arm / 'prefill_seq.txt').read_bytes():
                    raise ValueError('business prefill sequence differs')
                print(f'PROBE PASS {name} events={len(all_events)}', flush=True)
            finally:
                self.stop()
        return arm

    def compare(self, parent, new, parent_p, new_p, cases=None):
        result = {}
        for label, a, b in (('D0', parent, new), ('PROD', parent_p, new_p)):
            result[label] = {'args': strict_args(self.parser(str(a / 'serve.log')), self.parser(str(b / 'serve.log')), self.allowed)}
            for case, _, target, tokens in cases or [('det', '', 32052, 128)]:
                result[label][case] = check_det([a / (case + '.json'), b / (case + '.json')], target, tokens)
            x, y = (a / 'prefill_seq.txt').read_bytes(), (b / 'prefill_seq.txt').read_bytes()
            if not x or x != y:
                raise ValueError(f'{label} business prefill sequence differs')
            result[label]['sequence'] = 'SAME'
        result['prefill'] = check_prefill(parent, new,
                                        tail_fix=prefill_tail_contract(new),
                                        parent_tail_fix=prefill_tail_contract(parent))
        return result

    def execute(self):
        opts = self.options
        if opts.gate == 'D01':
            parent_wt, parent_commit = ROOT / 'wt/e2base', '3db7b50'
            new_wt, new_commit = ROOT / 'wt/e1r008', 'f91054b'
        elif opts.gate == 'D02':
            parent_wt, parent_commit = ROOT / 'wt/e1r008', 'f91054b'
            new_wt, new_commit = ROOT / 'wt/e1ms', '23f2e2c'
        elif opts.gate == 'D03':
            parent_wt, parent_commit = ROOT / 'wt/e2base', D03_PARENT_COMMIT
            new_wt, new_commit = ROOT / 'wt/e1r003st', opts.candidate_commit
        else:
            parent_wt, parent_commit = ROOT / 'wt/e1r001b', '80943fd'
            new_wt, new_commit = ROOT / 'wt/e2base', '23f2e2c'
        self.gate(parent_wt, parent_commit)
        self.gate(new_wt, new_commit)
        if opts.gate == 'D03':
            parent_extensions = self.compiled_extensions(parent_wt)
            new_extensions = self.compiled_extensions(new_wt)
            parent_hashes = {name: record['sha256'] for name, record in parent_extensions.items()}
            new_hashes = {name: record['sha256'] for name, record in new_extensions.items()}
            if parent_hashes != new_hashes:
                raise ValueError(f'compiled extension mismatch: {parent_hashes} != {new_hashes}')
            self.d03_extensions = {'parent': parent_extensions, 'new': new_extensions}
            print('D03 EXTENSIONS PASS ' + json.dumps(self.d03_extensions, sort_keys=True), flush=True)
        env = self.environment(parent_wt)
        command(['numactl', '--cpunodebind=0,1', '--interleave=all', FT, '--help'], env=env, cwd=parent_wt)
        required = ['cold_eq.py', 'probe_ft_cold32k.py', 'ft_probe_ckpt_tax.py', 'serve_args_diff.py']
        hashes = {name: hashlib.md5((SCR / name).read_bytes()).hexdigest() for name in required}
        if hashes != TOOL_MD5:
            raise ValueError(f'probe source hashes differ from local originals: {hashes}')
        print('PREFLIGHT PASS tools=' + json.dumps(hashes), flush=True)
        if not opts.run:
            return
        if opts.gate != 'D01':
            self.directory.mkdir(exist_ok=False)
        elif not self.directory.is_dir():
            raise ValueError('D01 open directory missing')
        self.lock_take()
        try:
            write_new(self.directory / f'tools_batch{opts.batch}.json', hashes)
            script_copy = self.directory / f'runner_batch{opts.batch}.py'
            with script_copy.open('xb') as target:
                target.write(Path(__file__).read_bytes())
            wrapper = Path(__file__).parent / f'batch{opts.batch}_{opts.rid}_python.sh'
            with (self.directory / f'batch{opts.batch}.sh').open('xb') as target:
                target.write(wrapper.read_bytes())
            self.set_status(state='running')
            suffix = f'_b{opts.batch}'
            if opts.gate == 'D01':
                parent = self.directory / 'PARENT'
                for name in ('SERVE_CMD.txt', 'serve.log', 'serve_args.txt', 'ENV.txt', 'det.json', 'tax.json', 'prefill_seq.txt', 'd0_prefill.jsonl'):
                    if not (parent / name).is_file() or not (parent / name).stat().st_size:
                        raise ValueError(f'PARENT incomplete: {name}')
                if json.loads((parent / 'det.json').read_text())['record']['cold_id'] != opts.rid + '-det':
                    raise ValueError('historical parent cold ID differs')
                write_new(self.directory / f'parent_hashes_batch{opts.batch}.json',
                          {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in parent.iterdir() if p.is_file()})
                new = self.run_arm('NEW' + suffix, new_wt, new_commit, True, compare_to=parent)
            else:
                parent = self.run_arm('PARENT' + suffix, parent_wt, parent_commit, True)
                new = self.run_arm('NEW' + suffix, new_wt, new_commit, True, compare_to=parent)
            parent_p = self.run_arm('PARENT_P' + suffix, parent_wt, parent_commit, False)
            new_p = self.run_arm('NEW_P' + suffix, new_wt, new_commit, False, compare_to=parent_p)
            result = {'layer_major': self.compare(parent, new, parent_p, new_p),
                      'arms': [str(p.name) for p in (parent, new, parent_p, new_p)]}
            if opts.gate == 'D00':
                cases = [('short', opts.rid + '-short', 2000, 128), ('chunked', opts.rid + '-chunked', 32052, 128)]
                a = self.run_arm('CHUNK_PARENT' + suffix, parent_wt, parent_commit, True, False, cases=cases)
                b = self.run_arm('CHUNK_NEW' + suffix, new_wt, new_commit, True, False, a, cases)
                c = self.run_arm('CHUNK_PARENT_P' + suffix, parent_wt, parent_commit, False, False, cases=cases)
                d = self.run_arm('CHUNK_NEW_P' + suffix, new_wt, new_commit, False, False, c, cases)
                result['non_layer_major'] = self.compare(a, b, c, d, cases)
                result['arms'] += [p.name for p in (a, b, c, d)]
            result.update(proposed_verdict='kept', gate=opts.gate, parent_commit=parent_commit, new_commit=new_commit)
            if self.d03_extensions is not None:
                result['compiled_extensions'] = self.d03_extensions
            write_new(self.directory / f'gate_batch{opts.batch}.json', result)
            self.set_status(state='complete', proposed_verdict='kept')
            print('T16 PASS ' + json.dumps(result, ensure_ascii=False), flush=True)
        except BaseException as exc:
            self.set_status(state='failed', error=repr(exc))
            raise
        finally:
            try:
                self.stop()
            finally:
                if self.proc is None:
                    self.lock_release()


def self_test():
    from types import SimpleNamespace
    from unittest.mock import patch, MagicMock

    baseline = {'model_path': "'/model'", 'server_port': '8095', 'special_token_ckpt': 'True', '_unique_suffix': "'.pid=1'"}
    fresh = {**baseline, '_unique_suffix': "'.pid=2'", 'prefill_anchor_cut': 'True'}
    strict_args(baseline, fresh, {'prefill_anchor_cut': 'True'})
    for bad in ({**fresh, 'server_port': '8096'}, {**fresh, '_unique_suffix': "'other.pid=2'"},
                {**fresh, 'mamba_host_slots': '0'}):
        try:
            strict_args(baseline, bad, {'prefill_anchor_cut': 'True'})
        except ValueError:
            pass
        else:
            raise AssertionError('bad argument comparison accepted')
    with tempfile.TemporaryDirectory() as temp:
        a, b = Path(temp) / 'a', Path(temp) / 'b'
        a.mkdir(); b.mkdir()
        log = '#new-seq: 1, #new-token: 12, #cached-token: 0\n#new-seq: 1, #new-token: 64, #cached-token: 4\n'
        for directory in (a, b):
            (directory / 'serve.log').write_text(log)
        first = {'chunk': 0, 'h2d_bytes': 123, 'd2d_bytes': 0, 'seg_reason': 'other', 't_start': 1., 't_end': 2.,
                 'reqs': [{'rid': 0, 'new_tokens': 12, 'cached_tokens': 0}]}
        last = {**first, 'chunk': 1, 'reqs': [{'rid': 1, 'new_tokens': 64, 'cached_tokens': 4}]}
        (a / 'd0_prefill.jsonl').write_text(json.dumps(first) + '\n')
        (b / 'd0_prefill.jsonl').write_text(json.dumps(first) + '\n' + json.dumps(last) + '\n')
        check_prefill(a, b, True)
        for bad in ([first], [first, {**last, 'chunk': 0}], [first, {**last, 'reqs': first['reqs']}],
                    [{**first, 'h2d_bytes': 999}, last]):
            (b / 'd0_prefill.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in bad))
            try:
                check_prefill(a, b, True)
            except ValueError:
                pass
            else:
                raise AssertionError('corrupt telemetry comparison accepted')
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        a, b = root / 'd03-parent', root / 'd03-new'
        a.mkdir(); b.mkdir()
        event_rows = [(1, 100 + i, i) for i in range(13)]
        log = ''.join(f'#new-seq: {bs}, #new-token: {new}, #cached-token: {cached}\n'
                      for bs, new, cached in event_rows)
        records = [
            {'chunk': i, 'h2d_bytes': 10 + i, 'd2d_bytes': i, 'seg_reason': 'other',
             't_start': float(i), 't_end': float(i) + .5,
             'reqs': [{'rid': i, 'new_tokens': new, 'cached_tokens': cached}]}
            for i, (_, new, cached) in enumerate(event_rows)
        ]
        for directory in (a, b):
            (directory / 'serve.log').write_text(log)
            (directory / 'd0_prefill.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in records))
        d03 = check_prefill(a, b, True, True)
        if d03['parent_rows'] != 13 or d03['new_rows'] != 13 or not d03['parent_tail_aligned']:
            raise AssertionError(f'D03 final-tail alignment not preserved: {d03}')
        (b / 'd0_prefill.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in records[:-1]))
        try:
            check_prefill(a, b, True, True)
        except ValueError:
            pass
        else:
            raise AssertionError('D03 missing final prefill tail accepted')
        source = root / 'wt/python/freetoken/moe'
        source.mkdir(parents=True)
        cache = source / 'offload_cache.py'
        cache.write_text('def end_prefill(self):\n    self._d0_flush_chunk()\n')
        if not has_d02_prefill_tail(root / 'wt'):
            raise AssertionError('D02 final-tail source not detected')
        cache.write_text('def begin_prefill(self):\n    pass\n')
        if has_d02_prefill_tail(root / 'wt'):
            raise AssertionError('missing final-tail source accepted')
        runner = object.__new__(Runner)
        runner.options = SimpleNamespace(gate='D03')
        arm = root / 'd03-arm'
        with patch.dict(os.environ, {'FT_DEV_STATE_DUMP_AT': '7', 'FT_DEV_LOGITS_DUMP': '/tmp/logits'}, clear=False):
            env = runner.environment(root / 'wt', arm, d0=True)
        if {'FT_DEV_STATE_DUMP_AT', 'FT_DEV_LOGITS_DUMP'} & env.keys() or arm.exists():
            raise AssertionError('D03 diagnostics leaked into the default T16 environment')
        if env.get('FT_DEV_D0') != '1' or env.get('FT_DEV_D0_PATH') != str(arm / 'd0'):
            raise AssertionError('D0 environment changed for D03')
        d03_args = {**baseline, 'prefill_layer_major': 'True', 'max_prefill_length': '4096',
                    'moe_cache_auto': 'True', 'special_token_ckpt': 'True'}
        strict_args(d03_args, dict(d03_args), {})
        try:
            strict_args(d03_args, {**d03_args, 'dev_state_dump_at': '7'}, {})
        except ValueError:
            pass
        else:
            raise AssertionError('D03 argument pollution accepted')

    runner = object.__new__(Runner)
    runner.token = None
    runner.lock_inode = None
    simulated_wt = Path('/simulation/wt')
    resource = MagicMock()
    resource.__enter__.return_value.connect_ex.return_value = 1

    def simulated_command(argv, **kwargs):
        if argv[0] == 'nvidia-smi':
            return '4'
        if argv[0] == 'ps':
            return f'PID COMMAND\n{os.getpid()} current-executor'
        if argv[0] == 'git':
            return '1234567' if 'rev-parse' in argv else ''
        return str(simulated_wt / 'python/freetoken/__init__.py')

    with patch('socket.socket', return_value=resource), patch.object(Path, 'exists', return_value=False), patch(__name__ + '.command', side_effect=simulated_command):
        runner.gate(simulated_wt, '1234567')

    def full_commit_command(argv, **kwargs):
        if argv[0] == 'git' and 'rev-parse' in argv:
            return D03_PARENT_COMMIT
        return simulated_command(argv, **kwargs)

    with patch('socket.socket', return_value=resource), patch.object(Path, 'exists', return_value=False), patch(__name__ + '.command', side_effect=full_commit_command):
        runner.gate(simulated_wt, D03_PARENT_COMMIT)
        try:
            runner.gate(simulated_wt, D03_CANDIDATE_COMMIT)
        except RuntimeError:
            pass
        else:
            raise AssertionError('full D03 source commit mismatch accepted')
    for kind in ('ps-failed', 'foreign-service', 'occupied-gpu', 'dirty-source'):
        def broken_command(argv, **kwargs):
            if argv[0] == 'ps' and kind == 'ps-failed':
                raise subprocess.CalledProcessError(1, argv)
            if argv[0] == 'ps' and kind == 'foreign-service':
                return 'PID COMMAND\n999 ft serve --model-path elsewhere'
            if argv[0] == 'nvidia-smi' and kind == 'occupied-gpu':
                return '1500'
            if argv[0] == 'git' and 'status' in argv and kind == 'dirty-source':
                return ' M tracked.py'
            return simulated_command(argv, **kwargs)
        with patch('socket.socket', return_value=resource), patch.object(Path, 'exists', return_value=False), patch(__name__ + '.command', side_effect=broken_command):
            try:
                runner.gate(simulated_wt, '1234567')
            except (RuntimeError, subprocess.CalledProcessError):
                pass
            else:
                raise AssertionError(f'resource gate accepted {kind}')
    print('SELFTEST PASS: D01/D02 checks preserved; D03 13-row tails, source-tail detection, exact commits, and default diagnostics rejection verified')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--gate', choices=('D01', 'D02', 'D03', 'D00'))
    parser.add_argument('--rid')
    parser.add_argument('--batch', type=int)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--candidate-commit', default=D03_CANDIDATE_COMMIT,
                        help='D03 candidate full commit SHA (default: committed root candidate)')
    options = parser.parse_args()
    if options.self_test:
        self_test()
        return
    assigned_rids = {'D00': 'E2-pre-gate-D00', 'D01': 'E2-pre-gate-D01',
                     'D02': 'E2-pre-gate-D02', 'D03': 'E2-R002-gate-D03'}
    if not (options.gate and options.rid and options.batch and options.rid == assigned_rids.get(options.gate)):
        parser.error('gate/rid/batch required')
    if options.rid != assigned_rids[options.gate]:
        parser.error('RID does not match assigned gate')
    if options.gate == 'D03' and not re.fullmatch(r'[0-9a-f]{40}', options.candidate_commit):
        parser.error('D03 candidate commit must be an explicit full 40-hex SHA')
    if sys.platform != 'linux':
        parser.error('GPU preflight/run require the Linux test host')
    runner = Runner(options)
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda signum, frame: (_ for _ in ()).throw(InterruptedError(f'signal {signum}')))
    runner.execute()


if __name__ == '__main__':
    main()
