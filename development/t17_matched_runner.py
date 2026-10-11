"""Measure aligned-chunk prefix and suffix states without accepting the T17 gate."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import signal
import socket
import sys
import time

import t17_d14_gpu as original
from t17_d14_gpu import artifacts, helper

HERE = Path(__file__).resolve().parent
ROOT, ROUNDS = original.ROOT, original.ROUNDS
R023 = ROUNDS / 'E2-R023-gate-T17'
R023_ROUND_SHA = '92618df52121bf141a6f231d46961d394860ade1b756295b6a5cf6c228c08c1d'
R023_MANIFEST_SHA = 'ef2d98846aa8a23c8168596d641e0c2614e0a2dac47f88e07d099b27c0391cfa'


def prerequisite():
    if helper.sha256(R023 / 'round.json') != R023_ROUND_SHA or helper.sha256(R023 / 'MANIFEST.sha256') != R023_MANIFEST_SHA:
        raise ValueError('exact sealed R023 counterexample changed')
    if json.loads((R023 / 'round.json').read_text()).get('verdict') != 'not_met':
        raise ValueError('R023 retained not_met required')
    for line in (R023 / 'MANIFEST.sha256').read_text().splitlines():
        digest, name = line.split('  ', 1)
        raw = R023 / name
        path = raw.resolve(strict=True)
        if raw.is_symlink() or R023.resolve() not in path.parents or helper.sha256(path) != digest:
            raise ValueError('sealed R023 manifest entry differs')
    return {'rid': R023.name, 'round_sha256': R023_ROUND_SHA, 'manifest_sha256': R023_MANIFEST_SHA}


def identity(pid):
    path = Path('/proc') / str(pid)
    fields = (path / 'stat').read_text().rpartition(') ')[2].split()
    result = {'pid': pid, 'state': fields[0], 'pgid': int(fields[2]),
              'session': int(fields[3]), 'start_ticks': int(fields[19])}
    if result['pgid'] != pid or result['session'] != pid or result['state'] == 'Z':
        raise ValueError('new process identity differs')
    return result


def prefix(arm, uid):
    root = arm / 'matched'
    final = json.loads((root / ('final_' + str(uid) + '.json')).read_text())
    if final.get('valid') is not True or str(final.get('uid')) != str(uid):
        raise ValueError('matched prefix completeness rejected')
    path = root / final['receipt_file']
    if path.is_symlink() or root.resolve() not in path.resolve().parents or helper.sha256(path) != final['receipt_sha256']:
        raise ValueError('matched prefix receipt changed')
    result = json.loads(path.read_text())
    if (str(result['uid']) != str(uid) or result['boundary'] != 8192
            or result['cached_tokens'] != 512 or result['extend_tokens'] != 7680
            or result['device_tokens'] != 8192):
        raise ValueError('actual matched prefix coordinates differ')
    installations = [json.loads(path.read_text()) for path in root.glob('installed_*.json')]
    if len(installations) != 1 or installations[0]['FT_LM_CHUNK'] != '7680':
        raise ValueError('actual worker chunk environment or observer installation differs')
    layers = result['linear_layers_by_local']
    if (len(layers) != installations[0]['num_linear_layers']
            or [layer['local_index'] for layer in layers] != list(range(len(layers)))
            or len(set(layer['decoder_layer_idx'] for layer in layers)) != len(layers)
            or len(set(layer['gdn_layer_id'] for layer in layers)) != len(layers)):
        raise ValueError('actual prefix local-layer mapping incomplete')
    if (installations[0]['observer_source_sha256'] != helper.sha256(HERE / 't17_matched_observe.py')
            or installations[0]['startup_source_sha256'] != helper.sha256(HERE / 't17_matched_startup.py')):
        raise ValueError('actual observer/startup source binding differs')
    for role in helper.STATE_ROLES:
        item = result['roles'][role]
        path = root / item['file']
        if path.is_symlink() or root.resolve() not in path.resolve().parents or helper.sha256(path) != item['sha256']:
            raise ValueError('actual prefix role file differs')
        tensor = artifacts.load_tensor(path)
        if list(tensor.shape) != item['shape'] or str(tensor.dtype) != item['dtype']:
            raise ValueError('matched prefix tensor shape/dtype differs')
    return result


def compare_prefix(left, a, right, b):
    rows = {}
    for role in helper.STATE_ROLES:
        x = artifacts.load_tensor(left / 'matched' / a['roles'][role]['file'])
        y = artifacts.load_tensor(right / 'matched' / b['roles'][role]['file'])
        compatible = x.shape == y.shape and x.dtype == y.dtype
        rows[role] = {'equal': artifacts.bit_equal(x, y), 'shape_left': list(x.shape),
                      'shape_right': list(y.shape), 'dtype_left': str(x.dtype), 'dtype_right': str(y.dtype),
                      'max_abs': float((x.float() - y.float()).abs().max()) if compatible and x.numel() else None,
                      'left': a['roles'][role], 'right': b['roles'][role]}
    return rows


class Run(original.Run):
    def startup_wrapper(self):
        return HERE / 't17_matched_startup.py'

    def environment(self, wt, arm=None, d0=False):
        env = super().environment(wt, arm, d0)
        env['FT_LM_CHUNK'] = '7680'
        if arm is not None:
            env['FT_T17_MATCHED'] = str(arm / 'matched')
        return env

    def set_status(self, **values):
        handle = identity(os.getpid())
        if values.get('state') == 'loading':
            process = identity(values['service_pid'])
            self.service_handle = process
            original.put(self.directory / values['arm'] / 'process_identity.json', process)
        original.protocol['Runner'].set_status(
            self, rid=self.options.rid, card='T17-diagnostic', batch_start_ticks=handle['start_ticks'], **values)

    def stop(self):
        if self.proc is None:
            return
        process = self.proc
        handle = getattr(self, 'service_handle', None)
        if handle is None or handle['pid'] != process.pid:
            raise ValueError('captured owned service identity required before stopping')
        stat = Path('/proc') / str(process.pid) / 'stat'
        if stat.exists():
            fields = stat.read_text().rpartition(') ')[2].split()
            if int(fields[19]) != handle['start_ticks'] or int(fields[2]) != process.pid or int(fields[3]) != process.pid:
                raise ValueError('owned service identity changed before stop')
        source = HERE / helper.T16_LAUNCH_PROTOCOL
        if helper.sha256(source) != helper.T16_LAUNCH_SHA256:
            raise ValueError('reviewed owned-session stop source changed')
        owned = runpy.run_path(str(source), run_name='ft_matched_owned_stop')
        owned['stop_owned_process'](process)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            gpu = original.protocol['command'](['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'])
            with socket.socket() as sock:
                free = sock.connect_ex(('127.0.0.1', 8095)) != 0
            if free and all(int(value) < 1000 for value in gpu.splitlines()):
                self.proc = None
                print('STOP PASS owned_pid=' + str(process.pid) + ' gpu=' + gpu, flush=True)
                return
            time.sleep(2)
        raise RuntimeError('owned stopped service did not release GPU/port')

    def service(self, name, operation):
        try:
            return super().service(name, operation)
        finally:
            arm = self.directory / name
            path = arm / 'process_identity.json'
            if path.exists():
                handle = json.loads(path.read_text())
                stat = Path('/proc') / str(handle['pid']) / 'stat'
                if stat.exists():
                    fields = stat.read_text().rpartition(') ')[2].split()
                    if int(fields[19]) != handle['start_ticks'] or fields[0] != 'Z':
                        raise ValueError('owned service not terminal with captured identity')
                original.put(arm / 'stop_identity.json', {'terminal': True, **handle})

    def execute(self):
        prior = prerequisite()
        helper.t16_prerequisite()
        self.gate(original.WT, helper.CANDIDATE)
        if not self.options.run:
            print(json.dumps({'preflight': 'PASS', 'diagnostic_only': True, 'prerequisite': prior}))
            return
        self.lock_take()
        owned = False
        try:
            if self.directory.exists():
                raise FileExistsError('diagnostic round already exists')
            self.directory.mkdir()
            owned = True
            original.put(self.directory / 'prerequisite.json', prior)
            for name in ('t17_d14_gpu.py', 't17_d14_runner.py', 't17_d14_artifacts.py', 't17_d14_observe.py',
                         't17_matched_startup.py', 't17_original_startup.py', 't17_d14_exact_ids.py', 't17_owned_launch_protocol.py',
                         't16_full_tail_base_runner.py', 't17_matched_runner.py', 't17_matched_observe.py', 'real_inputs.json'):
                with (self.directory / name).open('xb') as stream:
                    stream.write((HERE / name).read_bytes())
            inputs = json.loads((HERE / 'real_inputs.json').read_text())
            if helper.sha256(HERE / 'real_inputs.json') != helper.sha256(R023 / 'real_inputs.json'):
                raise ValueError('retained original exact input cases changed')
            case = inputs['cases'][0]
            if case['length'] != 8192:
                raise ValueError('exact R023 counterexample input required')
            def warm(arm):
                donor = self.request(arm, 'donor', case['donor'], 0, 2)
                saved_prefix = prefix(arm, donor['uid'])
                hit = self.request(arm, 'short', case['short'], 8192, 128)
                return donor, hit, saved_prefix
            donor, hit, hot_prefix = self.service('matched_warm', warm)
            cold = self.service('matched_cold', lambda arm: self.request(arm, 'query', case['short'], 0, 128))
            warm_arm, cold_arm = self.directory / 'matched_warm', self.directory / 'matched_cold'
            cold_prefix = prefix(cold_arm, cold['uid'])
            prefix_roles = compare_prefix(warm_arm, hot_prefix, cold_arm, cold_prefix)
            raw = artifacts.validate_case({'name': 'matched-8192', 'length': 8192, 'trace_index': case['trace_index'],
                                           'context': case['expected_ngram']}, cold_arm, warm_arm, tail=65,
                                          cold_request='query', hit_request='short', state_root=warm_arm / 'dump')
            def donation(arm, uid):
                return helper.load_dump_record(arm / 'dump', kind='donate', length=8256, uid=str(uid))
            suffix_roles = original.tensor_comparison(warm_arm / 'dump', donation(warm_arm, hit['uid']),
                                                     cold_arm / 'dump', donation(cold_arm, cold['uid']))
            result = {'schema': 'ft_t17_matched_diagnostic/v1', 'rid': self.options.rid, 'batch': self.options.batch,
                      'diagnostic_only': True, 'candidate_commit': helper.CANDIDATE, 'FT_LM_CHUNK': 7680,
                      'prefix_8192': prefix_roles, 'suffix_8256': suffix_roles, 'raw_validator': raw,
                      'prefix_equal': all(x['equal'] for x in prefix_roles.values()),
                      'suffix_equal': all(x['equal'] for x in suffix_roles.values()),
                      'tokens_equal': raw['tokens_bitwise_equal'], 'text_equal': raw['full_text_equal'],
                      'acceptance': 'diagnostic_measurement_pending_review; original_T17_not_met_retained'}
            original.put(self.directory / ('diagnostic_batch' + str(self.options.batch) + '.json'), result)
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rid', required=True)
    parser.add_argument('--batch', type=int, required=True)
    parser.add_argument('--run', action='store_true')
    options = parser.parse_args()
    if sys.platform != 'linux' or not re.fullmatch(r'E2-R\d{3}-diagnostic-T17', options.rid) or options.batch < 1:
        parser.error('Linux and exact diagnostic round/batch required')
    options.gate = 'T17-diagnostic'
    run = Run(options)
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda signum, frame: (_ for _ in ()).throw(InterruptedError('owned diagnostic signal')))
    run.execute()


if __name__ == '__main__':
    main()
