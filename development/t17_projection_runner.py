"""Observe six first-layer tensors under original 4096 chunking, diagnostic only."""
import argparse
import json
from pathlib import Path
import re
import signal
import sys

import t17_matched_runner as retained
from t17_matched_runner import original, helper, artifacts

HERE = Path(__file__).resolve().parent
ROLES = ('embedding_output', 'ple_input', 'ple_value_projection_output',
         'ple_conv_output', 'gdn_qkv_input', 'gdn_qkv_output')


def projection(arm, uid, cached):
    root = arm / 'projection'
    final = json.loads((root / ('final_' + str(uid) + '.json')).read_bytes())
    if final.get('valid') is not True or str(final.get('uid')) != str(uid):
        raise ValueError('projection terminal completeness rejected')
    path = root / final['receipt_file']
    if path.is_symlink() or root.resolve() not in path.resolve().parents or helper.sha256(path) != final['receipt_sha256']:
        raise ValueError('projection receipt changed')
    record = json.loads(path.read_bytes())
    if (record.get('schema') != 't17_projection_observe/v1' or str(record['uid']) != str(uid)
            or record['positions'] != list(range(8192, 8257))
            or record['cached_tokens'] != cached or record['device_tokens'] != 8257
            or record['extend_tokens'] != 8257 - cached or set(record['roles']) != set(ROLES)):
        raise ValueError('actual target projection coordinates or roles differ')
    installations = [json.loads(p.read_bytes()) for p in root.glob('installed_*.json')]
    if (len(installations) != 1 or installations[0]['FT_LM_CHUNK'] != '4096'
            or installations[0]['output_dir'] != str(root)
            or installations[0]['observer_source_sha256'] != helper.sha256(HERE / 't17_projection_observe.py')
            or installations[0]['startup_source_sha256'] != helper.sha256(HERE / 't17_projection_startup.py')):
        raise ValueError('actual projection worker/source installation differs')
    selection = record['selection']
    if (selection != installations[0]['decoder_selection'] or selection['gdn']['decoder_index'] != 0
            or selection['gdn']['decoder_layer_id'] != 0 or selection['ple']['decoder_index'] != 1
            or selection['ple']['decoder_layer_id'] != 1 or selection['ple_layer_id'] != 1
            or installations[0]['model_structure']['sha256'] != 'deef67a61f3311faf051b23dc4192f442c7fee4f9cd2f38cbcbe4da55c763a80'
            or installations[0]['model_structure'].get('hf_ple_layer_ids') != [2]
            or installations[0]['model_structure'].get('parsed_ple_decoder_indices') != [1]
            or installations[0]['model_structure'].get('parser', {}).get('sha256') != '72905266db8c384ea3cd267a1b739c58a32b8b069f37039b778665cc2be14607'):
        raise ValueError('actual target GDN0/PLE1 decoder selection/parser mapping differs')
    tensors = {}
    for role in ROLES:
        item = record['roles'][role]
        for key in ('uid', 'slot', 'positions', 'cached_tokens', 'device_tokens', 'extend_tokens'):
            if item[key] != record[key]:
                raise ValueError('role target identity differs: ' + role)
        path = root / item['file']
        if path.is_symlink() or root.resolve() not in path.resolve().parents or helper.sha256(path) != item['sha256']:
            raise ValueError('projection tensor changed: ' + role)
        binding = item['module_binding']
        source = Path(binding['source_file'])
        if (source.is_symlink() or original.WT.resolve() not in source.resolve().parents
                or helper.sha256(source) != binding['source_sha256']):
            raise ValueError('actual first-layer source binding differs: ' + role)
        tensor = artifacts.load_tensor(path)
        if (list(tensor.shape) != item['shape'] or str(tensor.dtype) != item['dtype']
                or tensor.shape[0] != 65):
            raise ValueError('projection shape/dtype differs: ' + role)
        tensors[role] = tensor
    return record, tensors


def compare_projections(warm, cold):
    import torch
    results = {}
    for role in ROLES:
        x, y = warm[role], cold[role]
        if x.shape != y.shape or x.dtype != y.dtype:
            raise ValueError('projection shape/dtype mismatch: ' + role)
        different = x != y
        byte_diff = (x.contiguous().view(torch.uint8).reshape(65, -1)
                     != y.contiguous().view(torch.uint8).reshape(65, -1))
        rows = byte_diff.any(dim=1)
        results[role] = {'equal': artifacts.bit_equal(x, y), 'shape': list(x.shape), 'dtype': str(x.dtype),
                         'max_abs': float((x.float() - y.float()).abs().max()) if x.numel() else 0.0,
                         'different_values': int(different.sum()),
                         'different_bytes': int(byte_diff.sum()),
                         'different_positions': [8192 + i for i, changed in enumerate(rows.tolist()) if changed]}
    return results


class Run(retained.Run):
    def startup_wrapper(self):
        return HERE / 't17_projection_startup.py'

    def environment(self, wt, arm=None, d0=False):
        env = super().environment(wt, arm, d0)
        env['FT_LM_CHUNK'] = '4096'
        env.pop('FT_T17_MATCHED', None)
        if arm is not None:
            env['FT_T17_PROJECTION'] = str(arm / 'projection')
        return env

    def execute(self):
        prior = retained.prerequisite()
        helper.t16_prerequisite()
        self.gate(original.WT, helper.CANDIDATE)
        if not self.options.run:
            print(json.dumps({'preflight': 'PASS', 'diagnostic_only': True, 'FT_LM_CHUNK': 4096, 'prerequisite': prior}))
            return
        self.lock_take()
        owned = False
        try:
            if self.directory.exists():
                raise FileExistsError('projection diagnostic already exists')
            self.directory.mkdir()
            owned = True
            original.put(self.directory / 'prerequisite.json', prior)
            for name in ('t17_d14_gpu.py', 't17_d14_runner.py', 't17_d14_artifacts.py', 't17_d14_observe.py',
                         't17_matched_runner.py', 't17_original_startup.py', 't17_d14_exact_ids.py',
                         't17_owned_launch_protocol.py', 't16_full_tail_base_runner.py', 't17_projection_runner.py',
                         't17_projection_observe.py', 't17_projection_startup.py', 'real_inputs.json'):
                with (self.directory / name).open('xb') as stream:
                    stream.write((HERE / name).read_bytes())
            if helper.sha256(HERE / 'real_inputs.json') != helper.sha256(retained.R023 / 'real_inputs.json'):
                raise ValueError('retained exact input cases changed')
            case = json.loads((HERE / 'real_inputs.json').read_bytes())['cases'][0]
            if case['length'] != 8192:
                raise ValueError('original counterexample required')

            def warm(arm):
                donor = self.request(arm, 'donor', case['donor'], 0, 2)
                hit = self.request(arm, 'short', case['short'], 8192, 128)
                receipt, _ = projection(arm, hit['uid'], 8192)
                return donor, hit, receipt

            donor, hit, hot = self.service('projection_warm', warm)

            def fresh(arm):
                response = self.request(arm, 'query', case['short'], 0, 128)
                receipt, _ = projection(arm, response['uid'], 4608)
                return response, receipt

            cold, cool = self.service('projection_cold', fresh)
            warm_arm, cold_arm = self.directory / 'projection_warm', self.directory / 'projection_cold'
            _, warm_tensors = projection(warm_arm, hit['uid'], 8192)
            _, cold_tensors = projection(cold_arm, cold['uid'], 4608)
            roles = compare_projections(warm_tensors, cold_tensors)
            raw = artifacts.validate_case({'name': 'projection-8192', 'length': 8192,
                                           'trace_index': case['trace_index'], 'context': case['expected_ngram']},
                                          cold_arm, warm_arm, tail=65, cold_request='query', hit_request='short',
                                          state_root=warm_arm / 'dump')

            def donation(arm, uid):
                return helper.load_dump_record(arm / 'dump', kind='donate', length=8256, uid=str(uid))

            suffix = original.tensor_comparison(warm_arm / 'dump', donation(warm_arm, hit['uid']),
                                                cold_arm / 'dump', donation(cold_arm, cold['uid']))
            original.put(self.directory / ('diagnostic_batch' + str(self.options.batch) + '.json'), {
                'schema': 'ft_t17_projection_diagnostic/v1', 'rid': self.options.rid, 'batch': self.options.batch,
                'diagnostic_only': True, 'candidate_commit': helper.CANDIDATE, 'FT_LM_CHUNK': 4096,
                'projection_roles': roles, 'warm_receipt': hot, 'cold_receipt': cool, 'suffix_8256': suffix,
                'raw_validator': raw, 'tokens_equal': raw['tokens_bitwise_equal'], 'text_equal': raw['full_text_equal'],
                'acceptance': 'diagnostic_measurement_pending_review; original_T17_not_met_retained'})
            self.set_status(state='complete_measurements_pending_review')
        except BaseException as error:
            if owned:
                self.set_status(state='failed', error=repr(error))
            raise
        finally:
            try:
                self.stop()
            finally:
                if self.proc is None:
                    self.lock_release()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rid', required=True)
    parser.add_argument('--batch', type=int, required=True)
    parser.add_argument('--run', action='store_true')
    options = parser.parse_args()
    if sys.platform != 'linux' or not re.fullmatch(r'E2-R\d{3}-diagnostic-T17', options.rid) or options.batch < 1:
        parser.error('Linux and exact diagnostic round/batch required')
    options.gate = 'T17-diagnostic'
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: (_ for _ in ()).throw(InterruptedError('owned diagnostic signal')))
    Run(options).execute()
