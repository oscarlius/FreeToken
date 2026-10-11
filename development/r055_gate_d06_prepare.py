"""Run the existing T16 protocol against an explicitly declared candidate.

R055 D06 pause-fix measurement-tree gate; shared runners and rounds remain immutable. This adapter reuses a pinned
copy of the original protocol and changes only candidate binding and coverage.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import runpy
import signal
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE_SHA256 = "379948776d42d5429304afb11dafb0d316e641638caf7cad15fb5b5e6be7340f"
ADAPTER_SOURCE_SHA256 = '3a85f8e378862e6971f1b72164107c54fefe3b0c858f84d4332979eb28bf0a9c'
HERE = Path(__file__).resolve().parent
BASE_PATH = HERE / 't16_full_tail_base_runner.py'
PRIVATE_BASE_PATH = HERE / 't16_private_port_base_runner.py'
PRIVATE_BASE_SHA256 = '76ed60475d3bb86a92ce9a5cf3aa34ca06b5a5297a1ccda9c5312ed6b5b636e9'
if not BASE_PATH.is_file():
    raise RuntimeError(f'missing full-tail base runner: {BASE_PATH}')
_base_source = BASE_PATH.read_bytes()
if hashlib.sha256(_base_source).hexdigest() != BASE_SHA256:
    raise RuntimeError('T16 base runner hash differs from the reviewed source')
_spec = importlib.util.spec_from_file_location('ft_t16_pinned_protocol', BASE_PATH)
_protocol = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _protocol
exec(compile(_base_source, str(BASE_PATH), 'exec'), _protocol.__dict__)
base = vars(_protocol)
if not PRIVATE_BASE_PATH.is_file() or hashlib.sha256(PRIVATE_BASE_PATH.read_bytes()).hexdigest() != PRIVATE_BASE_SHA256:
    raise RuntimeError('R055 private-port runner hash differs from the reviewed source')
_private_spec = importlib.util.spec_from_file_location('ft_r055_private_protocol', PRIVATE_BASE_PATH)
_private_protocol = importlib.util.module_from_spec(_private_spec)
sys.modules[_private_spec.name] = _private_protocol
exec(compile(PRIVATE_BASE_PATH.read_bytes(), str(PRIVATE_BASE_PATH), 'exec'), _private_protocol.__dict__)
PrivateRunner = _private_protocol.Runner
ROOT, ROUNDS = base['ROOT'], base['ROUNDS']
# Explicit bindings for the R055-only copied run_arm; no inherited global lookup.
PY, FT, SCR, MODEL = base['PY'], base['FT'], base['SCR'], base['MODEL']
command, write_new, events, rows = base['command'], base['write_new'], base['events'], base['rows']
strict_args, check_det, check_prefill = base['strict_args'], base['check_det'], base['check_prefill']
WRAPPERS = ROOT / 'runs/plan_batches'
CASES = {
    'D06': {
        'card': 'D06', 'parent_wt': 'e2base1-ordinary-rewind', 'new_wt': 'e2base1-p1',
        'parent_commit': '0aa23431e5b800797543bdecbf35a01045131d7d',
        'new_commit': 'effb9969706922ddad9e59b96377e46469ebe97f', 'ordinary_prefill': True,
    },
}

ASSIGNED_RID = 'E2-R055-gate-D06'
OWNED_SOURCE = ROOT / 'runs/dev_D16/t20_startup_cpu_5d485bd933e4/source_tools'
RAW_HELPERS = OWNED_SOURCE / 'helpers/raw'
R055_TOOL_SPECS = {
    'cold_eq.py': (RAW_HELPERS / 'cold_eq.py', '7141f874c41c310ac20d2da72490eccb',
                   '1fe95158522da413621e58187c0198f26cf5860b64e3d74dd76df8cfb75a6093', True),
    'probe_ft_cold32k.py': (RAW_HELPERS / 'probe_ft_cold32k.py', 'de5ccb4f2fee8c5d5eb1881a9fb11674',
                            '68e6c3f707fc97a6d04e4d9ac2bb582888af5b13b39584e863fe6be649cc306d', True),
    'serve_args_diff.py': (base['SCR'] / 'serve_args_diff.py', 'ce123cb0af201d99baac91f7f8e4f8c7',
                           '61ef1c553ef383cfa59c2cec609528ed9cde8998061c354224a17b497948bd21', False),
}

def r055_tool_preflight():
    """Bind the exact helper bytes R055 executes; never inherit a live probe."""
    evidence = {}
    for name, (path, expected_md5, expected_sha256, must_be_readonly) in R055_TOOL_SPECS.items():
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f'R055 tool source is absent or symlinked: {name}')
        mode = path.stat().st_mode
        if must_be_readonly and mode & 0o222:
            raise RuntimeError(f'R055 frozen helper is writable: {name}')
        data = path.read_bytes()
        md5, sha256 = hashlib.md5(data).hexdigest(), hashlib.sha256(data).hexdigest()
        if md5 != expected_md5 or sha256 != expected_sha256:
            raise RuntimeError(f'R055 tool source hash differs: {name}')
        evidence[name] = {'path': str(path), 'md5': md5, 'sha256': sha256,
                          'readonly_required': must_be_readonly,
                          'readonly': not bool(mode & 0o222)}
    return evidence

def validate_identity(options):
    case = CASES[options.case]
    if options.rid != ASSIGNED_RID:
        raise ValueError('RID must name a newly assigned E2 round and the declared card')
    if type(options.batch) is not int or options.batch < 1:
        raise ValueError('positive batch identity required')
    if options.candidate_commit != case['new_commit']:
        raise ValueError('candidate commit differs from the declared immutable candidate')
    return case


class CandidateRunner(PrivateRunner):
    def __init__(self, options):
        self.case = validate_identity(options)
        options.gate = self.case['card']
        super().__init__(options)

    def private_probe_bootstrap(self):
        """Run only the sealed raw cold/probe pair against this private port."""
        probe, client = (R055_TOOL_SPECS[name][0] for name in ('probe_ft_cold32k.py', 'cold_eq.py'))
        url = f'http://127.0.0.1:{self.port}/v1/chat/completions'
        return (
            'import importlib.util,runpy,sys;'
            f'spec=importlib.util.spec_from_file_location("probe_ft_cold32k",{str(probe)!r});'
            'mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);'
            f'mod.URL={url!r};sys.modules["probe_ft_cold32k"]=mod;'
            f'sys.argv=[{str(client)!r}]+sys.argv[1:];'
            f'ns=runpy.run_path({str(client)!r},run_name="r055_private_client");'
            f'ns["main"].__globals__["URL"]={url!r};ns["main"]()'
        )

    def environment(self, wt, arm=None):
        # The pinned base clears inherited development flags. R055 never enables D0.
        env = super().environment(wt, arm, False)
        # CPU validation shells may have hidden CUDA; GPU execution is explicit.
        env['CUDA_VISIBLE_DEVICES'] = '0'
        return env

    def set_status(self, **values):
        super().set_status(rid=self.options.rid, candidate_case=self.options.case, **values)

    def _freeze_observer(self, arm):
        import shutil, importlib.util
        runner_path = HERE / "t17_d14_runner.py"; observer = HERE / "t17_d14_observe.py"
        for src in (runner_path, observer):
            if not src.is_file() or src.is_symlink(): raise RuntimeError("R055 T17 observer source is unavailable")
            shutil.copy2(src, arm / src.name)
        # This arm-local observer records the first real decode state without
        # changing scheduler selection or the request contents.
        observer_copy = arm / "t17_d14_observe.py"
        text = observer_copy.read_text(encoding="utf-8")
        hook = '''\ndef r055_install_decode_hook(scheduler_type):\n    """Persist one actual 128-token cold state immediately before first decode."""\n    original = scheduler_type._forward\n    seen = set()\n    def wrapped(self, value):\n        batch = value.batch\n        if not getattr(batch, "is_prefill", False):\n            for req in batch.reqs:\n                uid = str(req.uid)\n                slot = getattr(req, "linear_slot_idx", -1)\n                maximum = getattr(getattr(req, "sampling_params", None), "max_tokens", None)\n                if uid not in seen and slot >= 0 and maximum == 128:\n                    seen.add(uid)\n                    self.engine.linear_state_pool.dump_state(\n                        "r055_before_decode", dev_slots=[slot], length=int(req.device_len), uid=uid)\n        return original(self, value)\n    scheduler_type._forward = wrapped\n'''
        marker = '\ndef startup():'
        if marker not in text:
            raise RuntimeError('R055 observer startup marker is unavailable')
        # The definition must precede startup: spawned workers execute startup
        # before the original module reaches any later appended declaration.
        text = text.replace(marker, hook + marker, 1)
        old = 'install(Scheduler, SchedulerIOMixin, Engine, sink=sink)'
        if text.count(old) != 1:
            raise RuntimeError('R055 observer install marker is ambiguous')
        text = text.replace(old, old + '\n    r055_install_decode_hook(Scheduler)', 1)
        observer_copy.write_text(text, encoding="utf-8")
        for frozen in (arm / "t17_d14_runner.py", observer_copy):
            frozen.chmod(0o444)
            if frozen.is_symlink() or frozen.stat().st_mode & 0o222:
                raise RuntimeError('R055 observer source is not frozen')
        write_new(arm / "observer_sources.json", {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (arm / "t17_d14_runner.py", observer_copy)
        })
        spec=importlib.util.spec_from_file_location("r055_t17_runner", arm / "t17_d14_runner.py"); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        self._r055_t17 = mod
        return mod.freeze_startup_wrapper(arm)

    def _startup_argv(self, wrapper, ft_argv): return self._r055_t17.startup_argv(wrapper, ft_argv)

    def ready(self, arm, port):
        if port != self.port or port == 8095:
            raise RuntimeError('R055 private port binding differs')
        return PrivateRunner.ready(self, arm)

    def _stop_private(self):
        if self.proc is None: return
        return PrivateRunner.stop(self)


    def run_arm(self, name, wt, commit, layer_major=True, compare_to=None, cases=None):
        # R055 owns a dynamically allocated private loopback port and frozen observer sources.
        source = self.gate(wt, commit)
        arm = self.directory / name
        arm.mkdir(exist_ok=False)
        env = self.environment(wt, arm)
        # Reuse one guarded port for all sequential arms, so strict argument
        # comparison sees identical service configuration.
        port = self.port
        wrapper = self._freeze_observer(arm)
        env.update(FT_DEV_STATE_DUMP=str(arm / "state_dump"), FT_T17_OBSERVATIONS=str(arm / "t17_observations.jsonl"))
        env["PYTHONPATH"] = str(arm) + ":" + env["PYTHONPATH"]
        ft_argv = ['serve',
                '--model-path', str(ROOT / 'models/Qwen3.8-Flash-Next-NVFP4-overlay'),
                '--served-model-name', MODEL, '--host', '127.0.0.1', '--port', str(port),
                '--memory-ratio', '0.88', '--moe-cache-auto', '--moe-prefill-hit-d2d', '--ple-backend', 'pinned',
                '--moe-strategy', 'offload', '--quant-backend', 'moe.nvfp4=triton',
                '--max-running-requests', '2', '--cuda-graph-max-bs', '2', '--kv-reserve-tokens', '49152',
                '--max-seq-len-override', '49152', '--max-prefill-length', '4096', '--enable-cache-report',
                '--enable-special-token-ckpt', '--tool-call-parser', 'qwen3_coder', '--reasoning-parser', 'qwen3']
        if layer_major:
            ft_argv.append('--prefill-layer-major')
        argv = ['numactl', '--cpunodebind=0,1', '--interleave=all'] + self._startup_argv(wrapper, ft_argv)
        selected = ['PYTHONPATH', 'PYTHONUNBUFFERED', 'VIRTUAL_ENV', 'PATH', 'LD_LIBRARY_PATH']
        (arm / 'SERVE_CMD.txt').write_text('env ' + ' '.join(k + '=' + shlex.quote(env[k]) for k in selected)
                                         + ' ' + shlex.join(argv) + '\n')
        (arm / 'ENV.txt').write_text(time.strftime('%F %T %Z') + '\n' + source + '\n'
                                   + command(['git', '-C', str(wt), 'log', '-1', '--format=%H %s']) + '\n'
                                   + command(['nvidia-smi']) + '\n' + command(['numactl', '-H']) + '\n'
                                   + command(['ps', '-eo', 'pid,pcpu,pmem,comm', '--sort=-pcpu']).split('\n')[0]
                                   + '\n' + '\n'.join(command(['ps', '-eo', 'pid,pcpu,pmem,comm', '--sort=-pcpu']).split('\n')[1:9]) + '\n')
        with (arm / 'serve.log').open('x') as log:
            self.proc = subprocess.Popen(argv, env=env, cwd=wt, stdout=log, stderr=subprocess.STDOUT,
                                         start_new_session=True)
            self.set_status(state='loading', arm=name, service_pid=self.proc.pid)
            print(f'START {name} SPID={self.proc.pid}', flush=True)
            try:
                self.service_birth = PrivateRunner.owned_lifecycle(self).process_identity(self.proc.pid)
                if (self.service_birth is None or self.service_birth['pgid'] != self.proc.pid
                        or self.service_birth['session'] != self.proc.pid):
                    raise RuntimeError('R055 service lacks owned private PGID/session')
                write_new(arm / 'owned_process.json', {'birth': self.service_birth, 'port': self.port})
                self.ready(arm, port)
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
                        subprocess.run([PY, '-c', self.private_probe_bootstrap(), cold_id, str(arm / (label + '.json')),
                                        str(target), str(tokens)], env=env, cwd=wt, stdout=stdout, stderr=stderr,
                                       check=True, timeout=1800)
                    check_det([arm / (label + '.json')] * 2, target, tokens)
                    if compare_to is not None:
                        check_det([compare_to / (label + '.json'), arm / (label + '.json')], target, tokens)
                all_events = events(arm / 'serve.log')
                write_new(arm / 'business_prefill_events.json', all_events[p0:])
                (arm / 'prefill_seq.txt').write_text(''.join(f'#new-seq: {bs}, #new-token: {new}, #cached-token: {cached}\n'
                                                           for bs, new, cached in all_events[p0:]))
                if self.proc.poll() is not None:
                    raise RuntimeError('service exited before live telemetry verification')
                full_log = (arm / 'serve.log').read_text()
                if list(arm.glob('d0*')) or any(token in full_log for token in ('GDN bank:', 'D0 seg:', 'D0 prefill', 'D0 instrumentation enabled')):
                    raise RuntimeError('R055 D0 leakage')
                if compare_to is not None and (compare_to / 'prefill_seq.txt').read_bytes() != (arm / 'prefill_seq.txt').read_bytes():
                    raise ValueError('business prefill sequence differs')
                print(f'PROBE PASS {name} events={len(all_events)}', flush=True)
            finally:
                self._stop_private()
        return arm


    def _state_record(self, arm, *, uid, length, kind="r055_before_decode"):
        """Require observer identity and four persisted raw CPU state roles."""
        import importlib.util
        runner = arm / "t17_d14_runner.py"
        spec=importlib.util.spec_from_file_location("r055_state_runner", runner); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        obs = arm / "t17_observations.jsonl"
        if not obs.is_file() or not obs.read_text(encoding="utf-8").strip(): raise ValueError("missing observer admission/delivery evidence")
        rows=[json.loads(line) for line in obs.read_text(encoding="utf-8").splitlines() if line]
        inputs=[row for row in rows if row.get("kind")=="input" and str(row.get("uid"))==str(uid)]
        tokens=[row for row in rows if row.get("kind")=="token" and str(row.get("uid"))==str(uid)]
        token_ids=[row.get("token") for row in tokens]
        if (len(inputs)!=1 or not inputs[0].get("ids_int32le_sha256") or not tokens
                or any(type(token) is not int for token in token_ids) or not tokens[-1].get("finished")):
            raise ValueError("observer UID/input/delivery binding differs")
        record=mod.load_dump_record(arm / "state_dump", kind=kind, length=length, uid=str(uid))
        files=record.get("files",{})
        for role in mod.STATE_ROLES:
            value=files.get(role)
            if not isinstance(value,str) or not value.endswith('.pt') or not (arm/"state_dump"/value).is_file():
                raise ValueError("state role metadata is incomplete")
        packed=','.join(map(str,token_ids)).encode('ascii')
        return mod, record, {"uid":str(uid),"input_ids_sha256":inputs[0]["ids_int32le_sha256"],"tokens":token_ids,"tokens_sha256":hashlib.sha256(packed).hexdigest(),"state_labels":sorted(files),"state_files":files}

    def compare_state_triplet(self, reference_a, reference_b, candidate, *, uid, length):
        mod,a,ab=self._state_record(reference_a,uid=uid,length=length); mod2,b,bb=self._state_record(reference_b,uid=uid,length=length); mod3,c,cb=self._state_record(candidate,uid=uid,length=length)
        if mod.STATE_ROLES != mod2.STATE_ROLES or mod.STATE_ROLES != mod3.STATE_ROLES: raise ValueError("state role contract differs")
        if (ab["uid"] != bb["uid"] or ab["uid"] != cb["uid"]
                or ab["input_ids_sha256"] != bb["input_ids_sha256"]
                or ab["input_ids_sha256"] != cb["input_ids_sha256"]
                or ab["tokens"] != bb["tokens"] or ab["tokens"] != cb["tokens"]):
            raise ValueError("state UID/input SHA/token sequence differs")
        # torch.equal alone is insufficient: bind shape/dtype and raw uint8 bytes.
        import hashlib, torch
        def exact(left_arm, left, right_arm, right):
            out={}
            for role in mod.STATE_ROLES:
                x=torch.load(left_arm/"state_dump"/left["files"][role],map_location="cpu",weights_only=True)
                y=torch.load(right_arm/"state_dump"/right["files"][role],map_location="cpu",weights_only=True)
                xb=x.contiguous().view(torch.uint8).numpy().tobytes(); yb=y.contiguous().view(torch.uint8).numpy().tobytes()
                if x.shape != y.shape or x.dtype != y.dtype or xb != yb: raise ValueError("state tensor byte/shape/dtype difference")
                left_file=left_arm/"state_dump"/left["files"][role]
                right_file=right_arm/"state_dump"/right["files"][role]
                out[role]={"shape":list(x.shape),"dtype":str(x.dtype),"tensor_sha256":hashlib.sha256(xb).hexdigest(),"left_file":left["files"][role],"left_file_sha256":hashlib.sha256(left_file.read_bytes()).hexdigest(),"right_file":right["files"][role],"right_file_sha256":hashlib.sha256(right_file.read_bytes()).hexdigest()}
            return out
        stable=exact(reference_a,a,reference_b,b)
        candidate_equal=exact(reference_a,a,candidate,c)
        return {"reference_stable":stable,"candidate_equal":candidate_equal,"binding":cb}

    def compare(self, parent, new, parent_p, new_p, cases=None):
        result = {}
        for label, a, b in (('D0', parent, new), ('PROD', parent_p, new_p)):
            result[label] = {'args': base['strict_args'](
                self.parser(str(a / 'serve.log')), self.parser(str(b / 'serve.log')), {})}
            for case, _, target, tokens in cases or [('det', '', 32052, 128)]:
                result[label][case] = base['check_det'](
                    [a / (case + '.json'), b / (case + '.json')], target, tokens)
            old, fresh = (a / 'prefill_seq.txt').read_bytes(), (b / 'prefill_seq.txt').read_bytes()
            if not old or old != fresh:
                raise ValueError(f'{label} business prefill sequence differs')
            result[label]['sequence'] = 'SAME'
        result['prefill'] = base['check_prefill'](parent, new, True, True)
        return result

    def execute(self):
        opts, case = self.options, self.case
        if self.directory.exists():
            raise ValueError('assigned round already exists; historical artifacts are read-only')
        parent_wt, new_wt = ROOT / 'wt' / case['parent_wt'], ROOT / 'wt' / case['new_wt']
        for wt, commit in ((parent_wt, case['parent_commit']), (new_wt, case['new_commit'])):
            self.gate(wt, commit)
        actual_parent = base['command'](['git', '-C', str(new_wt), 'show', '-s', '--format=%P', 'HEAD'])
        if actual_parent != case['parent_commit']:
            raise ValueError('candidate immediate parent differs from the declared comparison')
        extensions = {'parent': self.compiled_extensions(parent_wt), 'new': self.compiled_extensions(new_wt)}
        if ({k: v['sha256'] for k, v in extensions['parent'].items()}
                != {k: v['sha256'] for k, v in extensions['new'].items()}):
            raise ValueError('compiled extensions differ between parent and candidate')
        base['command'](['numactl', '--cpunodebind=0,1', '--interleave=all', base['FT'], '--help'],
                        env=self.environment(parent_wt), cwd=parent_wt)
        tools = r055_tool_preflight()
        print('PREFLIGHT PASS ' + json.dumps({'case': opts.case, **case, 'tools': tools}), flush=True)
        if not opts.run:
            return
        wrapper = WRAPPERS / f'batch{opts.batch}_{opts.rid}_python.sh'
        if not wrapper.is_file() or wrapper.is_symlink():
            raise ValueError('atomic launcher wrapper is missing or a symlink')
        # Acquire the global lock before creating a writable round directory.
        self.lock_take()
        owned_directory = False
        try:
            self.directory.mkdir(exist_ok=False)
            owned_directory = True
            base['write_new'](self.directory / f'tools_batch{opts.batch}.json', tools)
            base['write_new'](self.directory / 'candidate_binding.json', {
                'case': opts.case, **case, 'base_runner_sha256': BASE_SHA256,
                'base_runner_filename': BASE_PATH.name,
                'candidate_runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'source_inventory': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                     for path in (Path(__file__), BASE_PATH, PRIVATE_BASE_PATH,
                                                  HERE / 't17_d14_runner.py', HERE / 't17_d14_observe.py')},
                'compiled_extensions': extensions, 'tools': tools, 'CUDA_VISIBLE_DEVICES': '0',
            })
            for src, name in ((Path(__file__), f'runner_batch{opts.batch}.py'),
                              (BASE_PATH, f'base_runner_batch{opts.batch}.py'),
                              (wrapper, f'batch{opts.batch}.sh'), (wrapper, 'batch.sh')):
                with (self.directory / name).open('xb') as target:
                    target.write(_base_source if src == BASE_PATH else src.read_bytes())
            self.set_status(state='running')
            result = {'arms': []}
            # R055 is a six-service correctness gate: one 32052/128 cold
            # case in each prefill mode, with two independent parent arms and
            # one candidate arm.  No D0 or checkpoint-tax probe is permitted.
            modes = [('layer_major', True, [('cold', opts.rid + '-layer-major', 32052, 128)])]
            if case['ordinary_prefill']:
                modes.append(('ordinary', False, [('cold', opts.rid + '-ordinary', 32052, 128)]))
            for mode, layer_major, samples in modes:
                prefix = '' if layer_major else 'CHUNK_'
                suffix = f'_b{opts.batch}'
                # Two structurally identical 0aa references and one eff candidate per mode.
                # The observer binding discovers the actual business UID rather than guessing it.
                p = self.run_arm(prefix + 'PARENT0' + suffix, parent_wt, case['parent_commit'], layer_major, cases=samples)
                p1 = self.run_arm(prefix + 'PARENT1' + suffix, parent_wt, case['parent_commit'], layer_major, compare_to=p, cases=samples)
                n = self.run_arm(prefix + 'NEW' + suffix, new_wt, case['new_commit'], layer_major, compare_to=p1, cases=samples)
                result[mode] = {"args": base['strict_args'](self.parser(str(p1/'serve.log')), self.parser(str(n/'serve.log')), {})}
                # Business UID and dump boundary are emitted by the observer contract; absence fails closed.
                def state_binding(arm):
                    rows=[json.loads(x) for x in (arm/'t17_observations.jsonl').read_text().splitlines() if x]
                    dumps=[json.loads(x) for x in (arm/'state_dump'/'index.jsonl').read_text().splitlines() if x]
                    dumped=[x for x in dumps if x.get('kind')=='r055_before_decode']
                    if len(dumped)!=1: raise ValueError('expected exactly one real pre-decode state dump')
                    uid=str(dumped[0].get('uid'))
                    inputs=[x for x in rows if x.get('kind')=='input' and str(x.get('uid'))==uid]
                    tokens=[x for x in rows if x.get('kind')=='token' and str(x.get('uid'))==uid]
                    if (len(inputs)!=1 or inputs[0].get('sampling',{}).get('max_tokens') != 128
                            or not inputs[0].get('ids_int32le_sha256') or not tokens or not tokens[-1].get('finished')):
                        raise ValueError('actual cold UID/input/delivery binding is incomplete')
                    return uid, int(dumped[0].get('length'))
                uid,length=state_binding(p)
                result[mode]['state'] = self.compare_state_triplet(p,p1,n,uid=uid,length=length)
                result['arms'].extend(a.name for a in (p,p1,n))
            result.update(proposed_verdict='kept', gate=case['card'], candidate_case=opts.case,
                          parent_commit=case['parent_commit'], new_commit=case['new_commit'],
                          compiled_extensions=extensions)
            base['write_new'](self.directory / f'gate_batch{opts.batch}.json', result)
            self.set_status(state='complete_measurements_pending_review', proposed_verdict='kept')
            print('T16 MEASUREMENTS PASS ' + json.dumps(result), flush=True)
        except BaseException as exc:
            if owned_directory:
                self.set_status(state='failed', error=repr(exc))
            raise
        finally:
            try:
                self.stop()
            finally:
                if self.proc is None:
                    self.lock_release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--case', choices=CASES)
    parser.add_argument('--rid')
    parser.add_argument('--batch', type=int)
    parser.add_argument('--candidate-commit')
    parser.add_argument('--run', action='store_true')
    opts = parser.parse_args()
    if opts.self_test:
        base['self_test']()
        print('CANDIDATE BASE SELFTEST PASS; run adapter regression tests separately')
        return
    if not opts.run:
        if opts.case or opts.rid or opts.batch or opts.candidate_commit:
            parser.error('--run is required for a gate execution')
        print(json.dumps({'schema':'ft_t16_gate_prepare/v1','rid':ASSIGNED_RID,'case':next(iter(CASES)),
                          'candidate_commit':next(iter(CASES.values()))['new_commit'],
                          'requests_sent':False,'gpu_lock_taken':False}))
        return
    # This leaf is callable only from r055_owned_launch.py after receipt and owner-lock binding.
    parser.error('direct execution is disabled; invoke r055_owned_launch.py --run')


if __name__ == '__main__':
    main()
