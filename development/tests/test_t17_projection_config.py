"""Validate target raw HF config and candidate parser mapping before engine load."""
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location('projection_config_test', Path(__file__).parents[1] / 't17_projection_startup.py')
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def source_config(tmp_path, monkeypatch, ple_indices):
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'architectures': ['Qwen4ExpForConditionalGeneration'], 'text_config': {
        'num_hidden_layers': 48, 'ple_layer_ids': ple_indices,
        'layer_types': ['linear_attention', 'linear_attention', 'linear_attention', 'full_attention'] * 12}}))
    monkeypatch.setattr(module, 'MODEL_CONFIG', path)
    monkeypatch.setattr(module, 'CONFIG_RESOLVED', path.resolve())
    monkeypatch.setattr(module, 'CONFIG_SHA', hashlib.sha256(path.read_bytes()).hexdigest())
    return path


def candidate_parse(raw_ids, parsed_ids=(1,)):
    hf = SimpleNamespace(text_config=SimpleNamespace(ple_layer_ids=raw_ids))
    parsed = SimpleNamespace(qwen4_args=SimpleNamespace(ple_layer_ids=parsed_ids), num_layers=48,
                             is_linear_layer=lambda index: index == 1)
    return hf, parsed, {'path': '/candidate/config.py', 'sha256': module.PARSER_SHA, 'qualname': 'parse_config'}


def test_hf_one_based_ple_id_binds_candidate_zero_based_decoder(tmp_path, monkeypatch):
    source_config(tmp_path, monkeypatch, [2])
    monkeypatch.setattr(module, 'parse_target_config', lambda: candidate_parse([2], [1]))
    structure = module.target_structure()
    assert structure['hf_ple_layer_ids'] == [2]
    assert structure['parsed_ple_decoder_indices'] == [1]
    assert structure['ple_decoder_indices'] == [1]
    assert structure['parser']['sha256'] == module.PARSER_SHA


def test_parser_mapping_other_than_one_is_rejected(tmp_path, monkeypatch):
    source_config(tmp_path, monkeypatch, [2])
    monkeypatch.setattr(module, 'parse_target_config', lambda: candidate_parse([2], [2]))
    with pytest.raises(ValueError, match='parser did not map'):
        module.target_structure()


def test_ple_on_decoder_zero_rejected_before_parser(tmp_path, monkeypatch):
    source_config(tmp_path, monkeypatch, [0])
    with pytest.raises(ValueError, match='decoder configuration differs'):
        module.target_structure()


def test_changed_source_bytes_rejected_before_engine_load(tmp_path, monkeypatch):
    path = source_config(tmp_path, monkeypatch, [2])
    path.write_text(path.read_text() + ' ')
    with pytest.raises(ValueError, match='configuration changed'):
        module.target_structure()
