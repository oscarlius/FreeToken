"""D16 CPU readers; these commands do not start a service or acquire a GPU."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .gate import evaluate
from .cases import batch_envelope, continuation_matrix, restoration_output
from .historical import replay_r023, replay_t16
from .schedule import compile_schedule, read_jsonl, read_schedule, validate_reference, write_new


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    compiler = commands.add_parser("compile")
    compiler.add_argument("--d0", type=Path, required=True)
    compiler.add_argument("--donor-uid", required=True)
    compiler.add_argument("--hit-uid", required=True)
    compiler.add_argument("--cached-tokens", type=int, required=True)
    compiler.add_argument("--prompt-tokens", type=int, required=True)
    compiler.add_argument("--output", type=Path, required=True)
    structure = commands.add_parser("check-structure")
    structure.add_argument("--d0", type=Path, required=True)
    structure.add_argument("--uid", required=True)
    structure.add_argument("--schedule", type=Path, required=True)
    replay = commands.add_parser("replay")
    replay.add_argument("--t16-fixture", type=Path, required=True)
    replay.add_argument("--t16-runner", type=Path, required=True)
    replay.add_argument("--r023-review", type=Path, required=True)
    replay.add_argument("--r023-review-sha256", required=True)
    replay.add_argument("--output", type=Path, required=True)
    gate = commands.add_parser("evaluate")
    gate.add_argument("--evidence", type=Path, required=True)
    gate.add_argument("--output", type=Path, required=True)
    commands.add_parser("matrix")
    for name in ("batch-envelope", "restoration-output"):
        command = commands.add_parser(name)
        command.add_argument("--evidence", type=Path, required=True)
        command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "compile":
        rows, digest = read_jsonl(args.d0)
        schedule = compile_schedule(rows, donor_uid=args.donor_uid, hit_uid=args.hit_uid,
                                    cached_tokens=args.cached_tokens, prompt_tokens=args.prompt_tokens)
        schedule_sha = write_new(args.output, schedule)
        result = {"schedule_sha256": schedule_sha, "d0_sha256": digest, "schedule": schedule}
        write_new(args.output.with_name(args.output.name + ".receipt.json"), result)
    elif args.command == "check-structure":
        rows, digest = read_jsonl(args.d0)
        schedule, schedule_sha = read_schedule(args.schedule)
        actual = validate_reference(rows, uid=args.uid, schedule=schedule)
        result = {"structure_verified": True, "d0_sha256": digest,
                  "schedule_sha256": schedule_sha, "segments": actual}
    elif args.command == "replay":
        raw = args.r023_review.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if args.r023_review.is_symlink() or digest != args.r023_review_sha256:
            raise ValueError("R023 review source differs")
        result = {"schema": "ft_equiv_historical/v1", "gpu_started": False,
                  "t16": replay_t16(args.t16_fixture, args.t16_runner),
                  "r023": replay_r023(json.loads(raw), review_sha256=digest)}
        write_new(args.output, result)
    elif args.command == "matrix":
        result = {"continuation_cases": continuation_matrix(), "batch_sizes": [2, 4],
                  "other_cases": ["S-parking", "S-cache", "S-interleave"]}
    elif args.command in ("batch-envelope", "restoration-output"):
        method = batch_envelope if args.command == "batch-envelope" else restoration_output
        result = method(json.loads(args.evidence.read_bytes()))
        write_new(args.output, result)
    else:
        result = evaluate(json.loads(args.evidence.read_bytes()))
        write_new(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
