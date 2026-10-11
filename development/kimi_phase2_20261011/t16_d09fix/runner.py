"""Run the pinned T16 protocol against the D09 default-off candidate.

This D09 adapter keeps the original protocol and its owned lifecycle intact.
It permits exactly one candidate-only parsed default: the public
``--enable-message-boundary-ckpt`` flag remains false.
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
BASE_PATH = HERE / 't16_private_port_dryrun_r062_v1.py'
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
    'D09FIX': {
        'card': 'D09FIX', 'parent_wt': 'release-e2', 'new_wt': 'd09_fix_20261011',
        'parent_commit': '481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9',
        'new_commit': '7d8d389ee5d85de7e4f8e533f35c27f4c4c02690', 'ordinary_prefill': True,
    },
}

ASSIGNED_RID = 'E2-D09FIX-T16-20261011'
PUBLIC_DEFAULT_OFF_FLAG = 'enable_message_boundary_ckpt'
# ServerArgs prints its dataclass destination, while the public CLI flag is
# --enable-message-boundary-ckpt.  The canonical comparison record preserves
# the public spelling, but only the destination appears in a real serve.log.
PARSED_DEFAULT_OFF_ARG = 'message_boundary_ckpt'
DEFAULT_OFF_CANDIDATE_ARGS = {PARSED_DEFAULT_OFF_ARG: 'False'}
EXTENSION_SHA256 = {'parent': {'_cpu_moe': '10a2bd8311b9569bd03a6569db59da707699a44e67d7b677c35c3547d77855b4', '_pinned_tensor': '07701be28030c4ebf63c210804b6eba2556cc0f4d2f1e5ed80b9d423ebfe7e68'}, 'new': {'_cpu_moe': '10a2bd8311b9569bd03a6569db59da707699a44e67d7b677c35c3547d77855b4', '_pinned_tensor': '07701be28030c4ebf63c210804b6eba2556cc0f4d2f1e5ed80b9d423ebfe7e68'}}
EXTENSION_SIZE = {'parent': {'_cpu_moe': 12448560, '_pinned_tensor': 10841304}, 'new': {'_cpu_moe': 12448560, '_pinned_tensor': 10841304}}
NATIVE_LINK_SOURCE_COMMIT = 'c17b69a46cd512fbf3d127d3879bce92caae457b'
NATIVE_LINK_SOURCE_WORKTREE = ROOT / 'wt/d09-message-boundary-v1'
NATIVE_EXTENSION_SUFFIX = '.cpython-310-x86_64-linux-gnu.so'
NATIVE_PROVENANCE = HERE / 'd09fix_native_provenance_7d8d389e.json'
NATIVE_PROVENANCE_SHA256 = '6d9de3232c799777caaa6f4ec9104911f64740a5653ead894c5c811f96500f7c'


def require_native_provenance():
    if NATIVE_PROVENANCE_SHA256 == 'PENDING':
        raise ValueError('D09 native provenance SHA is pending remote evidence')
    path = NATIVE_PROVENANCE
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222:
        raise ValueError('native provenance is absent, symlinked or writable')
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != NATIVE_PROVENANCE_SHA256:
        raise ValueError('native provenance SHA binding differs')
    value = json.loads(payload)
    case = CASES['D09FIX']
    wanted = {'schema': 'ft_d09_t16_native_provenance/v1', 'candidate_commit': case['new_commit'],
              'parent_commit': case['parent_commit'], 'candidate_worktree': str(ROOT / 'wt/d09_fix_20261011'),
              'regular_extensions': {'parent': {'sha256': EXTENSION_SHA256['parent'], 'size': EXTENSION_SIZE['parent']},
                                     'candidate': {'sha256': EXTENSION_SHA256['new'], 'size': EXTENSION_SIZE['new']}},
               'candidate_link_source_commit': NATIVE_LINK_SOURCE_COMMIT,
               'candidate_diff_non_python_or_docs': [], 'native_source_abi_unchanged': True,
              'import_cuda_initialized': False, 'cpu_only': True, 'gpu_validation_performed': False}
    if any(value.get(key) != expected for key, expected in wanted.items()):
        raise ValueError('candidate native provenance source/ABI/CPU binding differs')
    return path


def extension_path(worktree: Path, name: str) -> Path:
    return worktree / 'python/freetoken/kernel' / (name + NATIVE_EXTENSION_SUFFIX)


def require_native_extension_layout(parent_wt: Path, new_wt: Path) -> dict:
    """Bind parent regular files and the approved bd57-to-c17 links exactly.

    The bd57 tree is intentionally allowed to link only these two gitignored
    modules.  The source must be the designated clean c17 worktree and remain
    a regular file; no other symlink target, copied binary, build, or ABI may
    enter through this check.
    """
    if new_wt.name != CASES['D09FIX']['new_wt'] or parent_wt.name != CASES['D09FIX']['parent_wt']:
        raise ValueError('compiled extension worktree identities differ')
    source_head = base['command'](['git', '-C', str(NATIVE_LINK_SOURCE_WORKTREE), 'rev-parse', 'HEAD'])
    source_dirty = base['command'](['git', '-C', str(NATIVE_LINK_SOURCE_WORKTREE),
                                    'status', '--porcelain', '--untracked-files=no'])
    if source_head != NATIVE_LINK_SOURCE_COMMIT or source_dirty:
        raise ValueError('approved c17 native source identity or cleanliness differs')
    layout = {'parent': {}, 'new': {}}
    for name in EXTENSION_SHA256['parent']:
        parent_path, candidate_path = extension_path(parent_wt, name), extension_path(new_wt, name)
        source_path = extension_path(NATIVE_LINK_SOURCE_WORKTREE, name)
        if (parent_path.is_symlink() or not parent_path.is_file()
                or parent_path.resolve() != parent_path.absolute()):
            raise ValueError('parent native extension must be a regular exact-path file')
        if (not candidate_path.is_symlink() or not candidate_path.is_file()
                or not source_path.is_file() or source_path.is_symlink()
                or candidate_path.resolve() != source_path.absolute()):
            raise ValueError('candidate native extension must link only to the regular c17 source file')
        if parent_path.name != candidate_path.name or candidate_path.name != source_path.name:
            raise ValueError('native extension ABI filename differs')
        layout['parent'][name] = {'path': parent_path, 'resolved_path': parent_path}
        layout['new'][name] = {'path': candidate_path, 'resolved_path': source_path}
    return layout


def validate_extensions(extensions, parent_wt, new_wt):
    if EXTENSION_SHA256 is None or EXTENSION_SIZE is None:
        raise ValueError('D09 extension hashes are pending native provenance')
    if set(extensions) != {'parent', 'new'}:
        raise ValueError('compiled extension worktree keys differ')
    layout = require_native_extension_layout(parent_wt, new_wt)
    for role, wt in (('parent', parent_wt), ('new', new_wt)):
        actual, expected = extensions[role], EXTENSION_SHA256[role]
        if set(actual) != set(expected):
            raise ValueError('compiled extension module keys differ')
        for name, wanted_sha in expected.items():
            wanted_path = extension_path(wt, name)
            wanted_origin = layout[role][name]['resolved_path']
            record = actual[name]
            if (record.get('path') != str(wanted_path)
                    or record.get('resolved_path') != str(wanted_origin)
                    or record.get('sha256') != wanted_sha
                    or record.get('size') != EXTENSION_SIZE[role][name]):
                raise ValueError('compiled extension path/SHA binding differs')
            if (EXTENSION_SHA256['parent'][name] != EXTENSION_SHA256['new'][name]
                    or EXTENSION_SIZE['parent'][name] != EXTENSION_SIZE['new'][name]):
                raise ValueError('parent and approved c17 native ABI bytes differ')

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
        # The candidate alone adds this default-off ServerArgs field.  All
        # other parsed arguments remain byte-for-byte protocol comparisons.
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
        # CPU validation shells may have hidden CUDA; GPU execution is explicit.
        env['CUDA_VISIBLE_DEVICES'] = '' if getattr(self.options, 'file_dry_run', False) else '0'
        return env

    @staticmethod
    def assert_default_off_args(parent: dict, candidate: dict) -> None:
        """Require the disabled candidate field and the pinned dynamic-only diff."""
        key, expected = PARSED_DEFAULT_OFF_ARG, DEFAULT_OFF_CANDIDATE_ARGS[PARSED_DEFAULT_OFF_ARG]
        if key not in candidate or candidate[key] != expected:
            raise ValueError('D09 candidate is missing its parsed default-off message-boundary flag')
        # The pinned protocol owns the complete comparison policy.  In
        # particular, it validates (and permits) per-process _unique_suffix
        # PID changes while rejecting every other business-argument delta.
        base['strict_args'](parent, candidate, DEFAULT_OFF_CANDIDATE_ARGS)

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
                'native_provenance_filename': NATIVE_PROVENANCE.name,
                'native_provenance_sha256': NATIVE_PROVENANCE_SHA256,
                'default_off_public_flag': {PUBLIC_DEFAULT_OFF_FLAG: False},
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


def adapter_self_test():
    """CPU-only adapter checks; the pinned protocol file remains immutable."""
    if hashlib.sha256(BASE_PATH.read_bytes()).hexdigest() != BASE_SHA256:
        raise AssertionError('pinned T16 base hash changed during adapter self-test')
    case = CASES['D09FIX']
    if (case['parent_commit'] != '481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9'
            or case['new_commit'] != '7d8d389ee5d85de7e4f8e533f35c27f4c4c02690'
            or ASSIGNED_RID != 'E2-D09FIX-T16-20261011'):
        raise AssertionError('D09 identity binding differs')
    parent = {'model_path': "'/model'", 'server_port': '8095',
              'special_token_ckpt': 'True', '_unique_suffix': "'.pid=101'"}
    CandidateRunner.assert_default_off_args(parent, {
        **parent, '_unique_suffix': "'.pid=202'", PARSED_DEFAULT_OFF_ARG: 'False'})
    for invalid in ({**parent, '_unique_suffix': "'.pid=202'"},
                    {**parent, '_unique_suffix': "'.pid=202'", PARSED_DEFAULT_OFF_ARG: 'True'},
                    {**parent, '_unique_suffix': "'.pid=202'", 'server_port': '8096',
                     PARSED_DEFAULT_OFF_ARG: 'False'}):
        try:
            CandidateRunner.assert_default_off_args(parent, invalid)
        except ValueError:
            continue
        raise AssertionError('D09 accepted an invalid parsed default-off delta')
    print('D09 RETRY1 ADAPTER SELFTEST PASS: dynamic PID accepted; business argument delta rejected')


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
        adapter_self_test()
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
