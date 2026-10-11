import importlib.util,json
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('m',ROOT/'r046_failed_harness_close_prepare.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def w(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d))
def fixture(tmp_path,monkeypatch):
 tmp_path.mkdir(parents=True,exist_ok=True);root=tmp_path/'E2-R046';root.mkdir();term=tmp_path/'terminal.json';review=tmp_path/'review.json'
 failure={'rid':m.RID,'batch':m.BATCH,'error':'TimeoutError(x)','gpu_owner':{'execution_id':'1:2','pid':1,'start_ticks':2}}
 cleanup={'rid':m.RID,'batch':m.BATCH,'candidate_commit':m.COMMIT,'lock_released':True,'gpu_owner':dict(failure['gpu_owner'])}
 w(root/'failed_harness.json',failure);w(root/'owned_cleanup.json',cleanup)
 for arm in m.ARMS:w(root/arm/'SERVE_CMD.txt',{'arm':arm})
 w(root/'g3g4/g3_off/cold.json',{'record':{'cold_id':'x'}})
 w(term,{'rid':m.RID,'batch':m.BATCH,'state':'failed_harness_pending_D04','controller_absent':True,'service_absent':True,'lock_released':True,'round_tree_readonly':True,'full_raw_hash_performed':False,'files_sha256':{'failed_harness.json':m.sha(root/'failed_harness.json'),'owned_cleanup.json':m.sha(root/'owned_cleanup.json'),'g3g4/g3_off/cold.json':m.sha(root/'g3g4/g3_off/cold.json')}})
 w(review,{'schema':'ft_r046_live_incremental_g3off_review/v1','rid':m.RID,'batch':m.BATCH,'verdict':'G3_OFF_PASS_PENDING_ON_COMPARISON','candidate_commit':m.COMMIT,'cold':{'sha256':m.sha(root/'g3g4/g3_off/cold.json')}})
 monkeypatch.setattr(m,'TERMINAL_SHA',m.sha(term));monkeypatch.setattr(m,'FAILED_SHA',m.sha(root/'failed_harness.json'));monkeypatch.setattr(m,'CLEANUP_SHA',m.sha(root/'owned_cleanup.json'));monkeypatch.setattr(m,'COLD_SHA',m.sha(root/'g3g4/g3_off/cold.json'));monkeypatch.setattr(m,'REVIEW_SHA',m.sha(review));return root,term,review
def test_exact_two_arm_failed_proposal(tmp_path,monkeypatch):
 root,term,review=fixture(tmp_path,monkeypatch);d=m.prepare(root,term,review);assert d['mode']=='readonly_proposal' and d['proposed_metadata']['results']['started_service_arms']==2.0 and len(d['proposed_metadata']['missing_outputs'])==1
def test_rejects_fabricated_on_output_or_wrong_birth(tmp_path,monkeypatch):
 root,term,review=fixture(tmp_path,monkeypatch);w(root/'g3g4/g3_on/cold.json',{}); 
 with pytest.raises(ValueError):m.prepare(root,term,review)
 root,term,review=fixture(tmp_path/'birth',monkeypatch);x=json.loads((root/'owned_cleanup.json').read_text());x['gpu_owner']['start_ticks']=3;w(root/'owned_cleanup.json',x)
 with pytest.raises(ValueError):m.prepare(root,term,review)
def test_rejects_terminal_raw_hash_claim(tmp_path,monkeypatch):
 root,term,review=fixture(tmp_path,monkeypatch);x=json.loads(term.read_text());x['full_raw_hash_performed']=True;w(term,x);monkeypatch.setattr(m,'TERMINAL_SHA',m.sha(term))
 with pytest.raises(ValueError):m.prepare(root,term,review)
