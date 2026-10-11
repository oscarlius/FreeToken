"""T00 baseline measurement; starts only after a closed, independently reviewed D00 gate."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import signal
import socket
import subprocess
import sys
import time

from t16_runner import Runner, ROOT, ROUNDS, SCR, PY, FT, MODEL, LOCK, TOOL_MD5
from t16_runner import command, write_new, rows, events, strict_args

COMMIT = '23f2e2c'
WT = ROOT / 'wt/e2base'
RAW = ROOT / 'runs/cold32k_20261002'
PERF_MD5 = '3f2e657b7b3aa27fa97851f24ad32c92'


def finite_positive(value):
    return type(value) in (float, int) and math.isfinite(value) and value > 0


def validate_cold(value, cold_id, target):
    record, diagnostic = value['record'], value['diag']
    if (record['cold_id'] != cold_id or record['cached_tokens'] != 0
            or abs(record['prompt_tokens'] - target) >= 2000
            or not 1 < record['completion_tokens'] <= 128
            or not finite_positive(record['ttft_s']) or not finite_positive(record['decode_tps'])
            or diagnostic['built_tokens'] != target or diagnostic['enable_thinking'] is not False
            or diagnostic['content_events'] < 2 or not diagnostic['cache_ok']
            or not diagnostic['prompt_len_ok'] or not diagnostic['decode_ok']):
        raise ValueError(f'invalid cold sample: {value}')
    return record


def classify_tax(value):
    if value['reps'] != 5:
        raise ValueError('checkpoint probe must contain one cold and four hot pairs')
    for key in ('single', 'multi'):
        if len(value[key]) != 5 or not all(finite_positive(v) for v in value[key]):
            raise ValueError(f'invalid tax {key}')
    return {'cold': {key: value[key][0] for key in ('single', 'multi')},
            'hot': {key: value[key][1:] for key in ('single', 'multi')}}


def validate_d0(arm):
    sequence = events(arm / 'serve.log')
    records = rows(arm / 'd0_prefill.jsonl')
    if len(sequence) != len(records):
        raise ValueError('D0 final row missing or extra rows')
    for i, record in enumerate(records):
        reqs = record['reqs']
        actual = (len(reqs), sum(r['new_tokens'] for r in reqs), sum(r['cached_tokens'] for r in reqs))
        if (record['chunk'] != i or actual != sequence[i] or not reqs
                or record['seg_reason'] not in ('anchor_cap', 'token_budget', 'layer_major_whole', 'continuation', 'other')
                or any(type(record[k]) is not int or record[k] < 0 for k in ('h2d_bytes', 'd2d_bytes'))
                or not math.isfinite(record['t_start']) or not math.isfinite(record['t_end'])
                or record['t_end'] < record['t_start']):
            raise ValueError(f'D0 metadata mismatch: row {i}')
    return {'events': len(sequence), 'rows': len(records),
            'h2d_bytes': [r['h2d_bytes'] for r in records],
            'd2d_bytes': [r['d2d_bytes'] for r in records],
            'reasons': [r['seg_reason'] for r in records]}


class BaselineRunner(Runner):
    def gate(self, wt, commit):
        if getattr(self,'seed_sha256',None) is not None:
            seed = ROOT / 'wt/e1r003/seed_45k.txt'
            if hashlib.sha256(seed.read_bytes()).hexdigest() != self.seed_sha256:
                raise ValueError('checkpoint probe immutable seed changed')
        source = super().gate(wt, commit)
        gpu = command(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'])
        if any(int(v) > 100 for v in gpu.splitlines()):
            raise RuntimeError(f'T00 requires GPU memory <=100 MiB: {gpu}')
        for line in command(['ps', '-eo', 'pid,args']).splitlines()[1:]:
            pid, _, text = line.strip().partition(' ')
            if int(pid) != os.getpid() and re.search(r't00_runner\.py.*--run|ft_perf_decomp\.py run', text):
                raise RuntimeError(f'competing T00/performance process: {line}')
        return source

    def lock_take(self):
        self.token = json.dumps({'owner': self.options.rid, 'card': 'T00', 'pid': os.getpid(),
                                 'since': time.strftime('%F %T %Z')})
        fd = os.open(LOCK, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, 'w') as handle:
            handle.write(self.token)
        self.lock_inode = LOCK.stat().st_ino

    def prerequisites(self):
        full_commit = command(['git', '-C', str(WT), 'rev-parse', 'HEAD'])
        tag = command(['git', '-C', str(WT), 'describe', '--tags', '--exact-match'])
        if tag != 'E2-base@' + COMMIT or full_commit[:7] != COMMIT:
            raise RuntimeError('E2-base exact tag/commit not admitted')
        directory = ROUNDS / 'E2-pre-gate-D00'
        gate = json.loads((directory / 'gate_batch26.json').read_text())
        review = json.loads((directory / 'review_batch26.json').read_text())
        status = json.loads((directory / 'status_batch26.json').read_text())
        if (gate['new_commit'] != COMMIT or gate['proposed_verdict'] != 'kept'
                or review.get('verdict') != 'PASS' or status['state'] != 'complete'):
            raise RuntimeError('D00 passing gate and independent review required')
        manifest = directory / 'MANIFEST.sha256'
        if not (directory / 'round.json').is_file() or directory.stat().st_mode & 0o222:
            raise RuntimeError('D00 gate must be closed read-only')
        for line in manifest.read_text().splitlines():
            expected, relative = line.split('  ', 1)
            if hashlib.sha256((directory / relative).read_bytes()).hexdigest() != expected:
                raise ValueError(f'D00 artifact digest differs: {relative}')
        hashes = {name: hashlib.md5((SCR / name).read_bytes()).hexdigest() for name in TOOL_MD5}
        if hashes != TOOL_MD5 or hashlib.md5((SCR / 'ft_perf_decomp.py').read_bytes()).hexdigest() != PERF_MD5:
            raise ValueError('original probe hash differs')
        seed = ROOT / 'wt/e1r003/seed_45k.txt'
        if not seed.is_file() or not seed.stat().st_size:
            raise ValueError('checkpoint probe seed missing')
        self.seed_sha256 = hashlib.sha256(seed.read_bytes()).hexdigest()
        self.gate(WT, COMMIT)
        command(['taskset', '-c', '1,3-47', FT, '--help'], env=self.environment(WT), cwd=WT)
        return {'commit': full_commit, 'code_version': tag,
                'gate_manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest(),
                'seed':{'path':str(seed),'sha256':self.seed_sha256},
                'probe_md5': {**hashes, 'ft_perf_decomp.py': PERF_MD5}}

    def cold(self, arm, env, label, target):
        cold_id = 'e2r000-' + label
        raw = RAW / (cold_id + '.json')
        if raw.exists():
            raise ValueError(f'original probe destination already exists: {raw}')
        prefill_start = len(events(arm / 'serve.log'))
        stdout = arm / (label + '.stdout.json')
        with stdout.open('x') as out, (arm / (label + '.err')).open('x') as err:
            subprocess.run([PY, str(SCR / 'probe_ft_cold32k.py'), cold_id, str(target), '128', 'nothink'],
                           env=env, cwd=WT, stdout=out, stderr=err, check=True, timeout=1800)
        value = json.loads(stdout.read_text())
        record = validate_cold(value, cold_id, target)
        raw_bytes = raw.read_bytes()
        if value['diag']['out_path'] != str(raw) or json.loads(raw_bytes) != record:
            raise ValueError('probe stdout/raw file disagree')
        destination = arm / (label + '.json')
        with destination.open('xb') as handle:
            handle.write(raw_bytes)
        source_sha = hashlib.sha256(raw_bytes).hexdigest()
        destination_sha = hashlib.sha256(destination.read_bytes()).hexdigest()
        if source_sha != destination_sha:
            raise ValueError('copied probe digest differs')
        write_new(arm / (label + '.source.json'), {'path': str(raw),
                  'source_sha256': source_sha, 'destination_sha256': destination_sha})
        prefill_end = len(events(arm / 'serve.log'))
        if prefill_end <= prefill_start:
            raise ValueError('cold probe has no new prefill event')
        write_new(arm / (label + '.prefill_range.json'), {'start':prefill_start,'end':prefill_end})
        print(f'SAMPLE {label} {json.dumps(record)}', flush=True)
        return record

    def run_baseline_arm(self, name, mode, ckpt=False, d0=False, reference=None):
        source = self.gate(WT, COMMIT)
        arm = self.directory / name
        arm.mkdir(exist_ok=False)
        env = self.environment(WT, arm, d0)
        argv = ['taskset', '-c', '1,3-47', FT, 'serve', '--model-path',
                str(ROOT / 'models/Qwen3.8-Flash-Next-NVFP4-overlay'), '--served-model-name', MODEL,
                '--host', '0.0.0.0', '--port', '8095', '--memory-ratio', '0.88', '--moe-cache-auto',
                '--moe-prefill-hit-d2d', '--ple-backend', 'pinned', '--moe-strategy', 'offload',
                '--quant-backend', 'moe.nvfp4=triton', '--max-running-requests', '2', '--cuda-graph-max-bs', '2',
                '--kv-reserve-tokens', '73728', '--max-seq-len-override', '73728', '--max-prefill-length', '4096', '--enable-cache-report',
                '--tool-call-parser', 'qwen3_coder', '--reasoning-parser', 'qwen3', '--prefill-layer-major']
        if ckpt:
            argv.append('--enable-special-token-ckpt')
        selected = ['PYTHONPATH', 'PYTHONUNBUFFERED', 'VIRTUAL_ENV', 'PATH', 'LD_LIBRARY_PATH']
        if d0:
            selected += ['FT_DEV_D0', 'FT_DEV_D0_PATH']
        (arm / 'SERVE_CMD.txt').write_text('env ' + ' '.join(k + '=' + shlex.quote(env[k]) for k in selected)
                                         + ' ' + shlex.join(argv) + '\n')
        (arm / 'ENV.txt').write_text(time.strftime('%F %T %Z') + '\n' + source + '\n'
                                   + command(['git', '-C', str(WT), 'log', '-1', '--format=%H %s']) + '\n'
                                   + command(['nvidia-smi']) + '\n' + command(['numactl', '-H']) + '\n'
                                   + '\n'.join(command(['ps', '-eo', 'pid,pcpu,pmem,comm', '--sort=-pcpu']).splitlines()[:9]) + '\n')
        artifacts = command([PY, '-c', 'import hashlib,json,freetoken.kernel._cpu_moe as a,freetoken.kernel._pinned_tensor as b;'
                             'print(json.dumps([{\"path\":m.__file__,\"sha256\":hashlib.sha256(open(m.__file__,\"rb\").read()).hexdigest()} for m in (a,b)]))'],
                            env=env, cwd=WT)
        write_new(arm / 'compiled_extensions.json', json.loads(artifacts))
        measurements = {}
        with (arm / 'serve.log').open('x') as log:
            self.proc = subprocess.Popen(argv, env=env, cwd=WT, stdout=log, stderr=subprocess.STDOUT,start_new_session=True)
            self.set_status(state='loading', arm=name, service_pid=self.proc.pid)
            print(f'START {name} SPID={self.proc.pid}', flush=True)
            try:
                if os.getpgid(self.proc.pid) != self.proc.pid or os.getsid(self.proc.pid) != self.proc.pid:
                    raise RuntimeError('service process-group ownership mismatch')
                self.ready(arm)
                parsed = self.parser(str(arm / 'serve.log'))
                if parsed['_unique_suffix'] != repr('.pid=' + str(self.proc.pid)) or parsed['special_token_ckpt'] != str(ckpt):
                    raise ValueError('owned service PID/checkpoint argument differs')
                text = (arm / 'serve.log').read_text()
                (arm / 'serve_args.txt').write_text('\n'.join(text[text.index('Parsed arguments'):].splitlines()[:2]) + '\n')
                if reference:
                    old = self.parser(str(reference / 'serve.log'))
                    intended = dict(parsed)
                    intended['special_token_ckpt'] = old['special_token_ckpt']
                    diff = strict_args(old, intended, {})
                    if parsed['special_token_ckpt'] != old['special_token_ckpt']:
                        diff['special_token_ckpt'] = [old['special_token_ckpt'], parsed['special_token_ckpt']]
                    write_new(arm / 'args_checked.json', diff)
                self.set_status(state='probing', arm=name, service_pid=self.proc.pid)
                if mode == 'production':
                    measurements['cold32'] = [self.cold(arm, env, 'prod32-' + str(i), 32052) for i in range(4)]
                    with (arm / 'short.stdout').open('x') as out, (arm / 'short.err').open('x') as err:
                        subprocess.run([PY, str(SCR / 'ft_perf_decomp.py'), 'run', '--fixture', 'short', '--repeat', '3',
                                        '--out', str(arm / 'short.jsonl')], env=env,cwd=WT,stdout=out,stderr=err,check=True,timeout=1800)
                    short = rows(arm / 'short.jsonl')
                    if len(short) != 3 or any(not r['expect_ok'] or r['prompt_tokens'] != 23 or r['cached_tokens'] != 0
                         or not r['completion_text'] or not finite_positive(r['decode_tps']) or not finite_positive(r['ttft_s']) for r in short):
                        raise ValueError('historical short fixture invalid')
                    measurements['short'] = short
                    measurements['cold64'] = [self.cold(arm, env, 'prod64-' + str(i), 65412) for i in range(2)]
                elif mode == 'd0':
                    measurements['cold32'] = [self.cold(arm, env, 'd0-32-' + str(i), 32052) for i in range(2)]
                elif mode == 'tax':
                    with (arm / 'tax.log').open('x') as out:
                        subprocess.run([PY, str(SCR / 'ft_probe_ckpt_tax.py'), str(arm / 'tax.json'), name],
                                       env=env,cwd=WT,stdout=out,stderr=subprocess.STDOUT,check=True,timeout=1800)
                    measurements['tax'] = classify_tax(json.loads((arm / 'tax.json').read_text()))
                else:
                    raise ValueError('unknown measurement arm mode')
                if self.proc.poll() is not None:
                    raise RuntimeError('service exited before live verification')
                if d0:
                    write_new(arm / 'd0_while_alive.json', {'service_pid': self.proc.pid,'process_alive': True,
                                                          **validate_d0(arm)})
                elif list(arm.glob('d0*')) or any(token in (arm / 'serve.log').read_text() for token in
                     ('GDN bank:', 'D0 seg:', 'D0 prefill', 'D0 instrumentation enabled')):
                    raise RuntimeError('D0-off diagnostic leakage')
                write_new(arm / 'measurements.json', measurements)
                print(f'ARM PASS {name}', flush=True)
            finally:
                self.stop()
        return arm

    def execute(self):
        admission = self.prerequisites()
        print('T00 PREFLIGHT PASS ' + json.dumps(admission), flush=True)
        if not self.options.run:
            return
        if self.directory.exists():
            raise ValueError('assigned T00 round directory already exists')
        self.lock_take()
        created = False
        try:
            self.directory.mkdir(exist_ok=False)
            created = True
            write_new(self.directory / 'admission.json', admission)
            for source, destination in [(Path(__file__), 'runner.py'),
                                         (Path(__file__).with_name('t16_runner.py'), 't16_runner.py'),
                                         (Path(__file__).with_name(f'batch{self.options.batch}_E2-R000_python.sh'), 'batch.sh')]:
                with (self.directory / destination).open('xb') as dst:
                    dst.write(source.read_bytes())
            self.set_status(state='running')
            prod = self.run_baseline_arm('PRODUCTION', 'production', ckpt=True)
            arms = [prod, self.run_baseline_arm('D0', 'd0', ckpt=True, d0=True, reference=prod)]
            for i in range(3):
                arms.append(self.run_baseline_arm(f'OFF_p{i+1}', 'tax', reference=prod))
                arms.append(self.run_baseline_arm(f'ON_p{i+1}', 'tax', ckpt=True, reference=prod))
            write_new(self.directory / 'measurements_complete.json', {'arms': [p.name for p in arms],
                      'code_version': admission['code_version'], 'state': 'complete_measurements_pending_review'})
            self.set_status(state='complete_measurements_pending_review')
            print('T00 MEASUREMENTS COMPLETE; independent historical comparison and closure pending', flush=True)
        except BaseException as exc:
            if created:
                self.set_status(state='failed', error=repr(exc))
            raise
        finally:
            try:
                self.stop()
            finally:
                if self.proc is None:
                    self.lock_release()


def self_test():
    import copy
    import tempfile
    from unittest.mock import patch

    sample = {'record': {'cold_id': 'case', 'cached_tokens': 0, 'prompt_tokens': 32064,
                         'completion_tokens': 128, 'ttft_s': 6.0, 'decode_tps': 38.0},
              'diag': {'built_tokens': 32052, 'enable_thinking': False, 'content_events': 128,
                       'cache_ok': True, 'prompt_len_ok': True, 'decode_ok': True}}
    validate_cold(sample, 'case', 32052)
    for container, key, value in [('record', 'cold_id', 'other'), ('record', 'cached_tokens', 64),
                                  ('record', 'prompt_tokens', 0), ('record', 'decode_tps', float('nan')),
                                  ('diag', 'built_tokens', 65412), ('diag', 'content_events', 0)]:
        bad = copy.deepcopy(sample)
        bad[container][key] = value
        try:
            validate_cold(bad, 'case', 32052)
        except ValueError:
            pass
        else:
            raise AssertionError(f'invalid cold sample accepted: {key}')
    classify_tax({'reps': 5, 'single': [1,2,3,4,5], 'multi': [2,3,4,5,6]})
    for bad in ({'reps': 4, 'single':[1]*5,'multi':[1]*5},
                {'reps':5,'single':[1]*4,'multi':[1]*5},
                {'reps':5,'single':[None]*5,'multi':[1]*5}):
        try:
            classify_tax(bad)
        except ValueError:
            pass
        else:
            raise AssertionError('invalid tax accepted')
    with tempfile.TemporaryDirectory() as temporary:
        runner = object.__new__(BaselineRunner)
        runner.directory = Path(temporary) / 'E2-R000'
        runner.options = argparse.Namespace(run=True)
        with patch.object(BaselineRunner, 'prerequisites', return_value={}), \
             patch.object(BaselineRunner, 'lock_take', side_effect=RuntimeError('foreign lock won race')):
            try:
                runner.execute()
            except RuntimeError:
                pass
            else:
                raise AssertionError('lock race accepted')
        if runner.directory.exists():
            raise AssertionError('lock race polluted assigned round directory')
    print('T00 SELFTEST PASS: cold-input/cache/finite-metric rejection; cold/hot separation')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=int)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    options = parser.parse_args()
    if options.self_test:
        self_test()
        return
    if sys.platform != 'linux' or options.batch is None:
        parser.error('Linux test host and assigned batch number required')
    options.rid, options.gate = 'E2-R000', 'T00'
    runner = BaselineRunner(options)
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda signum, frame: (_ for _ in ()).throw(InterruptedError(f'signal {signum}')))
    runner.execute()


if __name__ == '__main__':
    main()
