#!/usr/bin/env python3
"""Capture fixed raw-token inputs and compare prompt-tail logits without a tolerance."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import time
import urllib.request
from pathlib import Path

import torch

STATE_ROLES = {"conv_states", "recurrent_states", "slot:ple_conv", "slot:ple_ngram_ctx"}


def ids(path):
    tokens = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(tokens, list) or not tokens or any(
        type(token) is not int or not 0 <= token <= 2**31 - 1 for token in tokens
    ):
        raise ValueError("token JSON must be a nonempty flat int32 list")
    return tokens


def sha(tokens):
    return hashlib.sha256(struct.pack(f"<{len(tokens)}i", *tokens)).hexdigest()


def post(url, model, prompt, k):
    body = {"model": model, "prompt": prompt, "max_tokens": 1, "ignore_eos": True,
            "temperature": 0, "ft_dev_logits_k": k}
    request = urllib.request.Request(url.rstrip("/") + "/v1/completions",
                                     data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=3600) as response:
        return json.loads(response.read())


def read_tensor(directory, row, role):
    root = Path(directory).resolve()
    path = root / row["files"][role]
    if root not in path.resolve().parents:
        raise ValueError(f"tensor path escapes dump directory: {role}")
    digest = (row.get("sha256") or {}).get(role)
    if digest is not None and hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError(f"tensor SHA mismatch: {role}")
    tensor = torch.load(path, map_location="cpu", weights_only=True)
    if not isinstance(tensor, torch.Tensor) or not torch.isfinite(tensor).all():
        raise ValueError(f"invalid or non-finite tensor: {role}")
    return tensor


def latest(directory, old=0, expected_sha=None, expected_k=None, expected_length=None):
    index = Path(directory) / "index.jsonl"
    for _ in range(120):
        rows = [json.loads(line) for line in index.read_text().splitlines() if line] if index.exists() else []
        for row in reversed(rows):
            extra = row.get("extra") or {}
            if row.get("kind") != "logits" or int(row.get("seq", 0)) <= old:
                continue
            if any(expected is not None and extra.get(key) != expected for key, expected in (
                ("input_prefix_sha256", expected_sha), ("k", expected_k), ("input_length", expected_length)
            )):
                continue
            if "logits" in row.get("files", {}):
                return row, read_tensor(directory, row, "logits")
        time.sleep(.25)
    raise RuntimeError("no matching new logits record")


def binding(row, logits):
    extra = row.get("extra") or {}
    digest, k, length = (extra.get(name) for name in ("input_prefix_sha256", "k", "input_length"))
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("capture lacks the full input SHA256")
    if type(k) is not int or not 1 <= k <= 64 or type(length) is not int or length < k:
        raise ValueError("capture lacks valid K/input-length binding")
    positions = extra.get("positions")
    if positions != list(range(length - k, length)) or logits.ndim != 2 or logits.shape[0] != k:
        raise ValueError("capture positions or logits rows do not match K")
    if logits.dtype != torch.float32 or logits.shape[1] < 2:
        raise ValueError("capture must contain full fp32 vocabulary logits")
    return digest, k, length, positions


def valid_restore_proof(proof, uid, cached_len):
    return (
        isinstance(proof, dict) and proof.get("kind") in {"host", "device"}
        and all(type(proof.get(key)) is int and proof[key] > 0 for key in ("source_slot", "destination_slot"))
        and type(cached_len) is int and type(proof.get("length")) is int
        and 0 < proof["length"] <= cached_len and proof.get("uid") == uid
    )


def capture(args):
    prefix, suffix = ids(args.prefix), ids(args.suffix)
    if len(suffix) > 64:
        raise ValueError("fixed suffix X must contain at most 64 tokens")
    full = prefix + suffix
    index = Path(args.dump) / "index.jsonl"
    old = max((json.loads(line).get("seq", 0) for line in index.read_text().splitlines() if line), default=0) if index.exists() else 0
    warm = post(args.base_url, args.model, prefix, 0)
    measured = post(args.base_url, args.model, full, len(suffix))
    row, logits = latest(args.dump, old, sha(full), len(suffix), len(full))
    digest, k, length, positions = binding(row, logits)
    extra = row["extra"]
    proof = extra.get("restore_proof")
    if args.require_restore and not valid_restore_proof(proof, row.get("uid"), extra.get("cached_len")):
        raise ValueError("measurement did not prove an actual state restore")
    result = {"warm_input_sha256": sha(prefix), "suffix_sha256": sha(suffix),
              "input_sha256": digest, "input_length": length, "k": k, "positions": positions,
              "uid": row.get("uid"), "dump_seq": row["seq"], "warm_usage": warm.get("usage"),
              "measurement_usage": measured.get("usage"), "cached_len": extra.get("cached_len"),
              "restore_proof": proof, "logits_shape": list(logits.shape)}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


def bit_equal(left, right):
    return left.dtype == right.dtype and left.shape == right.shape and torch.equal(
        left.contiguous().view(torch.uint8), right.contiguous().view(torch.uint8)
    )


def metrics(left, right):
    if left.shape != right.shape or left.dtype != right.dtype or left.ndim != 2 or left.shape[1] < 2:
        raise ValueError("logits shape or dtype mismatch")
    if not torch.isfinite(left).all() or not torch.isfinite(right).all():
        raise ValueError("non-finite logits")
    bits = [bit_equal(a, b) for a, b in zip(left, right)]
    a, b = left.double(), right.double()
    top_a, top_b = a.argmax(-1), b.argmax(-1)
    margins_a, margins_b = torch.topk(a, 2, -1).values, torch.topk(b, 2, -1).values
    kl = (torch.softmax(a, -1) * (torch.log_softmax(a, -1) - torch.log_softmax(b, -1))).sum(-1)
    top_equal = (top_a == top_b).tolist()
    return {"bitwise_equal": all(bits), "bitwise_per_position": bits,
            "top1_per_position": top_equal, "top1_agreement": sum(top_equal) / len(top_equal),
            "top2_margin": (margins_a[:, 0] - margins_a[:, 1]).tolist(),
            "reference_top2_margin": (margins_b[:, 0] - margins_b[:, 1]).tolist(),
            "kl_per_position": kl.tolist(),
            "first_top1_mismatch": next((i for i, equal in enumerate(top_equal) if not equal), None),
            "first_bitwise_mismatch": next((i for i, equal in enumerate(bits) if not equal), None)}


def state_difference(left, right):
    expected = STATE_ROLES | {"logits"}
    if set(left.get("files", {})) != expected or set(right.get("files", {})) != expected:
        raise ValueError("state role sets differ or are incomplete")
    differences = []
    for role in sorted(STATE_ROLES):
        a, b = read_tensor(left["_dir"], left, role), read_tensor(right["_dir"], right, role)
        if a.dtype != b.dtype or a.shape != b.shape or a.ndim < 2 or a.shape[1] != 1:
            raise ValueError(f"state dtype/shape differs for {role}")
        layer_ids = left.get("extra", {}).get("layer_ids", {}).get(role)
        other_ids = right.get("extra", {}).get("layer_ids", {}).get(role)
        if not isinstance(layer_ids, list) or len(layer_ids) != a.shape[0] or layer_ids != other_ids:
            raise ValueError(f"state layer IDs differ or are missing: {role}")
        for i, layer_id in enumerate(layer_ids):
            if type(layer_id) is not int:
                raise ValueError(f"invalid state layer ID: {role}")
            if not bit_equal(a[i], b[i]):
                differences.append({"role": role, "layer_id": layer_id})
    return min(differences, key=lambda item: (item["layer_id"], item["role"])) if differences else None


def compare(args):
    reference, logits = latest(args.recompute)
    bound = binding(reference, logits)
    reference["_dir"] = str(args.recompute)
    candidates = {"peer_vs_recompute": args.peer} if args.peer else {
        "restore_vs_recompute": args.restore, "legal_vs_recompute": args.legal
    }
    result = {"input_prefix_sha256": bound[0], "k": bound[1], "input_length": bound[2], "positions": bound[3]}
    for label, directory in candidates.items():
        row, candidate = latest(directory)
        if binding(row, candidate) != bound:
            raise ValueError("capture SHA/K/input length/positions differ")
        row["_dir"] = str(directory)
        extra = row["extra"]
        if label == "restore_vs_recompute" and args.require_restore and not valid_restore_proof(
            extra.get("restore_proof"), row.get("uid"), extra.get("cached_len")
        ):
            raise ValueError("restore capture lacks actual restore proof")
        values = metrics(candidate, logits)
        first = values["first_bitwise_mismatch"]
        values["first_bitwise_input_position"] = bound[3][first] if first is not None else None
        values["first_state_difference"] = state_difference(row, reference)
        values["restore_proof"] = extra.get("restore_proof")
        result[label] = values
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    capture_parser = sub.add_parser("capture")
    for name in ("base-url", "model", "prefix", "suffix", "dump"):
        capture_parser.add_argument("--" + name, required=True)
    capture_parser.add_argument("--require-restore", action="store_true")
    capture_parser.set_defaults(func=capture)
    compare_parser = sub.add_parser("compare")
    compare_parser.add_argument("--recompute", required=True)
    compare_parser.add_argument("--restore")
    compare_parser.add_argument("--legal")
    compare_parser.add_argument("--peer", help="second independent process using the same arm")
    compare_parser.add_argument("--require-restore", action="store_true")
    compare_parser.set_defaults(func=compare)
    args = parser.parse_args()
    if args.command == "compare" and ((bool(args.peer) and (args.restore or args.legal)) or
                                      (not args.peer and not (args.restore and args.legal))):
        parser.error("compare requires either --peer or both --restore and --legal")
    args.func(args)


if __name__ == "__main__":
    main()
