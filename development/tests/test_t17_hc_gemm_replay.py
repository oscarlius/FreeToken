import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct

import pytest


PATH = Path(__file__).parents[1] / 't17_hc_gemm_replay.py'
SPEC = importlib.util.spec_from_file_location('t17_hc_gemm_replay', PATH)
MODULE = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MODULE)


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def put_json(path, value): path.write_text(json.dumps(value), encoding='utf-8')


def checkpoint(tmp_path):
    root = tmp_path / 'checkpoint'; root.mkdir(); put_json(root / 'config.json', {'ok': 1})
    prefix = MODULE.RAW_PREFIX
    names = {'hc_norm.weight': ('BF16', [10240]), 'input_mix_weight_down.weight': ('BF16', [320, 10240]),
             'block_inject_weight.weight': ('BF16', [4, 10240]), 'input_mix_weight_up.weight': ('BF16', [10240, 320])}
    header = {prefix + name: {'dtype': dtype, 'shape': shape, 'data_offsets': [0, 0]} for name, (dtype, shape) in names.items()}
    raw = json.dumps(header, sort_keys=True, separators=(',', ':')).encode(); shard = root / 'model-00001.safetensors'
    shard.write_bytes(struct.pack('<Q', len(raw)) + raw)
    put_json(root / 'model.safetensors.index.json', {'weight_map': {prefix + name: shard.name for name in names}})
    return root, digest(root / 'config.json'), digest(root / 'model.safetensors.index.json'), digest(shard), hashlib.sha256(raw).hexdigest()


def role(root, name, *, output=False):
    tensor = root / (name + '.pt'); tensor.write_bytes(name.encode())
    item = {'uid': '1', 'slot': 2, 'cached_tokens': 4608, 'device_tokens': 8193, 'extend_tokens': 3585,
            'positions': MODULE.POSITIONS, 'file': tensor.name, 'sha256': digest(tensor), 'shape': [64, 2],
            'dtype': 'torch.bfloat16', 'stride': [2, 1], 'operation': {'source_sha256': 'x', 'method_sha256': 'y'}}
    if output:
        item['leaf_operator'] = {'quant_method_class': 'pkg.UnquantizedLinearMethod', 'quant_kernel': 'pkg.TorchLinearKernel',
                                 'quant_requested': 'auto', 'weight': {'dtype': 'torch.bfloat16', 'device': 'cuda:0'}}
    return item


def arm(tmp_path, *, device=8193, extend=3585):
    root = tmp_path / 'arm' / 'hc'; root.mkdir(parents=True)
    down_in, down_out = role(root, 'hc_down_input'), role(root, 'hc_down_output', output=True)
    down_in.update(device_tokens=device, extend_tokens=extend); down_out.update(device_tokens=device, extend_tokens=extend)
    receipt = {'schema': 't17_hc_observe/v1', 'uid': '1', 'slot': 2, 'cached_tokens': 4608,
               'device_tokens': device, 'extend_tokens': extend, 'positions': MODULE.POSITIONS,
               'roles': {'hc_down_input': down_in, 'hc_down_output': down_out}}
    receipt_path = root / 'hc_1_receipt.json'; put_json(receipt_path, receipt)
    put_json(root / 'final_1.json', {'valid': True, 'uid': '1', 'receipt_file': receipt_path.name, 'receipt_sha256': digest(receipt_path)})
    return root.parent


def test_checkpoint_header_only_inventory_and_merged_rule(tmp_path):
    args = checkpoint(tmp_path)
    result = MODULE.checkpoint_metadata(*args[:1], expected_config_sha=args[1], expected_index_sha=args[2], expected_shard_sha=args[3], expected_header_sha=args[4])
    assert result['merged_down'] == {'raw_parts': ['input_mix_weight_down.weight', 'block_inject_weight.weight'], 'zero_pad_rows': 12, 'shape': [336, 10240]}
    assert result['tensors']['input_mix_weight_up.weight']['shape'] == [10240, 320]
    assert result['declared_config'] == result['config'] == str(args[0] / 'config.json')
    assert result['declared_index'] == result['index'] == str(args[0] / 'model.safetensors.index.json')


def test_streamed_sha_matches_hashlib_without_read_bytes(tmp_path):
    path = tmp_path / 'large'; path.write_bytes((b'0123456789abcdef' * (1 << 19)))
    assert MODULE.sha(path) == hashlib.sha256(path.read_bytes()).hexdigest()


def test_declared_config_or_index_symlink_requires_its_exact_target(tmp_path):
    target = tmp_path / 'base.json'; target.write_text('{}', encoding='utf-8')
    allowed = tmp_path / 'allowed.json'
    foreign = tmp_path / 'foreign.json'
    try:
        allowed.symlink_to(target)
        foreign.symlink_to(target)
    except (NotImplementedError, OSError):
        pytest.skip('symlink creation is unavailable on this platform')
    assert MODULE._resolved_declared(allowed, target, 'checkpoint config') == target
    with pytest.raises(ValueError, match='symlink target differs'):
        MODULE._resolved_declared(foreign, None, 'checkpoint index')


def test_overlay_config_and_index_bind_declared_and_exact_resolved_targets(tmp_path, monkeypatch):
    root, config_sha, index_sha, shard_sha, header_sha = checkpoint(tmp_path)
    base = tmp_path / 'base'; base.mkdir()
    config_target = base / 'config.json.qwen4_exp.orig'
    index_target = base / 'model.safetensors.index.json'
    (root / 'config.json').replace(config_target)
    (root / 'model.safetensors.index.json').replace(index_target)
    try:
        (root / 'config.json').symlink_to(config_target)
        (root / 'model.safetensors.index.json').symlink_to(index_target)
    except (NotImplementedError, OSError):
        pytest.skip('symlink creation is unavailable on this platform')
    monkeypatch.setattr(MODULE, 'OVERLAY', root)
    monkeypatch.setattr(MODULE, 'BASE', base)
    result = MODULE.checkpoint_metadata(root, expected_config_sha=config_sha, expected_index_sha=index_sha,
                                        expected_shard_sha=shard_sha, expected_header_sha=header_sha)
    assert result['declared_config'] == str(root / 'config.json')
    assert result['config'] == str(config_target)
    assert result['declared_index'] == str(root / 'model.safetensors.index.json')
    assert result['index'] == str(index_target)
    foreign = tmp_path / 'foreign-index.json'; foreign.write_bytes(index_target.read_bytes())
    (root / 'model.safetensors.index.json').unlink()
    (root / 'model.safetensors.index.json').symlink_to(foreign)
    with pytest.raises(ValueError, match='checkpoint index symlink target differs'):
        MODULE.checkpoint_metadata(root, expected_config_sha=config_sha, expected_index_sha=index_sha,
                                   expected_shard_sha=shard_sha, expected_header_sha=header_sha)


def test_observation_requires_actual_coords_hashes_and_observed_leaf_metadata(tmp_path):
    result = MODULE.observation(arm(tmp_path), 1, 'warm', 'down')
    assert result['coordinates']['extend_tokens'] == 3585
    assert set(result['roles']) == {'hc_down_input', 'hc_down_output'}
    root = arm(tmp_path / 'bad'); receipt = root / 'hc' / 'hc_1_receipt.json'; value = json.loads(receipt.read_text()); value['roles']['hc_down_output']['leaf_operator']['quant_requested'] = 'other'; put_json(receipt, value)
    with pytest.raises(ValueError, match='receipt hash/path'):
        MODULE.observation(root, 1, 'warm', 'down')


def test_source_flinear_binding_and_plan_limitations(tmp_path):
    source = tmp_path / 'unquantized.py'
    source.write_text('class TorchLinearKernel:\n pass\nclass UnquantizedLinearMethod:\n pass\ndef f(x,w,b):\n return F.linear(x, w, b)\n', encoding='utf-8')
    kernel = MODULE.verify_torch_linear_source(source, digest(source))
    warm = {'arm': 'warm'}; cold = {'arm': 'cold'}
    plan = MODULE.plan('down', warm, cold, {'checkpoint': 1}, kernel, include_m4096=True, include_m1_oracle=True)
    assert [row['M'] for row in plan['runs']] == [3585, 3649, 4096, 1]
    assert 'artificial zeros' in plan['limitations'][0]


def test_symlink_tensor_path_is_rejected(tmp_path, monkeypatch):
    root = arm(tmp_path); receipt = root / 'hc' / 'hc_1_receipt.json'; value = json.loads(receipt.read_text())
    link = root / 'hc' / 'link.pt'; link.write_bytes(b'x')
    value['roles']['hc_down_input']['file'] = link.name; value['roles']['hc_down_input']['sha256'] = digest(link); put_json(receipt, value)
    final = root / 'hc' / 'final_1.json'; final_value = json.loads(final.read_text()); final_value['receipt_sha256'] = digest(receipt); put_json(final, final_value)
    original = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda path: path == link or original(path))
    with pytest.raises(ValueError, match='HC tensor hash/path'):
        MODULE.observation(root, 1, 'warm', 'down')


def test_external_ownership_is_required_but_never_acquired_here():
    proof = {'rid': 'E2-R031-diagnostic-T17', 'pid': 7, 'start_ticks': 8, 'lock_owner': 'E2-R031-diagnostic-T17',
             'lock_token': 'owned-token', 'global_lock_path': '/data2/_shared/gpu.lock', 'lock_inode': 9}
    assert MODULE.validate_external_ownership(proof, rid=proof['rid']) == proof
    with pytest.raises(ValueError, match='RID/lock'):
        MODULE.validate_external_ownership({**proof, 'lock_owner': 'other'}, rid=proof['rid'])
