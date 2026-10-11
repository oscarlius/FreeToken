import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from t17_d14_artifacts import bit_equal

torch = pytest.importorskip('torch')


def test_singleton_nonunit_stride():
    sliced = torch.tensor([[1.0, 9.0]])[:, 0]
    assert sliced.stride() == (2,)
    assert bit_equal(sliced, torch.tensor([1.0]))
    assert not bit_equal(sliced, torch.tensor([2.0]))


def test_byte_identity_preserves_signed_zero_and_nan_payload():
    raw = torch.tensor([0x7FC00001, 0x7FC00002], dtype=torch.int32)
    assert bit_equal(raw[:1].view(torch.float32), raw[:1].view(torch.float32))
    assert not bit_equal(raw[:1].view(torch.float32), raw[1:].view(torch.float32))
    assert not bit_equal(torch.tensor([0.0]), torch.tensor([-0.0]))


def test_noncontiguous_bfloat16_and_empty():
    matrix = torch.arange(12, dtype=torch.bfloat16).reshape(3, 4).t()
    assert bit_equal(matrix, matrix.contiguous())
    assert bit_equal(torch.empty(0), torch.empty(0))
    assert not bit_equal(torch.empty(0), torch.empty(0, dtype=torch.int64))
    assert not bit_equal(torch.zeros(2, 1), torch.zeros(1, 2))


def test_r041_serialized_singleton_stride_compares_raw_bits(tmp_path):
    from t20_r041_sample4_closure import _same_tensor
    left, right = tmp_path / 'left.pt', tmp_path / 'right.pt'
    torch.save(torch.tensor([[1.0, 8.0]])[:, 0], left)
    torch.save(torch.tensor([1.0]), right)
    assert _same_tensor(left, right)
    torch.save(torch.tensor([2.0]), right)
    assert not _same_tensor(left, right)
