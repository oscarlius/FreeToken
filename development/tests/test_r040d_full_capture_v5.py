"""R040d regression over the complete retained sampler-capture implementation."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1] / "r040d_capture_v5"
pytest.importorskip("torch")
import torch
sys.path.insert(0, str(ROOT))
from equiv_suite.sampler_capture import SamplerCapture


class Req:
    def __init__(self, uid, ids, device_len=None):
        self.uid, self.input_ids = uid, torch.tensor(ids, dtype=torch.int32)
        self.device_len = len(ids) if device_len is None else device_len
        self.table_idx = uid if isinstance(uid, int) else 0
        self.linear_slot_idx = self.table_idx
    def complete_one(self): self.device_len += 1


class Batch:
    def __init__(self, reqs): self.reqs = reqs


class Sampler:
    def sample(self, logits, _args): return logits[:, 0].to(torch.int32)


class Engine:
    def __init__(self): self.sampler = Sampler()
    def forward_batch(self, batch, args):
        for req in batch.reqs: req.complete_one()
        logits = torch.arange(len(batch.reqs) * 8, dtype=torch.float32).reshape(len(batch.reqs), 8)
        return self.sampler.sample(logits, args)


class CompactEngine:
    """0aa shape: all reqs complete_one and sampler receives all physical rows."""
    def __init__(self, *, body="valid", sampled_rows=None):
        self.sampler, self.body, self.sampled_rows = Sampler(), body, sampled_rows
    def forward_batch(self, batch, args):
        for req in batch.reqs: req.complete_one()
        count = len(batch.reqs) if self.sampled_rows is None else self.sampled_rows
        if self.body == "three_dimensional": logits = torch.zeros((count, 2, 8), dtype=torch.float32)
        else: logits = torch.arange(count * 8, dtype=torch.float32).reshape(count, 8)
        return self.sampler.sample(logits, args)


class Args: temperatures = None


def test_mixed_chunked_prefill_keeps_complete_rows_and_preserves_v1_artifacts(tmp_path, monkeypatch):
    monkeypatch.setenv("FT_D16_EXECUTION_ID", "r040d-test")
    originals = {uid: [uid + 1] * 512 for uid in range(4)}
    cap = SamplerCapture(tmp_path / "sampler", registry=__import__("equiv_suite.sampler_capture", fromlist=["QueryRegistry"]).QueryRegistry(),
                         process_identity={"pid": 1, "start_ticks": 1, "execution_id": "r040d-test"}, max_captures=1024, max_bytes=64 * 1024 * 1024)
    for uid, ids in originals.items(): cap.registry.bind_query(uid, ids, f"event-{uid}")
    engine = Engine(); cap.attach(engine)
    # This is b97's mixed second prefill: UID3 is still at 384/512 and must
    # not discard UID1/UID2's valid sampler rows.
    engine.forward_batch(Batch([Req(1, originals[1]), Req(2, originals[2]), Req(3, originals[3][:384])]), Args())
    assert cap.registry.get(1)["sampled_tokens"] == [0]
    assert cap.registry.get(2)["sampled_tokens"] == [8]
    assert cap.registry.get(3)["sampled_tokens"] == []
    engine.forward_batch(Batch([Req(0, originals[0]), Req(3, originals[3])]), Args())
    # Decode uses only prompt + accepted physical history, and different row order.
    decode = [Req(uid, originals[uid] + cap.registry.get(uid)["sampled_tokens"]) for uid in (3, 1, 0, 2)]
    engine.forward_batch(Batch(decode), Args())
    expected = [{"uid": uid, "generation_index": gen, "event_identity": f"event-{uid}"}
                for uid in range(4) for gen in range(len(cap.registry.get(uid)["sampled_tokens"]))]
    cap.finalize(expected)
    manifest = json.loads((tmp_path / "sampler" / "manifest.json").read_text())
    assert manifest["schema"] == "ft_equiv_sampler_capture/v1" and manifest["terminal"] == "complete"
    receipts = [json.loads((tmp_path / "sampler" / entry["id"] / "receipt.json").read_text()) for entry in manifest["captures"]]
    assert any(receipt["capture_count"] == 2 and receipt["sbatch_coverage"] is True for receipt in receipts)
    assert all((tmp_path / "sampler" / entry["id"] / "logits_fp32.pt").is_file() for entry in manifest["captures"])


def test_full_hook_rejects_history_gap_after_real_complete_one(tmp_path, monkeypatch):
    monkeypatch.setenv("FT_D16_EXECUTION_ID", "r040d-test")
    from equiv_suite.sampler_capture import CaptureError, QueryRegistry
    registry = QueryRegistry(); registry.bind_query(9, [1] * 512, "event-9")
    cap = SamplerCapture(tmp_path / "sampler", registry=registry,
                         process_identity={"pid": 1, "start_ticks": 1, "execution_id": "r040d-test"}, max_captures=8, max_bytes=8 * 1024 * 1024)
    engine = Engine(); cap.attach(engine)
    engine.forward_batch(Batch([Req(9, [1] * 512)]), Args())
    engine.forward_batch(Batch([Req(9, [1] * 512 + [0, 0])]), Args())
    assert cap.errors[-1] == "indeterminate: physical sampler history is missing or out of order"


def test_complete_service_hook_preserves_original_artifacts_for_four_uids_128_generations(tmp_path, monkeypatch):
    """Exercise the retained hook through complete_one, sampler, delivery and seal."""
    monkeypatch.setenv("FT_D16_EXECUTION_ID", "r040d-test")
    from equiv_suite.service_capture import ServiceCaptureAdapter
    shutdown_spec = importlib.util.spec_from_file_location("r040d_shutdown", ROOT / "d16_native_capture_shutdown_v4.py")
    shutdown = importlib.util.module_from_spec(shutdown_spec); assert shutdown_spec.loader is not None
    shutdown_spec.loader.exec_module(shutdown)

    class Sampling:
        temperature = 0.0; top_k = 1; top_p = 1.0; ignore_eos = False; max_tokens = 128; stop_strs = []
    class User:
        def __init__(self, uid, ids): self.uid, self.input_ids, self.sampling_params = uid, torch.tensor(ids, dtype=torch.int32), Sampling()

    arm = tmp_path / "arm"
    prompts = {uid: [100 + uid, 200 + uid] for uid in range(4)}
    expected = [{"uid": uid, "generation_index": gen, "logical_label": f"ordinary-{uid}"}
                for uid in range(4) for gen in range(128)]
    adapter = ServiceCaptureAdapter(arm / "capture", expected_queries=expected,
                                    max_captures=512, max_bytes=64 * 1024 * 1024,
                                    process_identity={"pid": 7, "start_ticks": 9, "execution_id": "r040d-test"})
    engine = Engine(); adapter.attach(engine)
    for uid in range(4): adapter.admit_user_msg(User(uid, prompts[uid]))

    # The Engine method performs complete_one before calling the wrapped sampler,
    # matching 0aa Engine.forward_batch.  Every physical row is captured even
    # when subsequent scheduler batches reorder UID rows.
    for generation in range(128):
        order = [(generation + shift) % 4 for shift in range(4)]
        reqs = [Req(uid, prompts[uid] + adapter.registry.get(uid)["sampled_tokens"])
                for uid in order]
        engine.forward_batch(Batch(reqs), Args())
        for req in reqs:
            token = adapter.registry.get(req.uid)["sampled_tokens"][-1]
            adapter.observe_detokenize(type("Detok", (), {
                "uid": req.uid, "next_token": token, "finished": generation == 127,
            })())

    report = adapter.finalize()
    assert report["schema"] == "ft_equiv_service_capture/v2" and report["terminal"] == "complete"
    assert len(report["deliveries"]) == 512 and not report["un_delivered_samples"]
    manifest = json.loads((arm / "capture" / "sampler" / "manifest.json").read_text())
    assert manifest["schema"] == "ft_equiv_sampler_capture/v1" and manifest["terminal"] == "complete"
    assert len(manifest["captures"]) == 128
    assert all(len(adapter.registry.get(uid)["sampled_tokens"]) == 128 for uid in range(4))
    # This is the existing collector-facing terminal reader, not a replacement
    # schema; it must admit the complete original delivery report.
    assert shutdown.read_sealed_service_delivery(arm)["terminal"] == "complete"


def test_terminal_reader_names_arm_delivery_and_first_missing_uid(tmp_path):
    shutdown_spec = importlib.util.spec_from_file_location("r040d_shutdown_failure", ROOT / "d16_native_capture_shutdown_v4.py")
    shutdown = importlib.util.module_from_spec(shutdown_spec); assert shutdown_spec.loader is not None
    shutdown_spec.loader.exec_module(shutdown)
    arm = tmp_path / "G3-on"; capture = arm / "capture"; capture.mkdir(parents=True)
    (capture / "service_delivery.json").write_text(json.dumps({
        "terminal": "failed",
        "expected_deliveries": [{"uid": 17, "generation_index": 3}],
        "deliveries": [],
    }))
    with pytest.raises(shutdown.NativeCaptureShutdownError, match=r"arm=.*G3-on.*delivery=.*service_delivery.json.*expected=1 verified=0 first_missing=uid=17,generation=3"):
        shutdown.read_sealed_service_delivery(arm)


def test_startup_installs_retained_process_schedule_send_and_shutdown_lifecycle(tmp_path, monkeypatch):
    """Install the original public scheduler lifecycle, then seal through shutdown."""
    import types
    from equiv_suite import service_capture_startup as startup
    monkeypatch.setenv("FT_D16_EXECUTION_ID", "r040d-test")
    arm = tmp_path / "dev_D16" / "arm"; capture = arm / "capture"; expected = arm / "expected.json"
    expected.parent.mkdir(parents=True); expected.write_text(json.dumps([{
        "uid": 31, "generation_index": 0, "logical_label": "ordinary-31"
    }]))
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_DIR", str(capture))
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_EXPECTED_JSON", str(expected))
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_MAX_CAPTURES", "8")
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_MAX_BYTES", str(8 * 1024 * 1024))

    class UserMsg:
        def __init__(self):
            self.uid = 31; self.input_ids = torch.tensor([31, 32], dtype=torch.int32)
            self.sampling_params = type("Sampling", (), {
                "temperature": 0.0, "top_k": 1, "top_p": 1.0, "ignore_eos": False,
                "max_tokens": 1, "stop_strs": [],
            })()
    class DetokenizeMsg:
        def __init__(self, token): self.uid, self.next_token, self.finished = 31, token, True
    package = types.ModuleType("freetoken"); package.__path__ = []
    messages = types.ModuleType("freetoken.message"); messages.UserMsg = UserMsg; messages.DetokenizeMsg = DetokenizeMsg
    monkeypatch.setitem(sys.modules, "freetoken", package); monkeypatch.setitem(sys.modules, "freetoken.message", messages)

    req = Req(31, [31, 32])
    batch = Batch([req]); batch.phase = "prefill"; batch.padded_reqs = [req]; batch.active_table_idx = torch.tensor([31], dtype=torch.int32)
    class Scheduler:
        def __init__(self): self.engine, self.calls, self.did_shutdown = Engine(), [], False
        def _process_one_msg(self, value): self.calls.append(("process", value)); return "processed"
        def send_result(self, value): self.calls.append(("send", value)); return "sent"
        def _schedule_next_batch(self): self.calls.append(("schedule", None)); return type("Forward", (), {"batch": batch})()
        def shutdown(self): self.did_shutdown = True; return "closed"
    scheduler = Scheduler()
    adapter = startup.install_scheduler_capture(scheduler)
    assert adapter is not None
    assert scheduler._process_one_msg(UserMsg()) == "processed"
    scheduler._schedule_next_batch()
    token = scheduler.engine.forward_batch(batch, Args())[0].item()
    assert scheduler.send_result(DetokenizeMsg(token)) == "sent"
    assert scheduler.shutdown() == "closed" and scheduler.did_shutdown
    delivery = json.loads((capture / "service_delivery.json").read_text())
    assert delivery["terminal"] == "complete" and len(delivery["scheduler_batches"]) == 1


def test_shutdown_install_resolves_final_canonical_exact_role(monkeypatch):
    """The final capsule maps v5 origin bytes to the original v4 role name."""
    import types
    base = types.ModuleType("d16_exact_service_startup")
    base.parking_roundtrip = lambda scheduler, request_id: {"request_id": request_id}
    base.install = lambda: setattr(base, "installed", True)
    exact_spec = importlib.util.spec_from_file_location("d16_exact_service_startup_v4", ROOT / "d16_exact_service_startup_v4.py")
    exact = importlib.util.module_from_spec(exact_spec); assert exact_spec.loader is not None
    monkeypatch.setitem(sys.modules, "d16_exact_service_startup", base)
    monkeypatch.setitem(sys.modules, "d16_exact_service_startup_v4", exact); exact_spec.loader.exec_module(exact)
    launch = types.ModuleType("freetoken.server.launch"); original = object(); launch._run_scheduler = original
    package = types.ModuleType("freetoken"); package.__path__ = []
    server = types.ModuleType("freetoken.server"); server.launch = launch
    monkeypatch.setitem(sys.modules, "freetoken", package); monkeypatch.setitem(sys.modules, "freetoken.server", server)
    monkeypatch.setitem(sys.modules, "freetoken.server.launch", launch)
    shutdown_spec = importlib.util.spec_from_file_location("r040d_shutdown_install", ROOT / "d16_native_capture_shutdown_v4.py")
    shutdown = importlib.util.module_from_spec(shutdown_spec); assert shutdown_spec.loader is not None
    shutdown_spec.loader.exec_module(shutdown)
    shutdown.install()
    assert base.installed is True and launch._run_scheduler is shutdown.run_scheduler


def test_b100_physical_sampler_rows_keep_full_prefill_and_drop_middle_unfinished_row(tmp_path, monkeypatch):
    """0aa samples all three physical rows; retained uid3 is physical row two."""
    monkeypatch.setenv("FT_D16_EXECUTION_ID", "r040d-test")
    from equiv_suite.sampler_capture import QueryRegistry
    prompts = {uid: [1000 + uid] * 512 for uid in range(4)}
    registry = QueryRegistry()
    for uid, ids in prompts.items(): registry.bind_query(uid, ids, f"event-{uid}")
    cap = SamplerCapture(tmp_path / "sampler", registry=registry,
        process_identity={"pid": 1, "start_ticks": 1, "execution_id": "r040d-test"}, max_captures=1024, max_bytes=64 * 1024 * 1024)
    engine = CompactEngine(); cap.attach(engine)
    # uid2 is an unfinished 384-token continuation between two completed
    # prompts. Engine samples all three physical rows; capture retains uid1/3.
    mixed = Batch([Req(1, prompts[1]), Req(2, prompts[2][:384], 384), Req(3, prompts[3])])
    engine.forward_batch(mixed, Args())
    assert registry.get(1)["sampled_tokens"] == [0]
    assert registry.get(2)["sampled_tokens"] == []
    assert registry.get(3)["sampled_tokens"] == [16]
    first = json.loads((tmp_path / "sampler" / "capture-000001" / "receipt.json").read_text())
    assert [row["uid"] for row in first["rows"]] == [1, 3]
    assert [row["sampler_row_index"] for row in first["rows"]] == [0, 2]
    # uid2 reaches prompt completion later, then all four decode in a new order.
    engine.forward_batch(Batch([Req(2, prompts[2])]), Args())
    engine.forward_batch(Batch([Req(uid, prompts[uid] + registry.get(uid)["sampled_tokens"]) for uid in (2, 3, 0, 1)]), Args())
    assert not cap.errors
    assert all(registry.get(uid)["sampled_tokens"] for uid in range(4))


def test_all_partial_or_malformed_compact_sampler_input_never_reuses_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("FT_D16_EXECUTION_ID", "r040d-test")
    from equiv_suite.sampler_capture import QueryRegistry
    registry = QueryRegistry(); registry.bind_query(5, [5] * 512, "event-5"); registry.bind_query(6, [6] * 512, "event-6")
    cap = SamplerCapture(tmp_path / "sampler", registry=registry,
        process_identity={"pid": 1, "start_ticks": 1, "execution_id": "r040d-test"}, max_captures=8, max_bytes=8 * 1024 * 1024)
    partial = CompactEngine(); cap.attach(partial)
    all_partial = Batch([Req(5, [5] * 384, 384), Req(6, [6] * 256, 256)]); all_partial.sampled_count = 0
    partial.forward_batch(all_partial, Args())
    assert cap._current is None and not registry.get(5)["sampled_tokens"] and not (tmp_path / "sampler").exists()
    # Two complete physical requests but a one-row sampler body is rejected.
    bad_rows = CompactEngine(sampled_rows=1); cap2 = SamplerCapture(tmp_path / "bad-rows", registry=registry,
        process_identity={"pid": 2, "start_ticks": 2, "execution_id": "r040d-test"}, max_captures=8, max_bytes=8 * 1024 * 1024)
    cap2.attach(bad_rows); bad_rows.forward_batch(Batch([Req(5, [5] * 512), Req(6, [6] * 512)]), Args())
    assert any("logits rows do not cover selected physical requests" in item for item in cap2.errors)
    # Body dimensionality retains the old reject path, rather than silently reshaping.
    body = CompactEngine(body="three_dimensional"); cap4 = SamplerCapture(tmp_path / "bad-body-actual", registry=QueryRegistry(),
        process_identity={"pid": 4, "start_ticks": 4, "execution_id": "r040d-test"}, max_captures=8, max_bytes=8 * 1024 * 1024)
    cap4.registry.bind_query(7, [7] * 512, "event-7"); cap4.attach(body); body.forward_batch(Batch([Req(7, [7] * 512)]), Args())
    assert any("logits rows do not equal pre-forward request rows" in item for item in cap4.errors)


def test_actual_candidate_engine_forward_batch_uses_three_physical_logits_for_middle_partial(tmp_path, monkeypatch):
    """Invoke 8bf0ad's Engine.forward_batch and Req.complete_one, with CPU fakes only."""
    import contextlib, importlib
    worktree = Path(__import__('os').environ.get('FT_R040D_ENGINE_WORKTREE', ''))
    if not worktree.is_dir(): pytest.skip('set FT_R040D_ENGINE_WORKTREE to the exact D08 candidate')
    monkeypatch.syspath_prepend(str(worktree / 'python'))
    engine_module = importlib.import_module('freetoken.engine.engine')
    core_module = importlib.import_module('freetoken.core')
    assert engine_module.Engine.forward_batch.__module__ == 'freetoken.engine.engine'
    assert core_module.Req.complete_one.__module__ == 'freetoken.core'

    class LiveReq:
        complete_one = core_module.Req.complete_one
        def __init__(self, uid, ids, device_len=None):
            self.uid, self.input_ids = uid, torch.tensor(ids, dtype=torch.int32)
            self.device_len = len(ids) if device_len is None else device_len
            self.cached_len = 0
            self.table_idx = uid; self.linear_slot_idx = uid
    class LiveBatch:
        phase = 'prefill'; is_prefill = True; is_decode = False; mm_gather_plan = None; layer_major = False
        def __init__(self, reqs): self.reqs=reqs
        @property
        def size(self): return len(self.reqs)
    class FakeEvent:
        def record(self, _stream): pass
    fake_cuda = type('Cuda', (), {'current_stream': staticmethod(lambda: 'stream'), 'Event': FakeEvent})()
    monkeypatch.setattr(engine_module, 'torch', type('Torch', (), {'cuda': fake_cuda, 'int32': torch.int32})())
    class FakeSampler:
        def sample(self, logits, _args): return torch.argmax(logits, dim=-1)
    class FakeCtx:
        route_tracer = None
        @contextlib.contextmanager
        def forward_batch(self, _batch): yield
    class FakeGraph:
        def can_use_cuda_graph(self, _batch): return False
    class FakeModel:
        @contextlib.contextmanager
        def forward_host_ctx(self, _batch, _use_graph): yield
        def forward(self): return torch.tensor([[10.,0.],[0.,11.],[0.,0.]], dtype=torch.float32)
    live = type('LiveEngine', (), {})()
    live.stream='stream'; live.ctx=FakeCtx(); live.graph_runner=FakeGraph(); live.model=FakeModel(); live.sampler=FakeSampler()
    live.cpu_moe_executor=None; live.moe_offload_cache=None
    import types
    live.forward_batch = types.MethodType(engine_module.Engine.forward_batch, live)
    from equiv_suite.sampler_capture import QueryRegistry
    registry=QueryRegistry(); prompts={1:[1]*512,2:[2]*512,3:[3]*512}
    for uid, ids in prompts.items(): registry.bind_query(uid,ids,f'event-{uid}')
    cap=SamplerCapture(tmp_path/'sampler',registry=registry,process_identity={'pid':1,'start_ticks':1,'execution_id':'actual-engine'},max_captures=16,max_bytes=8*1024*1024)
    cap.attach(live)
    output=live.forward_batch(LiveBatch([LiveReq(1,prompts[1]),LiveReq(2,prompts[2][:384],384),LiveReq(3,prompts[3])]), Args())
    assert output.next_tokens_gpu.tolist() == [0,1,0]
    assert registry.get(1)['sampled_tokens']==[0] and registry.get(2)['sampled_tokens']==[] and registry.get(3)['sampled_tokens']==[0]
    receipt=json.loads((tmp_path/'sampler'/'capture-000001'/'receipt.json').read_text())
    assert [(row['uid'],row['sampler_row_index']) for row in receipt['rows']]==[(1,0),(3,2)]
