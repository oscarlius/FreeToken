"""Run the existing T16 protocol against an explicitly declared candidate.

R050/R051 dedicated D15 adapter; shared runners and rounds remain immutable.  This adapter reuses a pinned
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

BASE_SHA256 = "fed5ae7bbc6dcb94afcc39d6a5916a596871e3a1e5a9bca2c40df28175a4be58"
ADAPTER_SOURCE_SHA256 = '3a85f8e378862e6971f1b72164107c54fefe3b0c858f84d4332979eb28bf0a9c'
HERE = Path(__file__).resolve().parent
BASE_PATH = HERE / 't16_private_port_dryrun_base_v2.py'
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
    'D15': {
        'card': 'D15', 'parent_wt': 'e2base1-p1', 'new_wt': 'e2d15',
        'parent_commit': 'effb9969706922ddad9e59b96377e46469ebe97f',
        'new_commit': '988c9e183c8dca4415fd9b5d02318b26664da619', 'ordinary_prefill': False,
    },
}

ASSIGNED_RID = 'E2-R050-gate-D15'

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

    def environment(self, wt, arm=None, d0=False):
        # The pinned base clears inherited flags before adding this arm's D0.
        env = super().environment(wt, arm, d0)
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
        extensions = {'parent': self.compiled_extensions(parent_wt), 'new': self.compiled_extensions(new_wt)}
        if ({k: v['sha256'] for k, v in extensions['parent'].items()}
                != {k: v['sha256'] for k, v in extensions['new'].items()}):
            raise ValueError('compiled extensions differ between parent and candidate')
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
