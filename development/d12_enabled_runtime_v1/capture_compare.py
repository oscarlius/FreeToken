"""Join two stopped captures with ordinary SSE and pinned D03 numeric metrics.

This consumer does not choose a tolerance, run a service, or publish a verdict.
"""
from __future__ import annotations

import json
from pathlib import Path

from capture_reader import read_state_tail
from natural_capture import POLICY_FILE, REPORT_FILE
from ordinary_sse import _read
from prompt_tail import load_d03, validate_d03
from sse_compare import NATIVE_API_SHA256, read_native_sse


ACCOUNTING_SOURCES = {
    "python/freetoken/server/generation.py": "536affffc4de7ef6da883d284885cc393b3759964790a97c202203aa881c074c",
    "python/freetoken/tokenizer/server.py": "7ab5e4a630c058cea42a52582e0817cc7359c4441b26fbe67b3c6cc79a3268d6",
    "python/freetoken/scheduler/prefill.py": "52a4e53b072e7a325fec79f80881e726c8799531c8756f7ce09e54f9b1fe277b",
    "python/freetoken/scheduler/scheduler.py": "90c34945cb47126c8316c11569c72574eec27c3033890a55f4b423f31f9a2b0e",
}


def _require(condition, message):
    if not condition:
        raise ValueError("D12 capture comparison: " + message)


def _first_difference(left, right):
    for index, (a, b) in enumerate(zip(left, right)):
        if a != b:
            return index
    return min(len(left), len(right)) if len(left) != len(right) else None


def compare_capture_pair(reference, candidate, *, expected_natural_policy, expected_tail_policy,
                         expected_vocab_size, expected_state_layout, expected_moe_layer_ids,
                         d03_root, candidate_root, payload_paths, ordinary_client):
    """Compare a caller-selected pair; arm roles/calibration remain caller-owned.

    Each arm supplies capture, process_identity, threshold, and sse (UID ->
    path/sha256). Common expectations and payload paths are supplied separately.
    No configuration or tolerance is inferred from the observed differences.
    """
    source = Path(candidate_root).absolute()
    api = source / "python/freetoken/server/openai_api.py"

    def check_sources():
        for relative, digest in ACCOUNTING_SOURCES.items():
            _read(source / relative, digest)
        _read(api, NATIVE_API_SHA256)
        validate_d03(d03_root)

    check_sources()
    _require(set(payload_paths) == {0, 1, 2} and all(type(uid) is int for uid in payload_paths),
             "three external frozen payload paths required")
    roots = [Path(arm["capture"]).absolute() for arm in (reference, candidate)]
    _require(roots[0] != roots[1] and roots[0] not in roots[1].parents and roots[1] not in roots[0].parents,
             "independent capture directories required")
    _require(tuple(reference["process_identity"][key] for key in ("pid", "start_ticks"))
             != tuple(candidate["process_identity"][key] for key in ("pid", "start_ticks")),
             "distinct physical worker identities required")
    specs = {row["uid"]: row for row in expected_tail_policy["requests"]}
    _require(list(specs) == [0, 1, 2], "three frozen input specifications required")
    reads, streams, tokens, sampler_files = [], [], [], []
    for arm, root in zip((reference, candidate), roots):
        _require(set(arm["sse"]) == {0, 1, 2} and all(type(uid) is int for uid in arm["sse"]),
                 "three external stream path/SHA bindings required")
        result = read_state_tail(root, expected_natural_policy=expected_natural_policy,
            expected_tail_policy=expected_tail_policy, process_identity=arm["process_identity"],
            expected_vocab_size=expected_vocab_size, expected_state_layout=expected_state_layout,
            d03_root=d03_root, expected_moe_layer_ids=expected_moe_layer_ids,
            expected_routed_only_threshold=arm["threshold"], candidate_root=source)
        report = json.loads(_read(root / REPORT_FILE, result["natural_delivery"]["report_sha256"]))
        # Retain the native sampler's existing manifest -> receipt -> snapshot
        # chain for the final stability check; do not reinterpret its semantics.
        files = [(root / POLICY_FILE, result["natural_delivery"]["policy_sha256"]),
                 (root / "sampler/manifest.json", result["natural_delivery"]["sampler_manifest_sha256"])]
        manifest = json.loads(_read(*files[-1]))
        for entry in manifest["captures"]:
            folder = root / "sampler" / entry["id"]
            receipt = json.loads(_read(folder / "receipt.json", entry["receipt_sha256"]))
            files.extend([(folder / "receipt.json", entry["receipt_sha256"]),
                          (folder / receipt["snapshot"]["path"], receipt["snapshot"]["sha256"])])
        for path, digest in files:
            _read(path, digest)
        sampler_files.extend(files)
        delivered = {uid: [] for uid in specs}
        for row in report["deliveries"]:
            token = row["next_token"]
            _require(type(token) is int and 0 <= token < expected_vocab_size, "delivered token outside full vocabulary")
            delivered[row["uid"]].append(token)
        decoded = {}
        for uid, spec in specs.items():
            stream = arm["sse"][uid]
            decoded[uid] = read_native_sse(stream["path"], payload_paths[uid], raw_sha=stream["sha256"],
                payload_sha=spec["payload_sha256"], expected_uid=uid, api_source=api, ordinary_client=ordinary_client)
            usage = decoded[uid]["wire_usage"]
            first_outer = next(row for row in result["observed_outer_segments"] if row["uid"] == uid)
            cached = usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)
            _require(usage["prompt_tokens"] == spec["input_length"]
                     and usage["completion_tokens"] == len(delivered[uid])
                     and cached == first_outer["start"], "SSE usage differs from admitted input/delivery/initial cache")
        reads.append(result)
        streams.append(decoded)
        tokens.append(delivered)

    d03 = load_d03(d03_root)
    requests = {}
    for uid, spec in specs.items():
        rows = [dict(result["tail_records"][uid], _dir=str(root / "d12_prompt_tail"))
                for root, result in zip(roots, reads)]
        logits = [d03.reader.read_tensor(row["_dir"], row, "logits") for row in rows]
        _require(d03.reader.binding(rows[0], logits[0]) == d03.reader.binding(rows[1], logits[1]),
                 "cross-arm full input/K/positions differ")
        metrics = d03.reader.metrics(logits[1], logits[0])
        mismatch = metrics["first_bitwise_mismatch"]
        metrics["first_bitwise_input_position"] = spec["positions"][mismatch] if mismatch is not None else None
        metrics["first_state_difference"] = d03.reader.state_difference(rows[1], rows[0])
        a, b = streams[0][uid], streams[1][uid]
        _require(Path(reference["sse"][uid]["path"]).absolute() != Path(candidate["sse"][uid]["path"]).absolute(),
                 "independent response files required")
        _require(a["openai_version"] == b["openai_version"], "SDK versions differ")
        requests[str(uid)] = {
            "generated_tokens_equal": tokens[0][uid] == tokens[1][uid],
            "first_generated_token_difference": _first_difference(tokens[0][uid], tokens[1][uid]),
            "reference_token_ids": tokens[0][uid], "candidate_token_ids": tokens[1][uid],
            "sse_semantics_equal": a["semantic_completion"] == b["semantic_completion"],
            "end_states_bitwise_equal": metrics["first_state_difference"] is None,
            "prompt_tail_metrics": metrics, "reference_sse": a, "candidate_sse": b,
        }
    # The bound readers also validate histories and each native final state.
    # Recheck all consumed files after cross-arm reads to reject mid-read changes.
    for root, result, arm in zip(roots, reads, (reference, candidate)):
        for relative, digest in result["artifact_sha256"].items():
            _read(root / relative, digest)
        for uid, stream in arm["sse"].items():
            _read(stream["path"], stream["sha256"])
            _read(payload_paths[uid], specs[uid]["payload_sha256"])
    check_sources()
    for path, digest in sampler_files:
        _read(path, digest)
    return {
        "schema": "ft_d12_capture_pair_metrics/v1", "requests": requests,
        "reference_capture": reads[0], "candidate_capture": reads[1],
        "accounting_source_sha256": ACCOUNTING_SOURCES,
        "all_generated_tokens_equal": all(row["generated_tokens_equal"] for row in requests.values()),
        "all_sse_semantics_equal": all(row["sse_semantics_equal"] for row in requests.values()),
        "all_end_states_bitwise_equal": all(row["end_states_bitwise_equal"] for row in requests.values()),
        "all_prompt_tail_logits_bitwise_equal": all(row["prompt_tail_metrics"]["bitwise_equal"] for row in requests.values()),
        "numerical_acceptance_verified": False, "output_equivalence_verified": False, "performance_eligible": False,
        "calibration_status": "no independent numerical acceptance policy applied",
        "scope": "bound pairwise output comparison and D03 metrics; no model acceptance or D04 verdict",
    }
