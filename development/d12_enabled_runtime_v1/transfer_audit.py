"""Explicit D12 diagnostic adapter for Triton NVFP4 routed slot contents.

Importing this module changes nothing. The diagnostic startup wrapper must call
install_transfer_audit explicitly and bind emit/context to its existing D16
capture lifecycle. CPU results never claim CUDA transfer validation. Full row
reads synchronize and perturb timings; this adapter is forbidden in timing arms.
"""
from __future__ import annotations

import hashlib

ROLES = ('gate_up_packed', 'gate_up_scale', 'gate_up_global',
         'down_packed', 'down_scale', 'down_global')


def verify_routed_banks(cache, layer_id, original_ids, mapped_ids):
    """Compare every routed expert's complete registered row after preparation.

    This checks both existing resident hits and newly copied misses. It does not
    infer the number of physical H2D bytes from the number of selected rows.
    """
    import torch

    if cache.quant_format != 'nvfp4' or tuple(cache.bank_schema) != ROLES:
        raise ValueError('audit requires the six-bank Triton NVFP4 layout')
    if type(layer_id) is not int or not 0 <= layer_id < cache.num_layers:
        raise ValueError('invalid layer identity')
    if original_ids.dtype not in (torch.int32, torch.int64) or mapped_ids.dtype != original_ids.dtype:
        raise ValueError('raw and mapped expert IDs must use the same integer dtype')
    raw = original_ids.detach().cpu()
    mapped = mapped_ids.detach().cpu()
    if raw.ndim != 2 or raw.numel() == 0 or raw.shape != mapped.shape:
        raise ValueError('expert ID geometry differs')
    if bool(((raw < 0) | (raw >= cache.num_experts)).any()):
        raise ValueError('raw expert ID is out of bounds')
    if bool(((mapped < 0) | (mapped >= cache.cache_size)).any()):
        raise ValueError('mapped slot is out of bounds')
    experts = raw.flatten().unique(sorted=True).long()
    forward = cache.slot_for_id[layer_id].detach().cpu().long()
    slots = forward.index_select(0, experts)
    if bool(((slots < 0) | (slots >= cache.cache_size)).any()) or slots.unique().numel() != experts.numel():
        raise ValueError('routed experts do not have unique resident slots')
    if not torch.equal(forward[raw.long()], mapped.long()):
        raise ValueError('in-place mapped IDs disagree with slot_for_id')
    reverse = cache.id_of_slot.detach().cpu().long().index_select(0, slots)
    if not torch.equal(reverse, layer_id * cache.num_experts + experts):
        raise ValueError('reverse slot map points to another layer or expert')
    if cache.alphas_for_slots(layer_id) is not None:
        raise ValueError('Triton NVFP4 global scales must be captured in registered banks')
    views = cache.bank_views()
    if len(cache.banks) != len(ROLES) or len(views) != len(ROLES):
        raise ValueError('registered bank/view count differs')
    banks = []
    expected_dtypes = (torch.uint8, torch.float8_e4m3fn, torch.float16) * 2
    device_types = set()
    for name, expected_dtype, (per_layer, resident), view in zip(ROLES, expected_dtypes, cache.banks, views):
        source = per_layer[layer_id]
        if (source.device.type != 'cpu' or source.dtype != expected_dtype or resident.dtype != expected_dtype
                or source.shape[0] != cache.num_experts or resident.shape[0] != cache.cache_size
                or source.shape[1:] != resident.shape[1:]
                or not source.is_contiguous() or not resident.is_contiguous()):
            raise ValueError('host/resident bank geometry or dtype differs: ' + name)
        if (view.data_ptr() != resident.data_ptr() or view.shape != resident.shape
                or view.stride() != resident.stride() or view.dtype != resident.dtype):
            raise ValueError('GEMM bank view does not reference the checked resident bank: ' + name)
        device_types.add(resident.device.type)
        # View as bytes before gathering: torch does not implement CPU indexing
        # for every float8 dtype. Never clone the complete model/slot bank.
        source_bytes = source.view(torch.uint8).reshape(cache.num_experts, -1)
        resident_bytes = resident.view(torch.uint8).reshape(cache.cache_size, -1)
        source_digest, resident_digest = hashlib.sha256(), hashlib.sha256()
        compared_bytes = 0
        # Bound temporary GPU allocation to at most eight expert rows. Large
        # target banks must not be gathered in one allocation during low-headroom
        # diagnostics. Digests preserve sorted-expert order across chunks.
        for begin in range(0, experts.numel(), 8):
            expected = source_bytes.index_select(0, experts[begin:begin + 8])
            actual = resident_bytes.index_select(0, slots[begin:begin + 8].to(resident.device)).cpu()
            if not torch.equal(expected, actual):
                raise ValueError('selected bank bytes differ: ' + name)
            source_digest.update(expected.numpy().tobytes())
            resident_digest.update(actual.numpy().tobytes())
            compared_bytes += actual.numel()
        banks.append({'role': name, 'dtype': str(source.dtype), 'row_shape': list(source.shape[1:]),
                      'selected_rows': experts.numel(), 'compared_bytes': compared_bytes,
                      'source_sha256': source_digest.hexdigest(), 'resident_sha256': resident_digest.hexdigest(),
                      'bytewise_equal': True})
    if len(device_types) != 1 or device_types - {'cpu', 'cuda'}:
        raise ValueError('resident banks use inconsistent or unsupported devices')
    return {'schema': 'ft_d12_routed_bank_equality/v1', 'layer_id': layer_id,
            'prefill_segment_tokens': raw.shape[0], 'unique_experts': experts.tolist(),
            'resident_slots': slots.tolist(), 'banks': banks,
            'bidirectional_mapping_equal': True, 'all_selected_bank_bytes_equal': True,
            'scope': 'cuda_resident_rows' if device_types == {'cuda'} else 'cpu_protocol_only',
            'max_temporary_expert_rows': 8,
            'performance_sample': False, 'physical_h2d_bytes_inferred': False}


def install_transfer_audit(cache_type, emit, context_provider):
    """Install only in an explicitly selected diagnostic service worker.

    The original prepare is called once; fallback/error cannot yield successful
    equality evidence. Context comes from the enclosing D16 scheduler adapter.
    Return a cleanup callback so CPU tests and startup failure paths can restore
    the class without touching another wrapper installed in the meantime.
    """
    original = cache_type.prepare_prefill_routed_only
    if getattr(original, '_d12_transfer_audit', False):
        raise ValueError('D12 transfer audit already installed')

    def wrapped(cache, layer_id, expert_ids):
        if cache.device.type != 'cuda':
            raise ValueError('runtime transfer audit requires actual CUDA resident banks')
        supplied = context_provider()
        keys = {'uid', 'outer_segment_index', 'child_start', 'child_end', 'child_tokens'}
        if (not isinstance(supplied, dict) or set(supplied) != keys
                or any(type(supplied[key]) is not int for key in keys)
                or supplied['uid'] < 0 or supplied['outer_segment_index'] < 0
                or not 0 <= supplied['child_start'] < supplied['child_end']
                or supplied['child_end'] - supplied['child_start'] != supplied['child_tokens']
                or expert_ids.ndim != 2 or supplied['child_tokens'] != expert_ids.shape[0]):
            raise ValueError('D12 audit lacks matching scheduler UID and actual child extent')
        context = dict(supplied)
        raw = expert_ids.detach().cpu().clone()
        reason = original(cache, layer_id, expert_ids)
        if reason is not None:
            emit({'schema': 'ft_d12_routed_bank_fallback/v1', 'context': dict(context),
                  'layer_id': layer_id, 'reason': reason, 'equality_verified': False})
            return reason
        evidence = verify_routed_banks(cache, layer_id, raw, expert_ids)
        if evidence['scope'] != 'cuda_resident_rows':
            raise ValueError('runtime diagnostic produced non-CUDA evidence')
        evidence['context'] = dict(context)
        emit(evidence)
        return None

    wrapped._d12_transfer_audit = True
    cache_type.prepare_prefill_routed_only = wrapped

    def restore():
        if cache_type.prepare_prefill_routed_only is not wrapped:
            raise RuntimeError('D12 audit ownership changed before cleanup')
        cache_type.prepare_prefill_routed_only = original

    return restore
