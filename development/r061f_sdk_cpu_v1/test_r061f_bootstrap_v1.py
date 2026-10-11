import os
import hashlib,importlib.util,sys
from pathlib import Path
import pytest
DEV=Path(os.environ.get("R061F_RUNTIME_PACK", Path(__file__).parents[1] / "r061f_oom_runtime_v1"))
def load(n):
 s=importlib.util.spec_from_file_location(n,DEV/'r061f_oom_runtime_prepare_v1.py');m=importlib.util.module_from_spec(s);assert s.loader;s.loader.exec_module(m);return m
def test_writer_returns_rewritten_bootstrap_bytes_sha(tmp_path):
 m=load('v7');runtime=tmp_path/'runtime';runtime.mkdir();startup=runtime/'startup.py';startup.write_text('old');observer=runtime/'observer.py';observer.write_text('x')
 value=m.backend_startup_writer(lambda _: {'startup':str(startup),'startup_sha256':'stale','observer':str(observer),'observer_sha256':m.sha(observer)})(tmp_path)
 assert value['startup_sha256']==m.sha(startup) and value['startup_sha256']!='stale' and value['hook_sha256']==m.sha(Path(value['hook']))
 startup.write_text('tampered')
 assert value['startup_sha256']!=m.sha(startup)

def test_runtime_uses_one_round_identity_and_one_retained_runtime():
 m=load('v7');protocol,runtime=m.runtime()
 assert protocol.RID==runtime.RID==m.RID=='E2-R061f-OOM'
 assert protocol.r060() is runtime


def test_actual_owned_admission_rejects_changed_generated_wrapper(tmp_path, monkeypatch):
    import json
    spec = importlib.util.spec_from_file_location('owned_v7', DEV / 'r061f_oom_owned_launch_v1.py')
    owned = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(owned)
    native = tmp_path / 'native'
    native.write_text('native')
    native.chmod(0o444)
    monkeypatch.setattr(owned, 'NATIVE', native)
    monkeypatch.setattr(owned, 'NATIVE_SHA', owned.sha(native))
    monkeypatch.setattr(owned, 'candidate', lambda _: tmp_path)
    gate_proof = {'rid': 'R064', 'sha256': 'current'}
    monkeypatch.setattr(owned, 'require_r064_kept', lambda: gate_proof)
    sources = {'fixture': 'current'}
    inputs = {name: {'sha256': 'same'} for name in ('reference', 'affected', 'queued')}
    monkeypatch.setattr(owned, 'source_hashes', lambda: sources)
    monkeypatch.setattr(owned, 'input_hashes', lambda *args: inputs)
    bootstrap = {}
    for name in ('startup', 'observer', 'hook'):
        path = tmp_path / name
        path.write_text(name)
        bootstrap[name] = str(path)
        bootstrap[name + '_sha256'] = owned.sha(path)
    dry, review, pin = [tmp_path / name for name in ('dry.json', 'review.json', 'pin.json')]
    dry.write_text(json.dumps({'r064_kept': gate_proof, 'schema': 'ft_r061f_file_dry/v1', 'rid': owned.RID,
        'candidate_commit': owned.CANDIDATE, 'parent_commit': owned.BASE,
        'worktree': str(tmp_path), 'source_sha256': sources, 'input_sha256': inputs,
        'native_proof_sha256': owned.NATIVE_SHA, 'passed': True, 'bootstrap': bootstrap,
        **{name: False for name in ('service_started', 'requests_sent', 'gpu_lock_taken',
            'batch_allocated', 'formal_rid_directory_created', 'popen_reached')}}))
    review.write_text(json.dumps({'r064_kept': gate_proof, 'schema': 'ft_r061f_startup_review/v1', 'rid': owned.RID,
        'candidate_commit': owned.CANDIDATE, 'parent_commit': owned.BASE,
        'approved': True, 'verdict': 'PASS', 'source_sha256': sources,
        'input_sha256': inputs, 'file_dry_sha256': owned.sha(dry)}))
    pin.write_text(json.dumps({'schema': 'ft_r061f_startup_pin/v1', 'rid': owned.RID,
        'approved': True, 'verdict': 'PASS', 'review_sha256': owned.sha(review),
        'file_dry_sha256': owned.sha(dry)}))
    for path in (dry, review, pin):
        path.chmod(0o444)
    assert owned.require_admission(tmp_path, 'r', 'a', 'q', dry, review, pin)
    Path(bootstrap['startup']).write_text('changed')
    with pytest.raises(RuntimeError, match='bootstrap SHA differs'):
        owned.require_admission(tmp_path, 'r', 'a', 'q', dry, review, pin)

