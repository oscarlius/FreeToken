import importlib.util
import os
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
if str(ROOT) not in __import__('sys').path: __import__('sys').path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location('t17_hc_gemm_execute', ROOT / 't17_hc_gemm_execute.py')
MODULE = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MODULE)


def test_gdn_fusion_layout_has_the_actual_four_checkpoint_parts():
    tensors = {'in_proj_qkv.weight': {'shape': [10240, 2560]}, 'in_proj_z.weight': {'shape': [6144, 2560]},
               'in_proj_b.weight': {'shape': [48, 2560]}, 'in_proj_a.weight': {'shape': [48, 2560]}}
    assert MODULE.fusion_layout('gdn', tensors) == {'raw_keys': list(tensors), 'zero_pad_rows': 0, 'shape': [16480, 2560]}


def test_ownership_rejects_noncaller_pid_before_lock_or_cuda_access():
    proof = {'rid': 'E2-R031-diagnostic-T17', 'pid': os.getpid() + 1, 'start_ticks': 1,
             'lock_owner': 'E2-R031-diagnostic-T17', 'lock_token': 'x',
             'global_lock_path': '/data2/_shared/gpu.lock', 'lock_inode': 1}
    with pytest.raises(ValueError, match='caller PID'):
        MODULE.validate_owned_process(proof, rid=proof['rid'])


def test_exclusive_receipt_write_preserves_existing_bytes(tmp_path):
    path = tmp_path / 'receipt.json'; path.write_bytes(b'existing')
    with pytest.raises(FileExistsError): MODULE.exclusive_json(path, {'x': 1})
    assert path.read_bytes() == b'existing'


def test_absent_cpu_weight_preparation_keeps_generic_plan_usable():
    assert MODULE.validate_cpu_weight_preparation(None, None, {'shape': [1]}) is None


@pytest.mark.skipif(__import__('importlib').util.find_spec('torch') is None, reason='PyTorch unavailable')
def test_m1_oracle_invokes_fake_kernel_once_per_real_row():
    import torch
    class Kernel:
        def __init__(self): self.calls = []
        def apply(self, _layer, value): self.calls.append(tuple(value.shape)); return value + 1
    value, kernel = torch.arange(128, dtype=torch.float32).reshape(64, 2), Kernel()
    output = MODULE._run_once(kernel, object(), value, m1_oracle=True)
    assert kernel.calls == [(1, 2)] * 64
    assert torch.equal(output, value + 1)
