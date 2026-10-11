#!/usr/bin/env python3
"""Strict CPU state-envelope comparison for FreeToken state-dump directories.

Records are matched by kind, length, UID and (when available) prefix hash.  File
names are deliberately not identities because they include each dump's sequence.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

DEVICE_ROLES = ("conv_states", "recurrent_states", "slot:ple_conv", "slot:ple_ngram_ctx")
HOST_ROLES = ("host_conv_states", "host_recurrent_states", "hostslot:ple_conv", "hostslot:ple_ngram_ctx")
ALL_ROLES = frozenset(DEVICE_ROLES + HOST_ROLES)
PREFIX_KEYS = ("prefix_hash", "prefix_sha256", "input_prefix_sha256", "input_ids_sha256")


class EnvelopeError(ValueError):
    """An input is not an unambiguous, comparable state-dump dataset."""


@dataclass(frozen=True)
class Record:
    directory: Path
    row: dict[str, Any]

    @property
    def length(self) -> int:
        return int(self.row["length"])

    @property
    def seq(self) -> int:
        return int(self.row.get("seq", 0))

    @property
    def uid(self) -> str | None:
        value = self.row.get("uid")
        return None if value is None else str(value)

    def metadata(self, key: str) -> Any:
        values = []
        if self.row.get(key) is not None:
            values.append(self.row[key])
        extra = self.row.get("extra")
        if extra is not None:
            if not isinstance(extra, dict):
                raise EnvelopeError(f"extra must be an object in record seq={self.seq}")
            if extra.get(key) is not None:
                values.append(extra[key])
        if len(values) == 2 and values[0] != values[1]:
            raise EnvelopeError(f"conflicting {key} metadata in record seq={self.seq}")
        return values[0] if values else None

    @property
    def prefix_hash(self) -> str | None:
        present = [str(self.metadata(key)) for key in PREFIX_KEYS if self.metadata(key) is not None]
        if len(set(present)) > 1:
            raise EnvelopeError(f"conflicting prefix hashes in record seq={self.seq}")
        return present[0] if present else None


@dataclass
class Selection:
    records: dict[int, Record]
    repeats: dict[int, list[Record]]


def torch_module() -> Any:
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - exercised where torch is absent
        raise EnvelopeError("PyTorch is required; install the existing FreeToken torch dependency") from exc
    return torch


def read_rows(directory: Path) -> list[dict[str, Any]]:
    index = directory / "index.jsonl"
    if not index.is_file():
        raise EnvelopeError(f"missing index.jsonl: {directory}")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(index.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EnvelopeError(f"invalid JSON at {index}:{line_number}") from exc
        if not isinstance(row, dict) or "length" not in row or "kind" not in row or not isinstance(row.get("files"), dict):
            raise EnvelopeError(f"invalid dump record at {index}:{line_number}")
        try:
            int(row["length"])
            int(row.get("seq", 0))
        except (TypeError, ValueError) as exc:
            raise EnvelopeError(f"invalid length/seq at {index}:{line_number}") from exc
        rows.append(row)
    if not rows:
        raise EnvelopeError(f"empty index.jsonl: {directory}")
    return rows


def parse_lengths(value: str | None) -> set[int] | None:
    if value is None:
        return None
    try:
        values = {int(part) for part in value.split(",") if part.strip()}
    except ValueError as exc:
        raise EnvelopeError("--lengths must be comma-separated integers") from exc
    if not values or any(item <= 0 for item in values):
        raise EnvelopeError("--lengths must contain positive integers")
    return values


def parse_kinds(value: str | None) -> set[str] | None:
    if value is None:
        return None
    values = {part.strip() for part in value.split(",") if part.strip()}
    if not values:
        raise EnvelopeError("--kinds must contain at least one kind")
    return values


def selected_roles(tier: str) -> tuple[str, ...]:
    return DEVICE_ROLES if tier == "device" else HOST_ROLES


def record_roles(record: Record, tier: str) -> tuple[str, ...]:
    files = record.row["files"]
    names = set(files)
    unknown = names - ALL_ROLES
    if unknown:
        raise EnvelopeError(f"unknown role(s) at length={record.length} seq={record.seq}: {sorted(unknown)}")
    required = set(selected_roles(tier))
    missing = required - names
    if missing:
        raise EnvelopeError(f"missing {tier} role(s) at length={record.length} seq={record.seq}: {sorted(missing)}")
    for role in required:
        if not isinstance(files[role], str) or not files[role].endswith(".pt"):
            raise EnvelopeError(f"invalid tensor file for {role} at length={record.length} seq={record.seq}")
    return tuple(sorted(required))


def select_records(directory: Path, kind: str, uid: str | None, prefix_hash: str | None,
                   lengths: set[int] | None, tier: str, allowed_kinds: set[str] | None) -> Selection:
    if allowed_kinds is not None and kind not in allowed_kinds:
        raise EnvelopeError(f"selected kind {kind!r} is absent from --kinds")
    grouped: dict[int, list[Record]] = defaultdict(list)
    for row in read_rows(directory):
        if row.get("kind") != kind:
            continue
        record = Record(directory, row)
        if uid is not None and record.uid != uid:
            continue
        if prefix_hash is not None and record.prefix_hash != prefix_hash:
            continue
        if lengths is not None and record.length not in lengths:
            continue
        record_roles(record, tier)
        grouped[record.length].append(record)
    if not grouped:
        raise EnvelopeError(f"no {kind} records selected from {directory}")
    records: dict[int, Record] = {}
    repeats: dict[int, list[Record]] = {}
    for length, candidates in grouped.items():
        identities = {(candidate.uid, candidate.prefix_hash) for candidate in candidates}
        if len(identities) != 1:
            raise EnvelopeError(
                f"ambiguous records at length={length} in {directory}; use --uid-*/--prefix-hash-* selectors")
        ordered = sorted(candidates, key=lambda candidate: candidate.seq)
        records[length] = ordered[-1]
        if len(ordered) > 1:
            repeats[length] = ordered
    return Selection(records=records, repeats=repeats)


def strict_lengths(ref: Selection, test: Selection, requested: set[int] | None, label: str) -> list[int]:
    ref_lengths, test_lengths = set(ref.records), set(test.records)
    if requested is not None:
        missing_ref, missing_test = requested - ref_lengths, requested - test_lengths
        if missing_ref or missing_test:
            raise EnvelopeError(f"{label} misses requested lengths ref={sorted(missing_ref)} test={sorted(missing_test)}")
        return sorted(requested)
    if ref_lengths != test_lengths:
        raise EnvelopeError(f"{label} length sets differ only_ref={sorted(ref_lengths - test_lengths)} "
                            f"only_test={sorted(test_lengths - ref_lengths)}")
    return sorted(ref_lengths)


def verify_identity(ref: Record, test: Record, *, allow_explicit_uid_mapping: bool = False) -> None:
    if (ref.uid is not None and test.uid is not None and ref.uid != test.uid
            and not allow_explicit_uid_mapping):
        raise EnvelopeError(f"UID mismatch at length={ref.length}: {ref.uid!r} != {test.uid!r}")
    if ref.prefix_hash is not None and test.prefix_hash is not None and ref.prefix_hash != test.prefix_hash:
        raise EnvelopeError(f"prefix hash mismatch at length={ref.length}")
    if (ref.uid is None or test.uid is None) and (ref.prefix_hash is None or test.prefix_hash is None):
        raise EnvelopeError(f"no common UID or prefix hash to bind length={ref.length}")


def load_tensor(record: Record, role: str) -> Any:
    torch = torch_module()
    path = record.directory / record.row["files"][role]
    if not path.is_file():
        raise EnvelopeError(f"missing tensor file: {path}")
    try:
        tensor = torch.load(path, map_location="cpu", weights_only=True)
    except TypeError:  # older supported torch versions
        tensor = torch.load(path, map_location="cpu")
    if not isinstance(tensor, torch.Tensor):
        raise EnvelopeError(f"tensor file does not contain a tensor: {path}")
    if tensor.ndim < 1 or tensor.shape[0] < 1:
        raise EnvelopeError(f"tensor has no layer axis: {path}")
    if tensor.is_floating_point() and not bool(torch.isfinite(tensor).all().item()):
        raise EnvelopeError(f"non-finite tensor values: {path}")
    return tensor


def layer_ids(record: Record, role: str, count: int) -> tuple[list[int], bool]:
    supplied = record.metadata("layer_ids")
    if supplied is None:
        return list(range(count)), False
    values = supplied.get(role) if isinstance(supplied, dict) else supplied
    if not isinstance(values, list) or len(values) != count or any(type(value) is not int for value in values):
        raise EnvelopeError(f"invalid layer_ids for {role} at length={record.length} seq={record.seq}")
    return values, True


def metric(ref: Any, test: Any) -> tuple[float | None, float, str]:
    torch = torch_module()
    difference_norm = float(torch.linalg.vector_norm(test.float() - ref.float()).item())
    reference_norm = float(torch.linalg.vector_norm(ref.float()).item())
    unequal = float((test != ref).sum().item()) / float(test.numel())
    if reference_norm == 0.0:
        if difference_norm == 0.0:
            return 0.0, unequal, "zero_reference_equal"
        return None, unequal, "zero_reference_nonzero_delta"
    return difference_norm / reference_norm, unequal, "ok"


def maximum_absolute_delta(ref: Any, test: Any) -> float | int:
    """Return an exact integer delta or a float-state delta for one layer.

    Integer tensors must never be converted to float32 here: PLE ngram state
    can contain adjacent int64 values beyond the exact float32 range. Python
    integer subtraction also avoids signed-int64 overflow at the two bounds.
    """
    torch = torch_module()
    if ref.is_floating_point() or ref.is_complex():
        return float((test.to(torch.float64) - ref.to(torch.float64)).abs().max().item())
    if ref.dtype == torch.bool:
        return int(bool((test != ref).any().item()))
    return max((abs(int(right) - int(left))
                for left, right in zip(ref.reshape(-1).tolist(), test.reshape(-1).tolist())), default=0)


def paired_metrics(ref: Record, test: Record, tier: str, *, allow_explicit_uid_mapping: bool = False) -> list[dict[str, Any]]:
    verify_identity(ref, test, allow_explicit_uid_mapping=allow_explicit_uid_mapping)
    roles_ref, roles_test = record_roles(ref, tier), record_roles(test, tier)
    if roles_ref != roles_test:
        raise EnvelopeError(f"{tier} role sets differ at length={ref.length}: {roles_ref} != {roles_test}")
    points: list[dict[str, Any]] = []
    for role in roles_ref:
        ref_tensor, test_tensor = load_tensor(ref, role), load_tensor(test, role)
        if ref_tensor.shape != test_tensor.shape:
            raise EnvelopeError(f"shape mismatch length={ref.length} role={role}: {tuple(ref_tensor.shape)} != {tuple(test_tensor.shape)}")
        if ref_tensor.dtype != test_tensor.dtype:
            raise EnvelopeError(f"dtype mismatch length={ref.length} role={role}: {ref_tensor.dtype} != {test_tensor.dtype}")
        ref_layers, ref_explicit = layer_ids(ref, role, ref_tensor.shape[0])
        test_layers, test_explicit = layer_ids(test, role, test_tensor.shape[0])
        if ref_explicit and test_explicit:
            if ref_layers != test_layers:
                raise EnvelopeError(f"layer_ids mismatch length={ref.length} role={role}")
            output_layers, provenance = ref_layers, "explicit_equal"
        elif ref_explicit:
            output_layers, provenance = ref_layers, "index_aligned_test_missing"
        elif test_explicit:
            output_layers, provenance = test_layers, "index_aligned_ref_missing"
        else:
            output_layers, provenance = ref_layers, "index_aligned_both_missing"
        for index, layer in enumerate(output_layers):
            relative_l2, unequal_ratio, status = metric(ref_tensor[index], test_tensor[index])
            points.append({"length": ref.length, "role": role, "layer": layer, "relative_l2": relative_l2,
                           "max_abs": maximum_absolute_delta(ref_tensor[index], test_tensor[index]),
                           "unequal_ratio": unequal_ratio, "comparison_status": status,
                           "layer_mapping_provenance": provenance})
    return points


def intra_max_abs(records: Iterable[Record], tier: str) -> float:
    ordered = list(records)
    if len(ordered) < 2:
        return 0.0
    maximum = 0.0
    base = ordered[0]
    for other in ordered[1:]:
        for role in record_roles(base, tier):
            left, right = load_tensor(base, role), load_tensor(other, role)
            if left.shape != right.shape or left.dtype != right.dtype:
                raise EnvelopeError(f"repeated records disagree in shape/dtype at length={base.length} role={role}")
            maximum = max(maximum, float((left.float() - right.float()).abs().max().item()))
    return maximum


def compare(ref_dir: Path, test_dir: Path, legal_pairs: list[tuple[Path, Path]], *, kind_ref: str = "donate",
            kind_test: str = "donate", lengths: set[int] | None = None, uid_ref: str | None = None,
            uid_test: str | None = None, prefix_hash_ref: str | None = None, prefix_hash_test: str | None = None,
            tier: str = "device", allowed_kinds: set[str] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ref = select_records(ref_dir, kind_ref, uid_ref, prefix_hash_ref, lengths, tier, allowed_kinds)
    test = select_records(test_dir, kind_test, uid_test, prefix_hash_test, lengths, tier, allowed_kinds)
    selected_lengths = strict_lengths(ref, test, lengths, "ref/test")
    explicit_uid_mapping = uid_ref is not None and uid_test is not None
    rows: list[dict[str, Any]] = []
    for length in selected_lengths:
        ref_record, test_record = ref.records[length], test.records[length]
        if explicit_uid_mapping and (ref_record.uid != uid_ref or test_record.uid != uid_test):
            raise EnvelopeError(f"selected UID does not match explicit mapping at length={length}")
        uid_mapping_provenance = (
            "explicit_uid_ref_test_selectors"
            if explicit_uid_mapping else "record_uid_equal"
        )
        for point in paired_metrics(
                ref_record, test_record, tier,
                allow_explicit_uid_mapping=explicit_uid_mapping):
            point.update({"ref_seq": ref.records[length].seq, "test_seq": test.records[length].seq,
                          "uid": ref_record.uid if ref_record.uid == test_record.uid else "",
                          "ref_uid": ref_record.uid or "", "test_uid": test_record.uid or "",
                          "uid_mapping_provenance": uid_mapping_provenance,
                          "ref_prefix_hash": ref.records[length].prefix_hash or "",
                          "test_prefix_hash": test.records[length].prefix_hash or "",
                          "tier": tier, "ref_intra_max_abs": intra_max_abs(ref.repeats.get(length, []), tier),
                          "test_intra_max_abs": intra_max_abs(test.repeats.get(length, []), tier)})
            rows.append(point)
    envelopes: dict[tuple[int, str, int], list[float | None]] = defaultdict(list)
    for legal_ref_dir, legal_test_dir in legal_pairs:
        legal_ref = select_records(legal_ref_dir, kind_ref, uid_ref, prefix_hash_ref, lengths, tier, allowed_kinds)
        legal_test = select_records(legal_test_dir, kind_test, uid_test, prefix_hash_test, lengths, tier, allowed_kinds)
        legal_lengths = strict_lengths(legal_ref, legal_test, lengths, f"legal {legal_ref_dir}:{legal_test_dir}")
        if legal_lengths != selected_lengths:
            raise EnvelopeError("legal pair selected lengths differ from ref/test")
        for length in selected_lengths:
            for point in paired_metrics(legal_ref.records[length], legal_test.records[length], tier):
                envelopes[(point["length"], point["role"], point["layer"])].append(point["relative_l2"])
    exceeds = 0
    ratios: list[float] = []
    for row in rows:
        values = envelopes.get((row["length"], row["role"], row["layer"]))
        if values is None:
            row.update({"legal_max_relative_l2": "", "ratio": "", "envelope_status": "no_legal_envelope", "exceeds_envelope": ""})
            continue
        if any(value is None for value in values):
            raise EnvelopeError("legal envelope has nonzero delta against zero reference")
        envelope = max(value for value in values if value is not None)
        current = row["relative_l2"]
        if current is None:
            status, ratio, exceeded = "test_zero_reference_nonzero_delta", "", True
        elif envelope == 0.0:
            ratio, exceeded = (0.0, False) if current == 0.0 else ("", True)
            status = "zero_envelope_equal" if not exceeded else "zero_envelope_nonzero_test"
        else:
            ratio, exceeded, status = current / envelope, current > envelope, "ok"
        row.update({"legal_max_relative_l2": envelope, "ratio": ratio, "envelope_status": status,
                    "exceeds_envelope": exceeded})
        if exceeded:
            exceeds += 1
        if isinstance(ratio, float) and math.isfinite(ratio):
            ratios.append(ratio)
    summary = {"lengths": selected_lengths, "points": len(rows), "legal_pairs": len(legal_pairs),
               "exceed_points": exceeds, "max_ratio": max(ratios) if ratios else None,
               "ref_intra_max_abs": {str(length): intra_max_abs(items, tier) for length, items in ref.repeats.items()},
               "test_intra_max_abs": {str(length): intra_max_abs(items, tier) for length, items in test.repeats.items()}}
    return rows, summary


def parse_legal(value: str) -> tuple[Path, Path]:
    left, separator, right = value.partition(":")
    if not separator or not left or not right:
        raise argparse.ArgumentTypeError("--legal must be DIR_A:DIR_B")
    return Path(left), Path(right)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ("length", "ref_seq", "test_seq", "uid", "ref_uid", "test_uid", "uid_mapping_provenance",
              "ref_prefix_hash", "test_prefix_hash", "tier", "role", "layer",
              "relative_l2", "max_abs", "unequal_ratio", "legal_max_relative_l2", "ratio", "comparison_status", "layer_mapping_provenance",
              "envelope_status", "exceeds_envelope", "ref_intra_max_abs", "test_intra_max_abs")
    with path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", required=True, type=Path)
    parser.add_argument("--test", required=True, type=Path)
    parser.add_argument("--legal", action="append", type=parse_legal, default=[])
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--kinds", help="comma-separated allowed kinds; compatibility filter")
    parser.add_argument("--kind-ref", default="donate")
    parser.add_argument("--kind-test", default="donate")
    parser.add_argument("--lengths", help="explicit comma-separated lengths; out-of-range records are excluded")
    parser.add_argument("--uid-ref")
    parser.add_argument("--uid-test")
    parser.add_argument("--prefix-hash-ref")
    parser.add_argument("--prefix-hash-test")
    parser.add_argument("--tier", choices=("device", "host"), default="device")
    args = parser.parse_args()
    if args.out.exists():
        parser.error(f"--out already exists: {args.out}")
    try:
        rows, summary = compare(args.ref, args.test, args.legal, kind_ref=args.kind_ref, kind_test=args.kind_test,
                                lengths=parse_lengths(args.lengths), uid_ref=args.uid_ref, uid_test=args.uid_test,
                                prefix_hash_ref=args.prefix_hash_ref, prefix_hash_test=args.prefix_hash_test,
                                tier=args.tier, allowed_kinds=parse_kinds(args.kinds))
        write_csv(args.out, rows)
    except EnvelopeError as exc:
        parser.error(str(exc))
    print(json.dumps(summary, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
