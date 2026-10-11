import importlib.util
import json
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location("d17_gpu", Path(__file__).parents[1] / "d17_gpu_gate_runner.py")
m = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(m)


def context_inputs():
    retained = Path(__file__).parents[1] / 'realinput_28.json'
    if retained.exists():
        assert hashlib.sha256(retained.read_bytes()).hexdigest() == '90015a737cdc53f9c71e1f32cf1856bd0de0560362a31b2c91cac36d57806be0'
        return json.loads(retained.read_bytes())
    selector = m._load('d17_test_real_selection', m.HERE / 't17_continuation_selection.py')
    rows = []
    for length in selector.BOUNDARIES:
        for tail in selector.TAILS:
            donor, query = [3] * (length + 1), [3] * (length + tail)
            rows.append({'name': f'prefix-{length}-tail-{tail}', 'length': length, 'tail': tail,
                         'donor': donor, 'query': query, 'expected_ngram': query[length-2:length],
                         'donor_input_ids_sha256': selector._token_sha(donor), 'input_ids_sha256': selector._token_sha(query)})
    return {'cases': rows}


def test_execution_context_derived_from_byte_bound_query():
    document = context_inputs()
    for row in document['cases']:
        row.pop('context', None); row.pop('expected_ngram', None)
    selected = m.execution_cases(document)
    assert len(selected) == 4
    assert all(row['context'] == row['query'][row['length']-2:row['length']] for row in selected)


@pytest.mark.parametrize('field', ['context', 'expected_ngram'])
def test_execution_rejects_context_decoupled_from_real_query(field):
    document = context_inputs()
    row = next(row for row in document['cases'] if row['name'] == m.case_gate.R041_CASES[0])
    row[field] = [row['query'][row['length']-2] + 1, row['query'][row['length']-1]]
    with pytest.raises(m.D17ExecutionError, match='actual query'):
        m.execution_cases(document)


def test_rebound_restores_retained_module_globals(tmp_path):
    helper = SimpleNamespace(CANDIDATE="old")
    gpu = SimpleNamespace(WT=Path("old-wt"), helper=helper)
    with m.rebound(gpu, tmp_path, "new"):
        assert gpu.WT == tmp_path and helper.CANDIDATE == "new"
    assert gpu.WT == Path("old-wt") and helper.CANDIDATE == "old"


def test_warm_service_archives_birth_before_requests_and_rejects_restart(monkeypatch, tmp_path):
    identity = {"pid": 21, "start_ticks": 33, "execution_id": "21:33"}
    arm = tmp_path / "arm"; arm.mkdir()
    for name in ("SERVE_CMD.txt", "compiled_extensions.json", "environment.json"):
        (arm / name).write_text("fixture")
    gpu = SimpleNamespace(WT=tmp_path, helper=SimpleNamespace(CANDIDATE="old"))
    calls = []
    class Base:
        def service(self, label, operation, **kwargs): return operation(arm)
        def request(self, *args):
            assert json.loads((arm / "owned_process.json").read_text()) == identity
            calls.append(args[1])
    raw = SimpleNamespace(read_warm=lambda *args, **kwargs: {"warm": {}})
    monkeypatch.setattr(m, "_identity", lambda _: identity)
    case = {"donor": [1], "query": [1, 2], "length": 1}
    result = m.warm_service(gpu=gpu, artifacts=None, raw=raw, base=Base(), worktree=tmp_path,
                            commit="new", label="warm", case=case)
    assert calls == ["donor", "hit"] and result["process_identity"] == identity
    (arm / "owned_process.json").unlink()
    identities = iter([identity, {**identity, "start_ticks": 34, "execution_id": "21:34"}])
    monkeypatch.setattr(m, "_identity", lambda _: next(identities))
    with pytest.raises(m.D17ExecutionError, match="birth identity changed"):
        m.warm_service(gpu=gpu, artifacts=None, raw=raw, base=Base(), worktree=tmp_path,
                       commit="new", label="warm", case=case)


def test_compare_warm_requires_ids_text_and_all_four_role_bytes(monkeypatch, tmp_path):
    dump = tmp_path / "dump"; dump.mkdir()
    roles = {}
    for name in m.ROLES:
        path = dump / name; path.write_bytes(name.encode()); roles[name] = {"resume": {"file": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}}
    class Art:
        @staticmethod
        def load_tensor(path): return path.read_bytes()
        @staticmethod
        def bit_equal(left, right): return left == right
    left = {"warm": {"token_ids": [1] * 128, "text": "same", "input_ids_sha256": "ids"}, "arm": str(tmp_path), "restore_roles": roles, "coordinate": 8192, "process_identity": {"pid": 1}}
    right = {"warm": {"token_ids": [1] * 128, "text": "same", "input_ids_sha256": "ids"}, "arm": str(tmp_path), "restore_roles": roles, "coordinate": 8192, "process_identity": {"pid": 2}}
    assert m.compare_warm(Art, left, right)["passed"] is True
    right["warm"]["text"] = "different"
    assert m.compare_warm(Art, left, right)["passed"] is False


def test_execute_requires_exact_four_before_lock():
    options = SimpleNamespace(run=True, directory=Path("never-created"))
    gpu = SimpleNamespace(Run=lambda *_: pytest.fail("must not allocate service/lock"))
    with pytest.raises(m.D17ExecutionError, match="exact four"):
        m.execute(options, protocol=None, gpu=gpu, artifacts=None, raw=None, cases=[])


def test_dry_execution_never_constructs_service():
    options = SimpleNamespace(run=False)
    assert m.execute(options, protocol=None, gpu=None, artifacts=None, raw=None, cases=[])["gpu_started"] is False


def test_r041_run_requires_exact_named_candidate_tag(monkeypatch, tmp_path):
    commit = "2" * 40
    with pytest.raises(m.D17ExecutionError, match="tag required"):
        m.verify_candidate_tag(None, tmp_path, commit)
    monkeypatch.setattr(m.subprocess, "check_output", lambda *args, **kwargs: "3" * 40 + "\n")
    with pytest.raises(m.D17ExecutionError, match="another candidate"):
        m.verify_candidate_tag("E2-base.1@" + commit[:7], tmp_path, commit)
    monkeypatch.setattr(m.subprocess, "check_output", lambda *args, **kwargs: commit + "\n")
    assert m.verify_candidate_tag("E2-base.1@" + commit[:7], tmp_path, commit).endswith(commit[:7])


def test_execution_admission_rejects_arbitrary_pass_flags(tmp_path):
    stage, review = tmp_path / "stage.json", tmp_path / "review.json"
    stage.write_text(json.dumps({"verdict": "PASS", "runtime_lifecycle_verified": True}), encoding="utf-8")
    review.write_text(json.dumps({"verdict": "PASS", "stage_report_sha256": hashlib.sha256(stage.read_bytes()).hexdigest()}), encoding="utf-8")
    stage.chmod(0o444); review.chmod(0o444)
    with pytest.raises(ValueError, match="own CPU package"):
        m.verify_execution_admission(stage, review)


def test_execution_admission_resolves_stage_report_and_preserves_review_pin(monkeypatch, tmp_path):
    calls = []
    def verify(report, review, digest):
        calls.append((report, review, digest))
        return {"source_execution_ready": True, "model_admitted": False}
    monkeypatch.setattr(m, '_load', lambda name, path: SimpleNamespace(verify=verify))
    stage = tmp_path / 'stage'
    review = tmp_path / 'external-review.json'
    result = m.verify_execution_admission(stage, review, 'a' * 64)
    assert calls == [(stage / 'source_tools' / 'cpu_validation.json', review, 'a' * 64)]
    assert result == {"source_execution_ready": True, "model_admitted": False}


def test_execute_uses_one_common_cold_path_and_two_warm_services_per_case(monkeypatch, tmp_path):
    calls = []
    class Owner:
        def __init__(self, options):
            self.directory = options.directory; self.token = "token"; self.lock_inode = 7; self.proc = None
        def lock_take(self): calls.append("lock")
        def lock_release(self): calls.append("release")
        def stop(self): calls.append("stop")
        def set_status(self, **value): calls.append(value["state"])
    gpu = SimpleNamespace(Run=Owner)
    monkeypatch.setattr(m, "_make_owner", lambda gpu, options: gpu.Run(options))
    monkeypatch.setattr(m, "common_cold_compare", lambda *_: calls.append("cold") or {"verified": True})
    def warm(**kwargs):
        calls.append((kwargs["label"], kwargs["commit"]))
        return {"warm": {"token_ids": [1] * 128, "text": "same"}, "arm": str(tmp_path),
                "restore_roles": {role: {"resume": {"file": role}} for role in m.ROLES}}
    monkeypatch.setattr(m, "warm_service", warm)
    monkeypatch.setattr(m, "compare_warm", lambda *_: {"passed": True})
    cases = [{"name": name} for name in m.case_gate.R041_CASES]
    options = SimpleNamespace(run=True, rid="E2-R041-gate-D17", batch=64, directory=tmp_path / "round",
                              control_worktree=tmp_path, candidate_worktree=tmp_path)
    result = m.execute(options, protocol=object(), gpu=gpu, artifacts=object(), raw=object(), cases=cases)
    assert result["verdict"] == "measurements_pass_pending_independent_review"
    assert calls.count("cold") == 1
    assert len([row for row in calls if isinstance(row, tuple)]) == 8
    assert {row[1] for row in calls if isinstance(row, tuple)} == {m.CONTROL, m.CANDIDATE}
    assert calls[:2] == ["lock", "running"] and calls[-2:] == ["stop", "release"]
    gate = json.loads((options.directory/'gate_batch64.json').read_text())
    assert gate['parent_commit'] == m.COLD_CONTROL and gate['new_commit'] == m.CANDIDATE
    assert gate['warm_control_commit'] == m.CONTROL and gate['admitted'] is False
    assert gate['proposed_verdict'] == 'kept'
    assert gate['result_sha256'] == hashlib.sha256((options.directory/'result.json').read_bytes()).hexdigest()
    assert not (options.directory/'review_batch64.json').exists()


@pytest.mark.parametrize('different_text', [False, True])
def test_common_cold_uses_same_owner_and_actual_default_checks(tmp_path, different_text):
    import runpy
    protocol = runpy.run_path(str(Path(__file__).parents[1] / 't16_full_tail_base_runner.py'))
    calls = []
    class Owner:
        allowed = {}
        def parser(self, path):
            return {'model_path': 'model', 'server_port': '8095', 'special_token_ckpt': 'true',
                    '_unique_suffix': "'.pid=1'" if 'CONTROL' in path else "'.pid=2'"}
        def run_arm(self, name, wt, commit, d0, **kwargs):
            calls.append((name, d0, kwargs, commit, gpu.WT, gpu.helper.CANDIDATE))
            arm=tmp_path/name;arm.mkdir();(arm/'prefill_seq.txt').write_text('same')
            payload={'text':'different' if different_text and 'CANDIDATE' in name else 'same',
                     'events':1,'record':{'built_tokens':32052,'cached_tokens':0,'prompt_tokens':32052,
                     'completion_tokens':128,'ttft_s':1,'cold_id':'same-id'}}
            (arm/'det.json').write_text(json.dumps(payload))
            return arm
    gpu=SimpleNamespace(WT=Path('old'),helper=SimpleNamespace(CANDIDATE='old'),protocol=protocol)
    if different_text:
        assert m.common_cold_compare(Owner(),gpu,Path('control'),Path('candidate'))['passed'] is False
    else:
        result=m.common_cold_compare(Owner(),gpu,Path('control'),Path('candidate'))
        assert result['passed'] is True and result['sequence']=='SAME'
    assert len(calls)==2 and all(row[1] is False and row[2]['layer_major'] is True for row in calls)
    assert calls[0][3:] == (m.COLD_CONTROL, Path('control'), m.COLD_CONTROL)
    assert calls[1][3:] == (m.CANDIDATE, Path('candidate'), m.CANDIDATE)
    assert gpu.WT == Path('old') and gpu.helper.CANDIDATE == 'old'
    assert 'compare_to' not in calls[1][2]  # adapter classifies actual text mismatch
