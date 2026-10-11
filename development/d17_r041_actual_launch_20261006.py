import importlib.util,json,os,pathlib,hashlib,subprocess,sys
sys.dont_write_bytecode=True
root=pathlib.Path('/data2/FreeToken');rounds=pathlib.Path('/data2/_shared/runs/ft_rounds')
stage=root/'runs/dev_D16/d17_gate_cpu_0e33a49343a0';source=stage/'source_tools';review=root/'runs/dev_D16/r041_source_review_r_overlap/review.json'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(source/'cpu_validation.json')=='f9f0059888df99487a8b030921b59dfe631d9f3dac7c57f5c1c75a4d97a67e79'
assert sha(review)=='de38cbcf4f9dd3e701bee5e58896b6b0f6cd5810afbfcfc3d2f1d1439b28bd05'
assert not (rounds/'E2-R041-gate-D17').exists() and not pathlib.Path('/data2/_shared/gpu.lock').exists()
mem=subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],text=True)
assert mem.strip() and all(int(x)<1000 for x in mem.splitlines())
for k in list(os.environ):
 if k.startswith('FT_') or k=='PYTHONPATH':os.environ.pop(k)
os.environ['PYTHONDONTWRITEBYTECODE']='1';os.environ['CUDA_VISIBLE_DEVICES']='0'
spec=importlib.util.spec_from_file_location('actual_d17_owned_launch',source/'t17_owned_launch_protocol.py');owned=importlib.util.module_from_spec(spec);spec.loader.exec_module(owned)
helper=owned.verified_module(root/'runs/plan_batches/e2_launch.py',owned.HELPER_SHA,'actual_d17_atomic_launch')
batch=helper.next_batch(rounds);assert batch==68
rid='E2-R041-gate-D17'
argv=[str(root/'venv/bin/python'),'-u',str(source/'d17_gpu_gate_runner.py'),'--rid',rid,'--batch',str(batch),'--directory',str(rounds/rid),'--realinput28',str(stage/'real_inputs.json'),'--accepted-t17',str(rounds/'E2-R038/round.json'),'--independent-review',str(rounds/'E2-R038/combined_review.json'),'--source-cpu-stage',str(stage),'--source-review',str(review),'--source-review-sha256',sha(review),'--candidate-tag','E2-base.1@0aa23431','--cold-control-worktree',str(root/'wt/e2base'),'--control-worktree',str(root/'wt/e2d14-ordinary-rewind'),'--candidate-worktree',str(root/'wt/e2base1-ordinary-rewind')]
packet={'schema':'ft_d17_r041_launch/v1','state':'reserved','rid':rid,'batch':batch,'card':'D17','gate':'T16','candidate_commit':'0aa23431e5b800797543bdecbf35a01045131d7d','warm_control_commit':'a9dca443cd07e1f60d1533e0a678935a09d21636','parent_commit':'23f2e2caa3395837c9474735ffc83321f3b9b5a1','candidate_tag':'E2-base.1@0aa23431','source_stage':str(stage),'stage_report_sha256':sha(source/'cpu_validation.json'),'source_review':str(review),'source_review_sha256':sha(review),'runner_sha256':sha(source/'d17_gpu_gate_runner.py'),'case_gate_sha256':sha(source/'d17_gate_case.py'),'batch_template_sha256':sha(source/'batchNN_E2-R041_v3.sh'),'atomic_helper_sha256':owned.HELPER_SHA,'owned_launch_sha256':sha(source/'t17_owned_launch_protocol.py'),'accepted_t17_sha256':sha(rounds/'E2-R038/round.json'),'independent_t17_review_sha256':sha(rounds/'E2-R038/combined_review.json'),'inputs_sha256':sha(stage/'real_inputs.json'),'argv':argv+['--run'],'parent_environment':{'cleared':'FT_* and PYTHONPATH','PYTHONDONTWRITEBYTECODE':'1','CUDA_VISIBLE_DEVICES':'0'},'model_admitted':False}
p=root/'runs/dev_D17/launch_E2-R041-gate-D17.json';p.parent.mkdir(exist_ok=True)
receipt=owned.reserve_process(helper,batch,rid,argv,p,packet)
pid=receipt['batch_pid'];fields=(pathlib.Path('/proc')/str(pid)/'stat').read_text().rpartition(') ')[2].split();ticks=int(fields[19]);assert ticks>0 and os.getpgid(pid)==pid
receipt.update(batch_start_ticks=ticks,batch_execution_id=f'{pid}:{ticks}')
st=p.stat();owned.publish_receipt(p,(st.st_dev,st.st_ino),receipt)
print(json.dumps({'state':receipt['state'],'rid':rid,'batch':batch,'batch_pid':pid,'batch_pgid':receipt['batch_pgid'],'start_ticks':ticks,'launch_receipt':str(p),'launch_receipt_sha256':sha(p),'wrapper':receipt['wrapper'],'wrapper_sha256':receipt['wrapper_sha256'],'batch_log':receipt['batch_log']}),flush=True)