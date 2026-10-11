import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

PATH = Path(__file__).parents[1] / 't16_d14_schedule_runner.py'
SPEC = importlib.util.spec_from_file_location('t16_schedule_runner_test', PATH)
MODULE = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MODULE)


def test_declared_candidate_is_child_of_accepted_schedule_source_and_default_mode_is_ordinary():
    assert MODULE.CASE['parent_commit'] == 'e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7'
    assert MODULE.CASE['new_commit'] == 'a9dca443cd07e1f60d1533e0a678935a09d21636'
    assert MODULE.CASE['ordinary_prefill'] is True


def test_d18_source_is_inside_the_frozen_execution_directory():
    assert MODULE.D18_TEST == MODULE.HERE / 'tests/test_d18_client_params.py'


def test_d18_receipt_requires_complete_authorized_binding(tmp_path, monkeypatch):
    probe = tmp_path / 'probe_ft_cold32k.py'; probe.write_bytes(b'probe')
    bench = tmp_path / 'benchmark_client.py'; bench.write_bytes(b'bench')
    test_source = tmp_path / 'test_d18_client_params.py'; test_source.write_bytes(b'test')
    log = tmp_path / 'd18.log'; log.write_bytes(b'5 passed in 0.03s\n')
    digest = hashlib.sha256(probe.read_bytes()).hexdigest()
    receipt = tmp_path / 'd18.json'
    receipt.write_text(json.dumps({'schema':'ft_d18_independent_cpu/v1','card':'D18','returncode':0,'gpu_started':False,'requests_sent':False,'test_summary':'5 passed in 0.03s','log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'source_files':{'scripts/probe_ft_cold32k.py':digest,'../_shared/benchmark_client.py':hashlib.sha256(bench.read_bytes()).hexdigest(),'tests/test_d18_client_params.py':hashlib.sha256(test_source.read_bytes()).hexdigest()},'live_source_files':{'/data2/FreeToken/scripts/probe_ft_cold32k.py':{'sha256':digest,'regular':True}}}), encoding='utf-8')
    monkeypatch.setattr(MODULE, 'D18', receipt); monkeypatch.setattr(MODULE, 'D18_LOG', log); monkeypatch.setattr(MODULE, 'D18_TEST', test_source); monkeypatch.setattr(MODULE, 'BENCH', bench); monkeypatch.setattr(MODULE, 'PROBE_SHA', digest); monkeypatch.setattr(MODULE, 'PROBE_MD5', hashlib.md5(probe.read_bytes()).hexdigest()); monkeypatch.setitem(MODULE.shared.base, 'SCR', tmp_path)
    assert MODULE.d18_binding()['probe_sha256'] == digest
    receipt.write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError): MODULE.d18_binding()
