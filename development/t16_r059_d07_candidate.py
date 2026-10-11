"""R059 D07 T16 adapter, pinned to its private four-arm protocol copy."""
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

BASE_SHA256 = "d833686ff0f39323cc5787a7ce5e4164509ede85b9b6c7b6009f079a5458672d"
HERE = Path(__file__).resolve().parent
BASE_PATH = HERE / 't16_r059_private_port_base_v3.py'
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
    'D07': {
        'card': 'D07', 'parent_wt': 'e2base1-p1', 'new_wt': 'e2d07-trace-lm',
        'parent_commit': 'effb9969706922ddad9e59b96377e46469ebe97f',
        'new_commit': '151ee718b88882b57dba75317bb53c697d5f235f', 'ordinary_prefill': False,
    },
}

ASSIGNED_RID = 'E2-R059-gate-D07'
# Root copies the verified parent native artifacts into the candidate worktree.
# Their bytes are an admission invariant, not a T16 equivalence output.
EXTENSION_SHA256 = {
    'parent': {
        '_cpu_moe': '10a2bd8311b9569bd03a6569db59da707699a44e67d7b677c35c3547d77855b4',
        '_pinned_tensor': '07701be28030c4ebf63c210804b6eba2556cc0f4d2f1e5ed80b9d423ebfe7e68',
    },
    'new': {
        '_cpu_moe': '10a2bd8311b9569bd03a6569db59da707699a44e67d7b677c35c3547d77855b4',
        '_pinned_tensor': '07701be28030c4ebf63c210804b6eba2556cc0f4d2f1e5ed80b9d423ebfe7e68',
    },
}
EXTENSION_SIZE = {'parent': {'_cpu_moe': 12448560, '_pinned_tensor': 10841304},
                  'new': {'_cpu_moe': 12448560, '_pinned_tensor': 10841304}}
PARENT_NATIVE_COMMIT = '23f2e2caa3395837c9474735ffc83321f3b9b5a1'
PARENT_NATIVE_PROVENANCE_SHA256 = 'adeb2ccd8378f4b6ac78313a4ec23f3104381fb533939f18b36dc5ba6ef27bfc'
PARENT_NATIVE_PROVENANCE = ROOT / 'runs/dev_T16/r051_eff_parent_native_provenance_20261007.json'
CANDIDATE_NATIVE_PROVENANCE = ROOT / 'runs/dev_T16/r059_d07_native_provenance_20261007.json'
# This remains deliberately unset until root writes and reports the candidate
# provenance digest.  It must not be guessed or supplied at launch time.
CANDIDATE_NATIVE_PROVENANCE_SHA256 = '93b56f403ad08062c222cbe60e8f3acc703c174e7c4387c7d41e15c74fb483e1'


def require_native_provenance():
    path = PARENT_NATIVE_PROVENANCE
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222:
        raise ValueError('native provenance is absent, symlinked or writable')
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != PARENT_NATIVE_PROVENANCE_SHA256:
        raise ValueError('native provenance SHA binding differs')
    value = json.loads(payload)
    if (value.get('schema') != 'ft_r051_parent_native_provenance/v1'
            or value.get('business_python_parent', {}).get('commit') != CASES['D07']['parent_commit']
            or value.get('native_artifact_origin', {}).get('commit') != PARENT_NATIVE_COMMIT):
        raise ValueError('native provenance commit binding differs')
    candidate_path = CANDIDATE_NATIVE_PROVENANCE
    if candidate_path.is_symlink() or not candidate_path.is_file() or candidate_path.stat().st_mode & 0o222:
        raise ValueError('candidate native provenance is absent, symlinked or writable')
    candidate_payload = candidate_path.read_bytes()
    if hashlib.sha256(candidate_payload).hexdigest() != CANDIDATE_NATIVE_PROVENANCE_SHA256:
        raise ValueError('candidate native provenance SHA binding differs')
    candidate = json.loads(candidate_payload)
    wanted = {'schema': 'ft_r059_d07_native_provenance/v1', 'candidate_commit': CASES['D07']['new_commit'],
              'parent_commit': CASES['D07']['parent_commit'], 'native_artifact_origin_commit': PARENT_NATIVE_COMMIT,
              'parent_provenance': str(PARENT_NATIVE_PROVENANCE),
              'parent_provenance_sha256': PARENT_NATIVE_PROVENANCE_SHA256,
              'worktree': str(ROOT / 'wt/e2d07-trace-lm'), 'native_sources_unchanged': True,
              'existing_trees_modified': False, 'gpu_api_called': False, 'model_endpoints_connected': False}
    expected_native = {
        name: {'path': str(ROOT / 'wt/e2d07-trace-lm/python/freetoken/kernel' / (name + '.cpython-310-x86_64-linux-gnu.so')),
               'source': str(ROOT / 'wt/e2base1-p1/python/freetoken/kernel' / (name + '.cpython-310-x86_64-linux-gnu.so')),
               'sha256': EXTENSION_SHA256['new'][name], 'size': EXTENSION_SIZE['new'][name], 'regular_copy': True}
        for name in EXTENSION_SHA256['new']
    }
    if (any(candidate.get(key) != expected for key, expected in wanted.items())
            or candidate.get('native') != expected_native):
        raise ValueError('candidate native provenance source/ABI/CPU binding differs')
    return path


def validate_extensions(extensions, parent_wt, new_wt):
    if set(extensions) != {'parent', 'new'}:
        raise ValueError('compiled extension worktree keys differ')
    for role, wt in (('parent', parent_wt), ('new', new_wt)):
        actual, expected = extensions[role], EXTENSION_SHA256[role]
        if set(actual) != set(expected):
            raise ValueError('compiled extension module keys differ')
        for name, wanted_sha in expected.items():
            wanted_path = wt / 'python/freetoken/kernel' / (name + '.cpython-310-x86_64-linux-gnu.so')
            # Verified regular copies retain their explicit 23f2 build origin.
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

    def compiled_extensions(self, wt):
        imports = super().compiled_extensions(wt)
        for record in imports.values():
            path = Path(record['path'])
            record.update(size=path.stat().st_size, resolved_path=str(path.resolve()))
        return imports

    def gate(self, wt, commit):
        """Keep file-dry metadata checks real without touching GPU admission."""
        if not getattr(self.options, 'file_dry_run', False):
            return super().gate(wt, commit)
        actual = base['command'](['git', '-C', str(wt), 'rev-parse', 'HEAD'])
        if actual != commit:
            raise RuntimeError(f'source commit does not match: {actual} != {commit}')
        if base['command'](['git', '-C', str(wt), 'status', '--porcelain', '--untracked-files=no']):
            raise RuntimeError('tracked source tree is dirty')
        env = self.environment(wt)
        if env.get('CUDA_VISIBLE_DEVICES') != '' or env.get('PYTHONPATH') != str(wt / 'python'):
            raise RuntimeError('file-dry environment is not CPU/socket guarded')
        source = base['command']([base['PY'], '-c',
            'import freetoken,torch,freetoken.kernel._cpu_moe,freetoken.kernel._pinned_tensor;'
            f'assert freetoken.__file__ == {str(wt / "python/freetoken/__init__.py")!r};'
            'print(freetoken.__file__,torch.__version__,torch.version.cuda)'], env=env, cwd=wt)
        return source

    def environment(self, wt, arm=None, d0=False):
        # The pinned base clears inherited flags before adding this arm's D0.
        env = super().environment(wt, arm, d0)
        # The candidate's D07 switches are disabled for all four comparable
        # arms; absence is the product's zero/default state.
        env.pop('FT_DEV_ROUTE_TRACE', None)
        env.pop('FT_DEV_PAUSE_ENDPOINT', None)
        # CPU validation shells may have hidden CUDA; GPU execution is explicit.
        env['CUDA_VISIBLE_DEVICES'] = '' if getattr(self.options, 'file_dry_run', False) else '0'
        return env

    def set_status(self, **values):
        super().set_status(rid=self.options.rid, candidate_case=self.options.case, **values)

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
        self.gate(parent_wt.parent / 'e2base', PARENT_NATIVE_COMMIT)
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
                'trace_enabled': 0, 'pause_endpoint_enabled': 0,
                'parent_native_commit': PARENT_NATIVE_COMMIT,
                'parent_native_provenance_sha256': PARENT_NATIVE_PROVENANCE_SHA256,
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
