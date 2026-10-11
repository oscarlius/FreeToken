import importlib.util
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_startup_imports_structure_without_running_startup():
    source = (ROOT / 't17_hc_startup.py').read_text(encoding='utf-8')
    assert 'from t17_projection_startup import PARSER_SHA, target_structure' in source
    assert "if __name__ in ('__main__', '__mp_main__'):" in source
    assert "FT_T17_HC" in source and "FT_LM_CHUNK') != '4096'" in source


def test_runner_declares_exact_roles_and_original_protocol():
    source = (ROOT / 't17_hc_runner.py').read_text(encoding='utf-8')
    for role in ('embedding_output', 'hc_mix_input', 'hc_down_input', 'hc_down_output', 'hc_up_input', 'hc_up_output', 'hc_mix_output', 'gdn_qkv_input', 'gdn_qkv_output'):
        assert repr(role) in source
    assert "self.request(arm, 'donor', case['donor'], 0, 2)" in source
    assert "self.request(arm, 'short', case['short'], 8192, 128)" in source
    assert "self.request(arm, 'query', case['short'], 0, 128)" in source
    assert "kind='donate', length=8256" in source


@pytest.mark.skipif(__import__('importlib').util.find_spec('torch') is None, reason='PyTorch unavailable')
def test_signed_zero_aware_byte_metrics():
    import torch
    runner = load('t17_hc_runner')
    positive = torch.zeros((64, 1), dtype=torch.float32)
    negative = positive.clone(); negative[0, 0] = -0.0
    warm = {role: positive for role in runner.ROLES}; cold = {role: negative for role in runner.ROLES}
    result = runner.compare_tensors(warm, cold)
    assert result['embedding_output']['equal'] is False
    assert result['embedding_output']['different_bytes'] > 0
    assert result['embedding_output']['signed_zero_rows_or_values'] == 1
    assert result['embedding_output']['different_positions'] == [4608]


def test_cpu_reader_is_stdin_transport_and_cuda_clear_only():
    source = (ROOT / 't17_hc_read.py').read_text(encoding='utf-8')
    assert "'CUDA_VISIBLE_DEVICES']=''" in source
    assert "json.load(sys.stdin)" in source
    assert "terminal service identity differs" in source
    assert "CPU re-evaluation differs" in source
    assert "ft_t17_hc_cpu/v1" in source
