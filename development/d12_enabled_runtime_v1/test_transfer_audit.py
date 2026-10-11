from types import SimpleNamespace
import hashlib

import pytest
import torch

import transfer_audit
from transfer_audit import ROLES, install_transfer_audit, verify_routed_banks


def fixture_cache(expert_count=4, selected=(1, 3), selected_slots=(4, 0), cache_size=5):
    """Small CPU protocol fixture; not an inference model or a CUDA test."""
    cache = SimpleNamespace(quant_format='nvfp4', bank_schema=ROLES, num_layers=2,
                            num_experts=expert_count, cache_size=cache_size, banks=[])
    cache.slot_for_id = torch.full((2, expert_count), -1, dtype=torch.int32)
    cache.id_of_slot = torch.full((cache_size,), -1, dtype=torch.int32)
    for expert, slot in zip(selected, selected_slots):
        cache.slot_for_id[1, expert] = slot
        cache.id_of_slot[slot] = expert_count + expert
    for index, dtype in enumerate((torch.uint8, torch.float8_e4m3fn, torch.float16) * 2):
        layers = [(torch.arange(expert_count * 6).reshape(expert_count, 6) + layer * 25 + index).to(dtype) for layer in range(2)]
        resident = torch.zeros((cache_size, 6), dtype=dtype)
        for expert, slot in zip(selected, selected_slots):
            resident[slot].copy_(layers[1][expert])
        cache.banks.append((layers, resident))
    cache.bank_views = lambda: tuple(bank for _, bank in cache.banks)
    cache.alphas_for_slots = lambda layer: None
    raw = torch.tensor([[3, 1], [1, 3]], dtype=torch.int32) if expert_count == 4 else torch.tensor(selected, dtype=torch.int32).reshape(-1, 1)
    mapped = cache.slot_for_id[1][raw.long()].clone()
    return cache, raw, mapped


def test_all_six_banks_are_compared_without_promoting_cpu_to_cuda():
    cache, raw, mapped = fixture_cache()
    result = verify_routed_banks(cache, 1, raw, mapped)
    assert result['scope'] == 'cpu_protocol_only'
    assert result['unique_experts'] == [1, 3]
    assert result['resident_slots'] == [4, 0]
    assert [row['role'] for row in result['banks']] == list(ROLES)
    assert all(row['source_sha256'] == row['resident_sha256'] for row in result['banks'])
    assert result['physical_h2d_bytes_inferred'] is False


@pytest.mark.parametrize('bank_index', range(6))
@pytest.mark.parametrize('slot', [0, 4])
def test_last_byte_corruption_in_each_bank_fails(bank_index, slot):
    cache, raw, mapped = fixture_cache()
    data = cache.banks[bank_index][1].view(torch.uint8)
    data[slot, -1] ^= 1
    with pytest.raises(ValueError, match='selected bank bytes differ'):
        verify_routed_banks(cache, 1, raw, mapped)


@pytest.mark.parametrize('corrupt_last_chunk', [False, True])
def test_more_than_eight_rows_complete_digest_and_last_chunk(corrupt_last_chunk):
    selected, slots = tuple(range(17)), tuple(range(21, 4, -1))
    cache, raw, mapped = fixture_cache(20, selected, slots, 24)
    if corrupt_last_chunk:
        cache.banks[-1][1].view(torch.uint8)[slots[-1], -1] ^= 1
        with pytest.raises(ValueError, match='down_global'):
            verify_routed_banks(cache, 1, raw, mapped)
    else:
        result = verify_routed_banks(cache, 1, raw, mapped)
        for row, (layers, _) in zip(result['banks'], cache.banks):
            whole = layers[1].view(torch.uint8).reshape(20, -1)[list(selected)].numpy().tobytes()
            assert row['source_sha256'] == hashlib.sha256(whole).hexdigest()
            assert row['compared_bytes'] == len(whole)


def test_unrouted_bytes_are_outside_the_claim():
    cache, raw, mapped = fixture_cache()
    cache.banks[0][1][2].fill_(255)
    result = verify_routed_banks(cache, 1, raw, mapped)
    assert result['resident_slots'] == [4, 0]


@pytest.mark.parametrize('corruption', ['mapped', 'forward', 'reverse', 'view'])
def test_mapping_and_consumed_view_must_match(corruption):
    cache, raw, mapped = fixture_cache()
    if corruption == 'mapped':
        mapped[0, 0] = 4
    elif corruption == 'forward':
        cache.slot_for_id[1, 3] = 4
    elif corruption == 'reverse':
        cache.id_of_slot[4] = 1  # Same expert ID, wrong layer.
    else:
        cache.bank_views = lambda: tuple(bank.clone() for _, bank in cache.banks)
    with pytest.raises(ValueError):
        verify_routed_banks(cache, 1, raw, mapped)


def test_installation_requires_explicit_runtime_cuda_and_restores():
    class Cache:
        device = torch.device('cpu')

        def prepare_prefill_routed_only(self, layer, ids):
            raise AssertionError('CPU wrapper must refuse before product invocation')

    original = Cache.prepare_prefill_routed_only
    records = []
    restore = install_transfer_audit(Cache, records.append, lambda: context(1))
    with pytest.raises(ValueError, match='actual CUDA'):
        Cache().prepare_prefill_routed_only(1, torch.tensor([[1]], dtype=torch.int32))
    assert records == []
    restore()
    assert Cache.prepare_prefill_routed_only is original


def context(tokens):
    return {'uid': 2, 'outer_segment_index': 3, 'child_start': 12864,
            'child_end': 12864 + tokens, 'child_tokens': tokens}


def test_wrapper_preserves_raw_ids_calls_original_once_and_binds_context(monkeypatch):
    calls, records = [], []

    class Cache:
        device = SimpleNamespace(type='cuda')  # Protocol spy only, no CUDA tensors.

        def prepare_prefill_routed_only(self, layer, ids):
            calls.append(layer)
            ids.fill_(4)
            return None

    def verified(cache, layer, raw, mapped):
        assert raw.tolist() == [[1], [3]] and mapped.tolist() == [[4], [4]]
        return {'scope': 'cuda_resident_rows'}  # Synthetic return is confined to this unit test.

    monkeypatch.setattr(transfer_audit, 'verify_routed_banks', verified)
    restore = install_transfer_audit(Cache, records.append, lambda: context(2))
    try:
        Cache().prepare_prefill_routed_only(1, torch.tensor([[1], [3]], dtype=torch.int32))
    finally:
        restore()
    assert calls == [1]
    assert records == [{'scope': 'cuda_resident_rows', 'context': context(2)}]


@pytest.mark.parametrize('reason', ['prefill_overlap', 'error'])
def test_fallback_or_error_never_produces_equality_success(reason):
    records = []

    class Cache:
        device = SimpleNamespace(type='cuda')

        def prepare_prefill_routed_only(self, layer, ids):
            if reason == 'error':
                raise RuntimeError('original copy failed')
            return reason

    restore = install_transfer_audit(Cache, records.append, lambda: context(1))
    try:
        if reason == 'error':
            with pytest.raises(RuntimeError, match='original copy failed'):
                Cache().prepare_prefill_routed_only(1, torch.tensor([[1]], dtype=torch.int32))
            assert records == []
        else:
            assert Cache().prepare_prefill_routed_only(1, torch.tensor([[1]], dtype=torch.int32)) == reason
            assert len(records) == 1 and records[0]['equality_verified'] is False
    finally:
        restore()


@pytest.mark.parametrize('change', [{'uid': -1}, {'child_tokens': 3}, {'child_end': 12999}])
def test_context_child_extent_must_match_actual_forward(change):
    class Cache:
        device = SimpleNamespace(type='cuda')

        def prepare_prefill_routed_only(self, layer, ids):
            raise AssertionError('must reject mismatched child before product call')

    value = {**context(2), **change}
    restore = install_transfer_audit(Cache, lambda record: None, lambda: value)
    try:
        with pytest.raises(ValueError, match='actual child extent'):
            Cache().prepare_prefill_routed_only(1, torch.tensor([[1], [3]], dtype=torch.int32))
    finally:
        restore()
