#!/usr/bin/env python3
"""R065 scope binding around immutable R040j lifecycle and D07 tools."""
from __future__ import annotations
import argparse, getpass, hashlib, importlib.util, json, os, shutil, subprocess, sys, time
from pathlib import Path
HERE=Path(__file__).resolve().parent; ROOT=Path('/data2/FreeToken'); RID='E2-R065-d16-discriminate'
WT=ROOT/'wt/e2oom-protocol-restart'; CANDIDATE='481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9'
DEV=ROOT/'runs/dev_D16'; ROUNDS=Path('/data2/_shared/runs/ft_rounds')
AUTH=ROOT/'runs/plan_batches/SUPPLEMENT_20261009_0830.md'; AUTH_SHA='aae53a828566ac5f7d6f845612af13cbab09aceb5fc72321b0d8e756ca3c8051'
J_PATH=HERE.parent/'r040j_api_d16_v1/r040j_api_d16.py'; J_SHA='474915503b87d1f80d0bc6fe6245b6b365df09071c9ae0a53e48da0d998ac734'
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
if sha(J_PATH)!=J_SHA: raise RuntimeError('frozen J differs')
j=load(J_PATH,'r065_immutable_j')
write=j.write

def candidate():
    if WT.is_symlink() or sha(j.D07)!=j.D07_SHA or sha(j.PAIR)!=j.PAIR_SHA: raise RuntimeError('pinned lifecycle differs')
    head=subprocess.check_output(['git','-C',str(WT),'rev-parse','HEAD'],text=True).strip()
    dirty=subprocess.check_output(['git','-C',str(WT),'status','--porcelain','--untracked-files=no'],text=True)
    if head!=CANDIDATE or dirty: raise RuntimeError('clean R065 candidate required')
    return {'worktree':str(WT),'commit':head,'tracked_clean':True}

def sources():
    files={p.name:p for p in HERE.iterdir() if p.is_file() and p.suffix in ('.py','.json','.md')}
    files.update({'frozen_j.py':J_PATH,'d07.py':j.D07,'port_pair.py':j.PAIR,'sdk_completions.py':j.EVAL/'sdk_completions.py','interleave_input_binding.json':j.EVAL/'interleave_input_binding.json'})
    files['authorization.md']=AUTH
    if any(p.is_symlink() or not p.is_file() for p in files.values()): raise RuntimeError('source closure unavailable')
    return files

def plan():
    if Path.cwd()!=WT or getpass.getuser()!='dell': raise RuntimeError('canonical cwd/user required')
    if AUTH.is_symlink() or AUTH.stat().st_mode&0o222 or sha(AUTH)!=AUTH_SHA: raise RuntimeError('authorization receipt differs')
    binding=json.loads((j.EVAL/'interleave_input_binding.json').read_text()); inputs=json.loads((HERE/'inputs.json').read_text())
    if inputs['binding_sha256']!=sha(j.EVAL/'interleave_input_binding.json'): raise RuntimeError('input binding differs')
    from tokenizers import Tokenizer
    tokenizer=Path(binding['tokenizer_path'])/'tokenizer.json'
    if sha(tokenizer)!=inputs['tokenizer_sha256']: raise RuntimeError('target tokenizer differs')
    tok=Tokenizer.from_file(str(tokenizer)); original={row['label']:row for row in binding['inputs']}
    for key,label,n in (('long','slot_1_long_query',8257),('short','slot_0_short_512',512)):
        item=inputs['items'][key]; row=original[label]
        if item['prompt']!=row['decoded_prompt'] or tok.encode(item['prompt'],add_special_tokens=False).ids!=row['original_input_ids'] or item['prompt_tokens']!=n or item['max_tokens']!=128: raise RuntimeError('original full prompt differs')
    for key,other in (('alpha','beta'),('beta','alpha')):
        item=inputs['items'][key]; ids=tok.encode(item['prompt'],add_special_tokens=False).ids
        if len(ids)<8192 or len(ids)!=item['prompt_tokens'] or ids!=item['input_ids'] or item['max_tokens']!=64 or inputs['items'][other]['marker'] in item['prompt'] or item['marker'] not in item['prompt'] or not item['prompt'].startswith(inputs['items']['long']['prompt']): raise RuntimeError('discriminator full long prompt differs')
    closed=json.loads((ROUNDS/'E2-R040j-api-D16/round.json').read_text())
    if closed.get('verdict')!='not_met' or not closed.get('closed_at'): raise RuntimeError('R040j preserved closure differs')
    port=j.load(j.PAIR,'r065_pair_plan').dynamic_port(); argv=j.serve_argv(port)
    return {'schema':'ft_r065_d16_plan/v1','rid':RID,'candidate':candidate(),'scope':{'services':3,'calls':7},
            'source_sha256':{k:sha(v) for k,v in sources().items()},'serve_argv':argv,'serve_argv_sha256':j.argv_sha(argv),
            'port_pair':j.load(j.PAIR,'r065_port_receipt').port_receipt(port),'no_readiness_generation':True,
            'preserved_r040j':{'path':str(ROUNDS/'E2-R040j-api-D16/round.json'),'sha256':sha(ROUNDS/'E2-R040j-api-D16/round.json'),'verdict':'not_met'},
            'criteria':['A1=A2=B full text/finish/three token usage fields; early abort before C on mismatch','C long finish/three token usage fields equals A; text difference observational','64-token dual long own marker/no other marker/no replacement/surrogate/illegal-control response'],
            'authorization':{'path':str(AUTH),'sha256':AUTH_SHA},'missing_cache_policy':'missing/null, never fallback zero','original_token_counts':[8257,512]}

def freeze(out):
    runtime=out/'runtime_sources'; runtime.mkdir(); manifest={}
    for name,path in sources().items():
        target=runtime/name; shutil.copyfile(path,target); target.chmod(0o444); manifest[name]=sha(target)
    write(out/'source_manifest.json',{'schema':'ft_r065_source_manifest/v1','files':manifest}); (out/'source_manifest.json').chmod(0o444)

def child_argv(batch,receipt,admit): return [str(j.VENV/'bin/python'),str(HERE/'r065_runner.py'),'--run','--owned-child','--batch',str(batch),'--launch-receipt',str(receipt),'--admission',str(admit)]

def admission(path):
    if path is None or path.is_symlink() or not path.is_file() or path.stat().st_mode&0o222: raise RuntimeError('immutable root admission required')
    doc=json.loads(path.read_text()); current={k:sha(v) for k,v in sources().items()}
    for key,value in {'rid':RID,'candidate_commit':CANDIDATE,'worktree':str(WT),'cwd':str(Path.cwd()),'user':getpass.getuser(),'source_sha256':current}.items():
        if doc.get(key)!=value: raise RuntimeError('admission identity/source differs: '+key)
    docs={}
    for kind in ('filedry','preflight','source_manifest','independent_review'):
        p=Path(doc[kind+'_path'])
        if p.is_symlink() or not p.is_file() or p.stat().st_mode&0o222 or sha(p)!=doc[kind+'_sha256']: raise RuntimeError('unsafe/stale admission '+kind)
        docs[kind]=json.loads(p.read_text())
    fd=docs['filedry']; review=docs['independent_review']
    if fd.get('no_formal_rid_batch_lock_popen_or_request') is not True or fd.get('rid')!=RID or fd.get('candidate_commit')!=CANDIDATE: raise RuntimeError('R065 filedry binding differs')
    if docs['source_manifest'].get('files')!=current or docs['preflight'].get('candidate')!=candidate(): raise RuntimeError('admission preflight/source closure differs')
    expected={'schema':'ft_r065_d16_independent_review/v1','rid':RID,'candidate_commit':CANDIDATE,'scope':{'services':3,'calls':7},'source_manifest_sha256':doc['source_manifest_sha256'],'source_sha256':current,'filedry_sha256':doc['filedry_sha256'],'preflight_sha256':doc['preflight_sha256']}
    if any(review.get(k)!=v for k,v in expected.items()) or not (review.get('approved') is True or review.get('verdict') in ('PASS','approved')): raise RuntimeError('R065 independent review differs')
    return {'path':str(path),'sha256':sha(path),**doc}

def execute_owned(batch,receipt_path,admit):
    d07=j.load(j.D07,'r065_d07_child'); d07.CANDIDATE=CANDIDATE; d07.RID=RID; admitted=admission(admit)
    d07.require_child_receipt(receipt_path,batch,WT,ROUNDS,rid=RID,expected_argv=child_argv(batch,receipt_path,admit),schema='ft_r040j_api_owned_launch/v2')
    package={**plan(),'admission':admitted}; owner=None; process=None; run_dir=ROUNDS/RID
    try:
        owner=d07.take_d07_gpu_lock(RID,batch); d07.require_gpu_idle(); run_dir.mkdir(); freeze(run_dir); write(run_dir/'preflight.json',package)
        for service in ('A','B','C'):
            directory=run_dir/service; directory.mkdir(); port=j.load(j.PAIR,'r065_pair_run').dynamic_port()
            try:
                try: process=j.start(d07,directory,port)
                except BaseException as exc: process=getattr(exc,'owned_process',None); raise
                env={**d07.clean_environment(WT),'CUDA_VISIBLE_DEVICES':'','NO_PROXY':'127.0.0.1,localhost','no_proxy':'127.0.0.1,localhost',
                     'R065_API_BASE_URL':f'http://127.0.0.1:{port}','R065_API_SERVICE':service,'R065_API_RUN_DIR':str(run_dir)}
                subprocess.run([str(ROOT/'evaluation/toolchain/venv-eval/bin/python'),'-m','pytest','-q',str(HERE/'test_live_service.py')],cwd=WT,env=env,check=True)
            finally:
                if process is not None: d07.load_owned_lifecycle().stop_owned_process(process,120,30); process=None
        write(run_dir/'execution_complete.json',{'schema':'ft_r065_execution/v1','sdk_pytest_completed':True,'root_seal_required':True}); return {'run_dir':str(run_dir)}
    except BaseException as exc:
        if run_dir.is_dir() and not (run_dir/'criteria_result.json').exists(): write(run_dir/'criteria_result.json',{'schema':'ft_r065_d16_criteria/v1','rid':RID,'proposed_verdict':'failed_harness','handoff_ready':False,'reason':str(exc),'exception_type':type(exc).__name__})
        raise
    finally:
        if process is not None and d07.load_owned_lifecycle().owned_group_alive(process.pid): raise RuntimeError('owned service remains; preserve lock')
        if owner is not None: d07.release_d07_gpu_lock(owner)

def filedry():
    out=DEV/f'r065_d16_filedry_{time.strftime("%Y%m%d_%H%M%S")}'; out.mkdir(); package=plan(); freeze(out)
    write(out/'preflight.json',package); (out/'preflight.json').chmod(0o444); d07=j.load(j.D07,'r065_d07_dry')
    for service in ('A','B','C'):
        directory=out/service; directory.mkdir(); port=j.load(j.PAIR,'r065_pair_dry').dynamic_port(); j.service_plan(d07,directory,port)
        write(directory/'no_start.json',{'filedry':True,'popen':False,'request':False,'port_pair':j.load(j.PAIR,'r065_pair_receipt').port_receipt(port)})
    write(out/'filedry.json',{'schema':'ft_r065_d16_filedry/v1','rid':RID,'candidate_commit':CANDIDATE,'output':str(out),'admission_required_before_run':True,'no_formal_rid_batch_lock_popen_or_request':True})
    (out/'filedry.json').chmod(0o444); return {'output':str(out),'source_count':len(sources()),'filedry_sha256':sha(out/'filedry.json'),'preflight_sha256':sha(out/'preflight.json'),'source_manifest_sha256':sha(out/'source_manifest.json')}

for key,value in {'WT':WT,'RID':RID,'CANDIDATE':CANDIDATE,'HERE':HERE,'sources':sources,'candidate':candidate,'plan':plan,'freeze':freeze,'admission':admission,'child_argv':child_argv,'execute_owned':execute_owned,'filedry':filedry}.items(): setattr(j,key,value)
if __name__=='__main__': raise SystemExit(j.main())
