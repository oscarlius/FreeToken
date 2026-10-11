#!/usr/bin/env python3
"""D03 development GPU self-check; explicit --run only, never a formal round."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shlex
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path('/data2/FreeToken')
RUNS = ROOT / 'runs/dev_D03'
PARENT = ROOT / 'wt/e2base'
CANDIDATE = ROOT / 'wt/e1r003st'
PARENT_COMMIT = '23f2e2caa3395837c9474735ffc83321f3b9b5a1'
CANDIDATE_COMMIT = 'c30ae0d7003c3bbbf56867ce74da797332fa7ed5'
TRACE = Path('/data2/_shared/runs/ft_rounds/E1-R003-v2/trace_rev.json')
HISTORICAL_DUMP = Path('/data2/_shared/runs/ft_rounds/E1-R003-stateeq/dump_A')
LEGACY_REPLAY = Path('/data2/_shared/runs/ft_rounds/E1-R003-stateeq/S_A_coldfirst.json')
LOCK = Path('/data2/_shared/gpu.lock')
PY = str(ROOT / 'venv/bin/python')
FT = str(ROOT / 'venv/bin/ft')
MODEL = 'Qwen3.8-Flash-Next-NVFP4'
PORT = 8095
BOUNDARIES = (448, 4544, 8640, 12672, 14144, 18240, 21504)
SELF_CHECK_OUTPUT = ROOT / 'runs/dev_D03/gpu_selfcheck_c30ae0d_urlfix'
G4_RECORD = {'round': 11, 'messages_sha': '3550ee9010430096', 'prompt_tokens': 21976,
             'cached_tokens': 21568, 'recomputed_tokens': 408}


def output(argv, **kwargs):
    return subprocess.check_output(argv, text=True, **kwargs).strip()


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def trace_record(path, expected=G4_RECORD):
    """Select the one historical request spanning 12672; reject schema drift."""
    document = json.loads(Path(path).read_text(encoding='utf-8'))
    rounds = document.get('rounds')
    if not isinstance(rounds, list):
        raise ValueError('historical trace lacks rounds list')
    matches = []
    for item in rounds:
        record, messages = item.get('record'), item.get('messages')
        if not isinstance(record, dict) or not isinstance(messages, list):
            continue
        if all(record.get(key) == value for key, value in expected.items()):
            matches.append((record, messages))
    if len(matches) != 1:
        raise ValueError(f'historical G4 trace binding is ambiguous: {len(matches)} matches')
    record, messages = matches[0]
    if not all(isinstance(message, dict) and isinstance(message.get('role'), str)
               and isinstance(message.get('content'), str) for message in messages):
        raise ValueError('historical messages are malformed')
    canonical = hashlib.sha256(json.dumps(messages, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    if canonical != record['messages_sha']:
        raise ValueError('historical messages_sha does not bind the stored messages')
    if record['prompt_tokens'] < max(BOUNDARIES):
        raise ValueError('selected trace does not cover every requested boundary')
    return document, record, messages


def historical_archive(path):
    rows = [json.loads(line) for line in (Path(path) / 'index.jsonl').read_text(encoding='utf-8').splitlines() if line]
    matches = [row for row in rows if row.get('kind') == 'archive' and row.get('length') == 12672 and str(row.get('uid')) == '1']
    if len(matches) != 1:
        raise ValueError(f'historical archive12672/uid1 is ambiguous: {len(matches)} matches')
    required = {'conv_states', 'recurrent_states', 'slot:ple_conv', 'slot:ple_ngram_ctx'}
    if not required <= set(matches[0].get('files') or {}):
        raise ValueError('historical archive12672 lacks required device state roles')
    return matches[0]


def historical_payload(document, messages, legacy_replay_dict):
    """Reconstruct the archived stateeq replay request, not trace-generation provenance."""
    trace_meta = document.get('meta') or {}
    trace_params, tools = trace_meta.get('params'), document.get('tools')
    if (not isinstance(trace_params, dict) or trace_params.get('model') != MODEL
            or trace_params.get('thinking') is not True or trace_params.get('max_tokens') != 512):
        raise ValueError('historical generation provenance differs from the admitted trace')
    if not isinstance(tools, list) or not tools:
        raise ValueError('historical trace does not retain tool definitions')
    meta = legacy_replay_dict.get('meta') or {}
    params, rounds = meta.get('params'), legacy_replay_dict.get('rounds')
    if (meta.get('trace_path') != str(TRACE) or meta.get('fresh_note') != 'stateeq-resume'
            or not isinstance(params, dict) or params.get('model') != MODEL
            or params.get('thinking') is not True or params.get('thinking_mode') != 'auto'
            or params.get('max_tokens') != 32 or params.get('temperature') != 0
            or params.get('dry_run') is not False or not isinstance(rounds, list) or not rounds):
        raise ValueError('legacy stateeq replay metadata does not define the admitted request')
    first = rounds[0]
    canonical = hashlib.sha256(json.dumps(messages, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    if (first.get('round') != 0 or first.get('message_count') != len(messages)
            or first.get('messages_sha') != canonical or first.get('trace_messages_sha') != canonical
            or first.get('edit_applied') is not False or first.get('error') is not None
            or first.get('prompt_tokens') != G4_RECORD['prompt_tokens']
            or first.get('cached_tokens') != 0 or first.get('recomputed_tokens') != G4_RECORD['prompt_tokens']
            or first.get('completion_tokens') != 32):
        raise ValueError('legacy first replay does not bind the selected historical input')
    return {'model': MODEL, 'messages': messages, 'max_tokens': 32, 'temperature': 0, 'stream': True,
            'stream_options': {'include_usage': True}, 'tools': tools}


def request_sha(payload):
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def raw_binding(path, trace_digest, record, request_digest, tail_k):
    """Read external raw token proof; raw IDs are never manufactured by this runner."""
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    ids = data.get('ids')
    if not isinstance(ids, list) or not ids or any(type(token) is not int or not 0 <= token <= 2**31 - 1 for token in ids):
        raise ValueError('raw ID manifest must contain a non-empty flat int32 ids list')
    packed = b''.join(int(token).to_bytes(4, 'little', signed=True) for token in ids)
    digest = hashlib.sha256(packed).hexdigest()
    if (data.get('candidate_commit') != CANDIDATE_COMMIT
            or data.get('trace_sha256') != trace_digest or data.get('messages_sha') != record['messages_sha']
            or data.get('request_sha256') != request_digest or data.get('raw_ids_sha256') != digest
            or data.get('input_length') != len(ids)):
        raise ValueError('raw ID manifest does not bind exact historical trace/messages/input IDs')
    if not 1 <= tail_k <= 64 or len(ids) < tail_k:
        raise ValueError('tail K must be within 1..64 and not exceed fixed input length')
    return ids, digest


class SelfCheck:
    def __init__(self, args):
        self.args = args
        self.out = SELF_CHECK_OUTPUT
        self.token = None
        self.inode = None
        self.proc = None
        self.parser = runpy.run_path(str(ROOT / 'scripts/serve_args_diff.py'))['parse']

    def environment(self, worktree, arm, *, state=False, logits=False):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith(('FT_DEV_', 'FT_D3_')):
                env.pop(key)
        env.update(PYTHONPATH=str(worktree / 'python'), PYTHONUNBUFFERED='1',
                   VIRTUAL_ENV=str(ROOT / 'venv'))
        env['PATH'] = '/usr/local/cuda-13.0/bin:' + str(ROOT / 'venv/bin') + ':' + env.get('PATH', '')
        env['LD_LIBRARY_PATH'] = '/usr/local/cuda-13.0/lib64:' + env.get('LD_LIBRARY_PATH', '')
        if state:
            env.update(FT_DEV_STATE_DUMP=str(arm / 'state'),
                       FT_DEV_STATE_DUMP_AT=','.join(map(str, BOUNDARIES)))
        if logits:
            env['FT_DEV_LOGITS_DUMP'] = str(arm / 'logits')
        return env

    def gate(self, worktree, commit):
        if LOCK.exists() and not (self.token and LOCK.read_text() == self.token and LOCK.stat().st_ino == self.inode):
            raise RuntimeError('foreign GPU lock exists')
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1', PORT)) == 0:
                raise RuntimeError('port 8095 occupied')
        used = output(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'])
        if not used or any(int(value) >= 1000 for value in used.splitlines()):
            raise RuntimeError(f'GPU occupied: {used}')
        for line in output(['ps', '-eo', 'pid,args']).splitlines()[1:]:
            pid, _, text = line.strip().partition(' ')
            if pid == str(os.getpid()):
                continue
            if re.search(r'ft serve\b|agent_trace\.py (?:replay|generate)\b|cold_eq\.py|d03_gpu_selfcheck\.py.*--run', text):
                raise RuntimeError(f'competing GPU/test process: {line}')
        actual = output(['git', '-C', str(worktree), 'rev-parse', 'HEAD'])
        if actual != commit:
            raise RuntimeError(f'source commit mismatch: {actual} != {commit}')
        if output(['git', '-C', str(worktree), 'status', '--porcelain', '--untracked-files=no']):
            raise RuntimeError('tracked source tree is dirty')
        env = self.environment(worktree, self.out / '_no_arm')
        assertion = ('import freetoken,torch,freetoken.kernel._cpu_moe as a,freetoken.kernel._pinned_tensor as b;'
                     f'assert freetoken.__file__ == {str(worktree / "python/freetoken/__init__.py")!r};'
                     'import hashlib,json; print(json.dumps({"source":freetoken.__file__,"torch":torch.__version__,'
                     '"cuda":torch.version.cuda,"extensions":[{"path":m.__file__,"sha256":hashlib.sha256(open(m.__file__,"rb").read()).hexdigest()} for m in (a,b)]},sort_keys=True))')
        return json.loads(output([PY, '-c', assertion], cwd=worktree, env=env))

    def lock_take(self):
        self.token = json.dumps({'owner': self.out.name, 'card': 'D03', 'pid': os.getpid(),
                                 'since': time.strftime('%F %T %Z')})
        fd = os.open(LOCK, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(self.token)
        self.inode = LOCK.stat().st_ino

    def lock_release(self):
        if self.token and LOCK.exists() and LOCK.stat().st_ino == self.inode and LOCK.read_text() == self.token:
            LOCK.unlink()

    def stop(self):
        if self.proc is None:
            return
        proc, self.proc = self.proc, None
        for sig, timeout in ((signal.SIGINT, 30), (signal.SIGTERM, 15), (signal.SIGKILL, 10)):
            if proc.poll() is not None:
                break
            os.killpg(proc.pid, sig)
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                continue
        if proc.poll() is None:
            raise RuntimeError('owned process did not stop')
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            with socket.socket() as sock:
                port_free = sock.connect_ex(('127.0.0.1', PORT)) != 0
            used = output(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'])
            if port_free and all(int(value) < 1000 for value in used.splitlines()):
                return
            time.sleep(2)
        raise RuntimeError('owned process did not release port/GPU')

    def start(self, name, worktree, *, state=False, logits=False,
              host_slots=0, prefill_chunk=4096, layer_major=True):
        if (type(host_slots) is not int or host_slots not in (0, 32)
                or type(prefill_chunk) is not int or prefill_chunk not in (4096, 8192)
                or type(layer_major) is not bool):
            raise ValueError('unsupported D03 validation service configuration')
        arm = self.out / name
        arm.mkdir()
        if state:
            (arm / 'state').mkdir()
        if logits:
            (arm / 'logits').mkdir()
        env = self.environment(worktree, arm, state=state, logits=logits)
        argv = ['numactl', '--cpunodebind=0,1', '--interleave=all', FT, 'serve', '--model-path',
                str(ROOT / 'models/Qwen3.8-Flash-Next-NVFP4-overlay'), '--served-model-name', MODEL,
                '--host', '127.0.0.1', '--port', str(PORT), '--memory-ratio', '0.88', '--moe-cache-auto',
                '--moe-prefill-hit-d2d', '--ple-backend', 'pinned', '--moe-strategy', 'offload',
                '--quant-backend', 'moe.nvfp4=triton', '--max-running-requests', '2', '--cuda-graph-max-bs', '2',
                '--kv-reserve-tokens', '49152', '--max-seq-len-override', '49152', '--max-prefill-length', str(prefill_chunk),
                '--enable-cache-report', '--enable-special-token-ckpt', '--tool-call-parser', 'qwen3_coder',
                '--reasoning-parser', 'qwen3']
        if layer_major:
            argv.append('--prefill-layer-major')
        argv += ['--mamba-host-slots', str(host_slots)]
        selected = ['PYTHONPATH', 'PYTHONUNBUFFERED', 'VIRTUAL_ENV', 'PATH', 'LD_LIBRARY_PATH']
        selected += ['FT_DEV_STATE_DUMP', 'FT_DEV_STATE_DUMP_AT'] if state else []
        selected += ['FT_DEV_LOGITS_DUMP'] if logits else []
        (arm / 'SERVE_CMD.txt').write_text('env ' + ' '.join(f'{key}={shlex.quote(env[key])}' for key in selected)
                                              + ' ' + shlex.join(argv) + '\n', encoding='utf-8')
        (arm / 'ENV.txt').write_text(time.strftime('%F %T %Z') + '\n' + output(['hostname']) + '\n'
                                     + output(['git', '-C', str(worktree), 'log', '-1', '--format=%H %s']) + '\n'
                                     + output(['nvidia-smi']) + '\n' + output(['numactl', '-H']) + '\n', encoding='utf-8')
        with (arm / 'serve.log').open('x', encoding='utf-8') as log:
            self.proc = subprocess.Popen(argv, cwd=worktree, env=env, stdout=log, stderr=subprocess.STDOUT,
                                         start_new_session=True)
        write_new(arm / 'owned_process.json', {'pid': self.proc.pid, 'pgid': self.proc.pid, 'session': os.getsid(self.proc.pid)})
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError('owned service died during startup')
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/health', timeout=5) as response:
                    health = json.load(response)
                if health.get('status') == 'ok':
                    write_new(arm / 'health.json', health)
                    parsed = self.parser(str(arm / 'serve.log'))
                    try:
                        suffix = ast.literal_eval(parsed.get('_unique_suffix', ''))
                    except (SyntaxError, ValueError) as exc:
                        raise ValueError('parsed service PID suffix is invalid') from exc
                    if suffix != '.pid=' + str(self.proc.pid):
                        raise ValueError('parsed service PID differs from owned process')
                    text = (arm / 'serve.log').read_text(encoding='utf-8', errors='replace')
                    position = text.find('Parsed arguments')
                    if position < 0:
                        raise ValueError('service did not emit parsed arguments')
                    (arm / 'serve_args.txt').write_text('\n'.join(text[position:].splitlines()[:2]) + '\n', encoding='utf-8')
                    if not state and not logits:
                        if {'FT_DEV_STATE_DUMP', 'FT_DEV_STATE_DUMP_AT', 'FT_DEV_LOGITS_DUMP'} & env.keys():
                            raise ValueError('D03 diagnostics leaked into the default environment')
                        if (arm / 'state').exists() or (arm / 'logits').exists():
                            raise ValueError('D03 default path created diagnostic directories')
                    return arm, env
                if health.get('status') == 'error':
                    raise RuntimeError(f'health failure: {health}')
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(5)
        raise TimeoutError('service readiness timeout')

    @staticmethod
    def assert_off_clean(arm):
        arm = Path(arm)
        if (arm / 'state').exists() or (arm / 'logits').exists():
            raise ValueError('D03-off arm created diagnostic directories')
        text = (arm / 'serve.log').read_text(encoding='utf-8', errors='replace')
        if any(marker in text for marker in ('FT_DEV_STATE_DUMP', 'FT_DEV_LOGITS_DUMP', 'D3 state', 'D3 logits')):
            raise ValueError('D03-off arm leaked diagnostic logging')

    @staticmethod
    def terminal_tokens(arm, expected_ids, owned_pgid):
        paths = list((Path(arm) / 'logits').glob('tokens_uid*_pid*.json'))
        if len(paths) != 1:
            raise ValueError('G4 requires one actual terminal token record')
        row = json.loads(paths[0].read_text(encoding='utf-8'))
        generated = row.get('generated_ids')
        if (row.get('schema') != 'ft_dev_tokens/v1' or row.get('prompt_ids') != expected_ids
                or row.get('prompt_length') != len(expected_ids)
                or not isinstance(generated, list) or not generated
                or any(type(i) is not int or not 0 <= i <= 2**31 - 1 for i in generated)
                or type(row.get('uid')) is not int or row['uid'] < 0
                or type(row.get('pid')) is not int or row['pid'] <= 0
                or row.get('finish_reason') not in ('length', 'stop')):
            raise ValueError('G4 terminal record does not bind the actual prompt/UID')
        digest = lambda ids: hashlib.sha256(struct.pack(f'<{len(ids)}i', *ids)).hexdigest()
        for key, ids in [('prompt_ids_sha256_int32le', expected_ids),
                         ('generated_ids_sha256_int32le', generated),
                         ('input_ids_sha256_int32le', expected_ids + generated)]:
            if row.get(key) != digest(ids):
                raise ValueError('G4 terminal token hashes differ')
        if os.getpgid(row['pid']) != owned_pgid:
            raise ValueError('G4 terminal process does not belong to the owned service')
        return {'path': str(paths[0]), 'sha256': sha256(paths[0]), 'uid': row['uid'],
                'pid': row['pid'], 'prompt_sha256_int32le': digest(expected_ids),
                'generated_sha256_int32le': digest(generated), 'generated_length': len(generated)}

    @staticmethod
    def validate_cold(data, cold_id):
        record = data.get('record') or data.get('diag')
        text, events = data.get('text'), data.get('events')
        if not isinstance(record, dict) or record.get('cold_id') != cold_id:
            raise ValueError('cold_eq lacks its exact cold-id diagnostic record')
        if (not isinstance(text, str) or not text or type(events) is not int or events <= 0
                or record.get('cached_tokens') != 0 or record.get('built_tokens') != 32052
                or record.get('completion_tokens') != 128 or record.get('ttft_s') is None
                or record.get('content_chars') not in (None, len(text))
                or record.get('thinking') not in (None, False) or record.get('reasoning_chars') not in (None, 0)):
            raise ValueError('cold_eq did not produce a cold, completed, non-thinking text sample')
        return {'record': record, 'text': text, 'events': events}

    def cold(self, arm, env, cold_id):
        out = arm / 'cold.json'
        with (arm / 'cold.stdout').open('x', encoding='utf-8') as stdout, (arm / 'cold.err').open('x', encoding='utf-8') as stderr:
            subprocess.run([PY, str(ROOT / 'scripts/cold_eq.py'), cold_id, str(out), '32052', '128'], cwd=arm,
                           env=env, stdout=stdout, stderr=stderr, check=True, timeout=1800)
        return self.validate_cold(json.loads(out.read_text(encoding='utf-8')), cold_id)

    @staticmethod
    def logits_capture_argv(arm, prefix, suffix):
        return [PY, str(CANDIDATE / 'scripts/logits_probe.py'), 'capture', '--base-url', f'http://127.0.0.1:{PORT}',
                '--model', MODEL, '--prefix', str(prefix), '--suffix', str(suffix), '--dump', str(Path(arm) / 'logits')]

    @staticmethod
    def verify_g5_compare(path):
        lines = [line for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]
        if not lines:
            raise ValueError('G5 logits comparison produced no JSON')
        result = json.loads(lines[-1])
        peer = result.get('peer_vs_recompute')
        if not isinstance(peer, dict) or peer.get('bitwise_equal') is not True:
            raise ValueError('independent G5 logits are not bitwise equal')
        return result

    def chat(self, arm, payload):
        write_new(arm / 'historical_request.json', payload)
        request = urllib.request.Request(f'http://127.0.0.1:{PORT}/v1/chat/completions',
                                         data=json.dumps(payload, ensure_ascii=False).encode(),
                                         headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=3600) as response, (arm / 'historical_response.sse').open('xb') as sink:
            for line in response:
                sink.write(line)
        if not (arm / 'historical_response.sse').stat().st_size:
            raise ValueError('historical request produced no stream evidence')

    def logits(self, arm, env, raw_manifest, trace_digest, record, request_digest):
        ids, digest = raw_binding(raw_manifest, trace_digest, record, request_digest, self.args.tail_k)
        # logits_probe composes prefix+suffix; write each input once and preserve the full byte sequence.
        prefix, suffix = ids[:-self.args.tail_k], ids[-self.args.tail_k:]
        prefix_path, suffix_path = arm / 'raw_prefix_ids.json', arm / 'raw_tail_ids.json'
        write_new(prefix_path, prefix)
        write_new(suffix_path, suffix)
        capture = self.logits_capture_argv(arm, prefix_path, suffix_path)
        with (arm / 'logits_capture.log').open('x', encoding='utf-8') as sink:
            subprocess.run(capture, cwd=CANDIDATE, env=env, stdout=sink, stderr=subprocess.STDOUT, check=True, timeout=3600)
        return {'arm': str(arm), 'raw_ids_sha256': digest, 'input_length': len(ids), 'tail_k': self.args.tail_k}

    def run(self):
        parent = self.gate(PARENT, PARENT_COMMIT)
        candidate = self.gate(CANDIDATE, CANDIDATE_COMMIT)
        if [item['sha256'] for item in parent['extensions']] != [item['sha256'] for item in candidate['extensions']]:
            raise ValueError('parent/candidate compiled extensions differ')
        trace, record, messages = trace_record(self.args.trace)
        legacy_replay = json.loads(LEGACY_REPLAY.read_text(encoding='utf-8'))
        payload = historical_payload(trace, messages, legacy_replay)
        payload_digest = request_sha(payload)
        trace_digest = sha256(self.args.trace)
        actual_ids, _ = raw_binding(self.args.raw_ids, trace_digest, record, payload_digest, self.args.tail_k)
        archive = historical_archive(HISTORICAL_DUMP)
        if self.out.exists():
            raise FileExistsError(f'development output already exists: {self.out}')
        self.lock_take()
        created = False
        try:
            self.out.mkdir(); created = True
            runner_source = Path(__file__).read_bytes()
            with (self.out / Path(__file__).name).open('xb') as archived:
                archived.write(runner_source)
            (self.out / 'runner_sha256.txt').write_text(hashlib.sha256(runner_source).hexdigest() + '\n', encoding='utf-8')
            write_new(self.out / 'admission.json', {'parent': parent, 'candidate': candidate,
                      'parent_commit': PARENT_COMMIT, 'candidate_commit': CANDIDATE_COMMIT,
                      'trace': str(self.args.trace), 'trace_sha256': sha256(self.args.trace),
                      'historical_dump': str(HISTORICAL_DUMP), 'historical_dump_index_sha256': sha256(HISTORICAL_DUMP / 'index.jsonl'),
                      'legacy_replay': str(LEGACY_REPLAY), 'legacy_replay_sha256': sha256(LEGACY_REPLAY),
                      'historical_archive12672_uid1': archive})
            write_new(self.out / 'trace_binding.json', {'record': record, 'messages_sha': record['messages_sha'],
                      'trace_sha256': sha256(self.args.trace), 'request_sha256': payload_digest,
                      'legacy_replay': str(LEGACY_REPLAY), 'legacy_replay_sha256': sha256(LEGACY_REPLAY),
                      'legacy_dump_gap': 'dump_A/index.jsonl archive row lacks messages_sha; trace selection is evidence, not direct legacy-row binding'})
            p_arm, p_env = self.start('parent_off', PARENT)
            try:
                parent_cold = self.cold(p_arm, p_env, 'D03-cold-parity')
                self.assert_off_clean(p_arm)
            finally: self.stop()
            off_arm, off_env = self.start('candidate_off', CANDIDATE)
            try:
                off_cold = self.cold(off_arm, off_env, 'D03-cold-parity')
                self.assert_off_clean(off_arm)
            finally: self.stop()
            on_cold_arm, on_cold_env = self.start('candidate_on_state_logits', CANDIDATE, state=True, logits=True)
            try:
                on_cold = self.cold(on_cold_arm, on_cold_env, 'D03-cold-parity')
                if (parent_cold['text'].encode('utf-8') != off_cold['text'].encode('utf-8')
                        or off_cold['text'].encode('utf-8') != on_cold['text'].encode('utf-8')):
                    raise ValueError('cold_eq output bytes differ')
            finally: self.stop()
            boundary_arm, boundary_env = self.start('candidate_boundary', CANDIDATE, state=True, logits=True)
            try:
                self.chat(boundary_arm, payload)
                g4_tokens = self.terminal_tokens(boundary_arm, actual_ids, self.proc.pid)
                write_new(boundary_arm / 'terminal_binding.json', g4_tokens)
                index = boundary_arm / 'state/index.jsonl'
                rows = [json.loads(line) for line in index.read_text(encoding='utf-8').splitlines() if line]
                boundary_rows = [row for row in rows if row.get('kind') == 'boundary']
                found = {row.get('length') for row in boundary_rows}
                if (found != set(BOUNDARIES) or len(boundary_rows) != len(BOUNDARIES)
                        or any(str(row.get('uid')) != str(g4_tokens['uid']) for row in boundary_rows)):
                    raise ValueError(f'boundary records differ: lengths={sorted(found)} uids={[row.get("uid") for row in boundary_rows]}')
                for row in boundary_rows:
                    prefix = actual_ids[:row['length']]
                    prefix_sha = hashlib.sha256(struct.pack(f'<{len(prefix)}i', *prefix)).hexdigest()
                    if row.get('extra', {}).get('input_prefix_sha256') != prefix_sha:
                        raise ValueError('G4 boundary prefix differs from its actual raw input')
                envelope = [PY, str(CANDIDATE / 'scripts/state_envelope.py'), '--ref', str(HISTORICAL_DUMP), '--test', str(boundary_arm / 'state'),
                            '--out', str(boundary_arm / 'g4_envelope.csv'), '--lengths', '12672', '--kind-ref', 'archive', '--kind-test', 'boundary',
                            '--uid-ref', '1', '--uid-test', str(g4_tokens['uid']), '--tier', 'device']
                subprocess.run(envelope, cwd=CANDIDATE, env=boundary_env, check=True, timeout=1800)
            finally: self.stop()
            captures = []
            for name in ('candidate_logits_a', 'candidate_logits_b'):
                arm, env = self.start(name, CANDIDATE, logits=True)
                try: captures.append(self.logits(arm, env, self.args.raw_ids, trace_digest, record, payload_digest))
                finally: self.stop()
            comparison = [PY, str(CANDIDATE / 'scripts/logits_probe.py'), 'compare', '--recompute', str(Path(captures[0]['arm']) / 'logits'),
                          '--peer', str(Path(captures[1]['arm']) / 'logits')]
            compare_log = self.out / 'g5_logits_compare.log'
            with compare_log.open('x', encoding='utf-8') as sink:
                subprocess.run(comparison, cwd=CANDIDATE, check=True, stdout=sink, stderr=subprocess.STDOUT, timeout=1800)
            self.verify_g5_compare(compare_log)
            write_new(self.out / 'selfcheck.json', {'mode': 'development_selfcheck_not_acceptance', 'cold_eq': 'parent_off=candidate_off=candidate_on_state_logits (UTF-8 byte equal)',
                      'g4_boundaries': list(BOUNDARIES), 'g4_terminal_binding': g4_tokens, 'g5': captures})
        except BaseException as exc:
            if created: write_new(self.out / 'selfcheck_error.json', {'error': repr(exc)})
            raise
        finally:
            try: self.stop()
            finally:
                self.lock_release()
                if created:
                    files = sorted(path for path in self.out.rglob('*') if path.is_file() and path.name != 'MANIFEST.sha256')
                    (self.out / 'MANIFEST.sha256').write_text(''.join(f'{sha256(path)}  {path.relative_to(self.out)}\n' for path in files), encoding='utf-8')


def self_test():
    from types import SimpleNamespace
    from unittest.mock import patch

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        messages = [{'role': 'user', 'content': 'historic'}]
        digest = hashlib.sha256(json.dumps(messages, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
        doc = {'rounds': [{'messages': messages, 'record': {**G4_RECORD, 'messages_sha': digest}}]}
        trace = root / 'trace.json'; trace.write_text(json.dumps(doc), encoding='utf-8')
        _, record, got = trace_record(trace, {**G4_RECORD, 'messages_sha': digest})
        assert got == messages and record['round'] == G4_RECORD['round']
        provenance = {'meta': {'params': {'model': MODEL, 'thinking': True, 'max_tokens': 512, 'temperature': 0}},
                      'tools': [{'type': 'function'}]}
        legacy = {'meta': {'trace_path': str(TRACE), 'fresh_note': 'stateeq-resume',
                            'params': {'model': MODEL, 'thinking': True, 'thinking_mode': 'auto', 'max_tokens': 32,
                                       'temperature': 0, 'dry_run': False}},
                  'rounds': [{'round': 0, 'message_count': 1, 'messages_sha': digest, 'trace_messages_sha': digest,
                              'edit_applied': False, 'error': None, 'prompt_tokens': G4_RECORD['prompt_tokens'],
                              'cached_tokens': 0, 'recomputed_tokens': G4_RECORD['prompt_tokens'], 'completion_tokens': 32}]}
        payload = historical_payload(provenance, messages, legacy)
        assert provenance['meta']['params']['max_tokens'] == 512 and payload['max_tokens'] == 32
        assert payload['messages'] == messages and payload['tools'] and request_sha(payload)
        for bad_legacy in ({**legacy, 'rounds': [{**legacy['rounds'][0], 'messages_sha': '0' * 16}]},
                           {**legacy, 'meta': {**legacy['meta'], 'params': {**legacy['meta']['params'], 'max_tokens': 200}}}):
            try: historical_payload(provenance, messages, bad_legacy)
            except ValueError: pass
            else: raise AssertionError('mismatched legacy replay evidence accepted')
        off = root / 'off'; off.mkdir(); (off / 'serve.log').write_text('normal service')
        SelfCheck.assert_off_clean(off)
        (off / 'state').mkdir()
        try: SelfCheck.assert_off_clean(off)
        except ValueError: pass
        else: raise AssertionError('post-request D03-off directory leakage accepted')
        ids = [1, 2, 3, 4]
        packed = b''.join(value.to_bytes(4, 'little', signed=True) for value in ids)
        manifest = root / 'ids.json'
        manifest.write_text(json.dumps({'ids': ids, 'candidate_commit': CANDIDATE_COMMIT, 'trace_sha256': sha256(trace), 'messages_sha': digest,
                                        'request_sha256': request_sha({'fixture': True}), 'raw_ids_sha256': hashlib.sha256(packed).hexdigest(), 'input_length': 4}), encoding='utf-8')
        assert raw_binding(manifest, sha256(trace), record, request_sha({'fixture': True}), 4)[0] == ids
        stale = json.loads(manifest.read_text()); stale['candidate_commit'] = '0' * 40
        stale_path = root / 'stale.json'; stale_path.write_text(json.dumps(stale), encoding='utf-8')
        try: raw_binding(stale_path, sha256(trace), record, request_sha({'fixture': True}), 4)
        except ValueError: pass
        else: raise AssertionError('stale candidate raw-ID proof accepted')
        bad = json.loads(manifest.read_text()); bad['messages_sha'] = '0' * 16; manifest.write_text(json.dumps(bad), encoding='utf-8')
        try: raw_binding(manifest, sha256(trace), record, request_sha({'fixture': True}), 4)
        except ValueError: pass
        else: raise AssertionError('unbound raw IDs accepted')
        cold = {'diag': {'cold_id': 'cold', 'cached_tokens': 0, 'built_tokens': 32052,
                         'completion_tokens': 128, 'ttft_s': 1.0, 'content_chars': 2,
                         'thinking': False, 'reasoning_chars': 0}, 'text': 'ok', 'events': 2}
        assert SelfCheck.validate_cold(cold, 'cold')['text'] == 'ok'
        try: SelfCheck.validate_cold({**cold, 'diag': {**cold['diag'], 'thinking': True}}, 'cold')
        except ValueError: pass
        else: raise AssertionError('thinking cold output accepted')
        runner = object.__new__(SelfCheck)
        runner.args = SimpleNamespace(tail_k=2)
        arm = root / 'arm'; arm.mkdir()
        with patch(__name__ + '.raw_binding', return_value=([10, 11, 12, 13], 'sha')) as bind, patch('subprocess.run') as run:
            got = runner.logits(arm, {}, root / 'manifest.json', 'trace', {'messages_sha': 'm'}, 'request')
        assert got['arm'] == str(arm) and bind.call_count == 1 and run.call_count == 1
        assert json.loads((arm / 'raw_prefix_ids.json').read_text()) == [10, 11]
        assert json.loads((arm / 'raw_tail_ids.json').read_text()) == [12, 13]
        argv = run.call_args.args[0]
        assert argv[argv.index('--prefix') + 1] == str(arm / 'raw_prefix_ids.json')
        assert argv[argv.index('--suffix') + 1] == str(arm / 'raw_tail_ids.json')
        good = root / 'good.log'; good.write_text(json.dumps({'peer_vs_recompute': {'bitwise_equal': True}}) + '\n')
        assert SelfCheck.verify_g5_compare(good)['peer_vs_recompute']['bitwise_equal']
        bad_compare = root / 'bad.log'; bad_compare.write_text(json.dumps({'peer_vs_recompute': {'bitwise_equal': False}}) + '\n')
        try: SelfCheck.verify_g5_compare(bad_compare)
        except ValueError: pass
        else: raise AssertionError('non-bitwise G5 comparison accepted')
        json.dumps({'g5': [got]}, allow_nan=False)
        token_arm = root / 'token_arm'; (token_arm / 'logits').mkdir(parents=True)
        prompt, generated = [10, 11], [12]
        digest_ids = lambda values: hashlib.sha256(struct.pack(f'<{len(values)}i', *values)).hexdigest()
        token_path = token_arm / 'logits/tokens_uid0_pid12.json'
        token_path.write_text(json.dumps({'schema': 'ft_dev_tokens/v1', 'uid': 0, 'pid': 12,
            'prompt_ids': prompt, 'generated_ids': generated, 'prompt_length': 2, 'finish_reason': 'length',
            'prompt_ids_sha256_int32le': digest_ids(prompt), 'generated_ids_sha256_int32le': digest_ids(generated),
            'input_ids_sha256_int32le': digest_ids(prompt + generated)}), encoding='utf-8')
        with patch('os.getpgid', return_value=7, create=True):
            assert SelfCheck.terminal_tokens(token_arm, prompt, 7)['uid'] == 0
            try: SelfCheck.terminal_tokens(token_arm, prompt, 8)
            except ValueError: pass
            else: raise AssertionError('unowned terminal PID accepted')
    print('SELFTEST PASS: trace/raw binding, cold schema, one-write capture, G5 bitwise, and JSON result checks fail closed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--trace', type=Path, default=TRACE)
    parser.add_argument('--raw-ids', type=Path, help='required G5 raw-ID manifest bound to the historical trace')
    parser.add_argument('--tail-k', type=int, default=64)
    args = parser.parse_args()
    if args.self_test:
        self_test(); return
    if not args.run:
        parser.error('--run is required; this tool never starts a service by default')
    if sys.platform != 'linux':
        parser.error('--run requires the Linux GPU host')
    if args.raw_ids is None:
        parser.error('--raw-ids is required to prevent invented G5 inputs')
    SelfCheck(args).run()


if __name__ == '__main__':
    main()
