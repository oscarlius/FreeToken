import copy
import importlib.util
import json
import math
import os
import stat
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/f"{name}.py")
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

c=load("d04_failed_archive_close_v2")
t=load("t20_failed_initial_close_v1")
GENERIC=ROOT/"initial_measurement_close.py"
WRITER=ROOT.parent/"scripts"/"round_json_append.py"


def write(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,sort_keys=True))


def fixture(tmp_path, monkeypatch):
    root=tmp_path/"E2-R040";root.mkdir()
    status={"rid":t.RID,"batch":t.BATCH,"state":"failed","batch_pid":3576643,"card":"T20"}
    write(root/"status_batch71.json",status)
    failed={"schema":"ft_t17_continuation_failure/v1","admitted":False,"error":"missing"}
    write(root/"failed_harness.json",failed)
    for n in range(24):
        arm=f"arm-{n:02d}";d=root/arm
        write(d/"SERVE_CMD.txt",{"argv":["serve",arm]});(d/"serve.log").write_text("STOP PASS")
        if n<7:
            write(d/"source.json",{"arm":arm})
        else:
            write(d/"environment.json",{"arm":arm});write(d/"compiled_extensions.json",{"arm":arm})
            (d/"ENV.txt").write_text("X=1\n");(d/"serve_args.txt").write_text("--arm "+arm)
    write(root/"execution_archive.json",{"rid":t.RID})
    receipt=tmp_path/"launch.json"
    write(receipt,{"schema":"ft_t20_actual_launch/v1","state":"launched","rid":t.RID,"batch":t.BATCH,"candidate_commit":t.CANDIDATE,"batch_pid":3576643})
    review=tmp_path/"review.json"
    write(review,{"schema":"ft_t20_r040_partial_observation_review/v1","rid":t.RID,"batch":t.BATCH,"verdict":"PARTIAL_MEASUREMENTS_PENDING_USER_DISPOSITION","terminal_failure":{"status_sha256":t.sha(root/"status_batch71.json"),"failed_harness_sha256":t.sha(root/"failed_harness.json")}})
    monkeypatch.setattr(t,"REVIEW_SHA",t.sha(review));monkeypatch.setattr(t,"RECEIPT_SHA",t.sha(receipt));monkeypatch.setattr(t,"FAILED_SHA",t.sha(root/"failed_harness.json"))
    monkeypatch.setattr(c,"REVIEW_SHA",t.sha(review));monkeypatch.setattr(c,"RECEIPT_SHA",t.sha(receipt));monkeypatch.setattr(c,"FAILED_SHA",t.sha(root/"failed_harness.json"));monkeypatch.setattr(c,"GENERIC_SHA",c.sha(GENERIC));monkeypatch.setattr(c,"WRITER_SHA",c.sha(WRITER))
    return root,review,receipt,t.metadata(root,review,receipt)


def test_fixture_is_exact_24_arm_failed_archive(monkeypatch,tmp_path):
    root,review,receipt,doc=fixture(tmp_path,monkeypatch)
    c.validate(root,doc)
    assert len(doc["serve"]["arms"])==24
    assert len(doc["failure_archive"]["missing_serve_args"])==7
    assert len(doc["failure_archive"]["missing_environment"])==7


def test_rejects_truncated_inventory_and_proofs(monkeypatch,tmp_path):
    root,review,receipt,doc=fixture(tmp_path,monkeypatch)
    short=copy.deepcopy(doc);short["serve"]["arms"].pop(next(iter(short["serve"]["arms"])))
    with pytest.raises(ValueError):c.validate(root,short)
    missing=copy.deepcopy(doc)
    for k in ("partial_review","terminal_status","launch_receipt"):missing["proofs"].pop(k)
    with pytest.raises(ValueError):c.validate(root,missing)


def test_rejects_nan_complete_and_identity_tamper(monkeypatch,tmp_path):
    root,review,receipt,doc=fixture(tmp_path,monkeypatch)
    bad=copy.deepcopy(doc);bad["results"]["started_service_arms"]=math.nan
    with pytest.raises(ValueError):c.validate(root,bad)
    status=json.loads((root/"status_batch71.json").read_text());status["state"]="complete";write(root/"status_batch71.json",status)
    with pytest.raises(ValueError):t.metadata(root,review,receipt)


def test_rejects_matching_but_unpinned_review(monkeypatch,tmp_path):
    root,review,receipt,doc=fixture(tmp_path,monkeypatch)
    altered=json.loads(review.read_text());altered["note"]="different bytes";write(review,altered)
    doc["proofs"]["partial_review"]["sha256"]=t.sha(review)
    with pytest.raises(ValueError,match="immutable proof pin"):
        c.validate(root,doc)


@pytest.mark.parametrize('field,value',[
    ('round_id','E2-R999'),('epoch',3),('epoch',True),('card','T06'),
    ('base',{'commit':'0'*40,'code_version':'E2-base.1@00000000'}),
    ('base',{'commit':t.CANDIDATE,'code_version':'E2-base@0aa2343'}),
    ('verdict_history',[{'new':'kept'}]),('retractions',[{'reason':'fake'}]),
    ('created_at','not a CST timestamp'),
])
def test_rejects_wrong_round_card_base_and_initial_history(monkeypatch,tmp_path,field,value):
    root,review,receipt,doc=fixture(tmp_path,monkeypatch)
    doc[field]=value
    with pytest.raises(ValueError):c.validate(root,doc)


def test_rejects_generic_and_writer_pin_substitution(monkeypatch,tmp_path):
    root,review,receipt,doc=fixture(tmp_path,monkeypatch)
    fake=tmp_path/"generic.py";fake.write_text("x=1\n")
    with pytest.raises(ValueError,match="publisher pin"):
        c.load_generic(fake)
    fake_writer=tmp_path/"writer.py";fake_writer.write_text("x=1\n")
    with pytest.raises(ValueError,match="writer pin"):
        c.append_failed(root,fake_writer,"failed","failed_harness.json")


@pytest.mark.skipif(os.name=="nt",reason="POSIX permissions required")
def test_readonly_rollback_and_real_append(monkeypatch,tmp_path):
    root,review,receipt,doc=fixture(tmp_path,monkeypatch)
    os.chmod(root,0o555)
    with pytest.raises(RuntimeError):
        c.initial_publish(root,doc,GENERIC,inject=lambda phase: (_ for _ in ()).throw(RuntimeError("inject")) if phase=="round_published" else None)
    assert stat.S_IMODE(root.stat().st_mode)==0o555
    assert not (root/"round.json").exists() and not (root/"round_history").exists()
    c.initial_publish(root,doc,GENERIC)
    assert (root/"round.json").is_file() and (root/"MANIFEST.sha256").is_file()
    assert stat.S_IMODE(root.stat().st_mode)&0o222==0
    c.append_failed(root,WRITER,"failed harness","failed_harness.json")
    closed=json.loads((root/"round.json").read_text())
    assert closed["verdict"]=="failed_harness" and closed["verdict_history"]
