import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r067_prepare as r067
import r067_cold_hook as hook


def test_matrix_scope_geometry_and_sampling():
    plan = r067.plan()
    assert plan["scope"] == {"services": 6, "generation_calls": 26,
                             "limits": {"services": 6, "generation_calls": 28}}
    assert plan["sampling"] == {"max_tokens": 128, "temperature": 0, "top_p": 1, "ignore_eos": True}
    for service in plan["services"]:
        if service["kind"] == "hot":
            prefix = int(service["name"].removeprefix("hot_p"))
            assert service["seed"]["token_range"] == [0, prefix + 1]
            assert [q["cached_tokens"] for q in service["queries"]] == [prefix] * 4
        else:
            assert service["cache"] == "disabled"
            for query in service["queries"]:
                donor, tail = query["segments"]
                assert donor["end"] == tail["start"] + 1
                assert tail["end"] - tail["start"] == query["tail"]
                assert query["cached_tokens"] == 0


def test_source_freeze_is_narrow_and_same_end_fix_present():
    freeze = r067.source_freeze()
    assert freeze["runtime_changed_paths"] == ["python/freetoken/engine/engine.py"]
    assert freeze["changed_method"] == "_forward_dev_prefill_schedule"
    assert freeze["normal_scheduler_source_changed"] is False
    assert freeze["one_shot_schedule"] is True


def test_filedry_is_nonlaunching_and_requires_cold_rearm_admission(tmp_path):
    target = r067.write_packet(tmp_path)
    packet = json.loads(target.read_text(encoding="utf-8"))
    assert packet["cpu_only"] and not packet["gpu_started"]
    assert not packet["popen"] and not packet["http_requests"] and not packet["gpu_lock_taken"]
    assert packet["cold_matrix_admission"]["admittable"] == "pending_root_admission_and_independent_review"
    assert packet["cold_matrix_admission"]["one_shot_schedule"] is True
    assert packet["plan"]["admission_interlocks"]["cold_rearm"].startswith("R067-only")
    assert packet["plan"]["admission_interlocks"]["reject_if_exists"] == r067.CLEANUP_FAILED


def test_cold_hook_rearms_only_verified_idle_requests(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("r067_schedule", r067.D20 / "python/freetoken/scheduler/dev_prefill_schedule.py")
    schedule_module = importlib.util.module_from_spec(spec); assert spec.loader
    sys.modules[spec.name] = schedule_module; spec.loader.exec_module(schedule_module)
    rows = []
    for index, tail in enumerate(r067.TAILS):
        schedule = tmp_path / f"t{tail}.json"
        schedule.write_text(json.dumps(r067.segments(8192, tail)), encoding="utf-8")
        ids = [100, index + 1]
        rows.append({"id": f"t{tail}", "path": str(schedule), "sha256": r067.digest(schedule),
                     "input_ids_sha256": hook.ids_sha256(ids)})
    manifest = tmp_path / "manifest.json"; manifest.write_text(json.dumps(rows), encoding="utf-8")
    schedules = hook.load_manifest(manifest, parse_schedule=schedule_module.parse)
    class Manager:
        dev_prefill_schedule = None
        pending_list = []
    class Decode: runnable = False
    class Scheduler:
        def __init__(self): self.prefill_manager, self.decode_manager, self._last_data, self.seen = Manager(), Decode(), None, []
        def _process_one_msg(self, msg): self.seen.append(msg); self.prefill_manager.dev_prefill_schedule = None
    class Message:
        def __init__(self, uid, ids, marker): self.uid, self.input_ids, self.r067_cold = uid, ids, marker
    hook.install(Scheduler, schedules); scheduler = Scheduler()
    for index, tail in enumerate(r067.TAILS):
        ids = [100, index + 1]; sha = hook.ids_sha256(ids)
        scheduler._process_one_msg(Message(index, ids, {"uid": index, "schedule_id": f"t{tail}", "input_ids_sha256": sha}))
    assert len(scheduler.seen) == 4 and scheduler.prefill_manager.dev_prefill_schedule is None
    scheduler.decode_manager.runnable = True
    with __import__("pytest").raises(RuntimeError, match="idle drained"):
        scheduler._process_one_msg(Message(9, [100, 1], {"uid": 9, "schedule_id": "t1", "input_ids_sha256": hook.ids_sha256([100, 1])}))


def test_hook_consumes_matching_initial_environment_schedule_before_first_query(tmp_path):
    schedule = tmp_path / "t1.json"; schedule.write_text(json.dumps(r067.segments(8192, 1)), encoding="utf-8")
    ids = [100, 1]; record = {"schedule": __import__("types").SimpleNamespace(token="initial"),
                               "input_ids_sha256": hook.ids_sha256(ids)}
    class Manager:
        pending_list = []
        def __init__(self): self.dev_prefill_schedule = record["schedule"]
    class Scheduler:
        def __init__(self): self.prefill_manager = Manager(); self.decode_manager = __import__("types").SimpleNamespace(runnable=False); self._last_data = None
        def _process_one_msg(self, msg): self.prefill_manager.dev_prefill_schedule = None
    hook.install(Scheduler, {"t1": record}); instance = Scheduler()
    assert instance.prefill_manager.dev_prefill_schedule is None


def test_token_receipt_records_only_active_cold_uid(tmp_path):
    hook._ACTIVE_UIDS.clear(); hook._TOKENS.clear(); hook._ACTIVE_UIDS.add(7); hook._TOKENS[7] = []
    class IO:
        def _reply_tokenizer_rank0(self, messages): return list(messages)
    class Msg:
        def __init__(self, uid, token, finished=False): self.uid, self.next_token, self.finished = uid, token, finished
    hook.install_token_receipts(IO, tmp_path)
    IO()._reply_tokenizer_rank0([Msg(6, 99), Msg(7, 11), Msg(7, 12, True)])
    assert json.loads((tmp_path / "7.json").read_text()) == {"uid": 7, "token_ids": [11, 12], "finished": True}
    assert not (tmp_path / "6.json").exists()


def test_stable_wire_classes_are_module_importable():
    # The runtime probes JSON tokenizer transport and pickle separately on the
    # FT venv; this catches the earlier local-class regression before staging.
    source = (Path(__file__).resolve().parent / "r067_wire.py").read_text(encoding="utf-8")
    assert "class R067ExactIdsMsg(TokenizeMsg)" in source
    assert "class R067UserMsg(UserMsg)" in source
    assert "def register_wire_types" in source
