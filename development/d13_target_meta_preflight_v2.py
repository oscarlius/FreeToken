"""Read the target config and build TP rank declarations on meta, without weights or CUDA."""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--worktree', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('CUDA_VISIBLE_DEVICES') != '':
        raise RuntimeError('CPU-only preflight requires CUDA_VISIBLE_DEVICES empty')
    if args.output.exists():
        raise FileExistsError(args.output)
    commit = subprocess.check_output(['git', '-C', str(args.worktree), 'rev-parse', 'HEAD'], text=True).strip()
    if commit != args.commit or subprocess.check_output(
        ['git', '-C', str(args.worktree), 'status', '--porcelain', '--untracked-files=no'], text=True
    ).strip():
        raise RuntimeError('candidate commit or cleanliness differs')
    sys.path.insert(0, str(args.worktree / 'python'))
    import torch
    import freetoken
    import freetoken.distributed.info as info
    from freetoken.distributed import DistributedInfo
    from freetoken.engine.config import EngineConfig
    from freetoken.engine.engine import _decode_target
    from freetoken.layers import rotary
    from freetoken.moe.offload_cache import iter_offload_moe_layers
    from freetoken.mm.config import ENCODER_KINDS, MultimodalConfig
    from freetoken.models import create_model
    from freetoken.utils.torch_utils import torch_dtype

    assert Path(freetoken.__file__).resolve() == (args.worktree / 'python/freetoken/__init__.py').resolve()
    assert not torch.cuda.is_initialized()

    def reject_cuda(*_args, **_kwargs):
        raise RuntimeError('CUDA initialization is forbidden in target meta preflight')

    torch.cuda._lazy_init = reject_cuda
    rows = []
    for size in (1, 2, 4):
        for rank in range(size):
            info._TP_INFO = DistributedInfo(rank, size)
            engine = EngineConfig(model_path=str(args.model), tp_info=info._TP_INFO,
                                  dtype=torch.bfloat16, moe_strategy='offload',
                                  mm=MultimodalConfig(disabled_encoders=frozenset(ENCODER_KINDS)))
            object.__setattr__(engine.model_config, 'moe_strategy', 'offload')
            object.__setattr__(engine.model_config, 'decode_target', _decode_target(engine))
            prior_device = rotary._ROPE_DEVICE
            rotary.set_rope_device(torch.device('cpu'))
            rotary.get_rope.cache_clear()
            try:
                with torch.device('meta'), torch_dtype(torch.bfloat16):
                    model = create_model(engine.model_config)
            finally:
                rotary.set_rope_device(prior_device)
                rotary.get_rope.cache_clear()
            state = model.state_dict()
            assert state and all(value.is_meta for value in state.values())
            experts = list(iter_offload_moe_layers(model))
            assert len(experts) == 48
            assert all(module.tp_size == size and module.tp_rank == rank for module in experts)
            bank = experts[0].quant_method
            assert bank.kernel.name == 'triton' and bank.cfg.local_intermediate == 640 // size
            selected = {key: list(value.shape) for key, value in state.items()
                        if key.endswith(('layers.0.linear_attn.in_proj_qkvz.weight',
                                         'layers.0.linear_attn.out_proj.weight',
                                         'layers.3.self_attn.qkv_proj.weight',
                                         'layers.3.self_attn.o_proj.weight'))}
            rows.append({'tp_size': size, 'tp_rank': rank, 'state_entries': len(state),
                         'state_bytes_declared': sum(value.numel() * value.element_size() for value in state.values()),
                         'offload_layers': len(experts), 'local_intermediate': bank.cfg.local_intermediate,
                         'bank_layout': {key: {'shape': list(value.shape), 'dtype': str(value.dtype)}
                                         for key, value in bank.layout().items()},
                         'selected_state_shapes': selected})
            del state, experts, bank, model, engine
            gc.collect()
    assert not torch.cuda.is_initialized()
    config = args.model / 'config.json'
    result = {'schema': 'ft_d13_target_meta_preflight/v1', 'commit': commit,
              'model': str(args.model), 'config_sha256': hashlib.sha256(config.read_bytes()).hexdigest(),
              'ranks': rows, 'cuda_initialized': False, 'weights_loaded': False,
              'generation_verified': False, 'passed': True}
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    args.output.chmod(0o444)
    print(json.dumps({'passed': True, 'rank_declarations': len(rows), 'output': str(args.output)}))


if __name__ == '__main__':
    main()
