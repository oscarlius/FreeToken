"""Root-driver callable for a selected HC GEMM replay. This module never owns GPU lifecycle."""
from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import t17_hc_gemm_replay as prep


def _sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def _bytes(tensor: Any) -> bytes: return tensor.detach().contiguous().view(__import__('torch').uint8).cpu().numpy().tobytes()


def exclusive_json(path: Path, value: dict) -> None:
    with path.open('x', encoding='utf-8') as stream: json.dump(value, stream, sort_keys=True, indent=2); stream.write('\n')


def validate_owned_process(ownership: dict, *, rid: str, proc_root: Path = Path('/proc')) -> dict:
    proof = prep.validate_external_ownership(ownership, rid=rid)
    if proof['pid'] != os.getpid(): raise ValueError('replay caller PID is not the proven owner')
    stat = proc_root / str(proof['pid']) / 'stat'
    if not stat.is_file(): raise ValueError('replay owner process stat is unavailable')
    fields = stat.read_text().rpartition(') ')[2].split()
    if len(fields) < 20 or int(fields[19]) != proof['start_ticks']:
        raise ValueError('replay owner process birth differs')
    lock = Path(proof['global_lock_path'])
    if lock != Path('/data2/_shared/gpu.lock') or lock.is_symlink() or not lock.is_file(): raise ValueError('global lock proof is unavailable')
    raw_lock = lock.read_text(encoding='utf-8'); lock_value = json.loads(raw_lock)
    if (lock.stat().st_ino != proof['lock_inode'] or raw_lock != proof['lock_token']
            or lock_value.get('owner') != rid or lock_value.get('pid') != proof['pid']):
        raise ValueError('global lock owner/token/PID/inode differs')
    return proof


def fusion_layout(operator: str, tensors: dict) -> dict:
    if operator == 'down':
        if tensors['input_mix_weight_down.weight']['shape'] != [320, 10240] or tensors['block_inject_weight.weight']['shape'] != [4, 10240]:
            raise ValueError('down checkpoint shape differs')
        return {'raw_keys': ['input_mix_weight_down.weight', 'block_inject_weight.weight'], 'zero_pad_rows': 12, 'shape': [336, 10240]}
    if operator == 'up':
        if tensors['input_mix_weight_up.weight']['shape'] != [10240, 320]: raise ValueError('up checkpoint shape differs')
        return {'raw_keys': ['input_mix_weight_up.weight'], 'zero_pad_rows': 0, 'shape': [10240, 320]}
    if operator == 'gdn':
        expected = {'in_proj_qkv.weight': [10240, 2560], 'in_proj_z.weight': [6144, 2560],
                    'in_proj_b.weight': [48, 2560], 'in_proj_a.weight': [48, 2560]}
        if any(tensors[name]['shape'] != shape for name, shape in expected.items()): raise ValueError('GDN checkpoint shape differs')
        return {'raw_keys': list(expected), 'zero_pad_rows': 0, 'shape': [16480, 2560]}
    raise ValueError('operator must be down, up, or gdn')


def byte_metrics(left: Any, right: Any) -> dict:
    import torch
    if left.shape != right.shape or left.dtype != right.dtype: raise ValueError('comparison shape/dtype differs')
    a, b = left.contiguous().view(torch.uint8).reshape(left.shape[0], -1), right.contiguous().view(torch.uint8).reshape(right.shape[0], -1)
    changed = a != b
    zero_sign = ((left == 0) & (right == 0) & changed.reshape(left.shape[0], *left.shape[1:], -1).any(dim=-1)).sum()
    return {'bitwise_equal': not bool(changed.any()), 'different_bytes': int(changed.sum()),
            'different_values': int((left != right).sum()), 'signed_zero_rows_or_values': int(zero_sign),
            'max_abs': float((left.float() - right.float()).abs().max()) if left.numel() else 0.0,
            'different_rows': [index for index, item in enumerate(changed.any(dim=1).tolist()) if item]}


def _load_tensor(meta: dict):
    import torch
    path = Path(meta['file'])
    if path.is_symlink() or not path.is_file() or _sha(path) != meta['sha256']: raise ValueError('recorded role tensor changed')
    value = torch.load(path, map_location='cpu', weights_only=True)
    if (list(value.shape) != meta['shape'] or str(value.dtype) != meta['dtype'] or list(value.stride()) != meta['stride']):
        raise ValueError('recorded role tensor metadata differs')
    return value


def _kernel(kernel_source: Path, kernel_sha: str):
    bound = prep.verify_torch_linear_source(kernel_source, kernel_sha)
    module = importlib.import_module('freetoken.layers.quantization.linear.unquantized')
    cls = module.TorchLinearKernel
    source = Path(inspect.getsourcefile(cls) or '')
    if source != kernel_source or _sha(source) != kernel_sha: raise ValueError('imported TorchLinearKernel source differs')
    return cls(), bound


def _checkpoint_weight(checkpoint: dict, operator: str):
    """Read the selected BF16 payload only after all receipt/ownership checks."""
    import torch
    from safetensors import safe_open
    root, shard = Path(checkpoint['root']), Path(checkpoint['shard'])
    header = prep.checkpoint_metadata(root, operator=operator, expected_config_sha=checkpoint['config_sha256'], expected_index_sha=checkpoint['index_sha256'],
                                      expected_shard_sha=checkpoint['shard_sha256'], expected_header_sha=checkpoint['header_sha256'])
    layout = fusion_layout(operator, header['tensors'])
    with safe_open(str(shard), framework='pt', device='cpu') as handle:
        if operator == 'down':
            down = handle.get_tensor(prep.RAW_PREFIX + 'input_mix_weight_down.weight')
            inject = handle.get_tensor(prep.RAW_PREFIX + 'block_inject_weight.weight')
            pad = torch.zeros((12, 10240), dtype=down.dtype)
            weight = torch.cat((down, inject, pad), dim=0)
        elif operator == 'up':
            weight = handle.get_tensor(prep.RAW_PREFIX + 'input_mix_weight_up.weight')
        else:
            weight = torch.cat(tuple(handle.get_tensor(prep.GDN_PREFIX + name) for name in layout['raw_keys']), dim=0)
    if weight.dtype != torch.bfloat16 or list(weight.shape) != layout['shape']: raise ValueError('loaded checkpoint BF16 weight differs')
    return weight, header, layout


def validate_cpu_weight_preparation(expected: dict | None, weight, layout: dict) -> dict | None:
    """Bind a root driver's pre-CUDA fused-weight attestation when it is present."""
    if expected is None:
        return None
    if not isinstance(expected, dict): raise ValueError('CPU weight preparation must be an object')
    actual = {'fusion': layout, 'shape': list(weight.shape), 'dtype': str(weight.dtype),
              'tensor_sha256': hashlib.sha256(_bytes(weight)).hexdigest()}
    if actual != expected: raise ValueError('current CPU fused weight differs from prepared binding')
    return actual


def _full_input(value, m: int):
    import torch
    if value.shape[0] != 64: raise ValueError('selected replay input must have 64 real rows')
    result = torch.zeros((m, value.shape[1]), dtype=value.dtype)
    result[:64].copy_(value)
    return result


def _save_tensor(path: Path, value) -> dict:
    import torch
    try:
        with path.open('xb') as stream: torch.save(value, stream)
    except FileExistsError as exc: raise ValueError('refusing to replace replay output') from exc
    return {'file': path.name, 'sha256': _sha(path), 'shape': list(value.shape), 'dtype': str(value.dtype), 'stride': list(value.stride())}


def _run_once(kernel, layer, value, *, m1_oracle: bool):
    """The M=1 oracle is 64 independent invocations, never a truncated 64-row batch."""
    import torch
    if m1_oracle:
        return torch.cat(tuple(kernel.apply(layer, value[row:row + 1]) for row in range(value.shape[0])), dim=0)
    return kernel.apply(layer, value)


def execute(plan: dict, ownership: dict, output_dir: str | Path) -> dict:
    """Run only under a root-owned lock/process proof; caller owns lock/status/cleanup."""
    if plan.get('schema') != 'ft_t17_hc_gemm_replay_plan/v1' or plan.get('diagnostic_only') is not True:
        raise ValueError('exact diagnostic replay plan required')
    rid = ownership.get('rid') if isinstance(ownership, dict) else None
    if not isinstance(rid, str): raise ValueError('external replay RID is required')
    proof = validate_owned_process(ownership, rid=rid)  # must precede CUDA import/use
    operator = plan.get('operator'); input_role, output_role = prep.ROLES.get(operator, (None, None))
    if not input_role: raise ValueError('selected operator is invalid')
    arms = plan.get('arms', {}); warm, cold = arms.get('warm'), arms.get('cold')
    if not isinstance(warm, dict) or not isinstance(cold, dict): raise ValueError('two validated arm records required')
    warm_input, cold_input = _load_tensor(warm['roles'][input_role]), _load_tensor(cold['roles'][input_role])
    warm_live, cold_live = _load_tensor(warm['roles'][output_role]), _load_tensor(cold['roles'][output_role])
    if _bytes(warm_input) != _bytes(cold_input): raise ValueError('selected causal role inputs are not bitwise equal')
    checkpoint = plan.get('checkpoint'); kernel_info = plan.get('kernel')
    if not isinstance(checkpoint, dict) or not isinstance(kernel_info, dict): raise ValueError('checkpoint/kernel binding missing')
    output = Path(output_dir); output.mkdir(parents=True, exist_ok=False)
    # CUDA is allowed only below this point, after proof, receipt, and current-byte validation.
    import torch
    weight_cpu, current_checkpoint, layout = _checkpoint_weight(checkpoint, operator)
    cpu_weight_preparation = validate_cpu_weight_preparation(plan.get('cpu_weight_preparation'), weight_cpu, layout)
    kernel, kernel_binding = _kernel(Path(kernel_info['path']), kernel_info['sha256'])
    if not torch.cuda.is_available(): raise RuntimeError('owned GPU execution requires CUDA')
    weight = weight_cpu.cuda(); layer = SimpleNamespace(weight=weight, bias=None)
    runs = list(plan.get('runs', ())); results = {}
    primary_outputs = {}
    for row in runs:
        name, m = row['name'], row['M']
        source = warm_input if name in ('matched_m_4096', 'm1_oracle') else (warm_input if name.startswith('warm') else cold_input)
        x = source.cuda() if name == 'm1_oracle' else _full_input(source, m).cuda()
        outputs = []
        for _ in range(3):
            value = _run_once(kernel, layer, x, m1_oracle=name == 'm1_oracle'); torch.cuda.synchronize(); outputs.append(value[:64].detach().cpu().clone())
        saved = [_save_tensor(output / (name + '_repeat' + str(index + 1) + '.pt'), value) for index, value in enumerate(outputs)]
        primary_outputs[name] = outputs[0]
        results[name] = {'M': m, 'artificial_rows': 0 if name == 'm1_oracle' else m - 64, 'outputs': saved,
                         'vs_warm_live': byte_metrics(outputs[0], warm_live), 'vs_cold_live': byte_metrics(outputs[0], cold_live),
                         'repeat_count': 3, 'repeat_pair_metrics': [byte_metrics(outputs[0], item) for item in outputs[1:]],
                         'repeats_equal': all(byte_metrics(outputs[0], item)['bitwise_equal'] for item in outputs[1:])}
    pairs = {'warm_full_m__cold_full_m': byte_metrics(primary_outputs['warm_full_m'], primary_outputs['cold_full_m'])}
    for name in ('matched_m_4096', 'm1_oracle'):
        if name in primary_outputs:
            pairs['warm_full_m__' + name] = byte_metrics(primary_outputs['warm_full_m'], primary_outputs[name])
            pairs['cold_full_m__' + name] = byte_metrics(primary_outputs['cold_full_m'], primary_outputs[name])
    report = {'schema': 'ft_t17_hc_gemm_execute/v1', 'rid': rid, 'diagnostic_only': True, 'operator': operator,
              'ownership': proof, 'checkpoint': current_checkpoint, 'fusion': layout, 'kernel': kernel_binding,
              'cpu_weight_preparation': cpu_weight_preparation,
              'selected_input_role': input_role, 'selected_output_role': output_role, 'outputs': results, 'pair_metrics': pairs,
              'weight_tensor_sha256': hashlib.sha256(_bytes(weight_cpu)).hexdigest(),
              'torch': torch.__version__, 'cuda': torch.version.cuda, 'device': torch.cuda.get_device_name(),
              'precision': {'input': str(warm_input.dtype), 'weight': str(weight.dtype), 'output': str(next(iter(results.values()))['outputs'][0]['dtype']),
                            'allow_tf32': torch.backends.cuda.matmul.allow_tf32,
                            'allow_bf16_reduced_precision_reduction': torch.backends.cuda.matmul.allow_bf16_reduced_precision_reduction,
                            'allow_fp16_reduced_precision_reduction': torch.backends.cuda.matmul.allow_fp16_reduced_precision_reduction},
              'limitations': ['Only 64 input rows are real; remaining full-M rows are artificial zeros.', 'cuBLAS algorithm identity is unknown.', 'Checkpoint mapping is not a checksum of past service runtime weights.']}
    exclusive_json(output / 'receipt.json', report)
    return report
