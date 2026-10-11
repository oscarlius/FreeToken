from __future__ import annotations
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest

HERE=Path(__file__).parent; spec=importlib.util.spec_from_file_location('r040jv3',HERE/'r040j_api_d16.py'); mod=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(mod)

def test_child_argv_contains_run_receipt_and_admission_identity():
    receipt=Path('/tmp/receipt.json'); admission=Path('/tmp/admission.json'); command=mod.child_argv(17,receipt,admission)
    assert '--run' in command and command[-1]==str(admission) and command[command.index('--batch')+1]=='17'

def test_start_failure_stops_exact_owned_group(monkeypatch,tmp_path):
    calls=[]
    class P:
        pid=123
        def poll(self): return None
    life=SimpleNamespace(process_identity=lambda pid:{'pid':pid,'pgid':pid,'session':pid},stop_owned_process=lambda proc,term,kill:calls.append((proc.pid,term,kill)))
    d07=SimpleNamespace(clean_environment=lambda wt:{'CUDA_VISIBLE_DEVICES':'0','PYTHONPATH':'p','VIRTUAL_ENV':'v'},load_owned_lifecycle=lambda:life)
    monkeypatch.setattr(mod,'serve_argv',lambda port:['ft','serve']); monkeypatch.setattr(mod.subprocess,'Popen',lambda *a,**k:P()); monkeypatch.setattr(mod.urllib.request,'urlopen',lambda *a,**k:(_ for _ in ()).throw(OSError('not ready'))); monkeypatch.setattr(mod.time,'sleep',lambda _:None)
    with pytest.raises(TimeoutError): mod.start(d07,tmp_path,12345)
    assert calls==[(123,120,30)] and 'MASTER_PORT=12346' in (tmp_path/'SERVE_CMD.txt').read_text()


@pytest.mark.parametrize('becomes_ready', [True, False])
def test_start_paces_real_http_loading_responses(monkeypatch, tmp_path, becomes_ready):
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    requests=[]; sleeps=[]; stopped=[]
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.path=='/health'
            requests.append(self.path)
            body=json.dumps({'status':'ok' if becomes_ready and len(requests)==3 else 'loading'}).encode()
            self.send_response(200); self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
        def log_message(self, *args): pass
    class P:
        pid=123
        def poll(self): return None
    life=SimpleNamespace(process_identity=lambda pid:{'pid':pid,'pgid':pid,'session':pid},stop_owned_process=lambda proc,term,kill:stopped.append((proc.pid,term,kill)))
    d07=SimpleNamespace(clean_environment=lambda wt:{'CUDA_VISIBLE_DEVICES':'0','PYTHONPATH':'p','VIRTUAL_ENV':'v'},load_owned_lifecycle=lambda:life)
    monkeypatch.setenv('NO_PROXY','127.0.0.1,localhost'); monkeypatch.setenv('no_proxy','127.0.0.1,localhost')
    monkeypatch.setattr(mod,'serve_argv',lambda port:['ft','serve'])
    monkeypatch.setattr(mod.subprocess,'Popen',lambda *a,**k:P())
    monkeypatch.setattr(mod.time,'sleep',lambda seconds:sleeps.append(seconds))
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    try:
        if becomes_ready:
            assert mod.start(d07,tmp_path,server.server_port).pid==123
            assert len(requests)==3 and sleeps==[2,2] and stopped==[]
            assert json.loads((tmp_path/'health.json').read_text())=={'status':'ok'}
        else:
            with pytest.raises(TimeoutError): mod.start(d07,tmp_path,server.server_port)
            assert len(requests)==450 and sleeps==[2]*450 and stopped==[(123,120,30)]
            assert not (tmp_path/'health.json').exists()
    finally:
        server.shutdown(); thread.join(timeout=3); server.server_close()
    assert not thread.is_alive()

def test_filedry_writer_uses_plan_and_freeze_without_launch(monkeypatch,tmp_path):
    d07=SimpleNamespace(clean_environment=lambda wt:{'CUDA_VISIBLE_DEVICES':'0','PYTHONPATH':'p','VIRTUAL_ENV':'v'})
    pair=SimpleNamespace(dynamic_port=lambda:12345,port_receipt=lambda p:{'api':p,'tcpstore':p+1})
    monkeypatch.setattr(mod,'DEV',tmp_path); monkeypatch.setattr(mod,'plan',lambda:{'schema':'p'}); monkeypatch.setattr(mod,'freeze',lambda out:(out/'source_manifest.json').write_text('{}')); monkeypatch.setattr(mod,'load',lambda path,name:d07 if path==mod.D07 else pair); monkeypatch.setattr(mod,'serve_argv',lambda port:['ft','serve'])
    value=mod.filedry(); out=Path(value['output'])
    assert (out/'preflight.json').is_file() and (out/'filedry.json').is_file() and not (mod.ROUNDS/mod.RID).exists()


def test_child_uses_d07_receipt_contract_and_actual_batch_lock(monkeypatch, tmp_path):
    seen={}
    class StopHere(Exception): pass
    def require(receipt,batch,worktree,output_root,**kwargs):
        seen.update(receipt=receipt,batch=batch,worktree=worktree,output_root=output_root,**kwargs)
    d07=SimpleNamespace(require_child_receipt=require, take_d07_gpu_lock=lambda rid,batch:(_ for _ in ()).throw(StopHere()), release_d07_gpu_lock=lambda owner:pytest.fail('released absent lock'))
    monkeypatch.setattr(mod,'load',lambda path,name:d07); monkeypatch.setattr(mod,'admission',lambda path:{'sha256':'a'}); monkeypatch.setattr(mod,'plan',lambda:{'schema':'p'}); monkeypatch.setattr(mod,'ROUNDS',tmp_path)
    receipt=tmp_path/'receipt.json'; admit=tmp_path/'admission.json'
    with pytest.raises(StopHere): mod.execute_owned(29,receipt,admit)
    assert seen['batch']==29 and seen['rid']==mod.RID and seen['schema']=='ft_r040j_api_owned_launch/v2'
    assert seen['expected_argv']==mod.child_argv(29,receipt,admit)


def test_failed_start_with_live_owned_group_preserves_lock(monkeypatch, tmp_path):
    released=[]
    class P: pid=77
    class FailedStart(RuntimeError): pass
    failure=FailedStart('health failed'); failure.owned_process=P()
    life=SimpleNamespace(stop_owned_process=lambda process,term,kill:(_ for _ in ()).throw(RuntimeError('still alive')), owned_group_alive=lambda pid:True)
    d07=SimpleNamespace(require_child_receipt=lambda *a,**k:None, take_d07_gpu_lock=lambda rid,batch:{'lock':1}, release_d07_gpu_lock=lambda owner:released.append(owner), require_gpu_idle=lambda:None, load_owned_lifecycle=lambda:life)
    pair=SimpleNamespace(dynamic_port=lambda:12345)
    monkeypatch.setattr(mod,'load',lambda path,name:d07 if path==mod.D07 else pair); monkeypatch.setattr(mod,'admission',lambda path:{'sha256':'a'}); monkeypatch.setattr(mod,'plan',lambda:{'schema':'p'}); monkeypatch.setattr(mod,'freeze',lambda out:None); monkeypatch.setattr(mod,'ROUNDS',tmp_path); monkeypatch.setattr(mod,'start',lambda *a,**k:(_ for _ in ()).throw(failure))
    with pytest.raises(RuntimeError, match='owned service remains'):
        mod.execute_owned(31,tmp_path/'receipt.json',tmp_path/'admission.json')
    assert released==[]


def test_admission_binds_current_sources_filedry_and_approved_review(monkeypatch, tmp_path):
    source=tmp_path/'source.py'; source.write_text('source')
    candidate={'worktree':str(mod.WT),'commit':mod.CANDIDATE,'tracked_clean':True}
    filedry=tmp_path/'filedry.json'; filedry.write_text('{"no_formal_rid_batch_lock_popen_or_request": true}')
    preflight=tmp_path/'preflight.json'; preflight.write_text(__import__('json').dumps({'candidate':candidate}))
    manifest=tmp_path/'manifest.json'; manifest.write_text(__import__('json').dumps({'files':{'source.py':mod.sha(source)}}))
    review=tmp_path/'review.json'; review.write_text(__import__('json').dumps({'schema':'ft_r040j_api_independent_review/v1','rid':mod.RID,'candidate_commit':mod.CANDIDATE,'scope':{'services':6,'calls':8,'warm':'deferred_no_actual_expert_hit_proof'},'source_manifest_sha256':mod.sha(manifest),'source_sha256':{'source.py':mod.sha(source)},'approved':True}))
    admission=tmp_path/'admission.json'; doc={'rid':mod.RID,'candidate_commit':mod.CANDIDATE,'worktree':str(mod.WT),'cwd':str(Path.cwd()),'user':mod.getpass.getuser(),'filedry_path':str(filedry),'filedry_sha256':mod.sha(filedry),'preflight_path':str(preflight),'preflight_sha256':mod.sha(preflight),'source_manifest_path':str(manifest),'source_manifest_sha256':mod.sha(manifest),'independent_review_path':str(review),'independent_review_sha256':mod.sha(review),'source_sha256':{'source.py':mod.sha(source)}}; admission.write_text(__import__('json').dumps(doc))
    for path in (filedry,preflight,manifest,review,admission): path.chmod(0o444)
    monkeypatch.setattr(mod,'sources',lambda:{'source.py':source}); monkeypatch.setattr(mod,'candidate',lambda:candidate)
    assert mod.admission(admission)['sha256']==mod.sha(admission)


def test_launch_uses_sealed_admission_without_hidden_chdir_or_reservation(monkeypatch, tmp_path):
    canonical=tmp_path/'canonical'; canonical.mkdir(); monkeypatch.chdir(canonical)
    source=tmp_path/'source.py'; source.write_text('source')
    candidate={'worktree':str(mod.WT),'commit':mod.CANDIDATE,'tracked_clean':True}
    filedry=tmp_path/'filedry.json'; filedry.write_text('{"no_formal_rid_batch_lock_popen_or_request": true}')
    preflight=tmp_path/'preflight.json'; preflight.write_text(__import__('json').dumps({'candidate':candidate}))
    manifest=tmp_path/'manifest.json'; manifest.write_text(__import__('json').dumps({'files':{'source.py':mod.sha(source)}}))
    review=tmp_path/'review.json'; review.write_text(__import__('json').dumps({'schema':'ft_r040j_api_independent_review/v1','rid':mod.RID,'candidate_commit':mod.CANDIDATE,'scope':{'services':6,'calls':8,'warm':'deferred_no_actual_expert_hit_proof'},'source_manifest_sha256':mod.sha(manifest),'source_sha256':{'source.py':mod.sha(source)},'approved':True}))
    pin=tmp_path/'admission.json'; pin.write_text(__import__('json').dumps({'rid':mod.RID,'candidate_commit':mod.CANDIDATE,'worktree':str(mod.WT),'cwd':str(canonical),'user':mod.getpass.getuser(),'filedry_path':str(filedry),'filedry_sha256':mod.sha(filedry),'preflight_path':str(preflight),'preflight_sha256':mod.sha(preflight),'source_manifest_path':str(manifest),'source_manifest_sha256':mod.sha(manifest),'independent_review_path':str(review),'independent_review_sha256':mod.sha(review),'source_sha256':{'source.py':mod.sha(source)}}))
    for path in (filedry,preflight,manifest,review,pin): path.chmod(0o444)
    class HaltBeforeReserve(Exception): pass
    def reserve(*args):
        assert Path.cwd()==canonical
        raise HaltBeforeReserve()
    helper=SimpleNamespace(next_batch=lambda rounds:73)
    owned=SimpleNamespace(verified_module=lambda *args:helper,reserve_process=reserve)
    d07=SimpleNamespace(LOCK=tmp_path/'gpu.lock',ATOMIC_HELPER_SHA='a'*64,load_owned_lifecycle=lambda:owned,process_birth=lambda *args:{'pid':1,'start_ticks':2,'execution_id':'1:2'})
    monkeypatch.setattr(mod,'sources',lambda:{'source.py':source}); monkeypatch.setattr(mod,'candidate',lambda:candidate); monkeypatch.setattr(mod,'plan',lambda:{'schema':'p'}); monkeypatch.setattr(mod,'load',lambda *args:d07); monkeypatch.setattr(mod,'ROUNDS',tmp_path/'rounds'); monkeypatch.setattr(mod,'DEV',tmp_path/'dev'); monkeypatch.setattr(mod.sys,'platform','linux')
    mod.ROUNDS.mkdir()
    with pytest.raises(HaltBeforeReserve): mod.launch(pin)
    assert Path.cwd()==canonical and not (mod.ROUNDS/mod.RID).exists() and not d07.LOCK.exists()
