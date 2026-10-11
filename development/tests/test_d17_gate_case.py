import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

PATH = Path(__file__).parents[1] / "d17_gate_case.py"
SPEC = importlib.util.spec_from_file_location("d17_gate_case", PATH)
d17 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(d17)


def test_case_binds_complete_d17_and_d14_commits():
    case = d17.d17_case()
    assert case["candidate"]["commit"] == "0aa23431e5b800797543bdecbf35a01045131d7d"
    assert case["control"]["commit"] == "a9dca443cd07e1f60d1533e0a678935a09d21636"
    assert case['cold']['control_commit'] == '23f2e2caa3395837c9474735ffc83321f3b9b5a1'
    assert Path(case['cold']['control_worktree']) == Path('/data2/FreeToken/wt/e2base')
    assert case["default_hooks"] == {"D06": False, "D07": False}


def test_default_environment_uses_shared_t16_cleanup(monkeypatch):
    import runpy
    from types import SimpleNamespace
    actual = runpy.run_path(str(Path(__file__).parents[1]/'t16_full_tail_base_runner.py'))
    monkeypatch.setattr(d17,'_load_protocol',lambda:SimpleNamespace(**actual))
    env = d17.shared_default_environment({"FT_DEV_D0": "bad", "FT_DEV_ROUTE_TRACE": "bad"})
    assert not any(key.startswith(("FT_DEV_", "FT_D3_")) for key in env)
    assert env["CUDA_VISIBLE_DEVICES"] == "0"


def test_cold_argv_reuses_cold_eq_and_rejects_other_rid(monkeypatch, tmp_path):
    monkeypatch.setattr(d17, "_load_protocol", lambda: type("P", (), {"PY": "venv/python", "SCR": Path("scripts")}))
    argv = d17.shared_cold_argv("E2-R041-gate-D17", tmp_path)
    assert argv == ["venv/python", str(Path("scripts") / "cold_eq.py"), "E2-R041-gate-D17-cold", str(tmp_path / "cold.json"), "32052", "128"]
    with pytest.raises(d17.D17GateError, match="assigned"):
        d17.shared_cold_argv("E2-R040", tmp_path)


def test_real_case_selection_is_exact_four(monkeypatch, tmp_path):
    rows = []
    for name in d17.R041_CASES:
        prefix, tail = [int(v) for v in name.replace("prefix-", "").replace("tail-", "").split("-")]
        rows.append({"name": name, "length": prefix, "tail": tail, "donor": [1] * (prefix + 1), "query": [1] * (prefix + tail)})
    # This test supplies only the selection surface because the shared selector
    # validates the authoritative 28-case byte-bound document itself.
    class Selector:
        @staticmethod
        def load_realinput28(_): return {"cases": rows}
        @staticmethod
        def _cases(doc): return doc["cases"]
    class Loader:
        def exec_module(self, module): module.load_realinput28 = Selector.load_realinput28; module._cases = Selector._cases
    monkeypatch.setattr(d17.importlib.util, "spec_from_file_location", lambda *_: type("S", (), {"loader": Loader()})())
    monkeypatch.setattr(d17.importlib.util, "module_from_spec", lambda *_: type("M", (), {})())
    for row in rows:
        row["input_ids_sha256"] = "i-" + row["name"]; row["donor_input_ids_sha256"] = "d-" + row["name"]
    assert [row["name"] for row in d17.select_r041_cases(tmp_path / "inputs.json")] == list(d17.R041_CASES)


def _sealed(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    path.chmod(0o444)


def _manifest(directory, *paths):
    manifest = directory / "MANIFEST.sha256"
    manifest.write_text("".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in paths), encoding="utf-8")
    manifest.chmod(0o444)


def test_missing_accepted_t17_fails_closed(tmp_path):
    closure, review = tmp_path / "round.json", tmp_path / "review.json"
    _sealed(closure, {"schema": "ft_round/v2", "card": "T17", "verdict": "kept", "experimental": {"candidate_commit": d17.CONTROL_COMMIT}, "round_id": "E2-R034a"})
    _sealed(review, {"verdict": "PASS", "candidate_commit": d17.CONTROL_COMMIT, "rid": "E2-R034a"})
    _manifest(tmp_path, closure, review)
    tmp_path.chmod(0o555)
    with pytest.raises(d17.D17GateError):
        d17.verify_accepted_t17(closure, review)


def test_forged_28_case_summary_does_not_replace_raw_audit(monkeypatch, tmp_path):
    closure, review = tmp_path / "round.json", tmp_path / "review.json"
    audit = {"schema": "ft_t17_continuation_independent_audit/v1", "verdict": "kept_pending_independent_review",
             "candidate_commit": d17.CONTROL_COMMIT, "rid": "E2-R034a", "cases": [{"case": str(i)} for i in range(28)]}
    _sealed(review, audit)
    _sealed(closure, {"schema": "ft_round/v2", "card": "T17", "verdict": "kept", "closed_at": "2026-10-05", "retractions": [], "experimental": {"candidate_commit": d17.CONTROL_COMMIT},
                      "round_id": "E2-R034a", "results": audit, "independent_review_sha256": hashlib.sha256(review.read_bytes()).hexdigest()})
    _manifest(tmp_path, closure, review)
    tmp_path.chmod(0o555)
    called = []
    def require_actual_raw(directory, closed, saved):
        called.append(directory)
        raise d17.D17GateError('raw fixture is intentionally incomplete')
    monkeypatch.setattr(d17, '_recompute_closed_t17', require_actual_raw)
    with pytest.raises(d17.D17GateError, match='raw fixture'):
        d17.verify_accepted_t17(closure, review)
    assert called == [tmp_path]


def test_foreign_gpu_lock_fails_closed(tmp_path):
    lock = tmp_path / "gpu.lock"
    lock.write_text("owned elsewhere", encoding="utf-8")
    with pytest.raises(d17.D17GateError, match="foreign GPU lock"):
        d17.verify_no_foreign_gpu_lock(lock)


@pytest.mark.skipif(__import__('os').name == 'nt', reason='POSIX directory write-bit invariant')
def test_writable_t17_directory_rejected_before_auditor(tmp_path):
    closure, review = tmp_path/'round.json', tmp_path/'review.json'
    _sealed(closure, {});_sealed(review, {})
    assert tmp_path.stat().st_mode & 0o222
    with pytest.raises(d17.D17GateError, match='directory must be sealed'):
        d17.verify_accepted_t17(closure,review)


@pytest.fixture
def combined_t17(tmp_path):
    """Small evidence documents exercise reuse admission, never tensor parity."""
    directory = tmp_path/'E2-R038'
    directory.mkdir()
    source = tmp_path/'E2-R036'
    source.mkdir()
    def write(path, doc):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc), encoding='utf-8')
        return hashlib.sha256(path.read_bytes()).hexdigest()
    expected = [f'prefix-{p}-tail-{t}' for p in [8192,12416,12736,18944]
                for t in [65,4095,4096,4097,8191,8192,8193]]
    review = {'canonical_coverage': {'exact':True,'actual_positions':list(range(1,29)),
              'actual_case_names':expected}, 'r036_retained_cases':[], 'r038_recomputed_cases':[]}
    permit = {'schema':'ft_t17_retained_cases_review/v1','reuse_permitted':True,
              'source_rid':'E2-R036','target_candidate':d17.CONTROL_COMMIT,'computed_count':14,
              'source_round':str(source),'computed_cases':[],
              'admission_equivalence':{'changed_python_files':['python/freetoken/scheduler/dev_prefill_schedule.py']}}
    for position, name in enumerate(expected, 1):
        origin = source if position <= 14 else directory
        schedule = origin/'schedules'/name/'schedule.json'
        row = {'position':position,'case_path':str(origin/'cases'/(name+'.json')),
               'schedule_path':str(schedule),'schedule_sha256':write(schedule,{}),'input_ids_sha256':'1'*64}
        row['case_sha256'] = write(Path(row['case_path']),{'schedule':str(schedule),
                                   'evidence':{'requested_input_ids_sha256':row['input_ids_sha256']}})
        if position <= 14:
            review['r036_retained_cases'].append(row)
            permit['computed_cases'].append({'case':name,'case_doc_sha256':row['case_sha256'],
                 'schedule_sha256':row['schedule_sha256'],'input_ids_sha256':row['input_ids_sha256']})
        else:
            gate = {'state_handoff':{'roles':{r:True for r in d17.ROLES}},
                    'same_structure_reference':{k:{'tokens_equal':True,'text_equal':True,'first_token_fork':None}
                                                for k in ['repeat','warm_comparison']}}
            report = {'schema':'ft_r038_incremental_raw_recompute/v1','verdict':'PASS',
                      'case_sha256':row['case_sha256'],'guard_installed':True,'cuda_visible_devices':'',
                      'case':{'gate':gate}}
            row['report_sha256'] = write(directory/'independent_review'/(name+'.json'),report)
            review['r038_recomputed_cases'].append(row)
    review['r036_reuse_license_sha256'] = write(directory/'retained_review.json',permit)
    for key, filename in [('r037_closure_sha256','r037_closure_receipt.json'),
                          ('raw_input_sha256','real_inputs.json'),('r038_result_sha256','result.json')]:
        review[key] = write(directory/filename,{})
    review['candidate_binding'] = {'r038_input_provenance_sha256':write(directory/'input_provenance.json',{})}
    return directory, {'results':review}, review, write


def test_combined_reuse_checks_real_bindings_without_repeating_audit(combined_t17):
    directory, closed, review, _ = combined_t17
    d17._verify_reused_t17(directory,closed,review)


def test_combined_reuse_rejects_missing_case(combined_t17):
    directory, closed, review, _ = combined_t17
    review['r038_recomputed_cases'].pop()
    with pytest.raises(d17.D17GateError, match='ordered 14\\+14'):
        d17._verify_reused_t17(directory,closed,review)


def test_combined_reuse_rejects_revoked_permission(combined_t17):
    directory, closed, review, write = combined_t17
    path = directory/'retained_review.json'
    permit = json.loads(path.read_text())
    permit['reuse_permitted'] = False
    review['r036_reuse_license_sha256'] = write(path,permit)
    with pytest.raises(d17.D17GateError, match='permission differs'):
        d17._verify_reused_t17(directory,closed,review)


@pytest.mark.parametrize('kind',['state','tokens','text'])
def test_combined_reuse_rejects_nonpassing_raw_review(combined_t17,kind):
    directory, closed, review, write = combined_t17
    row = review['r038_recomputed_cases'][0]
    path = directory/'independent_review'/Path(row['case_path']).name
    report = json.loads(path.read_text())
    gate = report['case']['gate']
    if kind == 'state':
        gate['state_handoff']['roles'][d17.ROLES[0]] = False
    else:
        gate['same_structure_reference']['warm_comparison'][kind+'_equal'] = False
    row['report_sha256'] = write(path,report)
    with pytest.raises(d17.D17GateError, match='did not pass'):
        d17._verify_reused_t17(directory,closed,review)


def test_combined_reuse_rejects_changed_schedule(combined_t17):
    directory, closed, review, _ = combined_t17
    Path(review['r036_retained_cases'][0]['schedule_path']).write_text('{"changed":true}')
    with pytest.raises(d17.D17GateError, match='binding differs'):
        d17._verify_reused_t17(directory,closed,review)


def test_unpinned_combined_summary_cannot_authorize_r041(monkeypatch,tmp_path):
    directory = tmp_path/'E2-R038'
    directory.mkdir()
    review = directory/'combined_review.json'
    audit = {'schema':d17.COMBINED_T17_SCHEMA,'candidate_commit':d17.CONTROL_COMMIT,
             'verdict':'PASS_ALL_28_PENDING_CANONICAL_D04'}
    _sealed(review,audit)
    closure = directory/'round.json'
    _sealed(closure,{'schema':'ft_round/v2','card':'T17','verdict':'kept','round_id':'E2-R038',
                    'closed_at':'2026-10-06 17:00:00 CST','retractions':[],
                    'experimental':{'candidate_commit':d17.CONTROL_COMMIT},'results':audit,
                    'independent_review_sha256':hashlib.sha256(review.read_bytes()).hexdigest()})
    _manifest(directory,review)
    directory.chmod(0o555)
    monkeypatch.setattr(d17,'_recompute_closed_t17',lambda *_:pytest.fail('unpinned evidence reached raw verifier'))
    with pytest.raises(d17.D17GateError,match='external acceptance pins'):
        d17.verify_accepted_t17(closure,review)
