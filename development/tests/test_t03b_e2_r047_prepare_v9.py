import importlib.util
import json
import os
import py_compile
import subprocess
import sys
from types import SimpleNamespace

import pytest
from pathlib import Path


MODULE = Path(__file__).parents[1] / "t03b_e2_r047_prepare_v9.py"
spec = importlib.util.spec_from_file_location("t03b_prepare", MODULE)
probe = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(probe)


def test_positive_requires_close_and_decode():
    assert probe.classify_positive({"choices": [{"message": {"content": "<think>a</think>b"}}]})["classification"] == "hit"
    assert probe.classify_positive({"choices": [{"message": {"content": "<think>a</think>"}}]})["classification"] == "missed"


def test_retained_followup_binds_actual_prior_content():
    rows = probe.retained_followup([{"role": "user", "content": "q"}], {"choices": [{"message": {"content": "<think>x</think>y"}}]})
    assert rows[-2]["content"] == "<think>x</think>y"


def test_sse_ttft_skips_role_empty_and_usage(monkeypatch):
    ticks = iter((10.1, 10.4))
    lines = [
        'data: {"choices":[{"delta":{"role":"assistant"}}]}\n',
        'data: {"choices":[{"delta":{"content":""}}]}\n',
        'data: {"choices":[{"delta":{"reasoning_content":"think"}}]}\n',
        'data: {"choices":[],"usage":{"prompt_tokens_details":{"cached_tokens":12}}}\n',
    ]
    events, ttft, final = probe.parse_sse_events(lines, started=10.0, clock=lambda: next(ticks))
    assert len(events) == 4 and abs(ttft - 0.1) < 1e-9
    assert final["usage"]["prompt_tokens_details"]["cached_tokens"] == 12


def test_snapshot_count_is_final_log_evidence(tmp_path):
    log = tmp_path / "serve.log"
    log.write_text("D0 anchor_snapshots_taken=4\n")
    assert probe.write_snapshot_count(tmp_path) == 4
    assert json.loads((tmp_path / "snapshot_count.json").read_text())["actual_successful_snapshots"] == 4


def test_missing_or_multiple_snapshot_evidence_is_rejected(tmp_path):
    log = tmp_path / "serve.log"
    log.write_text("no D0 final count\n")
    try:
        probe.snapshot_count(log)
    except ValueError:
        pass
    else:
        raise AssertionError("missing D0 counter accepted")
    log.write_text("D0 anchor_snapshots_taken=0\nD0 anchor_snapshots_taken=1\n")
    try:
        probe.snapshot_count(log)
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate D0 counter accepted")


def test_service_flags_enable_snapshot_preconditions_and_dynamic_port():
    argv = probe.serve_argv(15000)
    assert argv[argv.index("--mamba-host-slots") + 1] == "0"
    assert "--enable-special-token-ckpt" in argv and "--prefill-layer-major" in argv
    assert "8095" not in argv
    assert probe.packet(Path("/candidate"))["fixture_port"] == "allocated only by --run after the admission gates"

def test_file_dry_writes_six_plans_without_lock_or_service(monkeypatch,tmp_path):
    executor=tmp_path/'executor.py';executor.write_text('# executor')
    review=tmp_path/'review.json';review.write_text('{}')
    monkeypatch.setattr(probe,'FORMAL_PARENT',tmp_path/'formal');(tmp_path/'formal').mkdir()
    monkeypatch.setattr(probe,'checked_worktree',lambda _:{})
    monkeypatch.setattr(probe,'require_predecessors',lambda:{})
    monkeypatch.setattr(probe,'validate_review_receipt',lambda *_:{})
    monkeypatch.setattr(probe,'source_bindings',lambda:{'actual':'sha'})
    monkeypatch.setattr(probe.os,'getuid',lambda:1000,raising=False)
    monkeypatch.setattr(probe.subprocess,'Popen',lambda *_a,**_k:pytest.fail('dry started a service'))
    dry=tmp_path/'formal'/'.dryrun_R047_cpu'
    receipt=probe.file_dry_run(dry,executor,review,tmp_path/'wt',tmp_path/'formal')
    assert receipt['gpu_lock_taken'] is False and len(receipt['arms'])==6
    assert all(row['port_pair']['tcpstore']==row['port_pair']['api']+1 for row in receipt['arms'])
    assert len({row['port_pair']['api'] for row in receipt['arms']})==1
    assert probe.require_file_dry_receipt(dry/'dry_run_receipt.json')['sha256']==probe.sha256_file(dry/'dry_run_receipt.json')
    for row in receipt['arms']:
        plan=json.loads((dry/row['arm']/'serve_argv.json').read_text())
        assert Path(plan['argv'][2]).is_file() and plan['argv'][3]=='serve'
        assert plan['environment']['FT_DEV_D0']=='1'
        assert not {'FT_DEV_ROUTE_TRACE','FT_DEV_PAUSE_ENDPOINT'} & plan['environment'].keys()
    (dry/'dry_run_receipt.json').chmod(0o600)


def test_all_predecessors_use_shared_closed_round_helper():
    calls = []
    def require_round(rid, verdict):
        calls.append((rid, verdict))
        return Path("/closed") / rid / "round.json"
    result = probe.require_predecessors(require_round)
    assert calls == list(probe.FORMAL_PREDECESSORS)
    assert result[probe.FORMAL_PREDECESSORS[0][0]].endswith("round.json")


def test_r047_requires_exact_r046d_measured_and_keeps_performance_ratio():
    assert ("E2-R046g", "measured") in probe.FORMAL_PREDECESSORS
    assert all(rid not in {"E2-R046a", "E2-R046b", "E2-R046c"} for rid, _ in probe.FORMAL_PREDECESSORS)
    argv = probe.serve_argv(15000)
    assert argv[argv.index("--memory-ratio") + 1] == "0.88"


@pytest.mark.parametrize("registered", [
    {"E2-R046a": "failed_harness"}, {"E2-R046c": "failed_harness"},
])
def test_r047_failed_a_cannot_substitute_for_r046d_measured(registered):
    calls = []
    def require_round(rid, verdict):
        calls.append((rid, verdict))
        if rid.startswith("E2-R046") and registered.get(rid) != verdict:
            raise RuntimeError(f"{rid} formal D04 verdict is not {verdict}")
        return Path("/closed") / rid / "round.json"
    with pytest.raises(RuntimeError, match="E2-R046g formal D04 verdict is not measured"):
        probe.require_predecessors(require_round)
    assert calls[-1] == ("E2-R046g", "measured")
    assert all(rid != "E2-R046a" for rid, _ in calls)

def test_unsealed_predecessor_rejects_before_batch_allocation(monkeypatch, tmp_path):
    monkeypatch.setattr(probe, "require_predecessors", lambda: (_ for _ in ()).throw(RuntimeError("R046 not sealed")))
    monkeypatch.setattr(probe.sys, "platform", "linux")
    monkeypatch.setattr(probe, "checked_worktree", lambda _: {})
    with pytest.raises(RuntimeError, match="R046 not sealed"):
        probe.controller_launch(tmp_path / "executor", tmp_path / "review", tmp_path, tmp_path)


def test_emit_binds_template_and_does_not_overwrite(tmp_path):
    emitted = probe.emit_review_executor(tmp_path / "r047_executor.py")
    text = emitted.read_text()
    assert "A_cut_on_p1" in text and "B_cut_off_p3" in text and "--review-receipt" in text
    try:
        probe.emit_review_executor(emitted)
    except RuntimeError:
        pass
    else:
        raise AssertionError("existing executor was overwritten")


def test_review_receipt_binds_fixed_sealed_review_and_pin(monkeypatch,tmp_path):
 executor=probe.emit_review_executor(tmp_path/'executor.py'); review_dir=tmp_path/'reviews/E2-R047-v2';review_dir.mkdir(parents=True)
 monkeypatch.setattr(probe,'REVIEW_DIR',review_dir);monkeypatch.setattr(probe,'FORMAL_PARENT',tmp_path/'formal')
 monkeypatch.setattr(probe,'source_bindings',lambda:{'actual':'sha'})
 monkeypatch.setattr(probe,'require_file_dry_receipt',lambda _: {'sha256':'dry_sha'})
 template=Path(os.environ.get('T03B_TEMPLATE_PATH',Path(probe.__file__).parents[1]/'plan/01_测试与调研/batches/batch29_E2-R008_python.sh'))
 review=review_dir/'review.json';review.write_text(json.dumps({'schema':'ft_t03b_r047_review/v2','rid':probe.RID,'candidate_commit':probe.CANDIDATE,'approved':True,'executor_sha256':probe.sha256_file(executor),'prepare_sha256':probe.sha256_file(Path(probe.__file__)),'template_sha256':probe.sha256_file(template),'input_sha256':probe.review_input_sha256(),'canonical_output_root':str(tmp_path/'formal'),'source_bindings':probe.source_bindings(),'file_dry_receipt':'dry','file_dry_receipt_sha256':'dry_sha'}))
 pin=review_dir/'pin.json';pin.write_text(json.dumps({'schema':'ft_t03b_r047_review_pin/v1','rid':probe.RID,'review_path':str(review),'review_sha256':probe.sha256_file(review),'prepare_sha256':probe.sha256_file(Path(probe.__file__))}))
 with pytest.raises(RuntimeError,match='fixed sealed'):
  probe._sealed_review_path(tmp_path/'forged.json')
 monkeypatch.setattr(probe,'_sealed_review_path',lambda path: None)
 assert probe.validate_review_receipt(review,executor)['approved'] is True
 pin.write_text('{}')
 with pytest.raises(RuntimeError,match='sealed review/pin') : probe.validate_review_receipt(review,executor)


def test_child_receipt_is_checked_before_gpu_lock_or_batch_assignment(monkeypatch, tmp_path):
    calls = []
    class Protocol:
        def require_child_receipt(self, *args, **kwargs):
            calls.append("receipt")
            raise RuntimeError("wrong receipt")
        def take_d07_gpu_lock(self, *args):
            calls.append("lock")
    monkeypatch.setattr(probe, "load_d07_protocol", lambda: Protocol())
    monkeypatch.setattr(probe.sys, "platform", "linux")
    with pytest.raises(RuntimeError, match="wrong receipt"):
        probe.child_execute(tmp_path / "executor.py", tmp_path / "review.json", tmp_path / "wt",
                            tmp_path / "out", 74, tmp_path / "launch.json")
    assert calls == ["receipt"]


def test_alive_owned_group_keeps_lock_on_failure(monkeypatch, tmp_path):
    released = []
    class Lifecycle:
        def owned_group_alive(self, pid):
            return True
        def stop_owned_process(self, process):
            raise RuntimeError("cleanup failure")
    class Protocol:
        def require_child_receipt(self, *args, **kwargs):
            return {}
        def take_d07_gpu_lock(self, *args):
            return {"owner": probe.RID}
        def require_gpu_idle(self):
            return [0]
        def release_d07_gpu_lock(self, owner):
            released.append(owner)
        def load_owned_lifecycle(self):
            return Lifecycle()
    process = SimpleNamespace(pid=321)
    monkeypatch.setattr(probe, "load_d07_protocol", lambda: Protocol())
    monkeypatch.setattr(probe.sys, "platform", "linux")
    monkeypatch.setattr(probe, "FORMAL_PARENT", tmp_path)
    monkeypatch.setattr(probe, "checked_worktree", lambda _wt: {})
    monkeypatch.setattr(probe, "require_predecessors", lambda: {})
    monkeypatch.setattr(probe, "validate_review_receipt", lambda *_args: {})
    monkeypatch.setattr(probe, "packet", lambda _wt: {})
    monkeypatch.setattr(probe, "dynamic_fixture_port", lambda: 17321)
    monkeypatch.setattr(probe, "start_server", lambda *_args, **_kwargs: process)
    monkeypatch.setattr(probe, "stream_request", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("request failure")))
    executor, review = tmp_path / "executor.py", tmp_path / "review.json"
    executor.write_text("# fixture executor\n")
    review.write_text("{}")
    with pytest.raises(RuntimeError, match="cleanup failure"):
        probe.child_execute(executor, review, tmp_path / "wt",
                            tmp_path, 74, tmp_path / "launch.json")
    assert released == []
    cleanup = next(tmp_path.glob("E2-R047/owned_cleanup.json"))
    assert json.loads(cleanup.read_text())["lock_released"] is False


def test_args_diff_rejects_dirty_control(tmp_path):
    arms = ("A_cut_on_p1", "B_cut_off_p1", "A_cut_on_p2", "B_cut_off_p2", "A_cut_on_p3", "B_cut_off_p3")
    values = {}
    for arm in arms:
        path = tmp_path / arm / "serve.log"
        path.parent.mkdir()
        path.write_text("x")
        values[str(path)] = {"model_path": "'model'", "server_port": "17777", "special_token_ckpt": "True",
                             "_unique_suffix": repr(".pid=" + str(100 + len(values))),
                             "prefill_anchor_cut": "True" if arm.startswith("A") else "False"}
    assert len(probe.verify_args_pairs(tmp_path, lambda path: values[str(path)])) == 7
    values[str(tmp_path / "B_cut_off_p2" / "serve.log")]["server_port"] = "123"
    with pytest.raises(RuntimeError, match="dirty control"):
        probe.verify_args_pairs(tmp_path, lambda path: values[str(path)])


def test_pinned_parser_reads_a_real_serverargs_line(tmp_path):
    log = tmp_path / "serve.log"
    log.write_text("Parsed arguments ServerArgs(model_path='model', server_port=17777, special_token_ckpt=True, _unique_suffix='.pid=19', prefill_anchor_cut=True)\n")
    parsed = probe.load_args_parser()(log)
    assert parsed["model_path"] == "'model'" and parsed["_unique_suffix"] == "'.pid=19'"


def test_emitted_executor_compiles_and_imports_source(tmp_path):
    executor = probe.emit_review_executor(tmp_path / "r047_executor.py")
    pyc = py_compile.compile(str(executor), doraise=True)
    assert Path(pyc).is_file()
    text = executor.read_text(encoding="utf-8")
    assert "--owned-child" in text and "controller_launch" in text and "child_execute" in text



def test_emitted_executor_imports_its_pinned_prepare_source(tmp_path):
    executor = probe.emit_review_executor(tmp_path / "r047_executor.py")
    completed = subprocess.run([sys.executable, str(executor), "--help"], text=True,
                               capture_output=True, check=False)
    assert completed.returncode == 0, completed.stderr
    assert "--owned-child" in completed.stdout


def test_arm_summary_keeps_real_zero_coverage_visible(tmp_path):
    for name in ("A_cut_on_p1", "B_cut_off_p1", "A_cut_on_p2", "B_cut_off_p2", "A_cut_on_p3", "B_cut_off_p3"):
        path = tmp_path / name
        path.mkdir()
        (path / "arm_result.json").write_text(json.dumps({
            "actual_successful_snapshots": 0, "turns": [{"first_token_s": 1.2, "cached_tokens": 3}],
            "post_trigger_cache_hit_length": 3, "first_token_s": 1.2,
        }))
    arms, covered = probe.summarize_arms(tmp_path)
    assert len(arms) == 6 and covered is False
    row = json.loads((tmp_path / "A_cut_on_p1" / "arm_result.json").read_text())
    row["actual_successful_snapshots"] = 1
    (tmp_path / "A_cut_on_p1" / "arm_result.json").write_text(json.dumps(row))
    assert probe.summarize_arms(tmp_path)[1] is True


def test_controller_reserves_once_and_publishes_normalized_child_birth(monkeypatch, tmp_path):
    calls = []
    executor, review = tmp_path / "executor.py", tmp_path / "review.json"
    executor.write_text("# executor\\n")
    review.write_text("{}")
    class Helper:
        def next_batch(self, root):
            calls.append(("next_batch", root))
            return 89
    class Owned:
        def verified_module(self, *args):
            return Helper()
        def reserve_process(self, helper, batch, rid, argv, receipt_path, reserved):
            calls.append(("reserve", batch, rid, argv, receipt_path, reserved))
            return {**reserved, "state": "launched", "batch_pid": 765}
        def process_identity(self, pid):
            return {"pid": pid, "start_ticks": 321, "pgid": pid, "session": pid}
    class Protocol:
        ATOMIC_HELPER_SHA = "a" * 64
        ROUNDS = Path("/shared/rounds")
        def load_owned_lifecycle(self):
            return Owned()
        def argv_sha256(self, argv):
            return "b" * 64
        def process_birth(self):
            return {"pid": 4, "start_ticks": 5, "execution_id": "4:5"}
        def publish_child_binding(self, path, receipt, child, *, lifecycle):
            calls.append(("publish", path, receipt, child, lifecycle))
            return {**receipt, "child": child}
    monkeypatch.setattr(probe.sys, "platform", "linux")
    monkeypatch.setattr(probe, "FORMAL_PARENT", tmp_path)
    monkeypatch.setattr(probe, "checked_worktree", lambda _wt: {})
    monkeypatch.setattr(probe, "require_predecessors", lambda: {})
    monkeypatch.setattr(probe, "validate_review_receipt", lambda *_args: {})
    monkeypatch.setattr(probe, "load_d07_protocol", lambda: Protocol())
    monkeypatch.setattr(probe, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(probe, "LOCK", tmp_path / "missing.lock")
    result = probe.controller_launch(executor, review, tmp_path / "wt", tmp_path)
    assert [row[0] for row in calls] == ["next_batch", "reserve", "publish"]
    reserve = calls[1]
    assert calls[0] == ("next_batch", Path("/shared/rounds"))
    assert reserve[1:3] == (89, probe.RID) and reserve[4].name == "launch_E2-R047_batch89.json"
    assert calls[2][3] == {"pid": 765, "start_ticks": 321, "execution_id": "765:321"}
    assert result["child"]["execution_id"] == "765:321"


def test_controller_and_child_reject_non_linux_before_admission(monkeypatch, tmp_path):
    monkeypatch.setattr(probe.sys, "platform", "win32")
    monkeypatch.setattr(probe, "checked_worktree", lambda _path: pytest.fail("non-Linux admitted worktree"))
    monkeypatch.setattr(probe, "load_d07_protocol", lambda: pytest.fail("non-Linux admitted protocol"))
    with pytest.raises(RuntimeError, match="Linux"):
        probe.controller_launch(tmp_path / "executor.py", tmp_path / "review.json", tmp_path / "wt", tmp_path / "out")
    with pytest.raises(RuntimeError, match="Linux"):
        probe.child_execute(tmp_path / "executor.py", tmp_path / "review.json", tmp_path / "wt",
                            tmp_path / "out", 1, tmp_path / "launch.json")


def test_startup_stop_failure_preserves_lock_when_group_probe_is_false(monkeypatch,tmp_path):
 released=[]
 class Process:
  pid=321
  returncode=17
  def poll(self): return 17
 class Lifecycle:
  def stop_owned_process(self,process): raise RuntimeError('first startup stop failed')
  def owned_group_alive(self,pid): return False
 class Protocol:
  def require_child_receipt(self,*args,**kwargs): return {}
  def take_d07_gpu_lock(self,*args): return {'owner':probe.RID}
  def require_gpu_idle(self): return [0]
  def release_d07_gpu_lock(self,owner): released.append(owner)
  def load_owned_lifecycle(self): return Lifecycle()
 protocol=Protocol()
 monkeypatch.setattr(probe,'load_d07_protocol',lambda:protocol)
 monkeypatch.setattr(probe.sys,'platform','linux')
 monkeypatch.setattr(probe,'FORMAL_PARENT',tmp_path)
 monkeypatch.setattr(probe,'checked_worktree',lambda _wt:{})
 monkeypatch.setattr(probe,'require_predecessors',lambda:{})
 monkeypatch.setattr(probe,'validate_review_receipt',lambda *_:{})
 monkeypatch.setattr(probe,'packet',lambda _wt:{})
 monkeypatch.setattr(probe,'dynamic_fixture_port',lambda:17321)
 monkeypatch.setattr(probe.subprocess,'Popen',lambda *args,**kwargs:Process())
 monkeypatch.setattr(probe.os,'getpgid',lambda _:321,raising=False);monkeypatch.setattr(probe.os,'getsid',lambda _:321,raising=False)
 executor,review=tmp_path/'executor.py',tmp_path/'review.json';executor.write_text('# executor');review.write_text('{}')
 with pytest.raises(RuntimeError,match='first startup stop failed') as error:
  probe.child_execute(executor,review,tmp_path/'wt',tmp_path,74,tmp_path/'launch.json')
 assert getattr(error.value,'owned_cleanup_failed',False) and error.value.owned_process.pid==321
 assert released==[]
 cleanup=next(tmp_path.glob('E2-R047/owned_cleanup.json'))
 assert json.loads(cleanup.read_text())['lock_released'] is False


def test_formal_output_root_rejects_noncanonical_before_batch_or_lock(monkeypatch,tmp_path):
 monkeypatch.setattr(probe,'FORMAL_PARENT',tmp_path/'formal')
 (tmp_path/'formal').mkdir()
 with pytest.raises(RuntimeError,match='must equal'):
  probe.require_formal_output_root(tmp_path/'other')
 with pytest.raises(RuntimeError,match='cannot contain'):
  probe.require_formal_output_root(tmp_path/'formal'/'..'/'other')
 link=tmp_path/'link'
 monkeypatch.setattr(Path,'is_symlink',lambda self:self==link)
 with pytest.raises(RuntimeError,match='symlink'):
  probe.require_formal_output_root(link)
 assert probe.require_formal_output_root(tmp_path/'formal')==(tmp_path/'formal').resolve()

def test_controller_rejects_bad_formal_root_before_batch(monkeypatch,tmp_path):
 monkeypatch.setattr(probe.sys,'platform','linux')
 monkeypatch.setattr(probe,'FORMAL_PARENT',tmp_path/'formal');(tmp_path/'formal').mkdir()
 monkeypatch.setattr(probe,'checked_worktree',lambda *_:{})
 monkeypatch.setattr(probe,'require_predecessors',lambda:{})
 monkeypatch.setattr(probe,'validate_review_receipt',lambda *_:{})
 monkeypatch.setattr(probe,'load_d07_protocol',lambda:pytest.fail('bad root reached batch/lock protocol'))
 with pytest.raises(RuntimeError,match='must equal'):
  probe.controller_launch(tmp_path/'executor',tmp_path/'review',tmp_path/'wt',tmp_path/'other')


def test_review_input_digest_uses_actual_serve_window(monkeypatch):
 import hashlib
 monkeypatch.setattr(probe, 'positive_payload', lambda: {'fixture': 'positive'})
 monkeypatch.setattr(probe, 'negative_payload', lambda: {'fixture': 'negative'})
 argv = probe.serve_argv(23456)
 window = int(argv[argv.index('--kv-reserve-tokens') + 1])
 assert str(window) == argv[argv.index('--max-seq-len-override') + 1]
 value = {"arms": ["A_cut_on_p1", "B_cut_off_p1", "A_cut_on_p2", "B_cut_off_p2", "A_cut_on_p3", "B_cut_off_p3"],
          "only_ab_difference": "--no-prefill-anchor-cut", "positive": probe.positive_payload(),
          "negative": probe.negative_payload(), "window": window, "host_slots": 0, "stream_measure": "actual_ttft"}
 expected = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
 assert probe.review_input_sha256() == expected
 value['window'] = 49152
 assert probe.review_input_sha256() != hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def test_runtime_copy_preserves_parser_directory_and_wrapper(tmp_path):
 rows=probe.copy_runtime_sources(tmp_path/'source')
 assert (tmp_path/'source/d04_original/serve_args_diff.py').is_file()
 assert (tmp_path/'source'/probe.SHUTDOWN_SOURCE.name).is_file()
 assert all(probe.sha256_file(Path(row['source']))==probe.sha256_file(Path(row['copy'])) for row in rows)

def test_file_dry_rejects_formal_directory_before_admission(monkeypatch,tmp_path):
 monkeypatch.setattr(probe,'FORMAL_PARENT',tmp_path/'formal')
 monkeypatch.setattr(probe,'checked_worktree',lambda _:pytest.fail('path reached worktree check'))
 for dry in (probe.FORMAL_PARENT/probe.RID,tmp_path/'.dryrun_R047_wrong'):
  with pytest.raises(RuntimeError,match='canonical hidden sibling'):
   probe.file_dry_run(dry,tmp_path/'executor',tmp_path/'review',tmp_path/'wt',probe.FORMAL_PARENT)

def test_r046f_failed_producer_is_not_an_accepted_predecessor():
 assert ('E2-R046g','measured') in probe.FORMAL_PREDECESSORS
 assert all(rid != 'E2-R046f' for rid,_ in probe.FORMAL_PREDECESSORS)
