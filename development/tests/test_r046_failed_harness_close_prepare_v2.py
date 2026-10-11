import importlib.util,json,os,stat
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('m',ROOT/'r046_failed_harness_close_prepare_v2.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def w(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d))
def writable(root):os.chmod(root,stat.S_IMODE(root.stat().st_mode)|stat.S_IWUSR)
def fixture(tmp_path,monkeypatch):
 tmp_path.mkdir(parents=True,exist_ok=True);root=tmp_path/'E2-R046';root.mkdir();term=tmp_path/'terminal.json';review=tmp_path/'review.json'
 failure={'rid':m.RID,'batch':m.BATCH,'error':'TimeoutError(x)','gpu_owner':{'execution_id':'1:2','pid':1,'start_ticks':2}}
 cleanup={'rid':m.RID,'batch':m.BATCH,'candidate_commit':m.COMMIT,'lock_released':True,'gpu_owner':dict(failure['gpu_owner'])}
 w(root/'failed_harness.json',failure);w(root/'owned_cleanup.json',cleanup);w(root/'preflight.json',{'rid':m.RID,'batch':m.BATCH,'candidate_commit':m.COMMIT})
 for arm in m.ARMS:
  w(root/arm/'SERVE_CMD.txt',{'arm':arm});(root/arm/'serve.log').write_text('log');w(root/arm/'owned_process.json',{'birth':dict(failure['gpu_owner'])})
 w(root/'g3g4/g3_off/cold.json',{'record':{'cold_id':'x'}})
 files={'failed_harness.json':m.sha(root/'failed_harness.json'),'owned_cleanup.json':m.sha(root/'owned_cleanup.json'),'preflight.json':m.sha(root/'preflight.json'),'g3g4/g3_off/cold.json':m.sha(root/'g3g4/g3_off/cold.json')}
 w(term,{'rid':m.RID,'batch':m.BATCH,'state':'failed_harness_pending_D04','controller_absent':True,'service_absent':True,'lock_released':True,'round_tree_readonly':True,'full_raw_hash_performed':False,'files_sha256':files})
 w(review,{'schema':'ft_r046_live_incremental_g3off_review/v1','rid':m.RID,'batch':m.BATCH,'verdict':'G3_OFF_PASS_PENDING_ON_COMPARISON','candidate_commit':m.COMMIT,'cold':{'sha256':m.sha(root/'g3g4/g3_off/cold.json')}})
 monkeypatch.setattr(m,'TERMINAL_SHA',m.sha(term));monkeypatch.setattr(m,'FAILED_SHA',m.sha(root/'failed_harness.json'));monkeypatch.setattr(m,'CLEANUP_SHA',m.sha(root/'owned_cleanup.json'));monkeypatch.setattr(m,'COLD_SHA',m.sha(root/'g3g4/g3_off/cold.json'));monkeypatch.setattr(m,'REVIEW_SHA',m.sha(review));os.chmod(root,0o555);return root,term,review
def test_metadata_has_two_missing_archives_and_full_inner_proofs(tmp_path,monkeypatch):
 root,term,review=fixture(tmp_path,monkeypatch);d=m.prepare(root,term,review);inner=d['proposed_metadata'];assert inner['created_at'] and set(inner['proofs'])=={'terminal_observation','failed_harness','owned_cleanup','preflight','g3_off_review','g3_off_cold'};assert len(inner['failure_archive']['missing_environment'])==2 and len(inner['failure_archive']['missing_serve_args'])==2
def test_rejects_wrong_root_or_missing_arm(tmp_path,monkeypatch):
 root,term,review=fixture(tmp_path,monkeypatch);bad=tmp_path/'E2-R999';root.rename(bad)
 with pytest.raises(ValueError):m.prepare(bad,term,review)
 root,term,review=fixture(tmp_path/'arm',monkeypatch);writable(root);(root/'g3g4/g3_on/SERVE_CMD.txt').unlink();os.chmod(root,0o555)
 with pytest.raises(ValueError):m.prepare(root,term,review)
def test_rejects_birth_or_archive_source_proof_mutation(tmp_path,monkeypatch):
 root,term,review=fixture(tmp_path,monkeypatch);writable(root);x=json.loads((root/'owned_cleanup.json').read_text());x['gpu_owner']['start_ticks']=3;w(root/'owned_cleanup.json',x);os.chmod(root,0o555)
 with pytest.raises(ValueError):m.prepare(root,term,review)
 root,term,review=fixture(tmp_path/'proof',monkeypatch);writable(root);(root/'g3g4/g3_off/serve.log').unlink();os.chmod(root,0o555)
 with pytest.raises(ValueError):m.prepare(root,term,review)
def test_rejects_nonreadonly_root(tmp_path,monkeypatch):
 root,term,review=fixture(tmp_path,monkeypatch);writable(root)
 with pytest.raises(ValueError):m.prepare(root,term,review)
