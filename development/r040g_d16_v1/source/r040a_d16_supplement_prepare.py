"""R040a missing D16 measurements; owned execution requires sealed R review."""
from __future__ import annotations
import hashlib, importlib.util, json, os, sys
from pathlib import Path
from types import SimpleNamespace

RID='E2-R040a'
CANDIDATE='0aa23431e5b800797543bdecbf35a01045131d7d'
SCHEMA='ft_r040a_d16_supplement_prepare/v1'
RUNS=Path('/data2/_shared/runs/ft_rounds')
SCOPE=('native_slots_2','native_slots_4','parking','cache','interleave','anchor_four_cell_if_missing')
REQUIRED=('d16_native_capture_shutdown_v3.py','d16_native_process_collection_v2.py','d16_exact_service_startup.py','d16_exact_service_startup_v4.py','r040a_anchor_four_cell_v1.py','equiv_suite/service_capture.py','equiv_suite/service_capture_startup.py','t17_d14_runner.py')
HERE=Path(__file__).resolve().parent
ROOT=Path('/data2/FreeToken'); WT=ROOT/'wt/e2base1'
PARENT='0aa23431e5b800797543bdecbf35a01045131d7d'
REVIEW_DIR=ROOT/'runs/dev_D16/r040a_startup_review_v3'

class R040aPreparationError(RuntimeError): pass

def sha(path: Path)->str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()

def prepare(source_root: str|Path)->dict:
 root=Path(source_root).resolve()
 files={}
 for name in REQUIRED:
  path=root/name
  if path.is_symlink() or not path.is_file(): raise R040aPreparationError(f'missing regular R040a source: {name}')
  files[name]={'path':str(path),'sha256':sha(path)}
 wrapper=files['d16_native_capture_shutdown_v3.py']
 # The collector receives this wrapper, whose install() first installs the
 # existing exact hooks then replaces only the worker run loop.
 plan=[]
 for arm in SCOPE:
  state='queued'
  reason=None
  if arm=='parking':
   reason='reuse actual before/host/cleared/restored PT capture; independent raw review required'
  plan.append({'arm':arm,'state':state,'reason':reason})
 return {'schema':SCHEMA,'rid':RID,'candidate_commit':CANDIDATE,'default_action':'inert_prepare_only','requires_preceding_d04_closure':True,'queue_position':'after_current_batch_before_T05','wrapper':wrapper,'source_files':files,'scope':plan,'gpu_execution_permitted':False,'model_admitted':False}

def run_supplement_body(owner, realinputs, wrapper, review, review_sha256, *, native_module=None, write_json=None):
    """Run only the approved unfinished D16 arms while the owner holds its lock."""
    if native_module is None:
        native_module=load_source(HERE/'d16_native_process_collection_v2.py','r040a_native_v2')
    cases=realinputs.get('cases',[]) if isinstance(realinputs,dict) else []
    chosen=[]; seen=set()
    for case in cases:
        query=case.get('query',[]); ids=query[-512:]
        if len(ids)==512 and tuple(ids) not in seen:
            seen.add(tuple(ids)); chosen.append({'source_case':case['name'],'source_input_ids_sha256':case['input_ids_sha256'],'slice_start':len(query)-512,'slice_end':len(query),'input_ids':ids})
        if len(chosen)==4: break
    if len(chosen)!=4: raise R040aPreparationError('R040a requires four distinct sealed 512-token slices')
    long=next((c for c in cases if 4096 < len(c.get('query',[])) <= 16384),None)
    if long is None: raise R040aPreparationError('R040a requires one bounded sealed long query')
    provenance={'short':chosen,'long_source_case':long['name'],'long_input_ids_sha256':long['input_ids_sha256'],'admitted':False}
    common={'wrapper':wrapper,'source_review':review,'source_review_sha256':review_sha256}
    ids=[x['input_ids'] for x in chosen]
    result={'schema':'ft_r040a_d16_supplement_result/v1','admitted':False,'d16':{},'anchor_four_cell':'not_executed_requires_separate_completion_metadata'}
    result['d16']['batch2']=native_module.collect_native_processes(owner,ids[:2],slots=2,**common)
    result['d16']['batch4']=native_module.collect_native_processes(owner,ids,slots=4,**common)
    result['d16']['parking']=native_module.collect_parking_processes(owner,ids[0],**common)
    result['d16']['cache']=native_module.collect_cache_processes(owner,ids[0],**common)
    result['d16']['interleave']=native_module.collect_native_processes(owner,[ids[0],long['query']],slots=2,interleave=True,**common)
    if write_json: write_json('d16_input_provenance.json',provenance); write_json('r040a_d16_supplement.json',result)
    return result,provenance

def configure_candidate_runtime(old, candidate):
    """R040a-local reproduction of frozen runtime_v2 lines 229-239."""
    from pathlib import Path
    old.WT=Path(candidate['worktree']); old.PARENT=candidate['parent_commit']; old.CANDIDATE=candidate['candidate_commit']
    actual_gpu, actual_artifacts=old._imports()
    actual_gpu.WT=old.WT
    actual_gpu.helper.PARENT=old.PARENT; actual_gpu.helper.CANDIDATE=old.CANDIDATE
    return actual_gpu, actual_artifacts

def make_owned_owner(options, *, gpu_module):
    """Construct the reviewed protocol Run(options) owner without GPU execution."""
    run=getattr(gpu_module,'Run',None)
    if run is None: raise R040aPreparationError('reviewed GPU Run constructor is unavailable')
    owner=run(options)
    if not callable(getattr(owner,'service',None)) or not callable(getattr(owner,'environment',None)):
        raise R040aPreparationError('retained Run lacks owned service lifecycle')
    return owner


def load_source(path, name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def shared_protocol():
    module=load_source(HERE/'d07_g3g4_prepare.py','r040a_d07')
    module.CANDIDATE=CANDIDATE; module.WORKTREE=WT
    return module


def write_new(path, value):
    with Path(path).open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,sort_keys=True,allow_nan=False);stream.write('\n')


def child_argv(batch, receipt, after):
    return [str(ROOT/'venv/bin/python'),str(Path(__file__).resolve()),'--run','--owned-child',
            '--batch',str(batch),'--launch-receipt',str(receipt),'--after-round',after]


def require_review(after):
    """Check sealed execution review and predecessors without reading prior raw data."""
    # Section eight permits this independent production-tree supplement to
    # follow an earlier ready batch when another queue entry is not ready.
    verdicts={'E2-R050-gate-D15':'kept','E2-R055a-gate-D06':'kept',
              'E2-R046a':'measured','E2-R049':'measured',
              'E2-R051-gate-D08':'kept','E2-R048':'measured'}
    if after not in verdicts: raise R040aPreparationError('R040a insertion must precede T05')
    d=shared_protocol(); d.require_t20_failed_harness(); d.require_r041_kept(ROOT)
    d.require_closed_round(after,verdicts[after]); d.checked_worktree(WT)
    review=REVIEW_DIR/'review.json'; pin=REVIEW_DIR/'pin.json'
    for p in (REVIEW_DIR,review,pin):
        if p.is_symlink() or not p.exists() or p.stat().st_mode&0o222:
            raise R040aPreparationError('R040a sealed startup review/pin missing')
    document=json.loads(review.read_text()); binding=json.loads(pin.read_text())
    if (binding.get('review_sha256')!=sha(review) or binding.get('rid')!=RID
        or document.get('rid')!=RID or document.get('verdict')!='PASS'
        or document.get('candidate_commit')!=CANDIDATE or document.get('after_round')!=after
        or document.get('source_execution_ready') is not True or document.get('model_admitted') is not False):
        raise R040aPreparationError('R040a review identity differs')
    sources=document.get('sources',{})
    required={str(HERE/name) for name in REQUIRED}
    required.update(str(HERE/name) for name in ('r040a_d16_supplement_prepare.py',
                    'd07_g3g4_prepare.py','t17_continuation_runner.py','d17_frozen_helpers.py'))
    if not required<=set(sources): raise R040aPreparationError('R040a review omits actual dependencies')
    for name,digest in sources.items():
        p=Path(name)
        if not p.is_absolute() or p.is_symlink() or not p.is_file() or p.stat().st_mode&0o222 or sha(p)!=digest:
            raise R040aPreparationError('R040a source binding differs: '+name)
    # If the four-cell item is incomplete, its executable collector must be
    # reviewed before allocating a batch; five D16 items cannot close that gap.
    anchor=document.get('anchor_four_cell',{})
    if anchor.get('state') not in ('already_complete_in_R040','queued_bound_supplement'):
        raise R040aPreparationError('anchor four-cell completion or executable supplement is still required')
    if anchor['state']=='queued_bound_supplement':
        probe=Path(anchor.get('probe_path',''))
        seed=anchor.get('input_binding',{})
        expected_probe=HERE/'helpers/raw/ft_probe_ckpt_tax.py'
        if (probe!=expected_probe or sources.get(str(probe))!=anchor.get('probe_sha256')
            or seed.get('path')!=str(ROOT/'wt/e1r003/seed_45k.txt')
            or not isinstance(seed.get('sha256'),str) or len(seed['sha256'])!=64):
            raise R040aPreparationError('anchor executable source or input binding differs')
    inputs=document.get('input_binding',{})
    expected=RUNS/'E2-R040/source_tools/realinput_28.json'
    if inputs.get('path')!=str(expected) or not isinstance(inputs.get('sha256'),str) or len(inputs['sha256'])!=64:
        raise R040aPreparationError('R040a input provenance binding differs')
    return document


def create_service_owner(batch, directory, d):
    old=load_source(HERE/'t17_continuation_runner.py','r040a_retained')
    gpu,_=configure_candidate_runtime(old,{'worktree':str(WT),'parent_commit':PARENT,'candidate_commit':CANDIDATE})
    helpers=load_source(HERE/'d17_frozen_helpers.py','r040a_retained_helpers')
    helpers.bind_protocol(gpu.protocol,HERE/'helpers')
    lifecycle=d.load_owned_lifecycle()
    # _imports adds continuation-only observers requiring current_case and
    # case_arms. D16 uses its own capture adapter and the real native service.
    native_run=next(cls for cls in gpu.Run.__mro__ if cls.__module__==gpu.__name__ and cls.__name__=='Run')
    class SupplementOwner(native_run):
        def set_status(self,**values):
            return gpu.protocol['Runner'].set_status(self,rid=RID,card='T20',**values)
        def environment(self,wt,arm=None,d0=False):
            env=gpu.protocol['Runner'].environment(self,wt,arm,d0)
            for key in list(env):
                if key.startswith('FT_'): env.pop(key)
            return env
        def stop(self):
            if self.proc is None:return
            process=self.proc
            try:lifecycle.stop_owned_process(process)
            except BaseException as error:
                error.owned_cleanup_failed=True;error.owned_process=process;raise
            self.proc=None
    owner=SupplementOwner(SimpleNamespace(rid=RID,batch=batch,run=True,gate='T20'))
    owner.directory=directory; owner.status=directory/f'status_batch{batch}.json'
    owner.token=d.LOCK.read_text(); owner.lock_inode=d.LOCK.stat().st_ino
    return owner


def execute(*,owned_child=False,batch=None,receipt=None,after='E2-R048'):
    if sys.platform!='linux': raise R040aPreparationError('R040a --run requires Linux')
    d=shared_protocol(); directory=RUNS/RID
    if directory.exists(): raise R040aPreparationError('R040a round already exists; preserve it')
    if not owned_child and (d.LOCK.exists() or d.LOCK.is_symlink()):
        raise R040aPreparationError('foreign GPU lock exists; R040a remains queued')
    review=require_review(after)
    if not owned_child:
        lifecycle=d.load_owned_lifecycle()
        allocator=lifecycle.verified_module(ROOT/'runs/plan_batches/e2_launch.py',d.ATOMIC_HELPER_SHA,'r040a_allocator')
        batch=allocator.next_batch(RUNS); receipt=ROOT/'runs/dev_D16'/f'launch_{RID}_batch{batch}.json'
        argv=child_argv(batch,receipt,after)
        reserved={'schema':'ft_r040a_owned_launch/v1','state':'reserved','rid':RID,'batch':batch,
                  'candidate_commit':CANDIDATE,'argv_sha256':d.argv_sha256(argv),'controller':d.process_birth()}
        value=lifecycle.reserve_process(allocator,batch,RID,argv,receipt,reserved)
        child=lifecycle.process_identity(value['batch_pid'])
        if child is None: raise R040aPreparationError('R040a child birth unavailable')
        return d.publish_child_binding(receipt,value,{k:child[k] for k in ('pid','start_ticks','execution_id')},lifecycle=lifecycle)
    if batch is None or receipt is None: raise R040aPreparationError('R040a child requires receipt')
    d.require_child_receipt(receipt,batch,WT,RUNS,rid=RID,expected_argv=child_argv(batch,receipt,after),schema='ft_r040a_owned_launch/v1')
    token=d.take_d07_gpu_lock(RID,batch); service_owner=None; created=False; cleanup_failed=False
    try:
        d.require_gpu_idle();directory.mkdir();created=True
        write_new(directory/f'status_batch{batch}.json',{'rid':RID,'gate':'T20','batch':batch,
                  'batch_pid':os.getpid(),'state':'preparing','owner':token})
        write_new(directory/'admission.json',{'rid':RID,'batch':batch,'candidate_commit':CANDIDATE,
                  'owner':token,'review_sha256':sha(REVIEW_DIR/'review.json'),'after_round':after,'admitted':False})
        inputs=Path(review['input_binding']['path']); payload=inputs.read_bytes()
        if hashlib.sha256(payload).hexdigest()!=review['input_binding']['sha256']:
            raise R040aPreparationError('R040a actual input bytes differ')
        service_owner=create_service_owner(batch,directory,d)
        anchor_result=review['anchor_four_cell']
        if anchor_result['state']=='queued_bound_supplement':
            anchor=load_source(HERE/'r040a_anchor_four_cell_v1.py','r040a_bound_anchor')
            anchor_result=anchor.collect_anchor_four_cell(service_owner,review)
        result,_=invoke_owned_supplement(service_owner,json.loads(payload),HERE/'d16_native_capture_shutdown_v3.py',
                    Path(review['collector_review']),review['collector_review_sha256'],
                    write_json=lambda name,value:write_new(directory/name,value))
        result['anchor_four_cell']=anchor_result
        write_new(directory/'result.json',result)
        service_owner.set_status(state='complete_measurements_pending_independent_review')
        return result
    except BaseException as error:
        cleanup_failed=bool(getattr(error,'owned_cleanup_failed',False))
        if created: write_new(directory/'failed_harness.json',{'rid':RID,'batch':batch,'error':repr(error),'admitted':False})
        if service_owner is not None: service_owner.set_status(state='failed',error=repr(error))
        elif created:
            status=directory/f'status_batch{batch}.json'; temporary=status.with_suffix('.tmp')
            write_new(temporary,{'rid':RID,'gate':'T20','batch':batch,'batch_pid':os.getpid(),
                                'state':'failed','error':repr(error),'owner':token})
            os.replace(temporary,status)
        raise
    finally:
        if service_owner is not None and service_owner.proc is not None:
            try:service_owner.stop()
            except BaseException:cleanup_failed=True
        if cleanup_failed:
            if created:write_new(directory/'owned_cleanup.json',{'lock_released':False,'cleanup_failed':True})
            raise R040aPreparationError('R040a owned cleanup uncertain; preserve GPU lock')
        d.release_d07_gpu_lock(token)
        if created:write_new(directory/'owned_cleanup.json',{'lock_released':True})

def invoke_owned_supplement(owner, realinputs, wrapper, review, review_sha256, **kwargs):
    if getattr(owner,'options',None) is None or owner.options.rid!=RID or owner.options.gate!='T20' or owner.options.run is not True:
        raise R040aPreparationError('R040a requires a live owned T20 supplement owner')
    return run_supplement_body(owner,realinputs,wrapper,review,review_sha256,**kwargs)

def main(argv=None):
 import argparse
 parser=argparse.ArgumentParser()
 parser.add_argument('--source-root',default=str(Path(__file__).resolve().parent))
 parser.add_argument('--write-prepare-json')
 parser.add_argument('--run',action='store_true')
 parser.add_argument('--owned-child',action='store_true',help=argparse.SUPPRESS)
 parser.add_argument('--batch',type=int,help=argparse.SUPPRESS)
 parser.add_argument('--launch-receipt',type=Path,help=argparse.SUPPRESS)
 parser.add_argument('--after-round',default='E2-R048')
 args=parser.parse_args(argv)
 if args.run:return execute(owned_child=args.owned_child,batch=args.batch,receipt=args.launch_receipt,after=args.after_round)
 value=prepare(args.source_root)
 if args.write_prepare_json:
  target=Path(args.write_prepare_json)
  if target.is_symlink() or target.exists(): raise R040aPreparationError('prepare output must be a new regular path')
  target.parent.mkdir(parents=True,exist_ok=True); target.write_text(json.dumps(value,sort_keys=True)+'\n')
 else: print(json.dumps(value,sort_keys=True))
 return value
if __name__=='__main__': main()
