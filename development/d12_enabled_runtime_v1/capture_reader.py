"""Read stopped D12 state/tail evidence against caller-owned expectations.

This is an artifact consumer, not a service runner or a model acceptance gate.
Bank-call completeness and SSE equivalence remain separate required checks.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

from natural_capture import REPORT_FILE, read_natural_delivery
from prompt_tail import D03_FILES, ROLES, _raw, load_d03


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _require(condition, message):
    if not condition:
        raise ValueError("D12 capture: " + message)


def _integer(value, minimum=0):
    return type(value) is int and value >= minimum


def read_state_tail(capture, *, expected_tail_policy, expected_natural_policy,
                    process_identity, expected_vocab_size, expected_state_layout, d03_root,
                    expected_moe_layer_ids=None, expected_routed_only_threshold=None, candidate_root=None):
    """Verify joins and tensor bytes; never infer missing expectations from artifacts.

    State layout maps each role to its exact shape, torch dtype string and layer
    IDs. Initial cache hits and the full MoE call inventory are reported but are
    not proved by this reader's post-prefill stream.
    """
    import torch

    root = Path(capture).absolute()
    _require(root.resolve() == root and root.is_dir(), "physical capture directory required")
    _require(_integer(expected_vocab_size, 2), "external full vocabulary size required")
    _require(set(expected_state_layout) == ROLES, "external four-role layout required")
    for item in expected_state_layout.values():
        shape, layers = item["shape"], item["layer_ids"]
        _require(isinstance(shape, list) and len(shape) >= 2 and shape[1] == 1
                 and all(_integer(n, 1) for n in shape) and isinstance(layers, list)
                 and len(layers) == shape[0] and len(set(layers)) == len(layers)
                 and all(type(n) is int for n in layers), "invalid external state layout")
    d03 = load_d03(d03_root)
    natural = read_natural_delivery(root, expected_policy=expected_natural_policy,
        process_identity=process_identity, logits_probe=Path(d03_root) / "scripts/logits_probe.py",
        logits_probe_sha256=D03_FILES["scripts/logits_probe.py"])
    artifacts = {}

    def read(relative):
        path = root / relative
        _require(path.resolve() == path and root in path.parents and path.is_file(),
                 "physical file unavailable: " + relative)
        raw = path.read_bytes()
        digest = _sha(raw)
        _require(relative not in artifacts or artifacts[relative] == digest, "file changed while reading")
        artifacts[relative] = digest
        return raw

    def file_name(name):
        _require(isinstance(name, str) and name not in ("", ".", "..")
                 and "/" not in name and "\\" not in name and Path(name).name == name,
                 "invalid tensor filename")
        return name

    def tensor(relative, digest):
        _require(isinstance(digest, str) and len(digest) == 64, "required tensor SHA missing")
        raw = read(relative)
        _require(_sha(raw) == digest, "tensor SHA differs: " + relative)
        value = torch.load(io.BytesIO(raw), map_location="cpu", weights_only=True)
        _require(isinstance(value, torch.Tensor) and bool(torch.isfinite(value).all()),
                 "invalid or non-finite tensor")
        return value

    def state_tensor(value, role):
        layout = expected_state_layout[role]
        _require(list(value.shape) == layout["shape"] and str(value.dtype) == layout["dtype"],
                 "state layout differs: " + role)

    report_raw = read(REPORT_FILE)
    _require(_sha(report_raw) == natural["report_sha256"], "natural report changed")
    report = json.loads(report_raw)
    admissions = {}
    for item in report["admission_receipts"]:
        raw = read(item["receipt_path"])
        _require(_sha(raw) == item["receipt_sha256"], "admission changed")
        admissions[item["uid"]] = json.loads(raw)

    policy_raw = read("d12_prompt_tail/policy.json")
    _require(policy_raw == _raw(expected_tail_policy), "external tail policy differs")
    policy = json.loads(policy_raw)
    _require(policy["schema"] == "ft_d12_prompt_tail_policy/v1"
             and policy["d03_source_sha256"] == D03_FILES
             and policy["prompt_tail_fixed_input"] is True and policy["restore_arm"] is False
             and policy["generated_suffix"] is False and policy["output_equivalence_verified"] is False
             and policy["bundle_sha256"] == expected_natural_policy["bundle_sha256"],
             "tail policy scope differs")
    specs = {item["uid"]: item for item in policy["requests"]}
    _require([item["uid"] for item in policy["requests"]] == list(admissions), "tail UID order differs")
    for source in expected_natural_policy["requests"]:
        uid, spec = source["uid"], specs[source["uid"]]
        ids, k = admissions[uid]["input_ids"], spec["k"]
        _require(_integer(k, 1) and k <= 64 and len(ids) > k
                 and spec["payload_sha256"] == source["payload_sha256"]
                 and spec["input_ids_json_sha256"] == source["input_ids_json_sha256"]
                 and spec["input_length"] == len(ids) and spec["prefix_length"] == len(ids) - k
                 and spec["input_prefix_sha256"] == d03.reader.sha(ids)
                 and spec["prefix_sha256"] == d03.reader.sha(ids[:-k])
                 and spec["suffix_sha256"] == d03.reader.sha(ids[-k:])
                 and spec["positions"] == list(range(len(ids) - k, len(ids))),
                 "tail input coordinates differ from actual admission")

    state_index = [json.loads(line) for line in read("d12_state/index.jsonl").splitlines()]
    tail_index = [json.loads(line) for line in read("d12_prompt_tail/index.jsonl").splitlines()]
    events = [json.loads(line) for line in read("d12_events.jsonl").splitlines()]
    states, tails, banks = [], {}, []
    by_uid = {uid: [] for uid in specs}
    for index, row in enumerate(events):
        event = row["evidence"]
        identity = event.get("context", event.get("outer", {}))
        uid = identity.get("uid")
        _require(_integer(uid) and uid in specs and type(row["d12_event_index"]) is int
                 and row["d12_event_index"] == index, "event index/UID differs")
        spec, admission = specs[uid], admissions[uid]
        _require(row["process_identity"] == process_identity
                 and row["physical_event_identity"] == admission["physical_event_identity"]
                 and row["prompt_ids_sha256"] == admission["input_ids_sha256"]
                 and row["frozen_input"] == {"bundle_sha256": policy["bundle_sha256"],
                     "payload_sha256": spec["payload_sha256"],
                     "input_ids_json_sha256": spec["input_ids_json_sha256"]},
                 "event does not bind the same worker/admission/input")
        schema = event["schema"]
        if schema == "ft_d12_post_prefill_state/v1":
            outer, native = event["outer"], event["native_record"]
            history = by_uid[uid]
            _require(uid not in tails and event["admitted"] is False
                     and all(_integer(outer[key]) for key in ("outer_segment_index", "start", "end", "linear_slot_idx"))
                     and outer["outer_segment_index"] == len(states)
                     and 0 <= outer["start"] < outer["end"] <= spec["input_length"]
                     and (not history or history[-1]["outer"]["end"] == outer["start"]),
                     "outer state geometry/order differs")
            _require(len(state_index) > len(states) and state_index[len(states)] == native
                     and native["kind"] == "d12_post_prefill" and native["uid"] == str(uid)
                     and native["length"] == outer["end"] and native["host_slots"] is None
                     and native["dev_slots"] == [outer["linear_slot_idx"]]
                     and set(native["files"]) == ROLES and set(event["role_files"]) == ROLES,
                     "native state index differs")
            for role, item in event["role_files"].items():
                name = file_name(item["path"])
                _require(native["files"][role] == name, "native state filename differs")
                relative = "d12_state/" + name
                value = tensor(relative, item["sha256"])
                _require(len(read(relative)) == item["bytes"], "state serialized size differs")
                state_tensor(value, role)
            states.append(event)
            history.append(event)
        elif schema == "ft_d12_prompt_tail_logits/v1":
            _require(uid not in tails and by_uid[uid], "duplicate tail or missing state")
            final = by_uid[uid][-1]
            record = event["record"]
            _require(final["outer"]["end"] == spec["input_length"]
                     and identity == {"uid": uid, "outer_segment_index": final["outer"]["outer_segment_index"]}
                     and event["policy_sha256"] == _sha(policy_raw)
                     and event["output_equivalence_verified"] is False
                     and len(tail_index) > len(tails) and tail_index[len(tails)] == record
                     and record["kind"] == "logits" and type(record["uid"]) is int and record["uid"] == uid
                     and record["length"] == spec["input_length"]
                     and set(record["files"]) == ROLES | {"logits"}
                     and set(record["sha256"]) == ROLES | {"logits"}, "tail/index/final-state join differs")
            values = {role: tensor("d12_prompt_tail/" + file_name(name), record["sha256"][role])
                      for role, name in record["files"].items()}
            _require(d03.reader.binding(record, values["logits"]) == (
                spec["input_prefix_sha256"], spec["k"], spec["input_length"], spec["positions"])
                and values["logits"].shape[1] == expected_vocab_size, "full-vocabulary tail binding differs")
            extra = record["extra"]
            _require(extra["restore_proof"] is None and extra["state_length"] == spec["input_length"]
                     and extra["d12_policy_sha256"] == _sha(policy_raw)
                     and extra["layer_ids"] == {role: layout["layer_ids"] for role, layout in expected_state_layout.items()},
                     "tail state metadata differs")
            for role in ROLES:
                state_tensor(values[role], role)
                item = final["role_files"][role]
                native_value = tensor("d12_state/" + item["path"], item["sha256"])
                _require(d03.reader.bit_equal(values[role], native_value), "tail state differs from native end-state")
            positions = []
            for segment in extra["d12_projection_segments"]:
                number = segment["outer_segment_index"]
                _require(_integer(number) and number < len(states), "tail references missing outer")
                outer = states[number]["outer"]
                start, end = segment["child_start"], segment["child_end"]
                _require(segment["uid"] == uid == outer["uid"] and _integer(start) and _integer(end)
                         and outer["start"] <= start < end <= outer["end"]
                         and segment["child_tokens"] == end - start
                         and segment["positions"] == list(range(max(start, spec["prefix_length"]), end))
                         and segment["positions"]
                         and segment["top_mixer_source"] in ("actual_top_mixer", "diagnostic_full_child_top_mixer"),
                         "tail projection geometry differs")
                positions.extend(segment["positions"])
            _require(positions == spec["positions"], "tail projection positions missing/duplicated")
            tails[uid] = record
        elif schema in ("ft_d12_routed_bank_equality/v1", "ft_d12_routed_bank_fallback/v1"):
            _require(identity["outer_segment_index"] == len(states), "bank event lies outside the active outer")
            banks.append(event)
        else:
            raise ValueError("D12 capture: unknown event schema")
    _require(len(states) == len(state_index) and len(tails) == len(tail_index)
             and set(tails) == set(specs), "missing/extra indexed state or tail")
    for event in banks:
        context = event["context"]
        number = context["outer_segment_index"]
        _require(_integer(number) and number < len(states), "bank references missing outer")
        outer = states[number]["outer"]
        _require(context["uid"] == outer["uid"] and _integer(context["child_start"])
                 and _integer(context["child_end"])
                 and outer["start"] <= context["child_start"] < context["child_end"] <= outer["end"]
                 and context["child_tokens"] == context["child_end"] - context["child_start"],
                 "bank references a different child/outer")
    coverage = {"bank_coverage_verified": False, "prefill_schedule_verified": False}
    if any(value is not None for value in (expected_moe_layer_ids, expected_routed_only_threshold, candidate_root)):
        _require(all(value is not None for value in (expected_moe_layer_ids, expected_routed_only_threshold, candidate_root)),
                 "D0 coverage requires external layers, threshold and candidate source")
        from d0_coverage import read_coverage
        coverage = read_coverage(states, banks, read_file=read, expected_layer_ids=expected_moe_layer_ids,
                                 expected_threshold=expected_routed_only_threshold, candidate_root=candidate_root)
    for relative, digest in list(artifacts.items()):
        _require(_sha(read(relative)) == digest, "artifact changed before reader completion")
    return {"schema": "ft_d12_state_tail_read/v1", "state_tail_bound": True,
            "natural_delivery": natural, "artifact_sha256": artifacts,
            "observed_outer_segments": [event["outer"] for event in states],
            "tail_records": tails, "bank_events_observed": len(banks),
            **coverage, "output_equivalence_verified": False, "performance_eligible": False}
