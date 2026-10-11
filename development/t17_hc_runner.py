"""Original-4096 HC boundary diagnostic; never treats a diagnostic as T17 acceptance."""
import argparse
import json
from pathlib import Path
import re
import signal
import sys

import t17_matched_runner as retained
from t17_matched_runner import artifacts, helper, original


HERE = Path(__file__).resolve().parent
ROLES = ('embedding_output', 'hc_mix_input', 'hc_down_input', 'hc_down_output',
         'hc_up_input', 'hc_up_output', 'hc_mix_output', 'gdn_qkv_input', 'gdn_qkv_output')


def _inside(root, path):
    return not path.is_symlink() and root.resolve() in path.resolve().parents


def observation(arm, uid, *, device, extend):
    root = arm / 'hc'
    final = json.loads((root / ('final_' + str(uid) + '.json')).read_bytes())
    if final.get('valid') is not True or str(final.get('uid')) != str(uid) or final.get('positions') != list(range(4608, 4672)):
        raise ValueError('HC terminal observation is incomplete')
    receipt_path = root / final['receipt_file']
    if not _inside(root, receipt_path) or helper.sha256(receipt_path) != final['receipt_sha256']:
        raise ValueError('HC receipt changed')
    record = json.loads(receipt_path.read_bytes())
    if (record.get('schema') != 't17_hc_observe/v1' or str(record.get('uid')) != str(uid)
            or record.get('cached_tokens') != 4608 or record.get('device_tokens') != device
            or record.get('extend_tokens') != extend or record.get('positions') != list(range(4608, 4672))
            or set(record.get('roles', ())) != set(ROLES)):
        raise ValueError('HC target coordinates or roles differ')
    installed = [json.loads(path.read_bytes()) for path in root.glob('installed_*.json')]
    if (len(installed) != 1 or installed[0].get('FT_LM_CHUNK') != '4096'
            or installed[0].get('output_dir') != str(root)
            or installed[0].get('observer_source_sha256') != helper.sha256(HERE / 't17_hc_observe.py')
            or installed[0].get('startup_source_sha256') != helper.sha256(HERE / 't17_hc_startup.py')):
        raise ValueError('HC source installation differs')
    structure, selection = installed[0].get('model_structure', {}), record.get('selection')
    if (selection != installed[0].get('decoder_selection') or selection.get('gdn', {}).get('decoder_index') != 0
            or selection['gdn'].get('decoder_layer_id') != 0 or selection.get('ple', {}).get('decoder_index') != 1
            or selection['ple'].get('decoder_layer_id') != 1 or selection.get('parsed_ple_layer_ids') != [1]
            or structure.get('hf_ple_layer_ids') != [2] or structure.get('parsed_ple_decoder_indices') != [1]
            or structure.get('parser', {}).get('sha256') != '72905266db8c384ea3cd267a1b739c58a32b8b069f37039b778665cc2be14607'):
        raise ValueError('HC GDN0/PLE1/parser binding differs')
    tensors = {}
    for role in ROLES:
        meta = record['roles'][role]
        if any(meta.get(key) != record.get(key) for key in ('uid', 'slot', 'cached_tokens', 'device_tokens', 'extend_tokens', 'positions')):
            raise ValueError('HC role identity differs: ' + role)
        path = root / meta['file']
        if not _inside(root, path) or helper.sha256(path) != meta['sha256']:
            raise ValueError('HC tensor changed: ' + role)
        binding = meta.get('operation', {}); source = Path(binding.get('source_file', ''))
        if (not source.is_file() or source.is_symlink() or original.WT.resolve() not in source.resolve().parents
                or helper.sha256(source) != binding.get('source_sha256') or not binding.get('method_sha256')):
            raise ValueError('HC operation binding differs: ' + role)
        tensor = artifacts.load_tensor(path)
        if (list(tensor.shape) != meta['shape'] or str(tensor.dtype) != meta['dtype']
                or list(tensor.stride()) != meta['stride'] or tensor.shape[0] != 64):
            raise ValueError('HC tensor shape/dtype/stride differs: ' + role)
        tensors[role] = tensor
    return record, tensors


def compare_tensors(warm, cold):
    import torch
    rows = {}
    for role in ROLES:
        left, right = warm[role], cold[role]
        if left.shape != right.shape or left.dtype != right.dtype:
            raise ValueError('HC tensor shape/dtype mismatch: ' + role)
        a, b = left.contiguous().view(torch.uint8).reshape(64, -1), right.contiguous().view(torch.uint8).reshape(64, -1)
        different = a != b
        signed_zero = ((left == 0) & (right == 0) & different.reshape(left.shape[0], *left.shape[1:], -1).any(dim=-1)).sum()
        changed_rows = different.any(dim=1)
        rows[role] = {'equal': artifacts.bit_equal(left, right), 'shape': list(left.shape), 'dtype': str(left.dtype),
                      'max_abs': float((left.float() - right.float()).abs().max()) if left.numel() else 0.0,
                      'different_values': int((left != right).sum()), 'different_bytes': int(different.sum()),
                      'signed_zero_rows_or_values': int(signed_zero),
                      'different_positions': [4608 + index for index, changed in enumerate(changed_rows.tolist()) if changed]}
    return rows


class Run(retained.Run):
    def startup_wrapper(self): return HERE / 't17_hc_startup.py'

    def environment(self, wt, arm=None, d0=False):
        env = super().environment(wt, arm, d0); env['FT_LM_CHUNK'] = '4096'; env.pop('FT_T17_MATCHED', None)
        if arm is not None: env['FT_T17_HC'] = str(arm / 'hc')
        return env

    def execute(self):
        prior = retained.prerequisite(); helper.t16_prerequisite(); self.gate(original.WT, helper.CANDIDATE)
        if not self.options.run:
            print(json.dumps({'preflight': 'PASS', 'diagnostic_only': True, 'FT_LM_CHUNK': 4096, 'prerequisite': prior})); return
        self.lock_take(); owned = False
        try:
            if self.directory.exists(): raise FileExistsError('HC diagnostic already exists')
            self.directory.mkdir(); owned = True; original.put(self.directory / 'prerequisite.json', prior)
            names = ('t17_d14_gpu.py', 't17_d14_runner.py', 't17_d14_artifacts.py', 't17_d14_observe.py',
                     't17_matched_runner.py', 't17_original_startup.py', 't17_d14_exact_ids.py',
                     't17_owned_launch_protocol.py', 't16_full_tail_base_runner.py', 't17_hc_runner.py',
                     't17_hc_observe.py', 't17_hc_startup.py', 't17_projection_startup.py', 'real_inputs.json')
            for name in names:
                source = HERE / name
                if source.is_symlink() or source.stat().st_mode & 0o222: raise ValueError('execution dependency is not frozen')
                with (self.directory / name).open('xb') as stream: stream.write(source.read_bytes())
            case = json.loads((HERE / 'real_inputs.json').read_bytes())['cases'][0]
            if case['length'] != 8192: raise ValueError('original 8192 counterexample required')
            if helper.sha256(HERE / 'real_inputs.json') != helper.sha256(retained.R023 / 'real_inputs.json'):
                raise ValueError('retained exact input cases changed')
            def warm(arm):
                donor = self.request(arm, 'donor', case['donor'], 0, 2)
                captured, _ = observation(arm, donor['uid'], device=8193, extend=3585)
                hit = self.request(arm, 'short', case['short'], 8192, 128)
                return donor, hit, captured
            donor, hit, hot = self.service('hc_warm', warm)
            def fresh(arm):
                cold = self.request(arm, 'query', case['short'], 0, 128)
                captured, _ = observation(arm, cold['uid'], device=8257, extend=3649)
                return cold, captured
            cold, cool = self.service('hc_cold', fresh)
            warm_arm, cold_arm = self.directory / 'hc_warm', self.directory / 'hc_cold'
            _, warm_tensors = observation(warm_arm, donor['uid'], device=8193, extend=3585)
            _, cold_tensors = observation(cold_arm, cold['uid'], device=8257, extend=3649)
            roles = compare_tensors(warm_tensors, cold_tensors)
            raw = artifacts.validate_case({'name': 'hc-8192', 'length': 8192, 'trace_index': case['trace_index'],
                                           'context': case['expected_ngram']}, cold_arm, warm_arm, tail=65,
                                          cold_request='query', hit_request='short', state_root=warm_arm / 'dump')
            def donate(arm, uid): return helper.load_dump_record(arm / 'dump', kind='donate', length=8256, uid=str(uid))
            suffix = original.tensor_comparison(warm_arm / 'dump', donate(warm_arm, hit['uid']),
                                                cold_arm / 'dump', donate(cold_arm, cold['uid']))
            original.put(self.directory / ('diagnostic_batch' + str(self.options.batch) + '.json'), {
                'schema': 'ft_t17_hc_diagnostic/v1', 'rid': self.options.rid, 'batch': self.options.batch,
                'diagnostic_only': True, 'candidate_commit': helper.CANDIDATE, 'FT_LM_CHUNK': 4096,
                'warm_observation': hot, 'cold_observation': cool, 'hc_roles': roles, 'suffix_8256': suffix,
                'raw_validator': raw, 'tokens_equal': raw['tokens_bitwise_equal'], 'text_equal': raw['full_text_equal'],
                'acceptance': 'diagnostic_measurement_pending_review; original_T17_not_met_retained'})
            self.set_status(state='complete_measurements_pending_review')
        except BaseException as error:
            if owned: self.set_status(state='failed', error=repr(error))
            raise
        finally:
            try: self.stop()
            finally:
                if self.proc is None: self.lock_release()


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--rid', required=True); parser.add_argument('--batch', type=int, required=True); parser.add_argument('--run', action='store_true')
    options = parser.parse_args()
    if sys.platform != 'linux' or not re.fullmatch(r'E2-R\d{3}-diagnostic-T17', options.rid) or options.batch < 1: parser.error('Linux and exact diagnostic round/batch required')
    options.gate = 'T17-diagnostic'
    for signum in (signal.SIGINT, signal.SIGTERM): signal.signal(signum, lambda *_: (_ for _ in ()).throw(InterruptedError('owned diagnostic signal')))
    Run(options).execute()


if __name__ == '__main__': main()
