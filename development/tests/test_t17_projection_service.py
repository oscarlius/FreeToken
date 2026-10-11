"""Verify service dispatch and byte comparisons without a model or GPU."""
import importlib.util
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('t17_projection_service_test', HERE / 't17_projection_runner.py')
projection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(projection)


def test_dispatch_preserves_original_chunk_and_owned_service(monkeypatch, tmp_path):
    for name in ('t17_projection_startup.py', 't17_d14_exact_ids.py'):
        path = tmp_path / name
        path.write_text('frozen test source\n')
        path.chmod(0o444)
    monkeypatch.setattr(projection, 'HERE', tmp_path)
    monkeypatch.setattr(projection.original, 'HERE', tmp_path)
    run = object.__new__(projection.Run)
    run.directory = tmp_path / 'round'
    run.directory.mkdir()
    for name, function in [('gate', lambda *_: 'bound source'), ('compiled_extensions', lambda *_: {'same': 'binding'}),
                           ('ready', lambda *_: None), ('set_status', lambda **_: None),
                           ('stop', lambda: setattr(run, 'proc', None))]:
        monkeypatch.setattr(run, name, function)
    run.parser = lambda _: {'_unique_suffix': repr('.pid=4242'), 'mamba_host_slots': '0'}
    captured = []

    class Process:
        pid = 4242

    def start(argv, **options):
        captured.append((argv, options))
        return Process()

    monkeypatch.setattr(projection.original.subprocess, 'Popen', start)
    monkeypatch.setitem(projection.original.protocol, 'command', lambda *_: 'read-only GPU receipt')
    assert projection.original.Run.service(run, 'projection_warm', lambda arm: arm.name) == 'projection_warm'
    assert len(captured) == 1
    argv, options = captured[0]
    assert str(tmp_path / 't17_projection_startup.py') in argv
    assert options['start_new_session'] is True
    assert options['env']['FT_LM_CHUNK'] == '4096'
    assert options['env']['FT_T17_PROJECTION'] == str(run.directory / 'projection_warm/projection')
    assert 'FT_T17_MATCHED' not in options['env']


def test_byte_comparison_reports_signed_zero_position():
    torch = pytest.importorskip('torch')
    warm = {role: torch.zeros((65, 2)) for role in projection.ROLES}
    cold = {role: value.clone() for role, value in warm.items()}
    cold['gdn_qkv_output'][3, 0] = -0.0
    results = projection.compare_projections(warm, cold)
    assert results['embedding_output']['equal']
    row = results['gdn_qkv_output']
    assert not row['equal'] and row['different_values'] == 0
    assert row['different_bytes'] == 1 and row['different_positions'] == [8195]


def test_projection_shape_mismatch_rejected():
    torch = pytest.importorskip('torch')
    warm = {role: torch.zeros((65, 2)) for role in projection.ROLES}
    cold = {role: value.clone() for role, value in warm.items()}
    cold['ple_input'] = torch.zeros((65, 3))
    with pytest.raises(ValueError, match='shape/dtype mismatch'):
        projection.compare_projections(warm, cold)
