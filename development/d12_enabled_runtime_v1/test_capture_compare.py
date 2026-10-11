"""Two independently emitted CPU captures plus synthetic ordinary SSE, no service."""
import copy
import json
import os
from pathlib import Path

import pytest

if not os.environ.get("FT_D12_NATIVE_SOURCE"):
    pytest.skip("requires pinned native Linux modules", allow_module_level=True)
pytest.importorskip("openai")

import torch

from capture_compare import compare_capture_pair
from test_capture_reader import make_joint_capture
from test_ordinary_sse import client
from test_replay_binding import BUNDLE
from test_sse_compare import write_stream


@pytest.fixture(scope="module")
def captures(tmp_path_factory):
    result = {}
    for index, variant in enumerate(("reference", "same", "state", "logits", "token",
                                     "multi_reference", "multi_same", "multi_late"), start=1):
        identity = {"pid": index, "start_ticks": index, "execution_id": "cpu-pair-" + variant}
        changed = "same" if variant in ("reference", "multi_reference", "multi_same") else variant
        if variant == "multi_late": changed = "token_late"
        result[variant] = make_joint_capture(tmp_path_factory, d0=True, identity=identity,
                                            variant=changed, generations=3 if variant.startswith("multi_") else 1)
    return result


def pair(tmp_path, captures, variant="same", *, stream_fault=None):
    multi = variant.startswith("multi_")
    reference, expected = captures["multi_reference" if multi else "reference"]
    candidate, candidate_expected = captures[variant]
    frozen = json.loads((BUNDLE / "binding.json").read_bytes())
    payloads = {row["uid"]: BUNDLE / row["payload_path"] for row in frozen["selected_history"]}
    assert {k: v for k, v in expected.items() if k != "process_identity"} == {
        k: v for k, v in candidate_expected.items() if k != "process_identity"}
    arms = []
    for side, capture, identity in (("reference", reference, expected["process_identity"]),
                                    ("candidate", candidate, candidate_expected["process_identity"])):
        streams = {}
        for spec in expected["expected_tail_policy"]["requests"]:
            uid = spec["uid"]
            payload = json.loads(payloads[uid].read_bytes())
            base = {"id": f"chatcmpl-{uid}", "object": "chat.completion.chunk",
                    "created": 1 if side == "reference" else 2, "model": payload["model"]}
            deltas = [{"role": "assistant", "content": ""}, {"reasoning_content": "CPU fixture only"},
                {"tool_calls": [{"index": 0, "id": "call_list-dir_0_" + ("12345678" if side == "reference" else "87654321"),
                    "type": "function", "function": {"name": "list_dir", "arguments": ""}}]},
                {"tool_calls": [{"index": 0, "function": {"arguments": '{"path":"."}'}}]}]
            chunks = [{**base, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]} for delta in deltas]
            count = 3 if multi else 1
            chunks += [{**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]},
                {**base, "choices": [], "usage": {"prompt_tokens": spec["input_length"], "completion_tokens": count,
                                                 "total_tokens": spec["input_length"] + count}}]
            if side == "candidate" and uid == 1:
                if stream_fault == "semantic": chunks[1]["choices"][0]["delta"]["reasoning_content"] += " differs"
                elif stream_fault == "count":
                    chunks[-1]["usage"]["completion_tokens"] += 1
                    chunks[-1]["usage"]["total_tokens"] += 1
                elif stream_fault == "prompt":
                    chunks[-1]["usage"]["prompt_tokens"] += 1
                    chunks[-1]["usage"]["total_tokens"] += 1
                elif stream_fault == "cache": chunks[-1]["usage"]["prompt_tokens_details"] = {"cached_tokens": 1}
            path, digest = write_stream(tmp_path / f"{side}-{uid}.sse", chunks)
            streams[uid] = {"path": path, "sha256": digest}
        arms.append({"capture": capture, "process_identity": identity, "threshold": 0, "sse": streams})
    args = {key: expected[key] for key in ("expected_natural_policy", "expected_tail_policy", "expected_vocab_size",
            "expected_state_layout", "expected_moe_layer_ids", "d03_root", "candidate_root")}
    args.update(payload_paths=payloads, ordinary_client=client)
    return arms, args


@pytest.mark.parametrize("variant", ["same", "state", "logits", "token"])
def test_native_component_pair_reports_independent_axes_without_numeric_verdict(tmp_path, captures, variant):
    arms, args = pair(tmp_path, captures, variant)
    result = compare_capture_pair(*arms, **args)
    assert result["all_generated_tokens_equal"] is (variant != "token")
    assert result["all_sse_semantics_equal"]
    assert result["all_end_states_bitwise_equal"] is (variant != "state")
    assert result["all_prompt_tail_logits_bitwise_equal"] is (variant not in ("logits", "token"))
    assert not result["numerical_acceptance_verified"] and not result["output_equivalence_verified"]
    assert not result["performance_eligible"] and not torch.cuda.is_initialized()
    for request in result["requests"].values():
        assert request["first_generated_token_difference"] == (0 if variant == "token" else None)
        metrics = request["prompt_tail_metrics"]
        assert metrics["top1_agreement"] == (0 if variant == "token" else 1)
        assert len(metrics["kl_per_position"]) == 64
        assert metrics["first_state_difference"] == ({"role": "conv_states", "layer_id": 0} if variant == "state" else None)
    (tmp_path / "capture_pair_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))


def test_same_tokens_do_not_hide_different_sse_semantics(tmp_path, captures):
    arms, args = pair(tmp_path, captures, stream_fault="semantic")
    result = compare_capture_pair(*arms, **args)
    assert result["all_generated_tokens_equal"] and not result["all_sse_semantics_equal"]
    assert not result["requests"]["1"]["sse_semantics_equal"]
    (tmp_path / "capture_pair_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))


@pytest.mark.parametrize("variant", ["multi_same", "multi_late"])
def test_complete_multi_token_delivery_compares_the_last_token(tmp_path, captures, variant):
    arms, args = pair(tmp_path, captures, variant)
    result = compare_capture_pair(*arms, **args)
    assert result["all_generated_tokens_equal"] is (variant == "multi_same")
    assert result["all_sse_semantics_equal"] and result["all_prompt_tail_logits_bitwise_equal"]
    for row in result["requests"].values():
        assert row["reference_token_ids"] == [4, 4, 4]
        assert row["candidate_token_ids"] == ([4, 4, 4] if variant == "multi_same" else [4, 4, 0])
        assert row["first_generated_token_difference"] == (None if variant == "multi_same" else 2)
        assert row["reference_sse"]["wire_usage"]["completion_tokens"] == 3
        assert row["candidate_sse"]["wire_usage"]["completion_tokens"] == 3
    (tmp_path / "capture_pair_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))


@pytest.mark.parametrize("fault", ["count", "prompt", "cache", "same_capture", "same_worker", "same_physical_worker", "same_sse", "source",
                                  "missing_stream", "wrong_sha", "payload", "threshold", "identity"])
def test_pair_rejects_unbound_or_inconsistent_inputs(tmp_path, captures, fault):
    arms, args = pair(tmp_path, captures, stream_fault=fault)
    if fault == "same_capture": arms[1]["capture"] = arms[0]["capture"]
    elif fault == "same_worker": arms[1]["process_identity"] = arms[0]["process_identity"]
    elif fault == "same_physical_worker":
        arms[1]["process_identity"] = {**arms[0]["process_identity"], "execution_id": "different-label-same-process"}
    elif fault == "same_sse": arms[1]["sse"][0] = arms[0]["sse"][0]
    elif fault == "source": args["candidate_root"] = tmp_path
    elif fault == "missing_stream": arms[1]["sse"].pop(0)
    elif fault == "wrong_sha": arms[1]["sse"][0]["sha256"] = "0" * 64
    elif fault == "payload": args["payload_paths"][0] = args["payload_paths"][1]
    elif fault == "threshold": arms[1]["threshold"] = 256
    elif fault == "identity": arms[1]["process_identity"] = {**arms[1]["process_identity"], "start_ticks": 999}
    with pytest.raises((ValueError, RuntimeError)):
        compare_capture_pair(*arms, **args)
