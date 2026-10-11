import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("t17_continuation_runner", HERE / "t17_continuation_runner.py")
runner = importlib.util.module_from_spec(SPEC); assert SPEC.loader; SPEC.loader.exec_module(runner)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value)); return path


def test_execution_archive_requires_template_and_bound_bytes(tmp_path, monkeypatch):
    source = tmp_path / "batchNN_T17.sh"
    source.write_bytes(b"#!/bin/bash\n")
    write(tmp_path / "cpu_validation.json", {"verdict": "PASS", "files": {source.name: runner.sha(source)}})
    monkeypatch.setattr(runner, "HERE", tmp_path)
    monkeypatch.setattr(runner, "frozen", lambda _path: None)
    monkeypatch.delenv("FT_T17_BATCH_TEMPLATE", raising=False)
    with pytest.raises(ValueError, match="before GPU lock"):
        runner.verify_execution_archive()
    monkeypatch.setenv("FT_T17_BATCH_TEMPLATE", str(source))
    assert runner.verify_execution_archive()["batch_sha256"] == runner.sha(source)
    source.write_bytes(b"changed")
    with pytest.raises(ValueError, match="source differs"):
        runner.verify_execution_archive()


def test_preflight_cannot_be_combined_with_run():
    with pytest.raises(SystemExit) as error:
        runner.main(["--rid", "E2-R033", "--batch", "1", "--inputs", "inputs.json",
                     "--closure-binding", "binding.json", "--directory", "/data2/_shared/runs/ft_rounds/E2-R033",
                     "--resource-preflight", "--run"])
    assert error.value.code == 2


def test_unbound_token_matrix_is_rejected_before_structural_validation(tmp_path, monkeypatch):
    path = write(tmp_path / "real_inputs.json", {"candidate_commit": runner.CANDIDATE, "cases": []})
    monkeypatch.setattr(runner, "frozen", lambda _path: None)
    with pytest.raises(ValueError, match="target-tokenizer"):
        runner.verify_input_provenance(path)


def test_rejects_unkept_or_unbound_r032_before_service(tmp_path, monkeypatch):
    rounds, directory = tmp_path / "rounds", tmp_path / "rounds" / runner.T16_RID
    directory.mkdir(parents=True)
    for name in ("round.json", "gate_batch60.json", "review_batch60.json", "batch.sh", "round_history"):
        (directory / name).write_text("{}")
    (directory / "MANIFEST.sha256").write_text("")
    binding = write(tmp_path / "closure_binding.json", {})
    with pytest.raises(ValueError, match="kept"):
        runner.verify_prerequisite(rounds, binding)


def test_positive_sealed_r032_fixture_uses_a_history_directory(tmp_path, monkeypatch):
    rounds, directory = tmp_path / "rounds", tmp_path / "rounds" / runner.T16_RID
    directory.mkdir(parents=True); history = directory / "round_history"; history.mkdir()
    (history / "0001.json").write_text('{"new":"kept"}')
    gate = {"proposed_verdict": "kept", "parent_commit": runner.PARENT, "new_commit": runner.CANDIDATE}
    review = {"verdict": "PASS", "rid": runner.T16_RID, "batch": runner.T16_BATCH}
    write(directory / "gate_batch60.json", gate); write(directory / "review_batch60.json", review)
    (directory / "batch.sh").write_text("#!/bin/sh\n")
    review_sha = runner.sha(directory / "review_batch60.json")
    round_json = {"round_id": runner.T16_RID, "card": "T16", "verdict": "kept", "closed_at": "now",
                  "retractions": [], "base": {"commit": runner.PARENT},
                  "experimental": {"candidate_commit": runner.CANDIDATE}, "independent_review_sha256": review_sha}
    write(directory / "round.json", round_json)
    declared = ["gate_batch60.json", "review_batch60.json", "batch.sh"]
    (directory / "MANIFEST.sha256").write_text("".join(f"{runner.sha(directory / name)}  ./{name}\n" for name in declared))
    binding = {"round": runner.T16_RID, "batch": runner.T16_BATCH, "parent_commit": runner.PARENT,
               "candidate_commit": runner.CANDIDATE, "round_sha256": runner.sha(directory / "round.json"),
               "gate_sha256": runner.sha(directory / "gate_batch60.json"), "review_sha256": review_sha,
               "manifest_sha256": runner.sha(directory / "MANIFEST.sha256")}
    path = write(tmp_path / "closure_binding.json", binding)
    for item in (directory / "round.json", directory / "gate_batch60.json", directory / "review_batch60.json",
                 directory / "batch.sh", directory / "MANIFEST.sha256", history / "0001.json", path): item.chmod(0o444)
    history.chmod(0o555); directory.chmod(0o555); path.chmod(0o444)
    monkeypatch.setattr(runner, "d04_check", lambda actual: actual == directory or (_ for _ in ()).throw(AssertionError()))
    result = runner.verify_prerequisite(rounds, path)
    assert result["directory"] == str(directory) and result["review_sha256"] == review_sha


def test_frozen_closure_binding_rejects_mutation(tmp_path):
    path = write(tmp_path / "closure_binding.json", {"round": runner.T16_RID})
    with pytest.raises(ValueError, match="frozen"):
        runner.frozen(path)
    path.chmod(0o444)
    runner.frozen(path)
    path.chmod(0o644); path.write_text('{"round":"changed"}')
    with pytest.raises(ValueError, match="frozen"):
        runner.frozen(path)


def test_input_matrix_requires_all_28_cases_and_token_sha(tmp_path, monkeypatch):
    class Cases:
        @staticmethod
        def continuation_matrix():
            return [{"name": f"p{boundary}-t{tail}", "boundary": boundary, "tail": tail}
                    for boundary in (2, 3, 4, 5) for tail in range(1, 8)]
    class Gate:
        @staticmethod
        def token_sha(ids): return hashlib.sha256(bytes(ids)).hexdigest()
    monkeypatch.setattr(runner, "_suite_modules", lambda _wt: (Cases, Gate, object()))
    good = {"candidate_commit": runner.CANDIDATE, "cases": [
        {"name": row["name"], "length": row["boundary"], "tail": row["tail"],
         "donor": list(range(row["boundary"] + 1)),
         "query": list(range(row["boundary"] + row["tail"])),
         "expected_ngram": list(range(row["boundary"] - 2, row["boundary"])), "trace_index": index,
         "input_ids_sha256": Gate.token_sha(list(range(row["boundary"] + row["tail"]))),
         "donor_input_ids_sha256": Gate.token_sha(list(range(row["boundary"] + 1))) }
        for index, row in enumerate(Cases.continuation_matrix())]}
    path = write(tmp_path / "inputs.json", good); path.chmod(0o444)
    checked = runner.load_inputs(path)
    assert len(checked) == 28 and checked[0]["context"] == [0, 1]
    path.chmod(0o644); good["cases"][0]["input_ids_sha256"] = "wrong"; write(path, good); path.chmod(0o444)
    with pytest.raises(ValueError, match="token SHA"):
        runner.load_inputs(path)
    path.chmod(0o644); good["cases"][0]["input_ids_sha256"] = Gate.token_sha(good["cases"][0]["query"])
    good["cases"][0]["expected_ngram"] = [99, 100]; write(path, good); path.chmod(0o444)
    with pytest.raises(ValueError, match="target-tokenizer IDs"):
        runner.load_inputs(path)


def test_xwrite_is_exclusive(tmp_path):
    path = tmp_path / "result.json"; runner.xwrite(path, {"ok": True})
    with pytest.raises(FileExistsError): runner.xwrite(path, {"ok": False})


def test_suite_modules_are_loaded_only_from_staged_tools(tmp_path, monkeypatch):
    tools = tmp_path / "equiv_suite"; tools.mkdir()
    for name, source in {"__init__.py": "", "cases.py": "def continuation_matrix(): return []\n",
                         "gate.py": "", "continuation.py": ""}.items():
        (tools / name).write_text(source)
    monkeypatch.setattr(runner, "TOOLS", tools)
    cases, gate, continuation = runner._suite_modules()
    assert cases.__file__.startswith(str(tools)) and gate.__file__.startswith(str(tools))
    assert continuation.__file__.startswith(str(tools))


def test_fail_stop_keeps_missing_diagnostic_and_does_not_continue(tmp_path):
    calls = []
    class Base:
        directory = tmp_path / "round"; proc = None
        def lock_take(self): calls.append("lock")
        def lock_release(self): calls.append("release")
        def stop(self): calls.append("stop"); self.proc = None
        def set_status(self, **values): calls.append(values["state"])
    class Gpu:
        WT = None; helper = SimpleNamespace(PARENT=None, CANDIDATE=None, T16_RID=None, T16_BATCH=None)
        Run = lambda self, options: Base()
    class Continuation:
        @staticmethod
        def run_case(resources, case):
            calls.append(case["name"]); return {"result": {"verdict": "not_met"}, "stopped": "not_met"}
    options = SimpleNamespace(rid="E2-R033", batch=1, directory=Base.directory)
    subject = runner.Run(options, gpu=Gpu(), artifacts=object(), continuation=Continuation)
    result = subject.execute([{"name": "first"}, {"name": "second"}], {"round": "R032"}, run=True)
    assert result["verdict"] == "failed_harness" and result["diagnostic"]["verdict"] == "diagnostic_missing"
    assert result["measurement_verdict"] == "not_met"
    assert calls == ["lock", "running", "first", "failed", "stop", "release"]


def test_directory_creation_failure_releases_the_owned_lock(tmp_path, monkeypatch):
    calls = []
    class Base:
        directory = tmp_path / "round"; proc = None
        def lock_take(self): calls.append("lock")
        def lock_release(self): calls.append("release")
        def stop(self): calls.append("stop")
        def set_status(self, **_values): calls.append("status")
    class Gpu:
        WT = None; helper = SimpleNamespace(PARENT=None, CANDIDATE=None, T16_RID=None, T16_BATCH=None)
        Run = lambda self, options: Base()
    original = Path.mkdir
    def fail_target(path, *args, **kwargs):
        if path == Base.directory: raise OSError("disk full")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "mkdir", fail_target)
    subject = runner.Run(SimpleNamespace(rid="E2-R033", batch=1, directory=Base.directory), gpu=Gpu(), artifacts=object(), continuation=object())
    with pytest.raises(OSError, match="disk full"):
        subject.execute([], {}, run=True)
    assert calls == ["lock", "stop", "release"]


@pytest.mark.parametrize('failure', [False, True])
def test_t20_followup_remains_inside_original_lock_and_failure_cleanup(tmp_path, failure):
    calls = []
    class Base:
        directory = tmp_path/'round'; proc = None
        def lock_take(self): calls.append('lock')
        def lock_release(self): calls.append('release')
        def stop(self): calls.append('stop'); self.proc = None
        def set_status(self, **values): calls.append(values['state'])
    class Gpu:
        WT = None; helper = SimpleNamespace(PARENT=None, CANDIDATE=None, T16_RID=None, T16_BATCH=None)
        Run = lambda self, options: Base()
    def followup(base):
        assert 'lock' in calls and 'release' not in calls
        assert not (base.directory/'result.json').exists()
        calls.append('measure')
        if failure: raise RuntimeError('quality failure')
        return {'admitted': False, 'all_sections_measured': True}
    options = SimpleNamespace(rid='E2-R040', gate='T20', batch=1, directory=Base.directory, after_cases=followup)
    subject = runner.Run(options, gpu=Gpu(), artifacts=object(), continuation=object())
    if failure:
        with pytest.raises(RuntimeError, match='quality failure'):
            subject.execute([], {}, run=True)
        assert (Base.directory/'failed_harness.json').exists() and not (Base.directory/'result.json').exists()
        assert calls == ['lock', 'running', 'measure', 'failed', 'stop', 'release']
    else:
        result = subject.execute([], {}, run=True)
        assert result['t20_measurements']['all_sections_measured']
        assert calls == ['lock', 'running', 'measure', 'complete_measurements_pending_independent_review', 'stop', 'release']


def test_t17_rejects_t20_followup_before_lock(tmp_path):
    gpu = SimpleNamespace(WT=None, helper=SimpleNamespace(PARENT=None, CANDIDATE=None, T16_RID=None, T16_BATCH=None),
        Run=lambda options: SimpleNamespace(directory=tmp_path/'round', proc=None))
    subject = runner.Run(SimpleNamespace(rid='E2-R038', gate='T17', batch=1, directory=tmp_path/'round',
        after_cases=lambda base: pytest.fail('must not execute')), gpu=gpu, artifacts=object(), continuation=object())
    with pytest.raises(ValueError, match='actual T20 batch'):
        subject.execute([], {}, run=True)
    assert not (tmp_path/'round').exists()


@pytest.mark.parametrize('fault', ['none', 'reader', 'content'])
def test_full_t20_component_covers_all_sections_and_rejects_unverified_envelope(tmp_path, monkeypatch, fault):
    from types import ModuleType
    batches = HERE.parent/'plan/01_测试与调研/batches'
    monkeypatch.syspath_prepend(str(batches))
    spec = importlib.util.spec_from_file_location('full_t20_component_test', batches/'t20_measurements.py')
    component = importlib.util.module_from_spec(spec); spec.loader.exec_module(component)
    calls = []
    native = ModuleType('d16_native_process_collection')
    native.verify_source_review = lambda *args: calls.append('source')
    def collect(owner, inputs, *, slots, interleave, **kwargs):
        calls.append('interleave' if interleave else 'batch'+str(slots))
        root = tmp_path/('interleave' if interleave else 'batch'+str(slots)); root.mkdir()
        assert all(len(ids) == 512 for ids in (inputs[:1] if interleave else inputs))
        if interleave: assert len(inputs[1]) > 4096
        return {'root': str(root), 'evidence_map': str(root/'evidence.json'), 'evidence_map_sha256': 'a'*64}
    native.collect_native_processes = collect
    native.collect_parking_processes = lambda *a, **k: calls.append('parking') or {'admitted': False}
    native.collect_cache_processes = lambda *a, **k: calls.append('cache') or {'admitted': False}
    monkeypatch.setitem(sys.modules, 'd16_native_process_collection', native)
    package = ModuleType('equiv_suite'); package.__path__ = []
    reader = ModuleType('equiv_suite.native_workloads')
    reader.read_native_workloads = lambda *a, **k: {'verdict': 'unverified' if fault == 'reader'
        else 'batch_envelope_diagnostic', 'admitted': False}
    monkeypatch.setitem(sys.modules, 'equiv_suite', package)
    monkeypatch.setitem(sys.modules, 'equiv_suite.native_workloads', reader)
    monkeypatch.setattr(component, 'run_baseline_measurements', lambda *a, **k:
        calls.append('baseline') or {'admitted': False})
    cases = [{'name': 'case'+str(index), 'input_ids_sha256': 'a'*64,
              'query': list(range(8193)) if fault == 'content' else [index]*8193} for index in range(4)]
    owner = SimpleNamespace(directory=tmp_path, options=SimpleNamespace(rid='E2-R040', gate='T20', run=True))
    kwargs = dict(candidate_commit='a'*40, realinputs={'cases': cases}, d16_wrapper='fixture',
                  d16_source_review='fixture', d16_source_review_sha256='fixture')
    if fault == 'content':
        with pytest.raises(ValueError, match='four distinct'):
            component.run_full_measurements(owner, **kwargs)
        assert calls == ['source']
    elif fault == 'reader':
        with pytest.raises(RuntimeError, match='unverified'):
            component.run_full_measurements(owner, **kwargs)
        assert not (tmp_path/'full_t20_measurements.json').exists()
    else:
        result = component.run_full_measurements(owner, **kwargs)
        assert result['all_sections_measured'] and result['independent_review_pending'] and result['admitted'] is False
        assert set(result['d16']) == {'batch2', 'batch4', 'parking', 'cache', 'cold', 'interleave'}
        assert calls == ['source', 'baseline', 'batch2', 'batch4', 'parking', 'cache', 'interleave']
