import hashlib, importlib.util, json, sys
from pathlib import Path
import pytest

DEV=Path(__file__).parents[1]
def load():
 s=importlib.util.spec_from_file_location('r061v5',DEV/'r061_oom_owned_launch_v5.py');m=importlib.util.module_from_spec(s);assert s.loader;sys.modules[s.name]=m;s.loader.exec_module(m);return m

def test_v5_formal_entry_has_strict_admission_before_controller_reservation():
 text=(DEV/'r061_oom_owned_launch_v5.py').read_text()
 assert "proof=require_admission(wt,r,a,q,dry,review,pin)" in text
 assert text.index("proof=require_admission(wt,r,a,q,dry,review,pin)") < text.index('owned.reserve_process')
 assert "ft_r061_file_dry/v5" in text and "ft_r061_startup_review/v5" in text and "ft_r061_startup_pin/v5" in text

def test_admission_binds_current_source_inputs_file_dry_review_and_pin(tmp_path,monkeypatch):
 m=load();native=tmp_path/'native';native.write_text('native');dry=tmp_path/'dry';review=tmp_path/'review';pin=tmp_path/'pin'
 for p in (dry,review,pin): p.write_text('{}')
 native.chmod(0o444)
 digest='0d09b38c508783c0dd9d9e743a6d9174e3f126667791e1d40cd53f5def1eeb3d';src={'new-v5':'current'};inputs={'reference':{'sha256':'same'},'affected':{'sha256':'same'},'queued':{'sha256':'same'}}
 monkeypatch.setattr(m,'NATIVE',native);monkeypatch.setattr(m,'NATIVE_SHA',digest);monkeypatch.setattr(m,'sha',lambda _p:digest);monkeypatch.setattr(m,'candidate',lambda _p:Path('/candidate'));monkeypatch.setattr(m,'input_hashes',lambda *_:inputs);monkeypatch.setattr(m,'source_hashes',lambda:src)
 dry.write_text(json.dumps({'schema':'ft_r061_file_dry/v5','rid':m.RID,'candidate_commit':m.CANDIDATE,'parent_commit':m.BASE,'worktree':str(Path('/candidate')),'source_sha256':src,'input_sha256':inputs,'native_proof_sha256':digest,'passed':True,'service_started':False,'requests_sent':False,'gpu_lock_taken':False,'batch_allocated':False,'formal_rid_directory_created':False,'popen_reached':False}));dry.chmod(0o444)
 review.write_text(json.dumps({'schema':'ft_r061_startup_review/v5','rid':m.RID,'candidate_commit':m.CANDIDATE,'parent_commit':m.BASE,'approved':True,'verdict':'PASS','source_sha256':src,'input_sha256':inputs,'file_dry_sha256':digest}));review.chmod(0o444)
 pin.write_text(json.dumps({'schema':'ft_r061_startup_pin/v5','rid':m.RID,'approved':True,'verdict':'PASS','review_sha256':digest,'file_dry_sha256':digest}));pin.chmod(0o444)
 assert m.require_admission('/candidate','r','a','q',dry,review,pin)['file_dry_sha256']==digest
 tampered=json.loads(dry.read_text());tampered['source_sha256']={'old':'sha'};dry.chmod(0o600);dry.write_text(json.dumps(tampered));dry.chmod(0o444)
 with pytest.raises(RuntimeError,match='FILEDRY binding'):m.require_admission('/candidate','r','a','q',dry,review,pin)
