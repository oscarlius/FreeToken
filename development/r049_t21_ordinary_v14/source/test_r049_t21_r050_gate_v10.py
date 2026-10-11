import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

DEV = Path(__file__).parent

def load():
    spec = importlib.util.spec_from_file_location('r049_r050_v9', DEV/'r049_t21_ordinary_prepare_v14.py')
    module = importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(module)
    return module

def closure_fixture(monkeypatch, tmp_path):
    m = load(); m.ROUNDS = tmp_path/'rounds'; m.ROOT = tmp_path/'root'; m.VENV = tmp_path/'venv'
    directory = m.ROUNDS/m.R050_RID; directory.mkdir(parents=True)
    round_json, manifest, checker = directory/'round.json', directory/'MANIFEST.sha256', directory/'round_json_append.py'
    round_json.write_text(json.dumps({'round_id':m.R050_RID, 'verdict':'kept'})); manifest.write_text('manifest\n'); checker.write_text('# checker\n')
    m.R050_ROUND_SHA = hashlib.sha256(round_json.read_bytes()).hexdigest(); m.R050_MANIFEST_SHA = hashlib.sha256(manifest.read_bytes()).hexdigest()
    pin = m.ROOT/'runs/plan_batches/closed_round_pins'/f'{m.R050_RID}.json'; pin.parent.mkdir(parents=True)
    pin.write_text(json.dumps({'rid':m.R050_RID, 'verdict':'kept', 'candidate_commit':m.CANDIDATE, 'round_sha256':m.R050_ROUND_SHA, 'manifest_sha256':m.R050_MANIFEST_SHA}))
    for path in (directory, pin.parent): path.chmod(0o555)
    for path in (round_json, manifest, checker, pin): path.chmod(0o444)
    monkeypatch.setattr(m.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0))
    return m, pin

def test_r050_kept_gate_accepts_only_exact_readonly_candidate_closure(monkeypatch, tmp_path):
    m, _ = closure_fixture(monkeypatch, tmp_path)
    assert m.require_r050_d15_closure()['round_sha256'] == m.R050_ROUND_SHA

@pytest.mark.parametrize('change,pattern', [('candidate', 'identity differs'), ('verdict', 'identity differs'), ('writable', 'missing, linked, or writable')])
def test_r050_gate_rejects_wrong_candidate_nonkept_or_nonreadonly(monkeypatch, tmp_path, change, pattern):
    m, pin = closure_fixture(monkeypatch, tmp_path)
    if change == 'writable':
        pin.chmod(0o600)
    else:
        pin.chmod(0o600); doc = json.loads(pin.read_text())
        doc['candidate_commit' if change == 'candidate' else 'verdict'] = 'wrong' if change == 'candidate' else 'measured'
        pin.write_text(json.dumps(doc)); pin.chmod(0o444)
    with pytest.raises(RuntimeError, match=pattern): m.require_r050_d15_closure()


def test_r049_failed_closure_rejects_reuse_or_wrong_d04(monkeypatch,tmp_path):
 m=load();m.ROUNDS=tmp_path/'rounds';m.ROOT=tmp_path/'root';m.VENV=tmp_path/'venv';m.R049_FAILED_D04_RECEIPT=m.ROOT/'runs/dev_T21/r049_d04_failed_closure_receipt_v1.json'
 d=m.ROUNDS/m.R049_FAILED_RID;d.mkdir(parents=True); r=d/'round.json'; q=d/'MANIFEST.sha256'; c=d/'round_json_append.py';r.write_text(json.dumps({'round_id':m.R049_FAILED_RID,'verdict':'failed_harness'}));q.write_text('m');c.write_text('#')
 pin=m.ROOT/'runs/plan_batches/closed_round_pins'/f'{m.R049_FAILED_RID}.json';pin.parent.mkdir(parents=True);pin.write_text(json.dumps({'rid':m.R049_FAILED_RID,'verdict':'failed_harness'}));m.R049_FAILED_D04_RECEIPT.parent.mkdir(parents=True)
 m.R049_FAILED_D04_RECEIPT.write_text(json.dumps({'rid':m.R049_FAILED_RID,'verdict':'failed_harness','round_sha256':'pending','manifest_sha256':'pending','pin_sha256':'pending','candidate_commit':m.CANDIDATE,'readonly':True,'d04_check':{'ok':True},'independent_review_sha256':m.R049_FAILED_REVIEW_SHA,'accepted_full_groups':0,'partial_unaccepted_workloads':4,'expected_tokens_per_stream':512,'observed_tokens_per_stream':[20,20],'measurement_retry_authorized':False}))
 for x in (r,q,c,pin,m.R049_FAILED_D04_RECEIPT):x.chmod(0o444)
 for x in (d,pin.parent,m.R049_FAILED_D04_RECEIPT.parent):x.chmod(0o555)
 m.R049_FAILED_ROUND_SHA=hashlib.sha256(r.read_bytes()).hexdigest();m.R049_FAILED_MANIFEST_SHA=hashlib.sha256(q.read_bytes()).hexdigest();m.R049_FAILED_PIN_SHA=hashlib.sha256(pin.read_bytes()).hexdigest();m.R049_FAILED_D04_RECEIPT.chmod(0o600); receipt=json.loads(m.R049_FAILED_D04_RECEIPT.read_text());receipt.update(round_sha256=m.R049_FAILED_ROUND_SHA,manifest_sha256=m.R049_FAILED_MANIFEST_SHA,pin_sha256=m.R049_FAILED_PIN_SHA);m.R049_FAILED_D04_RECEIPT.write_text(json.dumps(receipt));m.R049_FAILED_D04_RECEIPT.chmod(0o444);m.R049_FAILED_D04_SHA=hashlib.sha256(m.R049_FAILED_D04_RECEIPT.read_bytes()).hexdigest();monkeypatch.setattr(m.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0))
 assert m.require_r049_failure_closure()['performance_reuse_forbidden']
 m.R049_FAILED_D04_RECEIPT.chmod(0o600);receipt=json.loads(m.R049_FAILED_D04_RECEIPT.read_text());receipt['accepted_full_groups']=1;m.R049_FAILED_D04_RECEIPT.write_text(json.dumps(receipt));m.R049_FAILED_D04_RECEIPT.chmod(0o444)
 with pytest.raises(RuntimeError):m.require_r049_failure_closure()
