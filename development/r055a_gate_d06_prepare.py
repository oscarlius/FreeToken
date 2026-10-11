"""R055a D06 gate adapter with an executable, no-service dry-run path."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import shlex
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
RID = "E2-R055a-gate-D06"
CARD = "D06"
PARENT_COMMIT = "0aa23431e5b800797543bdecbf35a01045131d7d"
CANDIDATE_COMMIT = "effb9969706922ddad9e59b96377e46469ebe97f"


def _load_base():
    path = HERE / "r055_gate_d06_prepare.py"
    spec = importlib.util.spec_from_file_location("r055a_base", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


base = _load_base()
base.__file__ = str(Path(__file__).resolve())
base.ASSIGNED_RID = RID
base.CASES["D06"] = {**base.CASES["D06"], "parent_commit": PARENT_COMMIT,
                     "new_commit": CANDIDATE_COMMIT}
ROOT, ROUNDS = base.ROOT, base.ROUNDS
# These bindings are the original formal run_arm/execute globals.
PY, FT, SCR, MODEL = base.PY, base.FT, base.SCR, base.MODEL
command, write_new, events = base.command, base.write_new, base.events
strict_args, check_det = base.strict_args, base.check_det
r055_tool_preflight = base.r055_tool_preflight
PrivateRunner, WRAPPERS = base.PrivateRunner, base.WRAPPERS
BASE_SHA256, BASE_PATH, PRIVATE_BASE_PATH = base.BASE_SHA256, base.BASE_PATH, base.PRIVATE_BASE_PATH
_base_source = base._base_source



def _dry_base():
    path = HERE / "r055a_dryrun_base_v1.py"
    spec = importlib.util.spec_from_file_location("r055a_dry_base", path)
    module = importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(module)
    return module


def _write_probe(directory: Path, name: str) -> Path:
    path = directory / name
    with path.open("x", encoding="utf-8") as handle:
        handle.write("r055a writable probe\n")
    if path.read_text(encoding="utf-8") != "r055a writable probe\n":
        raise RuntimeError(f"R055a write probe differs: {path}")
    return path


class CandidateRunner(base.CandidateRunner):
    """The formal R055a runner; only its arm-local source-copy policy differs."""

    def _freeze_observer(self, arm):
        runner_source = HERE / "t17_d14_runner.py"
        observer_source = HERE / "t17_d14_observe.py"
        # The startup wrapper imports these modules from the arm root.  Make
        # that actual observer staging directory writable before copying.
        arm.chmod(0o700)
        _write_probe(arm, ".observer-writable-before-copy")
        copied = []
        for source in (runner_source, observer_source):
            if (not source.is_file() or source.is_symlink()
                    or (os.name != "nt" and source.stat().st_mode & 0o222)):
                raise RuntimeError("R055a observer source is unavailable or not frozen")
            target = arm / source.name
            # copyfile deliberately does not carry source mode 0444 into a writable staging copy.
            shutil.copyfile(source, target)
            target.chmod(0o600)
            copied.append(target)
        observer_copy = arm / "t17_d14_observe.py"
        text = observer_copy.read_text(encoding="utf-8")
        hook = '''\ndef r055a_install_decode_hook(scheduler_type):
    original = scheduler_type._forward
    seen = set()
    def wrapped(self, value):
        batch = value.batch
        if not getattr(batch, "is_prefill", False):
            for req in batch.reqs:
                uid = str(req.uid); slot = getattr(req, "linear_slot_idx", -1)
                maximum = getattr(getattr(req, "sampling_params", None), "max_tokens", None)
                if uid not in seen and slot >= 0 and maximum == 128:
                    seen.add(uid)
                    self.engine.linear_state_pool.dump_state("r055_before_decode", dev_slots=[slot], length=int(req.device_len), uid=uid)
        return original(self, value)
    scheduler_type._forward = wrapped
'''
        marker = "\ndef startup():"
        if marker not in text:
            raise RuntimeError("R055a observer startup marker is unavailable")
        text = text.replace(marker, hook + marker, 1)
        install = "install(Scheduler, SchedulerIOMixin, Engine, sink=sink)"
        if text.count(install) != 1:
            raise RuntimeError("R055a observer install marker is ambiguous")
        observer_copy.write_text(text.replace(install, install + "\n    r055a_install_decode_hook(Scheduler)", 1), encoding="utf-8")
        # Instrumentation completes while the copy is writable; only then freeze it.
        for frozen in copied:
            frozen.chmod(0o444)
            if frozen.stat().st_mode & 0o222:
                raise RuntimeError("R055a observer copy did not freeze")
        arm_sources = arm / "observer_sources.json"
        base.write_new(arm_sources, {item.name: hashlib.sha256(item.read_bytes()).hexdigest() for item in copied})
        spec = importlib.util.spec_from_file_location("r055a_t17_runner", arm / "t17_d14_runner.py")
        module = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(module)
        self._r055_t17 = module
        return module.freeze_startup_wrapper(arm)

    def environment(self, wt, arm=None):
        env = super().environment(wt, arm)
        env['CUDA_VISIBLE_DEVICES'] = '' if getattr(self.options, 'file_dry_run', False) else '0'
        return env

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
        if getattr(self.options, 'file_dry_run', False):
            files = _dry_base()
            outputs = ['serve.log', 'owned_process.json', 'health.json', 'ready_sayok.json',
                       'serve_args.txt', 'args_checked.json', 'markers.json',
                       'business_prefill_events.json', 'prefill_seq.txt',
                       't17_observations.jsonl', 'state_dump/index.jsonl']
            outputs += [label + suffix for label, *_ in (cases or [('cold', '', 32052, 128)])
                        for suffix in ('.stdout', '.err', '.json')]
            hashes = {filename: hashlib.sha256((arm / filename).read_bytes()).hexdigest()
                      for filename in ('ENV.txt', 'SERVE_CMD.txt')}
            for filename in outputs:
                path = arm / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                hashes[filename] = files.write_probe(path, 'CPU FILE PROBE ONLY; no measurement\n')
            files.write_json_probe(arm / 'file_dry_run.json', {
                'arm': name, 'source': source, 'port': port, 'argv': argv,
                'environment': {key: env[key] for key in selected + ['FT_DEV_STATE_DUMP', 'FT_T17_OBSERVATIONS']},
                'files': hashes, 'service_started': False, 'requests_sent': False})
            return arm
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


    def execute(self):
        opts, case = self.options, self.case
        if self.directory.exists():
            raise ValueError('assigned round already exists; historical artifacts are read-only')
        parent_wt, new_wt = ROOT / 'wt' / case['parent_wt'], ROOT / 'wt' / case['new_wt']
        for wt, commit in ((parent_wt, case['parent_commit']), (new_wt, case['new_commit'])):
            self.gate(wt, commit)
        actual_parent = base.base['command'](['git', '-C', str(new_wt), 'show', '-s', '--format=%P', 'HEAD'])
        if actual_parent != case['parent_commit']:
            raise ValueError('candidate immediate parent differs from the declared comparison')
        extensions = {'parent': self.compiled_extensions(parent_wt), 'new': self.compiled_extensions(new_wt)}
        if ({k: v['sha256'] for k, v in extensions['parent'].items()}
                != {k: v['sha256'] for k, v in extensions['new'].items()}):
            raise ValueError('compiled extensions differ between parent and candidate')
        base.base['command'](['numactl', '--cpunodebind=0,1', '--interleave=all', base.base['FT'], '--help'],
                        env=self.environment(parent_wt), cwd=parent_wt)
        tools = r055_tool_preflight()
        print('PREFLIGHT PASS ' + json.dumps({'case': opts.case, **case, 'tools': tools}), flush=True)
        if not opts.run:
            return
        wrapper = Path(opts.dry_run_wrapper) if getattr(opts, 'file_dry_run', False) else WRAPPERS / f'batch{opts.batch}_{opts.rid}_python.sh'
        if not wrapper.is_file() or wrapper.is_symlink():
            raise ValueError('atomic launcher wrapper is missing or a symlink')
        # Acquire the global lock before creating a writable round directory.
        if not getattr(opts, "file_dry_run", False):
            self.lock_take()
        owned_directory = False
        try:
            self.directory.mkdir(exist_ok=False)
            owned_directory = True
            base.base['write_new'](self.directory / f'tools_batch{opts.batch}.json', tools)
            base.base['write_new'](self.directory / 'candidate_binding.json', {
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
                if getattr(opts, "file_dry_run", False):
                    result["arms"].extend(a.name for a in (p, p1, n))
                    continue
                result[mode] = {"args": base.base['strict_args'](self.parser(str(p1/'serve.log')), self.parser(str(n/'serve.log')), {})}
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
            if getattr(opts, 'file_dry_run', False):
                write_new(self.directory / 'file_dry_run_complete.json', {'arms': result['arms'], 'service_started': False, 'requests_sent': False})
                self.set_status(state='file_dry_run_complete')
                return
            result.update(proposed_verdict='kept', gate=case['card'], candidate_case=opts.case,
                          parent_commit=case['parent_commit'], new_commit=case['new_commit'],
                          compiled_extensions=extensions)
            base.base['write_new'](self.directory / f'gate_batch{opts.batch}.json', result)
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
                if self.proc is None and not getattr(opts, "file_dry_run", False):
                    self.lock_release()



def _check_worktree(path: Path, commit: str) -> dict[str, str]:
    if path.is_symlink():
        raise RuntimeError(f"R055a worktree is symlinked: {path}")
    head = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(path), "status", "--porcelain", "--untracked-files=no"], text=True)
    if head != commit or dirty:
        raise RuntimeError(f"R055a worktree identity differs: {path}")
    return {"path": str(path), "head": head}




def dry_run() -> dict:
    """Run the final formal file path in a unique non-round execution tree."""
    target = ROUNDS / f".dryrun_R055a_{RID}"
    if target.exists() or target.is_symlink():
        raise RuntimeError(f"R055a dry-run sibling already exists: {target}")
    target.mkdir(mode=0o700)
    wrapper = target / "batch_file_dry_run.sh"
    wrapper.write_text("# CPU FILE PROBE ONLY; never execute this wrapper\n", encoding="utf-8")
    wrapper.chmod(0o444)
    options = SimpleNamespace(case=CARD, rid=RID, batch=1, candidate_commit=CANDIDATE_COMMIT,
                              gate=None, run=True, file_dry_run=True, dry_run_wrapper=wrapper)
    runner = CandidateRunner(options)
    runner.directory = target / "round"
    runner.status = runner.directory / "status_batch1.json"
    runner.execute()
    completed = json.loads((runner.directory / "file_dry_run_complete.json").read_text())
    arms = [json.loads((runner.directory / name / "file_dry_run.json").read_text())
            for name in completed["arms"]]
    owner_path = HERE / "r055a_owned_launch.py"
    spec = importlib.util.spec_from_file_location("r055a_dry_owner", owner_path)
    owner = importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(owner)
    pause = owner.pause_file_dry_run(runner.directory / "PAUSE_ON", runner.port, ROOT / "wt/e2base1-p1")
    worktrees = {"parent": _check_worktree(ROOT / "wt/e2base1-ordinary-rewind", PARENT_COMMIT),
                 "candidate": _check_worktree(ROOT / "wt/e2base1-p1", CANDIDATE_COMMIT)}
    receipt = {"schema": "ft_r055a_dry_run/v2", "rid": RID,
               "user": {"uid": getattr(os, "getuid", lambda: None)(), "user": os.environ.get("USER")},
               "cwd": os.getcwd(), "owner_path": str(owner_path.resolve()), "adapter_path": str(Path(__file__).resolve()),
               "formal_rid_directory_created": False, "formal_directory": str(ROUNDS / RID), "service_started": False,
               "requests_sent": False, "gpu_lock_taken": False, "batch_allocated": False,
               "port": runner.port, "worktrees": worktrees, "arms": arms, "pause_on": pause,
               "source_sha256": owner.source_hashes(), "passed": True}
    if (ROUNDS / RID).exists() or runner.proc is not None:
        raise RuntimeError("R055a file dry-run touched a formal round or process")
    path = target / "dry_run_receipt.json"
    write_new(path, receipt); _dry_base().freeze(path)
    return {**receipt, "dry_run_directory": str(target), "receipt_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main(argv_in=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    options = parser.parse_args(argv_in)
    if options.dry_run:
        print(json.dumps(dry_run(), sort_keys=True))
        return 0
    if options.self_test:
        base.base["self_test"](); return 0
    print(json.dumps({"schema": "ft_r055a_gate_prepare/v1", "rid": RID, "requests_sent": False,
                      "gpu_lock_taken": False, "source_execution_ready": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
