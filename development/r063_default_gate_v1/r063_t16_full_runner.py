"""Run the existing T16 protocol against an explicitly declared candidate.

R063 dedicated D12 adapter; shared runners and rounds remain immutable.  This adapter reuses a pinned
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
import signal
import sys

BASE_SHA256 = "22ed68905b64a19c75251bf7be9d9ac9ebfd5464e4565ab2c757cd8dbea2f1d1"
HERE = Path(__file__).resolve().parent
BASE_PATH = HERE / 't16_private_port_dryrun_r063_v1.py'
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
# Keep the original request clients even when the shared scripts gain options.
base['SCR'] = HERE / 't16_frozen_helpers_v1'
ROOT, ROUNDS = base['ROOT'], base['ROUNDS']
WRAPPERS = ROOT / 'runs/plan_batches'
CASES = {
    'D12': {
        'card': 'D12', 'parent_wt': 'e2base1-p1', 'new_wt': 'e2d12-short-suffix',
        'parent_commit': 'effb9969706922ddad9e59b96377e46469ebe97f',
        'new_commit': '8f6a912ea6066f192c37dc74435efc9da0c7591c', 'ordinary_prefill': False,
    },
}

ASSIGNED_RID = 'E2-R063-gate-D12'
DEFAULT_OFF_CANDIDATE_ARG = 'moe_prefill_routed_only_max_tokens'
DEFAULT_OFF_CANDIDATE_ARGS = {DEFAULT_OFF_CANDIDATE_ARG: '0'}
# Exact imports reviewed separately for each immutable worktree. Binary identity
# across these two builds is not a T16 output-equivalence requirement.
EXTENSION_SHA256 = {'parent': {'_cpu_moe': '10a2bd8311b9569bd03a6569db59da707699a44e67d7b677c35c3547d77855b4', '_pinned_tensor': '07701be28030c4ebf63c210804b6eba2556cc0f4d2f1e5ed80b9d423ebfe7e68'}, 'new': {'_cpu_moe': '10a2bd8311b9569bd03a6569db59da707699a44e67d7b677c35c3547d77855b4', '_pinned_tensor': '07701be28030c4ebf63c210804b6eba2556cc0f4d2f1e5ed80b9d423ebfe7e68'}}
EXTENSION_SIZE = {'parent': {'_cpu_moe': 12448560, '_pinned_tensor': 10841304}, 'new': {'_cpu_moe': 12448560, '_pinned_tensor': 10841304}}
PARENT_NATIVE_PROVENANCE_SHA256 = '272a6129692f5b72d8ef58399b00bc361c4eb234967ae5f27ada147502b373a5'
PARENT_NATIVE_PROVENANCE = ROOT / 'runs/dev_T16/r063_d12_parent_native_provenance_v1.json'
CANDIDATE_NATIVE_PROVENANCE = ROOT / 'runs/dev_T16/r063_d12_native_provenance_v1.json'
CANDIDATE_NATIVE_PROVENANCE_SHA256 = 'ca7feeffa5b59e79c5bfef9bae761f7d888e54ecfe5f572967d249e0f65023f4'


def require_native_provenance():
    if PARENT_NATIVE_PROVENANCE_SHA256 is None or CANDIDATE_NATIVE_PROVENANCE_SHA256 is None:
        raise ValueError('R063 D12 native provenance SHA is pending independent remote evidence')
    path = PARENT_NATIVE_PROVENANCE
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222:
        raise ValueError('native provenance is absent, symlinked or writable')
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != PARENT_NATIVE_PROVENANCE_SHA256:
        raise ValueError('native provenance SHA binding differs')
    value = json.loads(payload)
    if (value.get('schema') != 'ft_r063_d12_parent_native_provenance/v1'
            or value.get('parent_commit') != CASES['D12']['parent_commit']):
        raise ValueError('native provenance commit binding differs')
    candidate_path = CANDIDATE_NATIVE_PROVENANCE
    if candidate_path.is_symlink() or not candidate_path.is_file() or candidate_path.stat().st_mode & 0o222:
        raise ValueError('candidate native provenance is absent, symlinked or writable')
    candidate_payload = candidate_path.read_bytes()
    if hashlib.sha256(candidate_payload).hexdigest() != CANDIDATE_NATIVE_PROVENANCE_SHA256:
        raise ValueError('candidate native provenance SHA binding differs')
    candidate = json.loads(candidate_payload)
    wanted = {'schema': 'ft_r063_d12_native_provenance/v1', 'candidate_commit': CASES['D12']['new_commit'],
              'parent_commit': CASES['D12']['parent_commit'], 'candidate_worktree': str(ROOT / 'wt/e2d12-short-suffix'),
              'regular_extensions': {'parent': {'sha256': EXTENSION_SHA256['parent'], 'size': EXTENSION_SIZE['parent']},
                                     'candidate': {'sha256': EXTENSION_SHA256['new'], 'size': EXTENSION_SIZE['new']}},
              'native_source_diff_empty': True, 'd12_cpu_report': {'tests': '60 passed, 3 skipped', 'path': '/data2/FreeToken/runs/dev_D12/cpu_8f6a912_20261008/report.json', 'sha256': '401a6db4a839e2fc405a73e4fcf7e9f85c3cf410aac82a32afdfcd5855e633ca', 'log_sha256': '668ca3974054d9bd40d6dcfd1133253b90941176932797f589042a211da148a9'},
              'cpu_only': True, 'gpu_validation_performed': False}
    csrc = ROOT / 'wt/e2d12-short-suffix/python/freetoken/kernel/csrc/cpu_moe/cpu_moe_ext.cpp'
    parent_csrc = ROOT / 'wt/e2base1-p1/python/freetoken/kernel/csrc/cpu_moe/cpu_moe_ext.cpp'
    if (any(candidate.get(key) != expected for key, expected in wanted.items())
            or candidate.get('csrc_sha256') != hashlib.sha256(csrc.read_bytes()).hexdigest()
            or hashlib.sha256(csrc.read_bytes()).hexdigest() != hashlib.sha256(parent_csrc.read_bytes()).hexdigest()):
        raise ValueError('candidate native provenance source/ABI/CPU binding differs')
    if candidate.get('import', {}).get('cuda_initialized') is not False:
        raise ValueError('candidate import proof initialized CUDA')
    return path


def validate_extensions(extensions, parent_wt, new_wt):
    if EXTENSION_SHA256 is None or EXTENSION_SIZE is None:
        raise ValueError('R063 extension hashes are pending independent native provenance')
    if set(extensions) != {'parent', 'new'}:
        raise ValueError('compiled extension worktree keys differ')
    for role, wt in (('parent', parent_wt), ('new', new_wt)):
        actual, expected = extensions[role], EXTENSION_SHA256[role]
        if set(actual) != set(expected):
            raise ValueError('compiled extension module keys differ')
        for name, wanted_sha in expected.items():
            wanted_path = wt / 'python/freetoken/kernel' / (name + '.cpython-310-x86_64-linux-gnu.so')
            # Verified regular copies match the effb parent binaries and complete unchanged csrc tree.
            origin_wt = wt
            wanted_origin = origin_wt / 'python/freetoken/kernel' / wanted_path.name
            record = actual[name]
            if (record.get('path') != str(wanted_path)
                    or wanted_path.resolve() != wanted_origin.absolute()
                    or wanted_origin.resolve() != wanted_origin.absolute()
                    or record.get('sha256') != wanted_sha
                    or record.get('size') != EXTENSION_SIZE[role][name]):
                raise ValueError('compiled extension path/SHA binding differs')

def validate_identity(options):
    case = CASES[options.case]
    if options.rid != ASSIGNED_RID:
        raise ValueError('RID must name a newly assigned E2 round and the declared card')
    if type(options.batch) is not int or options.batch < 1:
        raise ValueError('positive batch identity required')
    if options.candidate_commit != case['new_commit']:
        raise ValueError('candidate commit differs from the declared immutable candidate')
    return case


class CandidateRunner(base['Runner']):
    def __init__(self, options):
        self.case = validate_identity(options)
        options.gate = self.case['card']
        super().__init__(options)
        # This candidate alone introduces the parsed default-off threshold.
        # Keep the whitelist exact so the pinned base's per-arm checks reject
        # every other launch-argument delta before probes run.
        self.allowed = DEFAULT_OFF_CANDIDATE_ARGS

    def compiled_extensions(self, wt):
        imports = super().compiled_extensions(wt)
        for record in imports.values():
            path = Path(record['path'])
            record.update(size=path.stat().st_size, resolved_path=str(path.resolve()))
        return imports

    def environment(self, wt, arm=None, d0=False):
        # The pinned base clears inherited flags before adding this arm's D0.
        env = super().environment(wt, arm, d0)
        # R063 is the default-path gate: inherited developer experimentation
        # may not turn profile/adapt on for either comparison arm.
        env['FT_DEV_EXPERT_POLICY'] = 'lru'
        env['FT_DEV_EXPERT_ADAPT_EVERY'] = '0'
        env['FT_DEV_EXPERT_ADAPT_SWAPS'] = '0'
        # CPU validation shells may have hidden CUDA; GPU execution is explicit.
        env['CUDA_VISIBLE_DEVICES'] = '' if getattr(self.options, 'file_dry_run', False) else '0'
        return env

    @staticmethod
    def assert_default_off_args(parent: dict, candidate: dict) -> None:
        """Require the actual candidate option and its disabled parsed value."""
        key, expected = DEFAULT_OFF_CANDIDATE_ARG, DEFAULT_OFF_CANDIDATE_ARGS[DEFAULT_OFF_CANDIDATE_ARG]
        if key not in candidate or candidate[key] != expected:
            raise ValueError('D12 candidate is missing its parsed default-off zero threshold')
        changed = {name for name in set(parent) | set(candidate) if parent.get(name) != candidate.get(name)}
        if changed - {key}:
            raise ValueError('D12 default-off parsed arguments differ outside the candidate threshold')

    def set_status(self, **values):
        super().set_status(rid=self.options.rid, candidate_case=self.options.case, **values)

    def compare(self, parent, new, parent_p, new_p, cases=None):
        result = {}
        for label, a, b in (('D0', parent, new), ('PROD', parent_p, new_p)):
            parent_args, candidate_args = self.parser(str(a / 'serve.log')), self.parser(str(b / 'serve.log'))
            self.assert_default_off_args(parent_args, candidate_args)
            result[label] = {'args': base['strict_args'](parent_args, candidate_args, self.allowed)}
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
            if not base['has_d02_prefill_tail'](wt):
                raise ValueError('both declared trees must publish the D02 final prefill segment')
        # A card contains several rebased commits; the comparison tree is its
        # declared ancestor, rather than the parent of its final docs commit.
        actual_parent = base['command'](['git', '-C', str(new_wt), 'merge-base',
                                        case['parent_commit'], 'HEAD'])
        if actual_parent != case['parent_commit']:
            raise ValueError('candidate ancestry differs from the declared comparison')
        require_native_provenance()
        extensions = {'parent': self.compiled_extensions(parent_wt), 'new': self.compiled_extensions(new_wt)}
        validate_extensions(extensions, parent_wt, new_wt)
        self.gate(parent_wt, case['parent_commit'])
        base['command'](['numactl', '--cpunodebind=0,1', '--interleave=all', base['FT'], '--help'],
                        env=self.environment(parent_wt), cwd=parent_wt)
        for name in base['TOOL_MD5']:
            path = base['SCR'] / name
            if path.is_symlink() or not path.is_file() or (sys.platform == 'linux' and path.stat().st_mode & 0o222):
                raise ValueError('T16 original helper is absent, symlinked, or writable')
        hashes = {name: hashlib.md5((base['SCR'] / name).read_bytes()).hexdigest()
                  for name in base['TOOL_MD5']}
        if hashes != base['TOOL_MD5']:
            raise ValueError('T16 probe source hashes differ from the pinned protocol')
        print('PREFLIGHT PASS ' + json.dumps({'case': opts.case, **case, 'tools': hashes}), flush=True)
        if not opts.run:
            return
        wrapper = Path(opts.dry_run_wrapper) if getattr(opts, 'file_dry_run', False) else WRAPPERS / f'batch{opts.batch}_{opts.rid}_python.sh'
        if not wrapper.is_file() or wrapper.is_symlink():
            raise ValueError('atomic launcher wrapper is missing or a symlink')
        # Acquire the global lock before creating a writable round directory.
        if not getattr(opts, 'file_dry_run', False):
            self.lock_take()
        owned_directory = False
        try:
            self.directory.mkdir(exist_ok=False)
            owned_directory = True
            base['write_new'](self.directory / f'tools_batch{opts.batch}.json', hashes)
            base['write_new'](self.directory / 'candidate_binding.json', {
                'case': opts.case, **case, 'base_runner_sha256': BASE_SHA256,
                'base_runner_filename': BASE_PATH.name,
                'candidate_runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'helper_sources': {name: {'path': str(base['SCR'] / name),
                    'sha256': hashlib.sha256((base['SCR'] / name).read_bytes()).hexdigest()}
                    for name in base['TOOL_MD5']},
                'compiled_extensions': extensions, 'CUDA_VISIBLE_DEVICES': '0',
                'parent_native_commit': case['parent_commit'],
                'parent_native_provenance_sha256': PARENT_NATIVE_PROVENANCE_SHA256,
                'candidate_native_provenance_sha256': CANDIDATE_NATIVE_PROVENANCE_SHA256,
                'window': 98304, 'memory_ratio': 0.88,
            })
            for src, name in ((Path(__file__), f'runner_batch{opts.batch}.py'),
                              (BASE_PATH, f'base_runner_batch{opts.batch}.py'),
                              (wrapper, f'batch{opts.batch}.sh'), (wrapper, 'batch.sh')):
                with (self.directory / name).open('xb') as target:
                    target.write(_base_source if src == BASE_PATH else src.read_bytes())
            self.set_status(state='running')
            result = {'arms': []}
            modes = [('layer_major', True, None)]
            if case['ordinary_prefill']:
                modes.append(('non_layer_major', False, [
                    ('short', opts.rid + '-short', 2000, 128),
                    ('chunked', opts.rid + '-chunked', 32052, 128),
                ]))
            for mode, layer_major, samples in modes:
                prefix = '' if layer_major else 'CHUNK_'
                suffix = f'_b{opts.batch}'
                p = self.run_arm(prefix + 'PARENT' + suffix, parent_wt, case['parent_commit'],
                                 True, layer_major, cases=samples)
                n = self.run_arm(prefix + 'NEW' + suffix, new_wt, case['new_commit'],
                                 True, layer_major, compare_to=p, cases=samples)
                pp = self.run_arm(prefix + 'PARENT_P' + suffix, parent_wt, case['parent_commit'],
                                  False, layer_major, cases=samples)
                np = self.run_arm(prefix + 'NEW_P' + suffix, new_wt, case['new_commit'],
                                  False, layer_major, compare_to=pp, cases=samples)
                if not getattr(opts, 'file_dry_run', False):
                    result[mode] = self.compare(p, n, pp, np, samples)
                result['arms'].extend(a.name for a in (p, n, pp, np))
            if getattr(opts, 'file_dry_run', False):
                base['write_new'](self.directory / 'file_dry_run_complete.json', {
                    'arms': result['arms'], 'service_started': False,
                    'requests_sent': False, 'gpu_lock_taken': False,
                })
                base['write_new'](self.directory / f'gate_batch{opts.batch}.json', {'dry_run': True, 'arms': result['arms']})
                self.set_status(state='file_dry_run_complete')
                return
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
    if sys.platform != 'linux' or not opts.case:
        parser.error('Linux test host and an explicit candidate case are required')
    runner = CandidateRunner(opts)
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda signum, frame: (_ for _ in ()).throw(InterruptedError(f'signal {signum}')))
    runner.execute()


if __name__ == '__main__':
    main()
