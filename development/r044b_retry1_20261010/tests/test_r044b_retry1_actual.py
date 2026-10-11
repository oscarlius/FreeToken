from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

HERE = Path(__file__).resolve().parents[1]
SOURCE = HERE / 'run_r044b_retry1_actual.py'


def load():
    spec = importlib.util.spec_from_file_location('r044b_retry1_wrapper_test', SOURCE)
    value = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(value)
    return value


def test_frozen_predecessor_copy_is_exact_byte_pin():
    runner = load()
    assert runner.sha(runner.FROZEN) == runner.FROZEN_SHA256


def test_controller_uses_retry1_child_argv_and_receipt(monkeypatch, tmp_path):
    runner = load()
    worktree, output = tmp_path / 'wt', tmp_path / 'rounds'; worktree.mkdir(); output.mkdir()
    captured = {}
    def execute(wt, out, *, owned_child, batch, launch_receipt):
        argv = legacy.child_argv(88, out / 'launch.json', wt, out)
        captured.update({'wt': wt, 'out': out, 'owned_child': owned_child, 'argv': argv})
        return {'schema':'ft_t10_owned_launch/v3','state':'launched','rid':runner.RID,'batch':88,'argv_sha256':'a'*64,'packet_sha256':'b'*64,'child':{'pid':701,'start_ticks':1701,'execution_id':'701:1701'}}
    legacy = SimpleNamespace(MODES={'ordinary':False,'layer_major':True}, ARMS=('B1','B2','B3'), CAPTURE_REQUESTS=24, CAPTURE_MAX_TOKENS=200, VENV=tmp_path / 'venv', WT=worktree, ROUNDS=output, execute=execute, copy_runtime_sources=lambda _: [])
    monkeypatch.setattr(runner, 'filedry', lambda: {'bindings': {'retry1': 'pin'}})
    monkeypatch.setattr(runner, '_read_admission', lambda dry: {'rid':runner.RID,'bindings':dry['bindings']})
    monkeypatch.setenv('R044B_RETRY1_ROOT_AUTHORIZED', '1')
    result = runner.run(worktree=worktree, output_root=output, legacy_loader=lambda: legacy)
    assert result['controller_child'] == {'pid':701,'start_ticks':1701,'execution_id':'701:1701'}
    assert captured['owned_child'] is False
    assert captured['argv'] == [str(legacy.VENV / 'bin/python'), str(SOURCE.resolve()), '--run', '--owned-child', '--batch', '88', '--launch-receipt', str(output / 'launch.json'), '--worktree', str(worktree), '--output-root', str(output)]


def test_controller_requires_retry1_root_authorization_before_legacy_execute(monkeypatch, tmp_path):
    runner = load(); called = []
    legacy = SimpleNamespace(execute=lambda *a, **k: called.append(True))
    monkeypatch.setattr(runner, 'filedry', lambda: {'bindings': {}})
    with pytest.raises(RuntimeError, match='R044B_RETRY1_ROOT_AUTHORIZED'):
        runner.run(legacy_loader=lambda: legacy)
    assert called == []


def test_pre_popen_marker_is_failed_harness_zero_zero(tmp_path):
    runner = load(); run = tmp_path / runner.RID; run.mkdir()
    writes = []
    frozen = SimpleNamespace(write_new=lambda path, value: (writes.append((path, value)), path.write_text(json.dumps(value))))
    runner._pre_popen_marker(frozen, tmp_path, RuntimeError('materialize failed'), False)
    assert writes[0][0] == run / 'pre_popen_failed.json'
    assert writes[0][1]['classification'] == 'pre_gpu_failed'
    assert writes[0][1]['services_started'] == writes[0][1]['replay_calls'] == 0 and writes[0][1]['retry_budget_debited'] is False
    runner._pre_popen_marker(frozen, tmp_path, RuntimeError('second'), False)
    assert len(writes) == 1


def test_admission_requires_bound_sealed_file_dry_receipt(monkeypatch, tmp_path):
    runner = load(); runner.OLD = HERE.parent / 'r044_capture_path_retry2_20261010'; runner.READER = runner.OLD / 'd04_original' / 'serve_args_diff.py'; runner.LEAF = tmp_path / 'evidence.py'; runner.LEAF.write_text('# evidence'); dry = runner.filedry()
    receipt = tmp_path / 'dry.json'
    receipt.write_text(json.dumps({**dry, 'file_dry': {'services_materialized':6, 'service_started':False, 'requests_sent':False, 'gpu_lock_taken':False}}))
    receipt.chmod(0o444)
    admission = tmp_path / 'ROOT_ADMISSION_R044B.json'
    admission.write_text(json.dumps({'rid':runner.RID, 'bindings':dry['bindings'], 'file_dry_receipt':str(receipt), 'file_dry_receipt_sha256':runner.sha(receipt)}))
    monkeypatch.setattr(runner, 'ADMISSION', admission)
    assert runner._read_admission(dry)['rid'] == runner.RID
    receipt.chmod(0o644)
    admission.write_text(json.dumps({'rid':runner.RID, 'bindings':{'bad':'pin'}, 'file_dry_receipt':str(receipt), 'file_dry_receipt_sha256':'0'*64}))
    with pytest.raises(RuntimeError, match='source binding differs'):
        runner._read_admission(dry)



def test_owned_child_counts_only_successful_service_popen_and_ignores_monitor_or_controller(tmp_path):
    runner = load(); run = tmp_path / runner.RID; run.mkdir()
    calls = []
    class Proc: pass
    def popen(argv, *args, **kwargs):
        calls.append(argv)
        if 'raise-before-return' in argv: raise RuntimeError('no process')
        return Proc()
    legacy = SimpleNamespace(subprocess=SimpleNamespace(Popen=popen), CAPTURE_STARTUP=Path('/packet/source/t10_capture_startup_v3.py'))
    writes=[]
    frozen = SimpleNamespace(write_new=lambda p,v:(writes.append(v),p.write_text(json.dumps(v))), execute_owned_child=lambda *_a,**_k: (_ for _ in ()).throw(RuntimeError('ready failed')))
    with pytest.raises(RuntimeError, match='ready failed'):
        runner._owned_child(frozen, legacy, tmp_path, tmp_path, 1, tmp_path/'receipt')
    assert writes[0]['classification'] == 'pre_gpu_failed'
    # A full numactl argv with a source-copy startup path returns a process: no 0/0 marker.
    frozen.execute_owned_child=lambda *_a,**_k: legacy.subprocess.Popen(['numactl','--membind=0','/venv/bin/python','-u','/run/source/t10_capture_startup_v3.py','serve']) and (_ for _ in ()).throw(RuntimeError('ready failed'))
    writes.clear()
    with pytest.raises(RuntimeError, match='ready failed'):
        runner._owned_child(frozen, legacy, tmp_path, tmp_path, 1, tmp_path/'receipt')
    assert writes == []


def test_run_explicitly_injects_configured_retry1_telemetry_factory(monkeypatch, tmp_path):
    runner = load(); output=tmp_path/'rounds'; output.mkdir(); run=output/runner.RID; run.mkdir(); (run/'result.json').write_text('{}')
    class Reliable: pass
    frozen=SimpleNamespace(OwnedTelemetry=Reliable, evaluate_raw_measurement=lambda _:{'verdict':'measured_pending_independent_review','product_acceptance':False,'first_failure':None}, write_new=lambda p,v:p.write_text(json.dumps(v)))
    legacy=SimpleNamespace(WT=tmp_path/'wt', ROUNDS=output, sha=lambda p:'a'*64); legacy.WT.mkdir()
    seen={}
    monkeypatch.setenv('R044B_RETRY1_ROOT_AUTHORIZED','1'); monkeypatch.setattr(runner,'filedry',lambda:{'bindings':{}}); monkeypatch.setattr(runner,'_read_admission',lambda _:{})
    monkeypatch.setattr(runner,'configure',lambda _:(frozen,legacy)); monkeypatch.setattr(runner,'_owned_child',lambda *_a,**kw:(seen.update(kw) or {}))
    runner.run(owned_child=True,batch=1,launch_receipt=tmp_path/'receipt',worktree=legacy.WT,output_root=output,legacy_loader=lambda:legacy)
    assert seen['telemetry_factory'] is Reliable
