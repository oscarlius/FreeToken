import importlib.util, json, sys
from pathlib import Path
from types import SimpleNamespace
import pytest

DEV=Path(__file__).parents[1]
def load():
 s=importlib.util.spec_from_file_location('r061v2',DEV/'r061_oom_fault_prepare_v2.py');m=importlib.util.module_from_spec(s);assert s.loader;sys.modules[s.name]=m;s.loader.exec_module(m);return m

def test_actual_argv_requires_98k_ratio_and_explicit_adjacent_pair():
 m=load(); d=SimpleNamespace(serve_argv=lambda p:['ft','--port',str(p),'--kv-reserve-tokens','98304','--max-seq-len-override','98304','--memory-ratio','0.88'])
 assert m.actual_argv(d,{'api':1234,'tcpstore':1235})[4]=='98304'
 d.serve_argv=lambda p:['ft','--port',str(p),'--kv-reserve-tokens','49152','--memory-ratio','0.88']
 with pytest.raises(RuntimeError):m.actual_argv(d,{'api':1234,'tcpstore':1235})

def test_admission_rejects_every_bound_document_mismatch(tmp_path,monkeypatch):
 m=load(); worktree=tmp_path/'wt';worktree.mkdir(); inputs=tmp_path/'inputs';inputs.mkdir()
 for name in ('r','a','q'): (inputs/f'{name}.json').write_text('{}')
 dry,review,pin,native=(tmp_path/x for x in ('dry.json','review.json','pin.json','native.json'))
 source={'runner':'sha'}; hashed={'r':{'path':'r','sha256':'x','md5':'m'},'a':{'path':'a','sha256':'x','md5':'m'},'q':{'path':'q','sha256':'x','md5':'m'}}
 dry_doc={'schema':'ft_r061_file_dry/v2','rid':m.RID,'candidate_commit':m.CANDIDATE,'parent_commit':m.BASE,'worktree':str(worktree),'source_sha256':source,'input_sha256':hashed,'passed':True,'service_started':False,'requests_sent':False,'gpu_lock_taken':False,'batch_allocated':False,'formal_rid_directory_created':False,'popen_reached':False}
 for p,v in ((dry,dry_doc),(review,{'schema':'ft_r061_startup_review/v2','rid':m.RID,'candidate_commit':m.CANDIDATE,'parent_commit':m.BASE,'approved':True,'verdict':'PASS','source_sha256':source,'input_sha256':hashed,'file_dry_sha256':'dry'}),(pin,{'schema':'ft_r061_startup_pin/v2','approved':True,'verdict':'PASS','review_sha256':'review','file_dry_sha256':'dry'}),(native,{'candidate_commit':m.CANDIDATE})):p.write_text(json.dumps(v))
 monkeypatch.setattr(m,'NATIVE',native);monkeypatch.setattr(m,'candidate',lambda x:worktree);monkeypatch.setattr(m,'input_hashes',lambda *x:hashed);monkeypatch.setattr(m,'source_hashes',lambda:source);monkeypatch.setattr(m,'sealed',lambda p,l:Path(p));monkeypatch.setattr(m,'sha',lambda p:{native:'0d09b38c508783c0dd9d9e743a6d9174e3f126667791e1d40cd53f5def1eeb3d',dry:'dry',review:'review',pin:'pin'}.get(Path(p),'other'))
 assert m.require_admission(worktree,inputs/'r.json',inputs/'a.json',inputs/'q.json',dry,review,pin)['file_dry_sha256']=='dry'
 for key,value in (('approved',False),('verdict','FAIL'),('file_dry_sha256','bad')):
  changed=dict(json.loads(review.read_text()));changed[key]=value;review.write_text(json.dumps(changed))
  with pytest.raises(RuntimeError):m.require_admission(worktree,inputs/'r.json',inputs/'a.json',inputs/'q.json',dry,review,pin)
  review.write_text(json.dumps({'schema':'ft_r061_startup_review/v2','rid':m.RID,'candidate_commit':m.CANDIDATE,'parent_commit':m.BASE,'approved':True,'verdict':'PASS','source_sha256':source,'input_sha256':hashed,'file_dry_sha256':'dry'}))

def test_terminal_preserves_raw_failure_and_does_not_claim_cleanup(tmp_path):
 m=load();m.terminal(tmp_path,9,{'owner':'x'},RuntimeError('boom'),False)
 row=json.loads((tmp_path/'failed_harness.json').read_text())
 assert row['raw_preserved'] is True and row['cleanup_succeeded'] is False
 assert not (tmp_path/'owned_cleanup.json').exists()
