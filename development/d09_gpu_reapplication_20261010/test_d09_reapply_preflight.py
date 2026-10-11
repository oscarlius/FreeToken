import importlib.util, json, os, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('preflight', HERE/'d09_reapply_preflight.py')
preflight=importlib.util.module_from_spec(spec); sys.modules[spec.name]=preflight; spec.loader.exec_module(preflight)

def test_actual_bd57_filedry_binds_native_links_and_cpu_route_without_gpu():
    result=subprocess.run([sys.executable,str(HERE/'d09_reapply_preflight.py')],text=True,capture_output=True,check=True,timeout=120)
    data=json.loads(result.stdout)
    assert data['status']=='cpu_preflight_ready_not_gpu_admitted'
    assert len(data['native_links']) == 2 and data['native_cpu_import']['cuda_initialized_after'] is False
    assert all('/wt/d09-page-conservation-20261010/' in data['native_cpu_import'][key] for key in ('cpu_moe','pinned_tensor'))
    assert data['candidate_cpu_import']['cuda_initialized_after'] is False
    assert data['spawn_descriptor']['execute'] is False
    assert data['route_adapter']['probe']['route']=='/internal/t17/exact-ids'
    assert data['effects'][-1]['event']=='cleanup' and data['constraints']['gpu_started'] is False
    assert 'fresh bd57 T16 closure is absent' in data['t17_gate']

def test_t17_rejects_old_or_malformed_t16_closure_and_accepts_only_new_identity():
    for closure in ({}, {'rid':'E2-D09-T16-OLD','candidate_commit':preflight.CANDIDATE,'verdict':'kept','services':8,'calls':100}):
        try: preflight.require_fresh_t16_closure(closure)
        except RuntimeError: pass
        else: raise AssertionError('must reject closure')
    preflight.require_fresh_t16_closure({'rid':preflight.T16_RID,'candidate_commit':preflight.CANDIDATE,'verdict':'kept','services':8,'calls':100})

def test_t17_actual_candidate_validator_and_config_are_cpu_only():
    runner_path=HERE/'protocol_t17/runner.py'
    runner_spec=importlib.util.spec_from_file_location('t17_actual_candidate_validator',runner_path)
    runner=importlib.util.module_from_spec(runner_spec);sys.modules[runner_spec.name]=runner;runner_spec.loader.exec_module(runner)
    validation=runner.validate_candidate(); config=runner.cfg()
    assert validation['head']==preflight.CANDIDATE and validation['tracked_clean'] is True
    assert validation['feature_flag']=='--enable-message-boundary-ckpt'
    assert set(validation['native_extensions'])=={'_cpu_moe','_pinned_tensor'}
    assert config['candidate']==preflight.CANDIDATE and config['provenance_sha256']=='aaf7a1d1ee3f329affb1458da917bc689e05c01fbda53dcaaa9ed42fe747c18f'
    assert len(config['services'])==6 and config['budget']=={'services':6,'calls':8,'max_tokens':32}

def test_adapter_refuses_service_and_bounded_cleanup_retains_lock_on_busy():
    env=os.environ | {'PYTHONPATH':str(preflight.WT/'python'),'CUDA_VISIBLE_DEVICES':''}
    refused=subprocess.run([sys.executable,str(HERE/'bd57_route_adapter.py'),'serve'],text=True,capture_output=True,env=env)
    assert refused.returncode != 0 and 'refusing service start' in refused.stderr
    effects=preflight.CpuEffects(clock=lambda:10, idle=lambda:False)
    try: effects.cleanup(11)
    except RuntimeError: pass
    else: raise AssertionError('busy idle callback must fail closed')
    assert effects.events == [{'event':'cleanup_failed_harness','lock_retained':True}]

