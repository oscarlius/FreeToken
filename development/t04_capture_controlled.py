"""Controlled raw-token captures for the T04 phase-two payloads.

The frozen D03 probe owns HTTP encoding, dump selection, and diagnostic
validation.  This wrapper controls only the request history that precedes a
capture, so a warm prefix cannot be mistaken for a fresh computation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from types import ModuleType
from typing import Any, Sequence


REPOSITORY = Path("/data2/FreeToken")
FROZEN_PROBE = REPOSITORY / "wt/e1r003st/scripts/logits_probe.py"
FROZEN_PROBE_SHA256 = (
    "7ab4fd3a256c2fd3d510bd63d77b5181a648e5d8f8609ebf1a52b68f3a6c45e7"
)
DEFAULT_MODEL = "Qwen3.8-Flash-Next-NVFP4"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_frozen_probe(path: Path = FROZEN_PROBE) -> ModuleType:
    """Load only the reviewed probe source, after pinning its bytes."""
    source = path.read_bytes()
    if hashlib.sha256(source).hexdigest() != FROZEN_PROBE_SHA256:
        raise RuntimeError(f"frozen logits_probe SHA256 mismatch: {path}")
    module = ModuleType("t04_frozen_logits_probe")
    module.__file__ = str(path)
    module.__package__ = ""
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


def _write_exclusive(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output:
        json.dump(value, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.write("\n")


def _last_sequence(dump: Path) -> int:
    index = dump / "index.jsonl"
    if not index.is_file():
        return 0
    maximum = 0
    for line in index.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        sequence = row.get("seq")
        if type(sequence) is int and sequence > maximum:
            maximum = sequence
    return maximum


def _require_token_list(tokens: Sequence[int], name: str) -> list[int]:
    copied = list(tokens)
    if not copied or any(type(token) is not int or token < 0 for token in copied):
        raise ValueError(f"{name} must be a non-empty list of non-negative integers")
    return copied


def branch_prompt(
    prefix: Sequence[int], branch_length: int, branch_token_count: int
) -> tuple[list[int], dict[str, Any]]:
    """Build a legal competing branch with exactly the requested shared prefix."""
    source = _require_token_list(prefix, "prefix")
    if type(branch_length) is not int or not 0 < branch_length < len(source):
        raise ValueError("branch length must be inside the prefix")
    if type(branch_token_count) is not int or branch_token_count <= 0:
        raise ValueError("branch token count must be positive")

    reference = source[branch_length]
    tail = source[branch_length + 1 :]
    first = next((token for token in tail if token != reference), None)
    if first is None or len(tail) < branch_token_count - 1:
        raise ValueError("prefix cannot supply a distinct legal branch token sequence")

    branch_tokens = [first, *tail[: branch_token_count - 1]]
    prompt = [*source[:branch_length], *branch_tokens]
    details = {
        "common_prefix_length": branch_length,
        "branch_token_count": branch_token_count,
        "full_prompt_next_token": reference,
        "branch_first_token": first,
        "prefix_length": len(source),
    }
    return prompt, details


def _result_from_dump(
    probe: Any,
    dump: Path,
    old_sequence: int,
    full_prompt: list[int],
    k: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    expected_sha = probe.sha(full_prompt)
    row, logits = probe.latest(
        dump,
        old_sequence,
        expected_sha=expected_sha,
        expected_k=k,
        expected_length=len(full_prompt),
    )
    actual_sha, actual_k, actual_length, positions = probe.binding(row, logits)
    if actual_sha != expected_sha or actual_k != k or actual_length != len(full_prompt):
        raise RuntimeError("frozen probe returned a dump for a different raw input")

    extra = row.get("extra")
    if not isinstance(extra, dict):
        raise RuntimeError("logits index row lacks diagnostic metadata")
    cached_len = extra.get("cached_len")
    if type(cached_len) is not int or cached_len < 0:
        raise RuntimeError("logits index row has invalid cached_len")
    uid = row.get("uid")
    if type(uid) is not int or uid < 0:
        raise RuntimeError("logits index row has invalid uid")
    shape = getattr(logits, "shape", None)
    if shape is None:
        raise RuntimeError("logits dump has no shape")

    record = {
        "uid": uid,
        "dump_seq": row.get("seq"),
        "k": actual_k,
        "input_length": actual_length,
        "input_sha256": actual_sha,
        "positions": list(positions),
        "logits_shape": list(shape),
        "cached_len": cached_len,
        "restore_proof": extra.get("restore_proof"),
    }
    return record, extra


def capture_controlled(
    *,
    probe: Any,
    base_url: str,
    prefix: Sequence[int],
    suffix: Sequence[int],
    dump: Path,
    model: str,
    mode: str,
    branch_length: int = 12672,
    branch_token_count: int = 96,
) -> dict[str, Any]:
    """Capture a raw P+X request under an explicitly controlled history."""
    prefix_ids = _require_token_list(prefix, "prefix")
    suffix_ids = _require_token_list(suffix, "suffix")
    k = len(suffix_ids)
    if k > 64:
        raise ValueError("suffix length must be between one and 64 tokens")
    if mode not in {"fresh", "branch-bank", "diagnostic"}:
        raise ValueError("mode must be fresh, branch-bank, or diagnostic")

    full_prompt = [*prefix_ids, *suffix_ids]
    old_sequence = _last_sequence(dump)
    priming: dict[str, Any] = {"warm_usage": None}

    if mode == "branch-bank":
        branch_ids, branch_details = branch_prompt(
            prefix_ids, branch_length, branch_token_count
        )
        _write_exclusive(
            dump / "branch_ids.json",
            {
                **branch_details,
                "branch_ids": branch_ids,
                "branch_sha256": probe.sha(branch_ids),
                "full_input_sha256": probe.sha(full_prompt),
                "full_input_length": len(full_prompt),
            },
        )
        branch_response = probe.post(base_url, model, branch_ids, 0)
        priming["branch_usage"] = branch_response.get("usage")
        priming["branch_input_length"] = len(branch_ids)
        priming["common_prefix_length"] = branch_length

    measurement_response = probe.post(base_url, model, full_prompt, k)
    record, extra = _result_from_dump(probe, dump, old_sequence, full_prompt, k)
    proof = record["restore_proof"]

    if mode == "fresh":
        if record["cached_len"] != 0 or proof is not None:
            raise RuntimeError("fresh capture unexpectedly used cached state")
    elif mode == "branch-bank":
        if record["cached_len"] != branch_length:
            raise RuntimeError("branch-bank capture did not restore the declared prefix")
        if not probe.valid_restore_proof(proof, record["uid"], record["cached_len"]):
            raise RuntimeError("branch-bank capture lacks a valid restore proof")
        if proof["length"] != branch_length:
            raise RuntimeError("branch-bank proof restored less than the declared prefix")

    result = {
        **record,
        "mode": mode,
        "warm_usage": None,
        "branch_usage": priming.get("branch_usage"),
        "measurement_usage": measurement_response.get("usage"),
        "priming": priming,
    }
    _write_exclusive(dump / "controlled_capture.json", result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--prefix", required=True, type=Path)
    parser.add_argument("--suffix", required=True, type=Path)
    parser.add_argument("--dump", required=True, type=Path)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--mode", required=True, choices=("fresh", "branch-bank", "diagnostic"))
    parser.add_argument("--branch-length", type=int, default=12672)
    parser.add_argument("--branch-token-count", type=int, default=96)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    probe = load_frozen_probe()
    result = capture_controlled(
        probe=probe,
        base_url=args.base_url,
        prefix=probe.ids(args.prefix),
        suffix=probe.ids(args.suffix),
        dump=args.dump,
        model=args.model,
        mode=args.mode,
        branch_length=args.branch_length,
        branch_token_count=args.branch_token_count,
    )
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
