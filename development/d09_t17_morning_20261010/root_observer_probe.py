"""Independent CPU probe: real D09 snapshot and real pool dump, no fake tensors."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile

import torch
from freetoken.core import MessageBoundaryCarrier, Req, SamplingParams
from freetoken.kvcache import linear_state_pool as pool_module
from freetoken.models.config import LinearGatedDeltaGroupConfig, SlotStateSpec
from freetoken.scheduler.cache import CacheManager

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    observer = load('root_boundary_observer', HERE / 'tooling/t17_d14_observe.py')
    runner = load('root_t17_runner', HERE / 'runner.py')
    class Scheduler:
        def _restore_linear_states(self, *args): pass
        def _process_one_msg(self, *args): pass
        def _forward(self, *args): pass
    class IO:
        def _reply_tokenizer_rank0(self, *args): pass
    class Engine:
        def _build_layer_major_chunks(self, *args): pass
    observer.install(Scheduler, IO, Engine, sink=lambda row: None)
    group = LinearGatedDeltaGroupConfig(
        name='linear', layer_ids=(0,), num_key_heads=2, num_value_heads=4,
        key_head_dim=16, value_head_dim=16, conv_kernel_dim=4, output_gate='silu')
    results = []
    with tempfile.TemporaryDirectory(prefix='root_t17_cpu_') as temporary:
        root = Path(temporary)
        for source, uid, extra in [('coldA', 41, 17), ('coldB', 43, 17), ('hot', 88, 19)]:
            arm = root / source
            dump = arm / 'state_dump'
            receipts = arm / 'input_receipts'
            dump.mkdir(parents=True)
            receipts.mkdir()
            pool_module.DUMP_PATH = str(dump)
            os.environ.update(FT_DEV_STATE_DUMP=str(dump), FT_T17_ARM_SOURCE=source,
                              FT_T17_INPUT_RECEIPTS=str(receipts))
            pool = pool_module.LinearStatePool(
                group, 16, torch.bfloat16, torch.device('cpu'), 1,
                slot_states=(SlotStateSpec('ple_conv', (3,)), SlotStateSpec('ple_ngram_ctx', (2,))))
            cm = CacheManager(64, 64, torch.zeros(1, 8193, dtype=torch.int32),
                              'hybrid_radix', linear_state_pool=pool)
            ids = torch.cat((torch.arange(8192, dtype=torch.int32), torch.tensor([extra], dtype=torch.int32)))
            req = Req(ids, 0, 8192, 1, uid, SamplingParams(), None)
            req.linear_slot_idx = pool.alloc(1)[0]
            req.mamba_ping_pong = tuple(pool.alloc(2))
            req.message_boundary_len = 8192
            req.message_boundary_carrier = MessageBoundaryCarrier(8192)
            pool.conv_states[:, req.linear_slot_idx].fill_(7)
            pool.recurrent_states[:, req.linear_slot_idx].fill_(9)
            for tensor in pool.slot_states.values():
                tensor[:, req.linear_slot_idx].fill_(11)
            # Poison indices 0/1: selecting the ping-pong index instead of its
            # physical slot must be visible in the real serialized evidence.
            pool.conv_states[:, :2].fill_(-99)
            full_sha = runner.idsha(ids.tolist())
            prefix_sha = runner.idsha(ids[:8192].tolist())
            (receipts / f'{uid}.json').write_text(json.dumps({'uid': uid, 'int32le_sha256': full_sha}))
            assert cm.snapshot_message_boundary(req)
            row = json.loads((dump / 'index.jsonl').read_text())
            assert row['dev_slots'] == [req.mamba_ping_pong[req.message_boundary_snapshot_idx]]
            state = torch.load(dump / row['files']['conv_states'], weights_only=True)
            assert torch.all(state == 7)
            state_hash = runner.boundary_state_hash(dump, source=source, uid=uid, length=8192,
                                                    input_sha256=full_sha, prefix_sha256=prefix_sha)
            results.append({'source': source, 'uid': uid, 'full_input_sha256': full_sha,
                            'prefix_sha256': prefix_sha, 'physical_slot': row['dev_slots'][0],
                            'state_sha256': state_hash})
        assert len({item['state_sha256'] for item in results}) == 1
        assert results[0]['full_input_sha256'] != results[2]['full_input_sha256']
    assert not torch.cuda.is_initialized()
    print(json.dumps({'schema': 'root_d09_real_observer_cpu_probe/v1', 'results': results,
                      'actual_snapshot_and_tensor_dump': True, 'cuda_initialized': False,
                      'gpu_started': False, 'http_started': False}, sort_keys=True))


if __name__ == '__main__':
    main()
