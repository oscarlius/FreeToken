"""Compare two dependency failures to upstream; run the contribution gates."""
import importlib.util
from pathlib import Path
import shlex

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('transport', HERE.parent/'r067c_retry2_production_control_20261009/ssh_ops.py')
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)
code = r'''
import datetime,hashlib,json,os,pathlib,subprocess
root=pathlib.Path('/data2/FreeToken/development/local_finalization_20261014')
stage=root/'integration_a7c24b2'
baseline=root/'baseline_f02fbb1'
subprocess.run(['git','-C',str(stage),'worktree','add','--detach',str(baseline),'f02fbb16a213f5c81094e4017c988d41f0164141'],check=True,capture_output=True)
python='/data2/FreeToken/development/upstream_layer_major_pr_20261014/main-venv/bin/python'
receipts=[]
for label,source,tests in [
 ('CPU_BASELINE',baseline,['tests/engine/test_cache_budget.py::test_adjust_config_resolves_num_tokens_generic','tests/engine/test_cache_budget.py::test_adjust_config_defaults_moe_cache_auto_for_auto_resolved_offload_backend']),
 ('CPU_FINAL',stage,['tests/server','tests/tokenizer','tests/daemon','tests/scheduler','tests/kvcache','tests/engine/test_layer_major_tracks.py'])]:
    env=os.environ.copy()
    env.update(CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONPATH=str(source/'python'),PYTHONNOUSERSITE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
    argv=[python,'-m','pytest','-q',*tests]
    at=datetime.datetime.now().astimezone().isoformat()
    with (root/(label+'.stdout.log')).open('w') as out,(root/(label+'.stderr.log')).open('w') as err:
        result=subprocess.run(argv,cwd=source,env=env,stdout=out,stderr=err,timeout=180)
    output=(root/(label+'.stdout.log')).read_text()
    if label=='CPU_BASELINE':
        assert result.returncode==1 and '2 failed' in output and "requires flashinfer, which is" in output
    else:
        assert result.returncode==0
    receipt={'at':at,'finished_at':datetime.datetime.now().astimezone().isoformat(),'source':str(source),'head':subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip(),'argv':argv,'exit_code':result.returncode,'summary':output[-1800:],'cuda_visible_devices':'','generation_calls':0,'service_actions':0,
             'stdout_sha256':hashlib.sha256((root/(label+'.stdout.log')).read_bytes()).hexdigest(),'stderr_sha256':hashlib.sha256((root/(label+'.stderr.log')).read_bytes()).hexdigest()}
    (root/(label+'_RECEIPT.json')).write_text(json.dumps(receipt,indent=2)+'\n')
    receipts.append(receipt)
print(json.dumps(receipts,indent=2))
'''
client=transport.connect()
try:
    _,out,err=client.exec_command('/data2/FreeToken/venv/bin/python -c '+shlex.quote(code))
    result,errors=out.read().decode(),err.read().decode()
    status=out.channel.recv_exit_status()
    sftp=client.open_sftp()
    for label in ['CPU_BASELINE','CPU_FINAL']:
        for suffix in ['_RECEIPT.json','.stdout.log','.stderr.log']:
            try:
                sftp.get('/data2/FreeToken/development/local_finalization_20261014/'+label+suffix,str(HERE/(label+suffix)))
            except FileNotFoundError:
                pass
    sftp.close()
    print(result)
    if errors:
        print(errors)
    assert status==0,status
finally:
    client.close()
