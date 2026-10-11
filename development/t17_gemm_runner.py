"""Replay the recorded first-GDN boundary with real checkpoint weights; diagnostic only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import sys

import t17_d14_gpu as retained
import t17_hc_gemm_replay as prep

HERE = Path(__file__).resolve().parent
R030 = Path('/data2/_shared/runs/ft_rounds/E2-R030-diagnostic-T17')
R030_SHA = 'fc683f998652b3db5682aa9912d7eed469d257e0ea6e11387c1d91be6a6f798c'
R030_MANIFEST = 'ea6231ed396f8bb2470cf30d8bdf64bf427e90357236b97340412b01831fca15'
KERNEL = retained.WT / 'python/freetoken/layers/quantization/linear/unquantized.py'
KERNEL_SHA = '1277a7c93802298e5e0dc2b46136af82353797833332a7dd8aa10e86e7e20846'


def source_round():
    if prep.sha(R030 / 'round.json') != R030_SHA or prep.sha(R030 / 'MANIFEST.sha256') != R030_MANIFEST:
        raise ValueError('exact independently sealed R030 required')
    if any(p.is_symlink() or p.stat().st_mode & 0o222 for p in (R030, *R030.rglob('*'))):
        raise ValueError('R030 evidence must remain regular and read-only')
    record = json.loads((R030 / 'round.json').read_bytes())
    observed = record['results']
    roles = observed['hc_roles']
    if (record['verdict'] != 'kept' or not record['experimental']['diagnostic_only']
            or any(not role['equal'] for name, role in roles.items() if name != 'gdn_qkv_output')
            or roles['gdn_qkv_output']['equal'] or roles['gdn_qkv_output']['different_bytes'] != 789):
        raise ValueError('recorded first differing boundary is not the selected GDN projection')
    return {'rid': R030.name, 'round_sha256': R030_SHA, 'manifest_sha256': R030_MANIFEST,
            'diagnostic_sha256': observed['diagnostic_sha256']}


def build_plan():
    source = source_round()
    warm = prep.observation(R030 / 'hc_warm', 1, 'warm', 'gdn')
    cold = prep.observation(R030 / 'hc_cold', 1, 'cold', 'gdn')
    checkpoint = prep.checkpoint_metadata(
        Path('/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay'), operator='gdn',
        expected_config_sha='deef67a61f3311faf051b23dc4192f442c7fee4f9cd2f38cbcbe4da55c763a80',
        expected_index_sha='660414e8300728ba80062e6a3c81cb76a65e2ab136ac9e9ceb450ba0c51c3c0d',
        expected_shard_sha='63fde954be6f08b49b876f4f70a0ad0bcfee71aff7b1faa33779b6b32feca2a2',
        expected_header_sha='067c21570b51a074d1b15f12fa7e296effcefcec7ca59ff82a8ca150ef11f928')
    kernel = prep.verify_torch_linear_source(KERNEL, KERNEL_SHA)
    result = prep.plan('gdn', warm, cold, checkpoint, kernel, include_m4096=True, include_m1_oracle=True)
    result['source_round'] = source
    loader = retained.WT / 'python/freetoken/models/qwen4_exp/weight.py'
    loader_sha = '5aae8cba53326464b3fab7f10a36b1fd6022c6080d0c1f72bfc6d8b73d1671cd'
    if loader.is_symlink() or prep.sha(loader) != loader_sha:
        raise ValueError('candidate checkpoint loader source differs')
    result['checkpoint_loader_source'] = {'path': str(loader), 'sha256': loader_sha}
    import torch
    import t17_hc_gemm_execute as execute
    a = execute._load_tensor(warm['roles']['gdn_qkv_input'])
    b = execute._load_tensor(cold['roles']['gdn_qkv_input'])
    weight, current_checkpoint, layout = execute._checkpoint_weight(checkpoint, 'gdn')
    execute._kernel(KERNEL, KERNEL_SHA)
    if current_checkpoint != checkpoint:
        raise ValueError('checkpoint changed during CPU preparation')
    result['cpu_weight_preparation'] = {
        'fusion': layout, 'shape': list(weight.shape), 'dtype': str(weight.dtype),
        'tensor_sha256': hashlib.sha256(execute._bytes(weight)).hexdigest(),
    }
    if execute._bytes(a) != execute._bytes(b) or torch.cuda.is_initialized():
        raise ValueError('CPU preparation requires identical real inputs and no CUDA context')
    return result


def identity():
    fields = (Path('/proc') / str(os.getpid()) / 'stat').read_text().rpartition(') ')[2].split()
    return {'pid': os.getpid(), 'pgid': int(fields[2]), 'session': int(fields[3]), 'start_ticks': int(fields[19])}


class Run(retained.Run):
    def execute(self):
        source_round()
        plan_path = HERE / 'plan.json'
        plan = json.loads(plan_path.read_bytes())
        if plan.get('operator') != 'gdn' or plan.get('source_round', {}).get('round_sha256') != R030_SHA:
            raise ValueError('frozen, selected GDN replay plan required')
        self.gate(retained.WT, retained.helper.CANDIDATE)
        if not self.options.run:
            print(json.dumps({'preflight': 'PASS', 'diagnostic_only': True, 'operator': 'gdn',
                              'plan_sha256': prep.sha(plan_path)}))
            return
        self.lock_take()
        owned = False
        try:
            self.directory.mkdir(exist_ok=False)
            owned = True
            handle = identity()
            if handle['pgid'] != handle['pid'] or handle['session'] != handle['pid']:
                raise ValueError('replay batch must own its process group and session')
            retained.put(self.directory / 'process_identity.json', handle)
            retained.put(self.directory / 'plan.json', plan)
            self.set_status(state='probing', batch_start_ticks=handle['start_ticks'], operator='gdn')
            proof = {'rid': self.options.rid, 'pid': handle['pid'], 'start_ticks': handle['start_ticks'],
                     'lock_owner': self.options.rid, 'lock_token': self.token,
                     'global_lock_path': str(retained.protocol['LOCK']), 'lock_inode': self.lock_inode}
            os.environ['CUDA_VISIBLE_DEVICES'] = '0'
            retained.put(self.directory / 'environment.json', {
                'CUDA_VISIBLE_DEVICES': os.environ['CUDA_VISIBLE_DEVICES'],
                'python': sys.executable, 'operator_only': True,
                'candidate_worktree': str(retained.WT),
            })
            sys.path[:0] = [str(retained.WT / 'python'), str(retained.WT)]
            import t17_hc_gemm_execute as execute
            result = execute.execute(plan, proof, self.directory / 'gemm')
            retained.put(self.directory / 'diagnostic.json', result)
            self.set_status(state='complete_measurements_pending_review', batch_start_ticks=handle['start_ticks'], operator='gdn')
        except BaseException as error:
            if owned:
                self.set_status(state='failed', error=repr(error), batch_start_ticks=identity()['start_ticks'])
            raise
        finally:
            self.lock_release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cpu-preparation-probe', action='store_true')
    parser.add_argument('--rid')
    parser.add_argument('--batch', type=int)
    parser.add_argument('--run', action='store_true')
    options = parser.parse_args()
    if options.cpu_preparation_probe:
        print(json.dumps({'schema': 'ft_t17_gemm_preparation/v1', 'gpu_started': False, 'plan': build_plan()}))
        return
    if (sys.platform != 'linux' or not isinstance(options.rid, str)
            or not re.fullmatch(r'E2-R\d{3}-diagnostic-T17', options.rid)
            or not isinstance(options.batch, int) or options.batch < 1):
        parser.error('Linux and exact diagnostic RID/batch required')
    options.gate = 'T17-gemm-diagnostic'
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: (_ for _ in ()).throw(InterruptedError('owned replay signal')))
    Run(options).execute()


if __name__ == '__main__':
    main()
