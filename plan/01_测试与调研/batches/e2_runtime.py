"""Resource lifecycle shared by the remaining E2 measurement cards."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import time

from t16_runner import Runner, ROOT, ROUNDS, SCR, PY, FT, MODEL, LOCK, command, write_new, strict_args

WT = ROOT / 'wt/e2base'
COMMIT = '23f2e2c'


def verify_manifest(directory):
    document = json.loads((directory / 'round.json').read_text())
    if document.get('schema') != 'ft_round/v2' or not document.get('closed_at'):
        raise ValueError(f'closed round metadata missing: {directory}')
    history = directory / 'round_history'
    versions = sorted(history.glob('round.v*.json'))
    if not versions or (directory / 'round.json').read_bytes() != versions[-1].read_bytes():
        raise ValueError(f'round differs from latest history: {directory}')
    for line in (history / 'SHA256SUMS').read_text().splitlines():
        expected, relative = line.split('  ', 1)
        if hashlib.sha256((history / relative).read_bytes()).hexdigest() != expected:
            raise ValueError(f'history digest differs: {directory / relative}')
    manifest = directory / 'MANIFEST.sha256'
    for line in manifest.read_text().splitlines():
        expected, relative = line.split('  ', 1)
        if hashlib.sha256((directory / relative).read_bytes()).hexdigest() != expected:
            raise ValueError(f'closed artifact digest differs: {directory / relative}')
    if directory.stat().st_mode & 0o222:
        raise ValueError(f'round not closed read-only: {directory}')
    return hashlib.sha256(manifest.read_bytes()).hexdigest()


def admission():
    tag = command(['git', '-C', str(WT), 'describe', '--tags', '--exact-match'])
    commit = command(['git', '-C', str(WT), 'rev-parse', 'HEAD'])
    if tag != 'E2-base@' + COMMIT or commit[:7] != COMMIT:
        raise ValueError('E2 baseline tag does not identify admitted commit')
    d00 = ROUNDS / 'E2-pre-gate-D00'
    gate = json.loads((d00 / 'gate_batch26.json').read_text())
    review = json.loads((d00 / 'review_batch26.json').read_text())
    status = json.loads((d00 / 'status_batch26.json').read_text())
    if (gate['new_commit'] != COMMIT or gate['proposed_verdict'] != 'kept' or review['verdict'] != 'PASS'
            or review['rid'] != d00.name or review['batch'] != 26 or status['state'] != 'complete'):
        raise ValueError('D00 independent gate not admitted')
    t00 = ROUNDS / 'E2-R000'
    accepted = json.loads((t00 / 'baseline_acceptance.json').read_text())
    baseline = json.loads((t00 / 'round.json').read_text())
    if (accepted['verdict'] != 'kept' or accepted['code_version'] != tag or not accepted.get('reviewer')
            or baseline['base']['commit'] != commit or baseline['base']['code_version'] != tag):
        raise ValueError('T00 baseline has not been accepted')
    return {'commit': commit, 'code_version': tag, 'D00_manifest': verify_manifest(d00),
            'T00_manifest': verify_manifest(t00)}


class CardRunner(Runner):
    def set_status(self, **values):
        super().set_status(rid=self.options.rid, **values)

    def lock_take(self):
        self.token = json.dumps({'owner': self.options.rid, 'card': self.options.gate,
                                 'pid': os.getpid(), 'since': time.strftime('%F %T %Z')})
        fd = os.open(LOCK, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, 'w') as handle:
            handle.write(self.token)
        self.lock_inode = LOCK.stat().st_ino

    @contextmanager
    def round_scope(self):
        proof = admission()
        self.gate(WT, COMMIT)
        if not self.options.run:
            yield None
            return
        if self.directory.exists():
            raise ValueError('assigned round already exists')
        self.lock_take()
        created = False
        try:
            self.directory.mkdir(exist_ok=False)
            created = True
            write_new(self.directory / 'admission.json', {**proof, 'rid': self.options.rid, 'card': self.options.gate})
            sources = (Path(self.options.runner_file), Path(__file__), Path(__file__).with_name('t16_runner.py'),
                       Path(__file__).with_name('t00_runner.py'),
                       Path(__file__).with_name(f'batch{self.options.batch}_{self.options.rid}_python.sh'))
            for source in sources:
                with (self.directory / ('batch.sh' if source.suffix == '.sh' else source.name)).open('xb') as dst:
                    dst.write(source.read_bytes())
            self.set_status(state='running')
            yield proof
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

    @contextmanager
    def service(self, name, *, d0=False, window=49152, strategy='offload', layer_major=True,
                launch=None, reference=None, allowed_differences=None):
        source = self.gate(WT, COMMIT)
        arm = self.directory / name
        arm.mkdir(exist_ok=False)
        env = self.environment(WT, arm, d0)
        argv = list(launch or ['numactl', '--cpunodebind=0,1', '--interleave=all']) + [FT, 'serve',
                '--model-path', str(ROOT / 'models/Qwen3.8-Flash-Next-NVFP4-overlay'),
                '--served-model-name', MODEL, '--host', '0.0.0.0', '--port', '8095', '--memory-ratio', '0.88',
                '--moe-cache-auto', '--moe-prefill-hit-d2d', '--ple-backend', 'pinned', '--moe-strategy', strategy,
                '--quant-backend', 'moe.nvfp4=triton', '--max-running-requests', '2', '--cuda-graph-max-bs', '2',
                '--kv-reserve-tokens', str(window), '--max-seq-len-override', str(window),
                '--max-prefill-length', '4096', '--enable-cache-report', '--enable-special-token-ckpt',
                '--tool-call-parser', 'qwen3_coder', '--reasoning-parser', 'qwen3']
        if layer_major:
            argv.append('--prefill-layer-major')
        selected = ['PYTHONPATH', 'PYTHONUNBUFFERED', 'VIRTUAL_ENV', 'PATH', 'LD_LIBRARY_PATH']
        if d0:
            selected += ['FT_DEV_D0', 'FT_DEV_D0_PATH']
        (arm / 'SERVE_CMD.txt').write_text('env ' + ' '.join(k + '=' + shlex.quote(env[k]) for k in selected)
                                         + ' ' + shlex.join(argv) + '\n')
        (arm / 'ENV.txt').write_text(time.strftime('%F %T %Z') + '\n' + source + '\n'
                                   + command(['hostname']) + '\n'
                                   + command(['git', '-C', str(WT), 'log', '-1', '--format=%H %s']) + '\n'
                                   + command(['nvidia-smi']) + '\n' + command(['numactl', '-H']) + '\n'
                                   + '\n'.join(command(['ps', '-eo', 'pid,pcpu,pmem,comm', '--sort=-pcpu']).splitlines()[:9]) + '\n')
        extensions = command([PY, '-c', 'import hashlib,json,freetoken.kernel._cpu_moe as a,freetoken.kernel._pinned_tensor as b;'
                              'print(json.dumps([{\"path\":m.__file__,\"sha256\":hashlib.sha256(open(m.__file__,\"rb\").read()).hexdigest()} for m in (a,b)]))'],
                             env=env,cwd=WT)
        write_new(arm / 'compiled_extensions.json', json.loads(extensions))
        with (arm / 'serve.log').open('x') as log:
            self.proc = subprocess.Popen(argv, env=env,cwd=WT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            self.set_status(state='loading', arm=name, service_pid=self.proc.pid)
            print(f'START {name} SPID={self.proc.pid}', flush=True)
            try:
                if os.getpgid(self.proc.pid) != self.proc.pid or os.getsid(self.proc.pid) != self.proc.pid:
                    raise RuntimeError('service ownership mismatch')
                self.ready(arm)
                parsed = self.parser(str(arm / 'serve.log'))
                if parsed['_unique_suffix'] != repr('.pid=' + str(self.proc.pid)):
                    raise ValueError('service PID suffix mismatch')
                text = (arm / 'serve.log').read_text()
                (arm / 'serve_args.txt').write_text('\n'.join(text[text.index('Parsed arguments'):].splitlines()[:2]) + '\n')
                if reference:
                    old = self.parser(str(reference / 'serve.log'))
                    right = dict(parsed)
                    expected = {}
                    for key, pair in (allowed_differences or {}).items():
                        if (old.get(key), parsed.get(key)) != tuple(pair):
                            raise ValueError(f'intended parsed fields mismatch: {key}')
                        right[key] = old[key]
                        expected[key] = list(pair)
                    diff = strict_args(old, right, {})
                    write_new(arm / 'args_checked.json', {**diff, **expected})
                write_new(arm / 'affinity.json', {'actual': sorted(os.sched_getaffinity(self.proc.pid))})
                self.set_status(state='probing',arm=name,service_pid=self.proc.pid)
                yield arm, env
                if self.proc.poll() is not None:
                    raise RuntimeError('service died before live verification')
                if not d0 and (list(arm.glob('d0*')) or any(x in (arm / 'serve.log').read_text() for x in
                              ('GDN bank:', 'D0 seg:', 'D0 prefill', 'D0 instrumentation enabled'))):
                    raise ValueError('D0-off leakage')
                print(f'ARM PASS {name}',flush=True)
            finally:
                self.stop()
