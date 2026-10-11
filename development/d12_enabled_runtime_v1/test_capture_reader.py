"""Joint D16 admission/sampler + D12 worker/state + D03 tail CPU evidence."""
import hashlib
import json
import os
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

if not os.environ.get("FT_D12_NATIVE_SOURCE"):
    pytest.skip("requires native candidate and pinned D03 Linux modules", allow_module_level=True)

import torch
from freetoken.core import SamplingParams
from freetoken.kvcache import linear_state_pool
from freetoken.message import DetokenizeMsg, UserMsg

from capture_reader import read_state_tail
from natural_capture import NaturalServiceCapture, make_policy as natural_policy
from prompt_tail import make_policy as tail_policy
from replay_binding import load_replay_binding
from test_prompt_tail import batch, fixture
from test_replay_binding import BUNDLE, BUNDLE_SHA
import worker_capture


IDENTITY = {"pid": 1, "start_ticks": 2, "execution_id": "cpu-joint-state-tail"}
LAYOUT = {
    "conv_states": {"shape": [2, 1, 4], "dtype": "torch.bfloat16", "layer_ids": [0, 1]},
    "recurrent_states": {"shape": [2, 1, 4], "dtype": "torch.float32", "layer_ids": [0, 1]},
    "slot:ple_conv": {"shape": [1, 1, 4], "dtype": "torch.float32", "layer_ids": [1]},
    "slot:ple_ngram_ctx": {"shape": [1, 1, 4], "dtype": "torch.int64", "layer_ids": [-1]},
}


def make_joint_capture(tmp_path_factory, *, d0=False, identity=IDENTITY, variant="same", generations=1):
    root = tmp_path_factory.mktemp("joint-native-components")
    with pytest.MonkeyPatch.context() as patch:
        f = fixture(root / "model", patch, length=80, k=64)
        f.capture.restore()
        f.restore_segment()
        binding = load_replay_binding(BUNDLE, BUNDLE_SHA)
        capture = root / "dev_D16" / "capture"
        dump = capture / "d12_state"
        patch.setattr(linear_state_pool, "DUMP_PATH", str(dump))
        for key, value in {"FT_DEV_STATE_DUMP": dump, "FT_DEV_LOGITS_DUMP": capture / "d12_prompt_tail",
            "FT_D12_PROMPT_TAIL": "1", "FT_D12_TAIL_HIDDEN_BYTES": "1000000",
            "FT_D12_DIAGNOSTIC": "1", "FT_D12_MAX_EVENTS": "1024", "FT_D12_MAX_EVENT_BYTES": "1000000",
            "FT_D16_SERVICE_CAPTURE_DIR": capture}.items():
            patch.setenv(key, str(value))
        patch.setenv("FT_D12_D0_COVERAGE", "1" if d0 else "0")
        if d0:
            patch.setenv("FT_DEV_D0", "1")
            patch.setenv("FT_DEV_D0_PATH", str(capture / "d12_d0"))
        assert worker_capture.prepare_environment() == (capture, dump, (1024, 1000000))

        class Cache:
            quant_format, prefill_overlap, prefill_routed_only_max_tokens = "nvfp4", False, 0
            def prepare_prefill_routed_only(self, *_):
                raise AssertionError("controlled CPU decoder layers do not execute MoE")

        engine = f.engine
        if variant == "state":
            engine.linear_state_pool.conv_states.add_(1)
        elif variant == "logits":
            engine.model.lm_head.tied_embedding.weight.mul_(1.0001)
        elif variant == "token":
            engine.model.lm_head.tied_embedding.weight = engine.model.lm_head.tied_embedding.weight.flip(0)
        else:
            assert variant in ("same", "token_late")
        engine.moe_offload_cache = Cache()
        if d0:
            from freetoken.layers.moe import OffloadMoELayer
            from freetoken.moe.offload_cache import OffloadMoeCache
            from test_transfer_audit import fixture_cache
            protocol, _, _ = fixture_cache()
            cache = OffloadMoeCache.__new__(OffloadMoeCache)
            cache.__dict__.update(protocol.__dict__)
            cache.device, cache.prefill_overlap = torch.device("cpu"), False
            cache.prefill_routed_only_max_tokens, cache.prefill_routed_only_stats = 0, None
            cache._d0_on, cache._d0_prefill_active, cache._d0_chunk_idx = True, False, 0
            cache._d0_prefill_path = str(capture / "d12_d0_prefill.jsonl")
            cache.materialize_layer = lambda layer: None
            cache.copy_missing = lambda: None
            cache.bank_views = lambda *args: tuple(value for _, value in cache.banks)
            cache.alphas_for_layer = lambda layer: None
            cache.num_indices = torch.tensor([2], dtype=torch.int64)
            class Event:
                def record(self, stream): pass
                def elapsed_time(self, other): return 0.125
            patch.setattr(torch.cuda, "Event", lambda **kwargs: Event())
            patch.setattr(torch.cuda, "current_stream", lambda *args: None)
            engine.moe_offload_cache = cache
            # Keep the actual candidate model's layer/child loops and actual
            # OffloadMoELayer branch; only device copies/GEMM/events are CPU seams.
            for layer in engine.model.model.layers.op_list:
                moe = OffloadMoELayer.__new__(OffloadMoELayer)
                moe.offload_cache, moe.layer_id, moe.num_experts = cache, layer.index, 4
                moe._expert_gemm = lambda cache, hidden, *args, **kwargs: hidden
                original_layer = layer.forward
                def forward_layer(hidden, current, original=original_layer, operation=moe):
                    ids = torch.tensor([[1, 3]], dtype=torch.int32).repeat(hidden.shape[0], 1)
                    value = operation._prefill_routed(hidden, torch.full(ids.shape, 0.5), ids)
                    return original(value, current)
                layer.forward = forward_layer
        engine.sampler = SimpleNamespace(sample=lambda logits, args: logits.argmax(-1))
        model_forward = engine.forward_batch
        def sample_forward(current, children=None):
            if not current.is_prefill:
                # Controlled decode logits exercise native sampler history and
                # delivery ordering, not the candidate's real decode/model path.
                generation = current.reqs[0].device_len - len(current.reqs[0].input_ids)
                selected = 0 if variant == "token_late" and generation == 2 else 4
                logits = torch.zeros(1, 5)
                logits[0, selected] = 10
                return engine.sampler.sample(logits, SimpleNamespace(temperatures=None))
            if d0:
                current.layer_major = children is not None
                cache._d0_begin_prefill(current)
                cache._d0_segment["subchunks"] = [child.reqs[0].extend_len for child in (children or [current])]
            logits = model_forward(current, children)
            if d0:
                cache.end_prefill()
            return engine.sampler.sample(logits, SimpleNamespace(temperatures=None))
        engine.forward_batch = sample_forward
        adapter = NaturalServiceCapture(capture, binding=binding, max_captures=32, max_bytes=4000000,
                                        process_identity=identity).attach(engine)
        shutdowns = []
        scheduler = SimpleNamespace(engine=engine, shutdown=lambda: shutdowns.append(1))
        close = worker_capture.install_worker_capture(scheduler, adapter, capture, dump, (1024, 1000000), binding)
        for source in binding["requests"]:
            uid, ids = source["uid"], source["input_ids"]
            message = UserMsg(uid=uid, input_ids=torch.tensor(ids, dtype=torch.int32),
                sampling_params=SamplingParams(max_tokens=source["max_tokens"], temperature=0))
            adapter.admit_user_msg(message)
            outer = batch(0, len(ids), uid)
            outer.input_ids = message.input_ids
            outer.reqs[0].input_ids = message.input_ids
            children = None
            if uid == 1:
                children = [batch(a, b, uid) for a, b in ((0, len(ids)-80), (len(ids)-80, len(ids)-32),
                                                         (len(ids)-32, len(ids))) ]
                for child in children:
                    child.input_ids = message.input_ids[child.reqs[0].cached_len:child.reqs[0].device_len]
                    child.reqs[0].input_ids = message.input_ids
            sampled = engine.forward_batch(outer, children)
            for generation in range(generations):
                if generation:
                    current = batch(len(ids) + generation - 1, len(ids) + generation, uid)
                    current.is_prefill, current.is_decode = False, True
                    current.reqs[0].input_ids = message.input_ids
                    sampled = engine.forward_batch(current)
                adapter.observe_detokenize(DetokenizeMsg(uid=uid, next_token=int(sampled[0]),
                                                        finished=generation == generations - 1))
        scheduler.shutdown()
        close()
        report = adapter.finalize()
        assert shutdowns == [1] and report["terminal"] == "complete" and report["errors"] == []
        assert not torch.cuda.is_initialized()
        expectations = {"expected_tail_policy": tail_policy(binding, f.d03, 1000000),
            "expected_natural_policy": natural_policy(binding, 32, 4000000), "process_identity": identity,
            "expected_vocab_size": 5, "expected_state_layout": LAYOUT, "d03_root": os.environ["FT_D12_D03_ROOT"]}
        if d0:
            expectations.update(expected_moe_layer_ids=[0, 1], expected_routed_only_threshold=0,
                                candidate_root=os.environ["FT_D12_NATIVE_SOURCE"])
        return capture, expectations


@pytest.fixture(scope="module", params=[False, True], ids=["state-tail", "state-tail-d0"])
def joint_capture(tmp_path_factory, request):
    return make_joint_capture(tmp_path_factory, d0=request.param)


def test_reader_joins_same_worker_native_components(joint_capture):
    capture, expectations = joint_capture
    result = read_state_tail(capture, **expectations)
    assert result["state_tail_bound"] is True
    assert result["natural_delivery"]["delivered_counts"] == {"0": 1, "1": 1, "2": 1}
    assert len(result["observed_outer_segments"]) == 3
    assert [row["extra"]["positions"] for row in result["tail_records"].values()] == [
        list(range(n - 64, n)) for n in (12660, 12905, 12987)]
    assert result["bank_events_observed"] == 0
    assert not result["bank_coverage_verified"] and not result["prefill_schedule_verified"]
    assert not result["output_equivalence_verified"] and not result["performance_eligible"]
    if "candidate_root" in expectations:
        assert result["d0_protocol_verified"] and result["completed_moe_calls"] == 10
        assert result["eligible_bank_calls"] == result["routed_bank_successes"] == 0
        assert result["per_uid_calls"] == {str(uid): {"moe_calls": count, "eligible_calls": 0}
                                           for uid, count in ((0, 2), (1, 6), (2, 2))}
        assert "d12_d0_prefill.jsonl" in result["artifact_sha256"]
        assert not result["routed_bank_bytes_verified"]
    (capture.parent / "state_tail_reader_result.json").write_text(json.dumps(result, indent=2))


@pytest.mark.parametrize("fault", ["process", "policy", "vocab", "layout", "layer_ids", "admission",
    "event_process", "event_identity", "frozen_input", "event_order", "missing_state", "extra_index",
    "outer_gap", "tail_index", "tail_sha", "state_sha", "projection", "state_value", "symlink"])
def test_reader_rejects_changed_binding_or_tensor(joint_capture, tmp_path, fault):
    source, original = joint_capture
    capture = tmp_path / "capture"
    shutil.copytree(source, capture)
    args = json.loads(json.dumps(original))
    events_path = capture / "d12_events.jsonl"
    events = [json.loads(line) for line in events_path.read_bytes().splitlines()]
    if fault == "process": args["process_identity"]["start_ticks"] += 1
    elif fault == "policy": args["expected_tail_policy"]["max_retained_hidden_bytes"] += 1
    elif fault == "vocab": args["expected_vocab_size"] += 1
    elif fault == "layout": args["expected_state_layout"]["conv_states"]["shape"][-1] += 1
    elif fault == "layer_ids": args["expected_state_layout"]["conv_states"]["layer_ids"] = [1, 0]
    elif fault == "admission":
        path = capture / "admissions/admission-000001.json"
        path.write_bytes(path.read_bytes() + b" ")
    elif fault == "event_process": events[0]["process_identity"]["pid"] += 1
    elif fault == "event_identity": events[0]["physical_event_identity"] = events[2]["physical_event_identity"]
    elif fault == "frozen_input": events[0]["frozen_input"]["payload_sha256"] = "0" * 64
    elif fault == "event_order": events[0]["d12_event_index"] = True
    elif fault == "missing_state": events.pop(0)
    elif fault == "extra_index":
        path = capture / "d12_state/index.jsonl"
        path.write_bytes(path.read_bytes() + path.read_bytes().splitlines()[0] + b"\n")
    elif fault == "outer_gap": events[0]["evidence"]["outer"]["end"] -= 1
    elif fault == "tail_index":
        path = capture / "d12_prompt_tail/index.jsonl"
        rows = path.read_bytes().splitlines()
        path.write_bytes(b"\n".join(rows[::-1]) + b"\n")
    elif fault in ("tail_sha", "state_sha", "symlink"):
        if fault == "state_sha":
            path = capture / "d12_state" / events[0]["evidence"]["role_files"]["conv_states"]["path"]
        else:
            path = capture / "d12_prompt_tail" / events[1]["evidence"]["record"]["files"]["logits"]
        if fault == "symlink":
            target = path.with_suffix(".moved")
            path.rename(target)
            path.symlink_to(target)
        else: path.write_bytes(path.read_bytes() + b"changed")
    elif fault == "projection":
        record = events[1]["evidence"]["record"]
        record["extra"]["d12_projection_segments"][0]["positions"].pop()
        path = capture / "d12_prompt_tail/index.jsonl"
        rows = [json.loads(line) for line in path.read_bytes().splitlines()]
        rows[0] = record
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    elif fault == "state_value":
        # Keep all producer SHA/index fields internally consistent. Independent
        # native-end-state content comparison must still reject this change.
        record = events[1]["evidence"]["record"]
        path = capture / "d12_prompt_tail" / record["files"]["conv_states"]
        value = torch.load(path, weights_only=True)
        torch.save(value + 1, path)
        record["sha256"]["conv_states"] = hashlib.sha256(path.read_bytes()).hexdigest()
        index = capture / "d12_prompt_tail/index.jsonl"
        rows = [json.loads(line) for line in index.read_bytes().splitlines()]
        rows[0] = record
        index.write_text("".join(json.dumps(row) + "\n" for row in rows))
    events_path.write_text("".join(json.dumps(row) + "\n" for row in events))
    with pytest.raises(ValueError):
        read_state_tail(capture, **args)
