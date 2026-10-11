"""Use native eager-prefill D0 records as the independent MoE call denominator."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from transfer_audit import ROLES


SOURCES = {
    "python/freetoken/engine/engine.py": "ee25277aac43720514cad160f2f886761d147235efde3baf27e93914e66cbbde",
    "python/freetoken/engine/graph.py": "0a4a9018c56d29c9bf4b91d739360a112006de5fcd75fed764153a5b15da7472",
    "python/freetoken/models/qwen4_exp/model.py": "d7f2a1d3d1ff390ec2a7ea1e17a3100a4c6d184c8ac405e96b718bb79e42de9a",
    "python/freetoken/models/qwen4_exp/moe.py": "71937e6d432cc2e460ffccbde0264d05ad65002e67e482304d22d2f040c6f5db",
    "python/freetoken/models/qwen3_5_moe/moe.py": "36a417fe3361fda69a124d871187a976b862e045890cfb840f6fb0a8e0238c7b",
    "python/freetoken/layers/moe.py": "6ddb79209f3a837251c56447eb3307a514a7e06462c4c6057543da193403fc93",
    "python/freetoken/moe/offload_cache.py": "589688ec591fa441f18f4b9992000913b3246874c25f9720f9bd653608fbf4e4",
    "python/freetoken/core.py": "006811ca4050ac4474407a511b8303fb67c469da9f41d58d48dc9ea2f39ecb91",
    "python/freetoken/scheduler/prefill.py": "52a4e53b072e7a325fec79f80881e726c8799531c8756f7ce09e54f9b1fe277b",
}


def _require(condition, message):
    if not condition:
        raise ValueError("D12 D0 coverage: " + message)


def _int(value, minimum=0):
    return type(value) is int and value >= minimum


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def validate_sources(root):
    root = Path(root).absolute()
    for relative, digest in SOURCES.items():
        path = root / relative
        _require(path.resolve() == path and path.is_file() and _digest(path.read_bytes()) == digest,
                 "candidate call/graph/phase source differs: " + relative)


def read_coverage(states, bank_events, *, read_file, expected_layer_ids, expected_threshold, candidate_root):
    """Consume already admission-bound events; return coverage separately from bank success.

    The pinned native GraphRunner only graphs decode. Batch phase is mutually
    exclusive, so ordinary prefill and layer-major prefill are both eager here.
    No decode graph/timeline setting needs changing to obtain this denominator.
    """
    validate_sources(candidate_root)
    _require(isinstance(expected_layer_ids, list) and expected_layer_ids
             and all(_int(n) for n in expected_layer_ids)
             and expected_layer_ids == list(range(len(expected_layer_ids))), "external complete MoE layer IDs required")
    _require(type(expected_threshold) is int and expected_threshold in (0, 256), "external threshold 0/256 required")
    raw = read_file("d12_d0_prefill.jsonl")
    offset, all_calls, expected_banks, observed_devices, per_uid = 0, [], [], set(), {}
    for state in states:
        outer, bound = state["outer"], state.get("native_d0")
        _require(isinstance(bound, dict) and bound["path"] == "d12_d0_prefill.jsonl"
                 and _int(bound["byte_offset"]) and bound["byte_offset"] == offset
                 and _int(bound["bytes"], 1), "missing/invalid outer-to-D0 append binding")
        line = raw[offset:offset + bound["bytes"]]
        offset += bound["bytes"]
        _require(len(line) == bound["bytes"] and line.endswith(b"\n") and len(line.splitlines()) == 1
                 and _digest(line) == bound["sha256"] and json.loads(line) == bound["record"],
                 "D0 byte range/SHA/record differs")
        record = bound["record"]
        _require(_int(record["chunk"]) and record["chunk"] == outer["outer_segment_index"]
                 and type(record["start"]) is int and record["start"] == outer["start"]
                 and type(record["end"]) is int and record["end"] == outer["end"]
                 and bound["eager_prefill"] is True and bound["prefill_overlap"] is False
                 and type(bound["cache_num_layers"]) is int and bound["cache_num_layers"] == len(expected_layer_ids)
                 and type(bound["routed_only_threshold"]) is int and bound["routed_only_threshold"] == expected_threshold
                 and bound["device_type"] in ("cpu", "cuda"), "D0 native outer/configuration differs")
        observed_devices.add(bound["device_type"])
        lengths = record["subchunks"]
        _require(isinstance(lengths, list) and lengths and all(_int(n, 1) for n in lengths)
                 and sum(lengths) == outer["end"] - outer["start"]
                 and record["mode"] in ("ordinary", "layer_major")
                 and (record["mode"] == "layer_major" or lengths == [outer["end"] - outer["start"]]),
                 "D0 actual child partition differs")
        # Cached tokens are admission accounting, not the absolute position:
        # native PrefillManager logs zero again on continuation chunks.
        _require(record["reqs"] in ([], *[[{"rid": outer["uid"], "new_tokens": outer["end"] - outer["start"],
                                           "cached_tokens": cached}] for cached in (0, outer["start"])]),
                 "D0 request metadata differs")
        _require(all(_int(record[key]) for key in ("h2d_bytes", "d2d_bytes")), "invalid native byte counters")
        children, start = [], outer["start"]
        for length in lengths:
            children.append((start, start + length))
            start += length
        calls = [(outer["uid"], outer["outer_segment_index"], layer, lo, hi)
                 for layer in expected_layer_ids for lo, hi in children]
        layers = record["layers"]
        _require(isinstance(layers, list) and len(layers) == len(calls)
                 and [row["layer"] for row in layers] == [call[2] for call in calls],
                 "D0 completed layer/child call denominator differs")
        for row in layers:
            _require(type(row["layer"]) is int and set(row) == {"layer", "copy_ms", "compute_ms", "d2d_ms"}
                     and all(type(row[key]) in (int, float) and math.isfinite(row[key]) and row[key] >= 0
                             for key in ("copy_ms", "compute_ms")) and row["d2d_ms"] is None,
                     "D0 non-overlap compute/copy record is incomplete")
        all_calls.extend(calls)
        eligible = [call for call in calls if 0 < expected_threshold >= call[4] - call[3]]
        expected_banks.extend(eligible)
        per_uid.setdefault(str(outer["uid"]), {"moe_calls": 0, "eligible_calls": 0})
        per_uid[str(outer["uid"])]["moe_calls"] += len(calls)
        per_uid[str(outer["uid"])]["eligible_calls"] += len(eligible)
    _require(states and offset == len(raw) and len(observed_devices) == 1, "extra D0 bytes or mixed device scopes")
    keys = [(row["context"]["uid"], row["context"]["outer_segment_index"], row["layer_id"],
             row["context"]["child_start"], row["context"]["child_end"]) for row in bank_events]
    _require(keys == expected_banks and all(type(row["layer_id"]) is int for row in bank_events),
             "missing/extra/reordered eligible routed-bank calls")
    cuda = observed_devices == {"cuda"}
    fallbacks, successes = [], 0
    for row in bank_events:
        if row["schema"] == "ft_d12_routed_bank_fallback/v1":
            _require(row["equality_verified"] is False and isinstance(row["reason"], str) and row["reason"],
                     "fallback incorrectly claims equality")
            fallbacks.append({"context": row["context"], "layer_id": row["layer_id"], "reason": row["reason"]})
            continue
        _require(row["schema"] == "ft_d12_routed_bank_equality/v1"
                 and row["scope"] == ("cuda_resident_rows" if cuda else "cpu_protocol_only")
                 and row["bidirectional_mapping_equal"] is True and row["all_selected_bank_bytes_equal"] is True
                 and row["performance_sample"] is False and row["physical_h2d_bytes_inferred"] is False
                 and row["max_temporary_expert_rows"] == 8
                 and row["prefill_segment_tokens"] == row["context"]["child_tokens"], "bank evidence scope differs")
        experts, slots = row["unique_experts"], row["resident_slots"]
        _require(isinstance(experts, list) and experts and all(_int(n) for n in experts)
                 and experts == sorted(set(experts)) and isinstance(slots, list) and len(slots) == len(experts)
                 and all(_int(n) for n in slots) and len(set(slots)) == len(slots), "expert/slot mapping differs")
        _require([bank["role"] for bank in row["banks"]] == list(ROLES), "six-bank role order differs")
        for bank, dtype, width in zip(row["banks"], ("torch.uint8", "torch.float8_e4m3fn", "torch.float16") * 2,
                                      (1, 1, 2) * 2):
            shape = bank["row_shape"]
            digest = bank["source_sha256"]
            _require(isinstance(shape, list) and all(_int(n, 1) for n in shape) and bank["dtype"] == dtype
                     and type(bank["selected_rows"]) is int and bank["selected_rows"] == len(experts)
                     and type(bank["compared_bytes"]) is int
                     and bank["compared_bytes"] == len(experts) * math.prod(shape) * width
                     and isinstance(digest, str) and len(digest) == 64 and all(c in "0123456789abcdef" for c in digest)
                     and bank["resident_sha256"] == digest and bank["bytewise_equal"] is True,
                     "selected bank byte coverage/digest differs")
        successes += 1
    validate_sources(candidate_root)
    verified_banks = cuda and successes > 0 and successes == len(expected_banks) and not fallbacks
    return {"d0_protocol_verified": True, "prefill_schedule_verified": cuda,
            "eligible_bank_call_events_complete": True, "bank_coverage_verified": verified_banks,
            "completed_moe_calls": len(all_calls), "eligible_bank_calls": len(expected_banks), "per_uid_calls": per_uid,
            "routed_bank_successes": successes, "routed_bank_fallbacks": fallbacks,
            "routed_path_exercised": successes > 0,
            "routed_bank_bytes_verified": verified_banks,
            "d0_source_sha256": SOURCES, "performance_eligible": False}
