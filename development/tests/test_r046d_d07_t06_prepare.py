import hashlib
import importlib.util
import json
import threading
from pathlib import Path

import pytest

DEV = Path(__file__).parents[1]

def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, DEV / filename)
    mod = importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(mod); return mod


def test_r046c_manifest_preserves_window_and_training_partition(tmp_path):
    mod = load("r046c_prepare", "r046d_d07_t06_prepare.py")
    arms = [
        {"role": "seed12k", "directory": "G_seed12k", "kind": "generate", "rounds": 12, "max_tokens": 2048, "seed_raw_sha256": mod.SEEDS["seed12k"]},
        {"role": "seed_45k", "directory": "G_seed_45k", "kind": "generate", "rounds": 12, "max_tokens": 2048, "seed_raw_sha256": mod.SEEDS["seed_45k"]},
        {"role": "seed_real", "directory": "G_seed_real", "kind": "generate", "rounds": 12, "max_tokens": 2048, "seed_raw_sha256": mod.SEEDS["seed_real"]},
        {"role": "two", "directory": "G_two", "kind": "two-decode", "same_prompt": False, "ctx": 8000, "max_tokens": 256},
    ]
    manifest = mod.manifest(tmp_path, {"g3": {}}, arms, {"pid": 1})
    path = tmp_path / "manifest.json"; path.write_text(json.dumps(manifest))
    assert mod.validate_manifest(path)["d15_training_route"] == "G_seed12k/route"
    manifest["arms"][1]["d15_training_input"] = True; path.write_text(json.dumps(manifest))
    with pytest.raises(RuntimeError, match="train/heldout"):
        mod.validate_manifest(path)


def test_r046c_predecessors_use_only_canonical_metadata():
    mod = load("r046c_predecessors", "r046d_d07_t06_prepare.py"); calls = []
    class D:
        def require_closed_round(self, rid, verdict): calls.append((rid, verdict)); return Path("/sealed") / rid
    assert set(mod.require_predecessors(D())) == {"E2-R059-gate-D07", "E2-R058", "E2-R041-gate-D17"}
    assert calls == [("E2-R059-gate-D07", "kept"), ("E2-R058", "measured"), ("E2-R041-gate-D17", "kept")]


def test_trace_env_is_single_variable_and_pause_is_off(tmp_path):
    mod = load("r046c_env", "r046d_d07_t06_prepare.py")
    d = type("D", (), {"clean_environment": lambda self, wt, trace_dir=None: {"FT_DEV_ROUTE_TRACE": str(trace_dir), "FT_DEV_PAUSE_ENDPOINT": "1"} if trace_dir else {}})()
    assert mod._ordinary_environment(d, Path("wt"), None) == {}
    on = mod._ordinary_environment(d, Path("wt"), tmp_path / "route")
    assert on["FT_DEV_ROUTE_TRACE"].endswith("route") and "FT_DEV_PAUSE_ENDPOINT" not in on


def test_prepare_invokes_the_ordinary_analyzer_contract(monkeypatch, tmp_path):
    mod = load("r046c_analyzer_contract", "r046d_d07_t06_prepare.py")
    output = tmp_path / "analysis.json"; calls = []
    monkeypatch.setattr(mod, "ROUTE_ANALYZER", DEV / "r046c_route_analyze_ordinary_v1.py")
    monkeypatch.setattr(mod, "apply_window", lambda d: d)
    monkeypatch.setattr(mod, "load_d07", lambda: object())
    monkeypatch.setattr(mod, "_ordinary_environment", lambda *_: {})
    def fake_run(command, **_):
        calls.append(command)
        output.write_text(json.dumps({"analysis_scope": "ordinary_worker_token_bound_requests", "ordinary_worker_token_bound": True}))
    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    assert mod.invoke_ordinary_analysis(Path("wt"), tmp_path / "route", tmp_path / "trace.json", tmp_path / "serve.log", output)["ordinary_worker_token_bound"]
    assert "--ordinary-traces" in calls[0] and "--analyzer" not in calls[0] and "r046c_route_analyze_ordinary_v1.py" in calls[0][1]


def test_r046c_uses_ordinary_session_driver_not_ft_dev_agent_trace():
    mod = load("r046c_driver_contract", "r046d_d07_t06_prepare.py")
    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert "r046c_ordinary_seed_driver.py" in source
    assert "ordinary_observer/inputs.jsonl" in source and "ordinary_observer/tokens.jsonl" in source
    assert "--generate" in source and "--two" in source
    assert "invoke_agent_trace" not in source and "FT_DEV_PAUSE_ENDPOINT" in source


class Original:
    TASK_PROMPT = "prompt"; FOLLOW_UPS = ["next"]
    @staticmethod
    def tool_specs(): return []
    @staticmethod
    def build_payload(messages, model, tools, thinking, max_tokens): return {"model": model, "messages": messages, "max_tokens": max_tokens, "stream": True, "stream_options": {"include_usage": True}}
    @staticmethod
    def messages_digest(messages): return hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()
    @staticmethod
    def consume_stream(events, _t):
        rows = list(events); return {"content_text": "ok", "tool_calls": [], "usage": rows[-1]["usage"], "finish_reason": "stop"}
    @staticmethod
    def assistant_message(result): return {"role": "assistant", "content": result["content_text"]}
    @staticmethod
    def exec_tool_call(root, call): raise AssertionError("no tool call")


class Client:
    def __init__(self): self.uid, self.lock = 40, threading.Lock()
    def ordinary_request(self, _url, payload, output):
        with self.lock: self.uid += 1; uid = self.uid
        raw = output.with_suffix(".sse"); raw.write_text('data: {"id":"chatcmpl-%s","choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}],"usage":{"prompt_tokens":2,"completion_tokens":1}}\n\ndata: [DONE]\n' % uid)
        value = {"uid": uid, "sse": str(raw), "usage": {"prompt_tokens": 2, "completion_tokens": 1}, "finish_reason": "stop"}; output.write_text(json.dumps(value)); return value
    def bind(self, payload, api, d0, route, inputs, tokens, out):
        data = json.loads(payload.read_text()); api_row = json.loads(api.read_text()); ids = [1, 2]
        value = {"worker_input": {"input_ids_sha256": hashlib.sha256(json.dumps(ids, separators=(",", ":")).encode()).hexdigest(), "input_tokens": 2}, "token_sidecar": {"events": [{"uid": api_row["uid"], "next_token": 9, "finished": True}]}}
        out.write_text(json.dumps(value)); return value


def test_ordinary_seed_driver_stops_at_natural_window_without_ft_dev(tmp_path):
    driver = load("r046c_driver", "r046c_ordinary_seed_driver.py"); seed = "seed"; client = Client(); calls = []
    def frontend(payload):
        calls.append(payload); return [1, 2] if len(calls) < 3 else list(range(driver.LIMIT + 1))
    result = driver.generate_session(client=client, original=Original(), frontend=frontend, base_url="http://127.0.0.1:4321/v1", seed=seed, seed_sha256=hashlib.sha256(seed.encode()).hexdigest(), directory=tmp_path, d0=tmp_path/"d0", route=tmp_path/"route", inputs=tmp_path/"inputs", tokens=tmp_path/"tokens", model="m", tool_root=tmp_path)
    assert result["meta"]["completed_k"] == 2 and result["meta"]["window_hit"]["request_k"] == 3
    assert all("ft_dev" not in path.read_text() for path in tmp_path.glob("*.sse"))


def test_ordinary_two_decode_is_parallel_different_content_and_distinct_uid(tmp_path):
    driver = load("r046c_driver_two", "r046c_ordinary_seed_driver.py"); result = driver.two_decode(client=Client(), original=Original(), frontend=lambda _: [1, 2], base_url="http://127.0.0.1:4321/v1", directory=tmp_path, d0=tmp_path/"d0", route=tmp_path/"route", inputs=tmp_path/"inputs", tokens=tmp_path/"tokens", model="m")
    assert result["parallel"] and result["same_prompt"] is False and len({x["uid"] for x in result["records"]}) == 2


def _ordinary_event(uid, sequence, *, finished=False):
    return {"schema": "ft_t06_ordinary_token/v3", "uid": uid, "request_seq": sequence,
            "completion_tokens_delta": 1, "completion_tokens_cumulative": sequence,
            "next_token": 100 + sequence, "finished": finished,
            "finish_reason": "stop" if finished else None, "time_ns": 10_000 + sequence}


def _ordinary_binding(uid=7, completion=2):
    return {"schema": "ft_t06_ordinary_binding/v3", "verdict": "worker_input_uid_token_bound",
            "worker_input": {"input_ids_sha256": "a" * 64, "input_tokens": 2},
            "api": {"uid": uid, "finish_reason": "stop", "usage": {"completion_tokens": completion}},
            "token_sidecar": {"events": [_ordinary_event(uid, 1), _ordinary_event(uid, 2, finished=True)]}}


def _route(route, uid=7):
    import numpy as np
    (route / "route-00000000.json").write_text(json.dumps({"seq": 0, "phase": "prefill", "t": 2,
        "layer_count": 1, "layer_ids": [0], "reqs": [{"rid": uid, "n_tokens": 2}], "file": "route-00000000.npz"}))
    np.savez(route / "route-00000000.npz", expert_ids=np.asarray([[[0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
                                                                         [10, 11, 12, 13, 14, 15, 16, 17, 18, 19]]], dtype=np.int16))


def test_ordinary_route_analyzer_uses_detokenize_sidecar_without_ack_labels(tmp_path):
    analyzer = load("r046c_ordinary_analyzer", "r046c_route_analyze_ordinary_v1.py")
    route = tmp_path / "route"; route.mkdir(); _route(route)
    trace = tmp_path / "trace.json"
    trace.write_text(json.dumps({"schema": "ft_r046c_ordinary_seed_trace/v1", "rounds": [{"record": {
        "api_uid": 7, "completion_tokens": 2, "finish_reason": "stop", "actual_input_binding": _ordinary_binding()}}]}))
    result = analyzer.analyze(route, ordinary_traces=[trace])
    encoded = json.dumps(result, sort_keys=True)
    assert result["analysis_scope"] == "ordinary_worker_token_bound_requests"
    assert result["ordinary_worker_token_bound"] is True and result["business_uids"] == [7]
    assert result["ordinary_token_source"].endswith("(DetokenizeMsg)")
    assert "ft_route_ack" not in encoded and "ft_dev" not in encoded


def test_ordinary_route_analyzer_rejects_tampered_detokenize_sequence(tmp_path):
    analyzer = load("r046c_ordinary_analyzer_bad", "r046c_route_analyze_ordinary_v1.py")
    route = tmp_path / "route"; route.mkdir(); _route(route)
    binding = _ordinary_binding(); binding["token_sidecar"]["events"][1]["request_seq"] = 3
    trace = tmp_path / "trace.json"
    trace.write_text(json.dumps({"schema": "ft_r046c_ordinary_seed_trace/v1", "rounds": [{"record": {
        "api_uid": 7, "completion_tokens": 2, "finish_reason": "stop", "actual_input_binding": binding}}]}))
    with pytest.raises(ValueError, match="DetokenizeMsg sequence"):
        analyzer.analyze(route, ordinary_traces=[trace])


def test_ordinary_two_decode_binds_distinct_uids_and_worker_token_sidecars(tmp_path):
    analyzer = load("r046c_ordinary_two_analyzer", "r046c_route_analyze_ordinary_v1.py")
    first, second = _ordinary_binding(7), _ordinary_binding(8)
    second["worker_input"]["input_ids_sha256"] = "b" * 64
    for event in second["token_sidecar"]["events"]:
        event["uid"] = 8
    source = tmp_path / "two.json"
    source.write_text(json.dumps({"schema": "ft_r046c_ordinary_two_decode/v1", "same_prompt": False,
        "parallel": True, "ctx": 8000, "max_tokens": 256, "records": [
            {"uid": 7, "input_ids_sha256": "a" * 64, "completion_tokens": 2, "finish_reason": "stop", "binding": first},
            {"uid": 8, "input_ids_sha256": "b" * 64, "completion_tokens": 2, "finish_reason": "stop", "binding": second},
        ]}))
    pair = analyzer.load_two_decode(source)[0]
    assert pair["uids"] == [7, 8] and pair["source_schema"] == "ft_r046c_ordinary_two_decode/v1"


def test_controller_reserves_once_then_publishes_normalized_child_before_gpu_lock(monkeypatch, tmp_path):
    mod = load("r046c_controller", "r046d_d07_t06_prepare.py"); seen = {}
    receipt_root = tmp_path / "root" / "runs/dev_D07"
    d = type("D", (), {})(); d.LOCK = tmp_path / "absent.lock"; d.ATOMIC_HELPER_SHA = "pin"
    d.argv_sha256 = lambda argv: "argv"; d.process_birth = lambda: {"pid": 1, "start_ticks": 2}
    d.take_d07_gpu_lock = lambda *_: pytest.fail("controller must not acquire GPU lock")
    def reserve(helper, batch, rid, argv, path, reserved):
        assert helper.next_batch(mod.ROUNDS) == 71 and rid == mod.RID and reserved["candidate_commit"] == mod.CANDIDATE
        assert path.parent == receipt_root and argv == mod.child_argv(batch, path, mod.WT, mod.ROUNDS)
        return {**reserved, "state": "launched", "batch_pid": 22}
    owned = type("Owned", (), {"verified_module": lambda *_: type("H", (), {"next_batch": lambda _, root: 71})(),
        "reserve_process": staticmethod(reserve), "process_identity": staticmethod(lambda _: {"pid": 22, "start_ticks": 33, "pgid": 22}),})()
    def publish(path, value, child, *, lifecycle):
        seen.update(path=path, value=value, child=child, lifecycle=lifecycle); return {"published": True}
    d.load_owned_lifecycle = lambda: owned; d.publish_child_binding = publish
    monkeypatch.setattr(mod.sys, "platform", "linux"); monkeypatch.setattr(mod, "ROOT", tmp_path / "root")
    monkeypatch.setattr(mod, "WT", tmp_path / "wt"); monkeypatch.setattr(mod, "ROUNDS", tmp_path / "rounds")
    monkeypatch.setattr(mod, "load_d07", lambda: d); monkeypatch.setattr(mod, "apply_window", lambda x: x)
    monkeypatch.setattr(mod, "require_output_root", lambda *_: None); monkeypatch.setattr(mod, "require_startup_review", lambda: {"review": True})
    monkeypatch.setattr(mod, "packet", lambda _: {"candidate": mod.CANDIDATE}); monkeypatch.setattr(mod, "require_predecessors", lambda _: {"E2-R059-gate-D07": Path("/sealed")})
    assert mod.execute(mod.WT, mod.ROUNDS) == {"published": True}
    assert seen["child"] == {"pid": 22, "start_ticks": 33, "execution_id": "22:33"} and seen["lifecycle"] is owned


def test_owned_child_rejects_bad_receipt_before_taking_lock(monkeypatch, tmp_path):
    mod = load("r046c_bad_child", "r046d_d07_t06_prepare.py")
    d = type("D", (), {"LOCK": tmp_path / "lock", "take_d07_gpu_lock": lambda *_: pytest.fail("bad receipt reached lock")})()
    monkeypatch.setattr(mod.sys, "platform", "linux"); monkeypatch.setattr(mod, "load_d07", lambda: d); monkeypatch.setattr(mod, "apply_window", lambda x: x)
    monkeypatch.setattr(mod, "require_output_root", lambda *_: None); monkeypatch.setattr(mod, "require_startup_review", lambda: {})
    monkeypatch.setattr(mod, "packet", lambda _: {}); monkeypatch.setattr(mod, "require_predecessors", lambda _: {})
    d.require_child_receipt = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("receipt differs"))
    with pytest.raises(RuntimeError, match="receipt differs"):
        mod.execute(tmp_path / "wt", tmp_path / "rounds", owned_child=True, batch=3, launch_receipt=tmp_path / "receipt")


def test_file_dry_run_never_starts_service_or_allocates_batch(monkeypatch, tmp_path):
    mod = load("r046c_filedry", "r046d_d07_t06_prepare.py")
    d = type("D", (), {"LOCK": tmp_path / "gpu.lock", "serve_argv": lambda _, port: ["ft", "serve", "--memory-ratio", "0.88", "--kv-reserve-tokens", "49152", "--max-seq-len-override", "49152", "--mamba-host-slots", "0"],
                         "clean_environment": lambda _self, _wt, *, trace_dir=None: {} if trace_dir is None else {"FT_DEV_ROUTE_TRACE": str(trace_dir), "FT_DEV_PAUSE_ENDPOINT": "1"}})()
    monkeypatch.setattr(mod.sys, "platform", "linux"); monkeypatch.setattr(mod, "load_d07", lambda: d); monkeypatch.setattr(mod, "apply_window", lambda x: x)
    monkeypatch.setattr(mod, "packet", lambda _: {"candidate": mod.CANDIDATE}); monkeypatch.setattr(mod, "require_predecessors", lambda _: {"E2-R058": Path("/sealed")})
    monkeypatch.setattr(mod, "private_port_pair", lambda: (24567, {"api": 24567, "tcpstore": 24568}))
    monkeypatch.setattr(mod, "copy_filedry_sources", lambda *_: {"source": {"sha256": "x", "md5": "y", "mode": "0o600"}})
    (tmp_path / "rounds").mkdir()
    result = mod.file_dry_run(tmp_path / "wt", tmp_path / "rounds")
    assert result["service_started"] is False and result["batch_allocated"] is False and all(not arm["pause_endpoint"] for arm in result["services"])
    assert all(arm["port_pair"] == {"api": 24567, "tcpstore": 24568} for arm in result["services"])
    assert result["port_pair"] == {"api": 24567, "tcpstore": 24568}
    assert result["foreign_lock_before"] == result["foreign_lock_after"] == {"state": "absent"}
    assert all(json.loads((tmp_path / "rounds" / ".filedry_E2-R046d" / ("g3g4/" + arm["name"] if arm["name"].startswith("g3_") else arm["name"]) / "serve_args_expected.json").read_text())["d0"] is True for arm in result["services"])
    assert {Path(arm["argv"][1]).name for arm in result["services"]} == {"r046c_ordinary_memory_startup_v2.py"}
    assert all((Path(arm["argv"][arm["argv"].index("--observer-dir") + 1]) / "filedry_writable_probe.json").is_file() for arm in result["services"])


def test_private_port_pair_requires_adjacent_tcpstore_and_memory_rows_are_complete(monkeypatch, tmp_path):
    mod = load("r046c_memory", "r046d_d07_t06_prepare.py")
    monkeypatch.setattr(mod, "load_port_pair", lambda: type("P", (), {"dynamic_port": staticmethod(lambda: 24000), "port_receipt": staticmethod(lambda _: {"api": 24000, "tcpstore": 24001})})())
    assert mod.private_port_pair() == (24000, {"api": 24000, "tcpstore": 24001})
    birth = {"pid": 2, "start_ticks": 3, "execution_id": "2:3", "pgid": 2, "session": 2}
    service = {"pid": 1, "start_ticks": 2, "execution_id": "1:2", "pgid": 1, "session": 1}
    rows = [
        {"schema": "ft_r056_model_memory/v1", "event": "model_loaded", "worker_birth": birth, "service_birth": service, "device": 0},
        {"schema": "ft_r056_model_memory/v1", "event": "request_before", "uid": "7", "time_ns": 10, "worker_birth": birth, "service_birth": service, "device": 0},
        {"schema": "ft_r056_model_memory/v1", "event": "request_after", "uid": "7", "time_ns": 20, "worker_birth": birth, "service_birth": service, "device": 0},
    ]
    (tmp_path / "owned_process.json").write_text(json.dumps({"birth": {**service, "state": "S"}}))
    observer = tmp_path / "ordinary_observer"; observer.mkdir()
    (observer / "inputs.jsonl").write_text(json.dumps({"service_birth": service, "worker_birth": birth}) + "\n")
    (tmp_path / "model_process_cuda.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    assert mod.require_memory_evidence(tmp_path)["complete"] is True
    rows.pop(); (tmp_path / "model_process_cuda.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    with pytest.raises(RuntimeError, match="request-before/request-after"):
        mod.require_memory_evidence(tmp_path)


def test_file_dry_copies_writable_runtime_native_and_seed_inputs(monkeypatch, tmp_path):
    mod = load("r046c_copy", "r046d_d07_t06_prepare.py"); worktree = tmp_path / "wt"
    for relative in (Path("scripts/_agent_trace_original.py"), *mod.NATIVE_SOURCE_RELATIVE):
        path = worktree / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_text("candidate-source"); path.chmod(0o444)
    own = tmp_path / "r046c_prepare.py"; own.write_text("entry"); own.chmod(0o444); monkeypatch.setattr(mod, "__file__", str(own))
    sources = [own]
    for name in ("D07_SOURCE", "STARTUP_V3", "MEMORY_STARTUP", "MEMORY_OBSERVER", "CLIENT_V3", "CLIENT_V2", "SESSION_DRIVER", "SEED_CLIENT", "ROUTE_ANALYZER", "PORT_SOURCE", "ARGS_PARSER"):
        path = tmp_path / f"{name}.py"; path.write_text(name); path.chmod(0o444); monkeypatch.setattr(mod, name, path); sources.append(path)
    seeds = {}
    for role, digest in mod.SEEDS.items():
        path = tmp_path / f"{role}.txt"; path.write_text(role); path.chmod(0o444); monkeypatch.setitem(mod.SEEDS, role, hashlib.sha256(role.encode()).hexdigest()); seeds[role] = path
    monkeypatch.setattr(mod, "seed_paths", lambda: seeds)
    (tmp_path / "dry").mkdir()
    records = mod.copy_execution_sources(tmp_path / "dry", worktree)
    assert len(records) == len(sources) + len(seeds) + 1 + len(mod.NATIVE_SOURCE_RELATIVE)
    assert all((int(row["mode"], 8) & 0o222) and len(row["md5"]) == 32 for row in records.values())
    assert all(path.stat().st_mode & 0o222 == 0 for path in [*sources, *seeds.values(), *(worktree / relative for relative in (Path("scripts/_agent_trace_original.py"), *mod.NATIVE_SOURCE_RELATIVE))])
    parser_copy = tmp_path / "dry/runtime_sources/d04_original" / mod.ARGS_PARSER.name
    assert parser_copy.is_file() and parser_copy.stat().st_mode & 0o222 and records[str(mod.ARGS_PARSER)]["copy"] == str(parser_copy)


def test_file_dry_preserves_foreign_lock_inode_and_bytes(monkeypatch, tmp_path):
    mod = load("r046c_filedry_foreign_lock", "r046d_d07_t06_prepare.py")
    lock = tmp_path / "gpu.lock"; lock.write_text('{\"owner\":\"other\"}\n', encoding="utf-8")
    d = type("D", (), {"LOCK": lock, "serve_argv": lambda _, port: ["ft", "serve", "--memory-ratio", "0.88", "--kv-reserve-tokens", "49152", "--max-seq-len-override", "49152", "--mamba-host-slots", "0"],
                         "clean_environment": lambda _self, _wt, *, trace_dir=None: {} if trace_dir is None else {"FT_DEV_ROUTE_TRACE": str(trace_dir)}})()
    monkeypatch.setattr(mod.sys, "platform", "linux"); monkeypatch.setattr(mod, "load_d07", lambda: d); monkeypatch.setattr(mod, "apply_window", lambda x: x)
    monkeypatch.setattr(mod, "packet", lambda _: {"candidate": mod.CANDIDATE}); monkeypatch.setattr(mod, "require_predecessors", lambda _: {})
    monkeypatch.setattr(mod, "private_port_pair", lambda: (24567, {"api": 24567, "tcpstore": 24568}))
    monkeypatch.setattr(mod, "copy_filedry_sources", lambda *_: {})
    rounds = tmp_path / "rounds"; rounds.mkdir()
    result = mod.file_dry_run(tmp_path / "wt", rounds)
    assert result["foreign_lock_before"] == result["foreign_lock_after"]
    assert result["foreign_lock_before"]["inode"] == lock.stat().st_ino
    assert result["foreign_lock_before"]["bytes_sha256"] == mod.sha(lock)


def test_g3_args_diff_allows_only_trace_environment_and_pid(monkeypatch, tmp_path):
    mod = load("r046c_g3_args_diff", "r046d_d07_t06_prepare.py")
    off, on = tmp_path / "g3_off", tmp_path / "g3_on"; off.mkdir(); on.mkdir(); (on / "route").mkdir()
    for directory, suffix in ((off, ".pid=1"), (on, ".pid=2")):
        (directory / "serve_args_actual.json").write_text(json.dumps({"parsed": {"memory_ratio": "0.88", "kv_reserve_tokens": "98304", "max_seq_len_override": "98304", "mamba_host_slots": "0", "_unique_suffix": suffix}}))
    (off / "ENV.json").write_text(json.dumps({"FT_R046C": "1", "FT_DEV_D0": "1", "FT_DEV_D0_PATH": str(off / "d0")}))
    (on / "ENV.json").write_text(json.dumps({"FT_R046C": "1", "FT_DEV_D0": "1", "FT_DEV_D0_PATH": str(on / "d0"), "FT_DEV_ROUTE_TRACE": str(on / "route")}))
    value = mod.write_g3_args_diff(off, on)
    assert value["parsed_differences"] == {"_unique_suffix": [".pid=1", ".pid=2"]}
    assert value["raw_environment_differences"] == {"FT_DEV_D0_PATH": [str(off / "d0"), str(on / "d0")], "FT_DEV_ROUTE_TRACE": [None, str(on / "route")]}
    assert value["normalized_environment_differences"] == {"FT_DEV_ROUTE_TRACE": [None, str(on / "route")]}


def test_service_files_and_driver_use_the_same_d0_prefill_contract(monkeypatch, tmp_path):
    mod = load("r046c_d0_contract", "r046d_d07_t06_prepare.py")
    for name in ("STARTUP_V3", "MEMORY_STARTUP", "MEMORY_OBSERVER"):
        path = tmp_path / f"{name}.py"; path.write_text("# source\n"); monkeypatch.setattr(mod, name, path)
    d = type("D", (), {"serve_argv": lambda _, port: ["ft", "serve", "--port", str(port), "--memory-ratio", "0.88", "--kv-reserve-tokens", "98304", "--max-seq-len-override", "98304", "--mamba-host-slots", "0"],
                         "clean_environment": lambda _self, _wt, *, trace_dir=None: {} if trace_dir is None else {"FT_DEV_ROUTE_TRACE": str(trace_dir)}})()
    directory = tmp_path / "g3_off"; prepared = mod.service_files(d, directory, tmp_path / "wt", 34567, None, ordinary_v3=True)
    assert prepared["env"]["FT_DEV_D0"] == "1" and prepared["env"]["FT_DEV_D0_PATH"] == str(directory / "d0")
    expected = json.loads((directory / "serve_args_expected.json").read_text())
    assert expected["d0"] is True and expected["d0_path"] == str(directory / "d0")
    args = mod._ordinary_driver_args(tmp_path / "wt", directory, 34567, directory / "route")
    assert args[args.index("--d0") + 1] == str(directory / "d0_prefill.jsonl")


def test_packet_accepts_actual_checked_worktree_commit_shape(monkeypatch, tmp_path):
    mod = load("r046c_packet_commit", "r046d_d07_t06_prepare.py")
    d = type("D", (), {"checked_worktree": lambda _self, _wt: {"worktree": str(_wt), "commit": mod.CANDIDATE, "tracked_clean": True},
                         "serve_argv": lambda _self, port: ["ft", "serve", "--memory-ratio", "0.88", "--kv-reserve-tokens", "49152", "--max-seq-len-override", "49152"]})()
    monkeypatch.setattr(mod, "load_d07", lambda: d); monkeypatch.setattr(mod, "apply_window", lambda value: value)
    monkeypatch.setattr(mod, "require_native_provenance", lambda _wt: {"path": "/sealed/native", "sha256": "a" * 64, "native": {}})
    monkeypatch.setattr(mod, "seed_paths", lambda: {role: tmp_path / f"{role}.txt" for role in mod.SEEDS})
    for role, path in mod.seed_paths().items(): path.write_text(role)
    monkeypatch.setitem(mod.SEEDS, "seed12k", mod.SEEDS["seed12k"])
    value = mod.packet(tmp_path / "wt")
    assert value["candidate"]["commit"] == mod.CANDIDATE
