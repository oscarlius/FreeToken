#!/usr/bin/env python3
"""Strict offline analysis of D07 raw route records."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np

RECORD_FIELDS = {"seq", "phase", "t", "layer_count", "layer_ids", "reqs", "file"}
ACK_SCHEMA = "ft_route_ack/v1"


def fail(message):
    raise ValueError(message)


def load_route(path):
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"invalid route json {path}") from exc
    if set(record) != RECORD_FIELDS or type(record.get("seq")) is not int:
        fail("invalid route fields")
    if path.name != f"route-{record['seq']:08d}.json" or record["seq"] < 0:
        fail("invalid route seq/path")
    if record["phase"] not in {"prefill", "decode"} or type(record["t"]) is not int or record["t"] <= 0:
        fail("invalid route phase/t")
    layer_ids = record["layer_ids"]
    if (type(record["layer_count"]) is not int or record["layer_count"] <= 0
            or not isinstance(layer_ids, list) or len(layer_ids) != record["layer_count"]
            or len(set(layer_ids)) != len(layer_ids) or any(type(x) is not int for x in layer_ids)):
        fail("invalid route layer metadata")
    reqs = record["reqs"]
    valid_req = lambda row: set(row) == {"rid", "n_tokens"} and type(row["rid"]) is int and type(row["n_tokens"]) is int and row["n_tokens"] > 0
    if not isinstance(reqs, list) or not reqs or any(not isinstance(row, dict) or not valid_req(row) for row in reqs):
        fail("invalid route reqs")
    if len({row["rid"] for row in reqs}) != len(reqs) or sum(row["n_tokens"] for row in reqs) != record["t"]:
        fail("duplicate or mismatched route reqs")
    name = record["file"]
    if not isinstance(name, str) or Path(name).name != name or not name.endswith(".npz"):
        fail("unsafe route npz path")
    npz_path = path.parent / name
    try:
        with np.load(npz_path, allow_pickle=False) as data:
            if set(data.files) != {"expert_ids"}:
                fail("unexpected npz fields")
            expert_ids = data["expert_ids"]
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"invalid/missing route npz {npz_path}") from exc
    if expert_ids.dtype != np.int16 or expert_ids.shape != (record["layer_count"], record["t"], 10):
        fail("route npz shape/dtype mismatch")
    if np.any(expert_ids < 0) or np.any(expert_ids >= 512):
        fail("expert id outside [0,511]")
    if any(len(set(token.tolist())) != 10 for token in expert_ids.reshape(-1, 10)):
        fail("duplicate expert in token row")
    return record, expert_ids


def ack_count(events, uid):
    if not isinstance(events, list) or not events:
        fail("trace ACK missing")
    previous_seq = previous_cumulative = 0
    for event in events:
        if not isinstance(event, dict):
            fail("invalid ACK event")
        seq = event.get("request_seq")
        delta = event.get("completion_tokens_delta")
        cumulative = event.get("completion_tokens_cumulative")
        if any(type(value) is not int for value in (seq, delta, cumulative)):
            fail("invalid ACK types")
        if (delta not in (0, 1) or seq != previous_seq + 1
                or cumulative != previous_cumulative + delta):
            fail("non-contiguous ACK evidence")
        if "uid" in event and (type(event["uid"]) is not int or event["uid"] != uid):
            fail("ACK UID changed")
        previous_seq, previous_cumulative = seq, cumulative
    if previous_cumulative <= 0:
        fail("trace ACK lacks positive completion")
    return previous_cumulative


def load_trace(path):
    """Read generate (`round.record`) and replay (direct round) D07 evidence."""
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict) or not isinstance(document.get("rounds"), list):
        fail(f"trace {path} has no rounds")
    output = {}
    for index, row in enumerate(document["rounds"]):
        if not isinstance(row, dict):
            fail(f"trace {path} round {index} invalid")
        record = row.get("record", row)
        uid, events, finish = record.get("uid"), record.get("token_events"), record.get("finish_reason")
        if (type(uid) is not int or uid < 0 or record.get("ack_schema") != ACK_SCHEMA
                or finish not in {"stop", "length", "tool_calls"}):
            fail(f"trace {path} round {index} lacks UID/ACK/finish")
        if record.get("dry_run") or record.get("error"):
            fail("failed or dry-run trace is not measurement evidence")
        if uid in output:
            fail(f"trace {path} repeats uid {uid}")
        completion = ack_count(events, uid)
        budget = record.get("max_tokens")
        if type(budget) is not int or budget <= 0 or completion > budget:
            fail("completion ACK exceeds or lacks the actual request budget")
        if type(record.get("completion_tokens")) is not int or record["completion_tokens"] != completion:
            fail("trace completion disagrees with ACKs")
        usage = record.get("usage", {})
        if usage and (not isinstance(usage, dict) or type(usage.get("completion_tokens", completion)) is not int or usage.get("completion_tokens", completion) != completion):
            fail("trace usage completion disagrees with ACKs")
        recomputed = record.get("recomputed_tokens")
        if recomputed is not None and (type(recomputed) is not int or recomputed < 0):
            fail("invalid trace recomputed_tokens")
        output[uid] = {"trace": str(path), "round": index, "completion_tokens": completion,
            "max_tokens": budget, "finish_reason": finish, "recomputed_tokens": recomputed}
    return output


def _ordinary_events(events, uid, completion, finish, *, where):
    """Validate backend DetokenizeMsg rows without relabelling them as ACKs."""
    if not isinstance(events, list) or len(events) != completion:
        fail(f"{where} DetokenizeMsg completion count differs")
    previous_time = 0
    for sequence, event in enumerate(events, 1):
        if not isinstance(event, dict):
            fail(f"{where} invalid DetokenizeMsg event")
        if (event.get("schema") != "ft_t06_ordinary_token/v3" or event.get("uid") != uid
                or event.get("request_seq") != sequence
                or event.get("completion_tokens_delta") != 1
                or event.get("completion_tokens_cumulative") != sequence
                or type(event.get("next_token")) is not int
                or type(event.get("finished")) is not bool
                or type(event.get("time_ns")) is not int or event["time_ns"] <= previous_time):
            fail(f"{where} DetokenizeMsg sequence differs")
        if event["finished"] != (sequence == completion):
            fail(f"{where} DetokenizeMsg terminal differs")
        previous_time = event["time_ns"]
    if events[-1].get("finish_reason") != finish:
        fail(f"{where} DetokenizeMsg finish differs")


def _ordinary_binding(binding, uid, completion, finish, *, where):
    if not isinstance(binding, dict) or binding.get("schema") != "ft_t06_ordinary_binding/v3":
        fail(f"{where} ordinary binding schema differs")
    if binding.get("verdict") != "worker_input_uid_token_bound":
        fail(f"{where} ordinary binding verdict differs")
    worker = binding.get("worker_input")
    api = binding.get("api")
    if (not isinstance(worker, dict) or not isinstance(api, dict)
            or not isinstance(worker.get("input_ids_sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", worker["input_ids_sha256"])
            or type(worker.get("input_tokens")) is not int or worker["input_tokens"] < 0
            or api.get("uid") != uid or api.get("finish_reason") != finish):
        fail(f"{where} ordinary worker/API identity differs")
    usage = api.get("usage")
    if not isinstance(usage, dict) or usage.get("completion_tokens") != completion:
        fail(f"{where} ordinary API completion differs")
    token = binding.get("token_sidecar")
    if not isinstance(token, dict):
        fail(f"{where} ordinary DetokenizeMsg sidecar differs")
    _ordinary_events(token.get("events"), uid, completion, finish, where=where)
    return worker


def load_ordinary_trace(path):
    """Read R046c ordinary UserMsg/DetokenizeMsg evidence, never pause ACKs."""
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if document.get("schema") != "ft_r046c_ordinary_seed_trace/v1" or not isinstance(document.get("rounds"), list):
        fail(f"ordinary trace {path} schema/rounds differ")
    output = {}
    for index, row in enumerate(document["rounds"]):
        if not isinstance(row, dict) or not isinstance(row.get("record"), dict):
            fail(f"ordinary trace {path} round {index} differs")
        record = row["record"]
        uid, completion, finish = record.get("api_uid"), record.get("completion_tokens"), record.get("finish_reason")
        if (type(uid) is not int or uid < 0 or type(completion) is not int or completion <= 0
                or finish not in {"stop", "length", "tool_calls"} or uid in output):
            fail(f"ordinary trace {path} UID/completion differs")
        worker = _ordinary_binding(record.get("actual_input_binding"), uid, completion, finish,
                                  where=f"ordinary trace {path} round {index}")
        output[uid] = {"trace": str(path), "round": index, "completion_tokens": completion,
                       "max_tokens": 2048, "finish_reason": finish, "recomputed_tokens": None,
                       "worker_input_ids_sha256": worker["input_ids_sha256"],
                       "worker_input_tokens": worker["input_tokens"],
                       "token_source": "DetokenizeMsg"}
    if not output:
        fail(f"ordinary trace {path} has no completed request")
    return output


def load_two_decode(path):
    """Bind route UID pairs to the existing D06 request/token sidecars."""
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > 2 * 1024 * 1024:
        fail("two-decode evidence must be a bounded regular file")
    payload = path.read_bytes()
    document = json.loads(payload)
    if document.get("schema") == "ft_r046c_ordinary_two_decode/v1":
        if (document.get("same_prompt") is not False or document.get("parallel") is not True
                or document.get("ctx") != 8000 or document.get("max_tokens") != 256
                or not isinstance(document.get("records"), list) or len(document["records"]) != 2):
            fail("ordinary two-decode contract differs")
        records, seen = [], set()
        for index, row in enumerate(document["records"]):
            uid, input_sha, completion, finish = (row.get("uid"), row.get("input_ids_sha256"),
                                                   row.get("completion_tokens"), row.get("finish_reason"))
            if (type(uid) is not int or uid < 0 or uid in seen
                    or not isinstance(input_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", input_sha)
                    or type(completion) is not int or completion <= 0 or completion > 256
                    or finish not in {"stop", "length", "tool_calls"}):
                fail("ordinary two-decode record differs")
            worker = _ordinary_binding(row.get("binding"), uid, completion, finish,
                                      where=f"ordinary two-decode record {index}")
            if worker["input_ids_sha256"] != input_sha:
                fail("ordinary two-decode input binding differs")
            seen.add(uid)
            records.append((uid, input_sha, worker["input_tokens"], row["binding"]["token_sidecar"]))
        if records[0][1] == records[1][1]:
            fail("ordinary two-decode inputs are not different")
        digest = hashlib.sha256(payload).hexdigest()
        return [{"experiment_id": f"{digest}:ordinary-v3", "source": str(path), "source_sha256": digest,
                 "source_schema": "ft_r046c_ordinary_two_decode/v1", "uids": [row[0] for row in records],
                 "prompt_sha256": [row[1] for row in records], "frontend_token_counts": [row[2] for row in records],
                 "token_sidecars": [{"uid": row[0], "sha256": hashlib.sha256(json.dumps(row[3], sort_keys=True).encode()).hexdigest()}
                                    for row in records]}]
    if (document.get("schema") != "multisession_probe/v1"
            or document.get("command") != "two-decode" or document.get("same_prompt") is not False
            or not isinstance(document.get("reps"), list) or not document["reps"]):
        fail("two-decode evidence must declare distinct-content requests")
    digest = hashlib.sha256(payload).hexdigest()
    pairs, seen_uids, seen_reps = [], set(), set()
    for repetition in document["reps"]:
        number = repetition.get("rep")
        hashes = repetition.get("prompt_sha256")
        counts = repetition.get("frontend_token_counts")
        ways = repetition.get("per_way")
        if type(number) is not int or number < 0 or number in seen_reps:
            fail("invalid two-decode repetition identity")
        seen_reps.add(number)
        if (not isinstance(hashes, list) or len(hashes) != 2
                or any(not isinstance(h, str) or not re.fullmatch(r"[0-9a-f]{64}", h) for h in hashes)
                or hashes[0] == hashes[1]):
            fail("two-decode inputs must have distinct actual token digests")
        if (not isinstance(counts, list) or len(counts) != 2
                or any(type(n) is not int or n <= 0 for n in counts)):
            fail("two-decode lacks actual frontend token counts")
        if not isinstance(ways, list) or len(ways) != 2:
            fail("two-decode requires two measured ways")
        uids, sidecars = [], []
        for index, way in enumerate(ways):
            uid = way.get("uid")
            if type(uid) is not int or uid < 0 or uid in seen_uids:
                fail("two-decode UID missing or reused")
            seen_uids.add(uid)
            expected = path.with_name(f"{path.stem}.rep{number}.way{index}.tokens.json")
            supplied = Path(way.get("token_timestamps", ""))
            if not supplied.is_absolute():
                supplied = path.parent / supplied
            if supplied.resolve() != expected.resolve() or supplied.is_symlink():
                fail("two-decode token sidecar does not bind the output identity")
            if supplied.stat().st_size > 2 * 1024 * 1024:
                fail("two-decode token sidecar exceeds its bounded size")
            sidecar_bytes = supplied.read_bytes()
            sidecar = json.loads(sidecar_bytes)
            if type(sidecar.get("uid")) is not int or sidecar["uid"] != uid:
                fail("two-decode sidecar UID mismatch")
            completion = ack_count(sidecar.get("token_events"), uid)
            if type(way.get("completion_tokens")) is not int or way["completion_tokens"] != completion:
                fail("two-decode completion disagrees with token sidecar")
            uids.append(uid)
            sidecars.append({"path": str(supplied), "sha256": hashlib.sha256(sidecar_bytes).hexdigest()})
        pairs.append({"experiment_id": f"{digest}:rep{number}", "source": str(path),
            "source_sha256": digest, "uids": uids, "prompt_sha256": hashes,
            "frontend_token_counts": counts, "token_sidecars": sidecars})
    return pairs


def distribution(values):
    if not values:
        return None
    quantiles = np.percentile(values, [0, 25, 50, 75, 100]).tolist()
    return dict(zip(("min", "p25", "median", "p75", "max"), quantiles))


def parse_serve_log(path):
    totals = defaultdict(int)
    found = False
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        routes = re.search(r"#route-reqs:\s*([0-9:,-]+)", line)
        if not routes:
            continue
        new = re.search(r"#new-token:\s*(\d+)", line)
        if new is None:
            fail("#route-reqs line lacks #new-token")
        pairs = [pair for pair in routes.group(1).split(",") if pair]
        line_total = 0
        for pair in pairs:
            try: uid, count = (int(x) for x in pair.split(":"))
            except ValueError as exc: raise ValueError("invalid #route-reqs") from exc
            if count <= 0: fail("invalid #route-reqs count")
            totals[uid] += count; line_total += count
        if int(new.group(1)) != line_total:
            fail("#new-token disagrees with #route-reqs on line")
        found = True
    if not found: fail("serve log lacks per-request #route-reqs evidence")
    return dict(totals)


def analyze(route_dir, traces=(), serve_log=None, two_decode=None, ordinary_traces=()):
    rows = [load_route(path) for path in sorted(Path(route_dir).glob("route-*.json"))]
    if not rows: fail("no route records")
    if [record["seq"] for record, _ in rows] != list(range(len(rows))): fail("route seq must be contiguous")
    layer_ids = rows[0][0]["layer_ids"]
    if any(record["layer_ids"] != layer_ids for record, _ in rows): fail("layer-id mapping changed")
    raw = defaultdict(lambda: {"n": 0, "sets": [set() for _ in layer_ids]})
    pairs = load_two_decode(two_decode) if two_decode is not None else []
    declared = {frozenset(pair["uids"]): pair for pair in pairs}
    pair_steps = {pair["experiment_id"]: 0 for pair in pairs}
    rb, decode_steps, unbound_decode_steps = defaultdict(list), 0, 0
    for record, ids in rows:
        offset = 0
        for req in record["reqs"]:
            count = req["n_tokens"]
            if record["phase"] == "prefill":
                value = raw[req["rid"]]; value["n"] += count
                for layer in range(len(layer_ids)):
                    value["sets"][layer].update(ids[layer, offset:offset + count].reshape(-1).tolist())
            offset += count
        if record["phase"] == "decode" and len(record["reqs"]) == 2:
            if any(req["n_tokens"] != 1 for req in record["reqs"]): fail("B=2 decode requires one token/request")
            if two_decode is None:
                unbound_decode_steps += 1
                continue
            pair = declared.get(frozenset(req["rid"] for req in record["reqs"]))
            if pair is None:
                fail("undeclared B=2 decode pair cannot enter R_B")
            pair_steps[pair["experiment_id"]] += 1
            decode_steps += 1
            for layer in range(len(layer_ids)):
                rb[layer].append(20 / len(set(ids[layer, 0]) | set(ids[layer, 1])))
    if not raw: fail("route trace has no prefill records")
    for pair in pairs:
        if any(uid not in raw for uid in pair["uids"]):
            fail("two-decode UID lacks prefill route evidence")
    raw_suffix = {str(uid): value["n"] for uid, value in raw.items()}
    if serve_log is not None and parse_serve_log(serve_log) != {int(k): v for k, v in raw_suffix.items()}:
        fail("serve log UID totals disagree with routes")
    trace_rows = {}
    for trace in traces:
        for uid, evidence in load_trace(trace).items():
            if uid in trace_rows: fail(f"duplicate trace UID {uid}")
            trace_rows[uid] = evidence
    for trace in ordinary_traces:
        for uid, evidence in load_ordinary_trace(trace).items():
            if uid in trace_rows: fail(f"duplicate trace UID {uid}")
            trace_rows[uid] = evidence
    business = {uid: raw[uid] for uid in trace_rows if uid in raw}
    missing = set(trace_rows) - set(raw)
    trace_enabled = bool(traces or ordinary_traces)
    if trace_enabled and missing: fail(f"business trace UID lacks routes: {sorted(missing)}")
    for uid, proof in trace_rows.items():
        if proof["recomputed_tokens"] is not None and proof["recomputed_tokens"] != raw[uid]["n"]:
            fail("trace recomputed_tokens disagrees with route UID totals")
    selected = business if trace_enabled else raw
    buckets = defaultdict(lambda: defaultdict(list))
    by_request, suffixes = {}, []
    for uid, value in sorted(selected.items()):
        n = value["n"]
        suffixes.append({"uid": uid, "n": n, "trace": trace_rows.get(uid, {}).get("trace"),
            "round": trace_rows.get(uid, {}).get("round")})
        by_request[str(uid)] = {}
        for layer, used in enumerate(value["sets"]):
            f = len(used) / 512; lo, hi = 10 / 512, min(1.0, 10 * n / 512)
            if not lo <= f <= hi: fail("unconditional f bound violated")
            buckets[n][layer].append(f)
            by_request[str(uid)][str(layer_ids[layer])] = {"value": f,
                "predicted": 1 - (1 - 10 / 512) ** n, "bounds": [lo, hi]}
    predicted = lambda n: 1 - (1 - 10 / 512) ** n
    completions = [row["completion_tokens"] for row in trace_rows.values()]
    suffix_counts = [row["n"] for row in suffixes]
    return {
        "analysis_scope": ("ordinary_worker_token_bound_requests" if ordinary_traces
                           else "trace_bound_business_requests" if traces else "all_prefill_requests"),
        "ordinary_worker_token_bound": bool(ordinary_traces),
        "ordinary_token_source": ("SchedulerIOMixin._reply_tokenizer_rank0(DetokenizeMsg)"
                                  if ordinary_traces else None),
        "suffix_tokens": suffixes, "suffix_distribution": distribution(suffix_counts),
        "suffix_le_64_count": sum(n <= 64 for n in suffix_counts),
        "suffix_le_64_fraction": sum(n <= 64 for n in suffix_counts)/len(suffix_counts) if suffix_counts else None,
        "f_by_request": by_request,
        "raw_suffix_tokens": raw_suffix, "business_uids": sorted(business), "missing_business_routes": sorted(missing),
        "f_measured": {str(n): {str(layer_ids[l]): sum(v)/len(v) for l, v in values.items()} for n, values in buckets.items()},
        "f_range": {str(n): {str(layer_ids[l]): [min(v),max(v)] for l,v in values.items()} for n,values in buckets.items()},
        "f_predicted": {str(n): predicted(n) for n in buckets},
        "f_difference": {str(n): {str(layer_ids[l]): sum(v)/len(v)-predicted(n) for l, v in values.items()} for n, values in buckets.items()},
        "f_bounds": {str(n): [10/512, min(1.0,10*n/512)] for n in buckets}, "f_sample_count": {str(n): len(next(iter(v.values()))) for n,v in buckets.items()},
        "R_B_definition": "20 / |two declared decode tokens' expert union|",
        "R_B": {str(layer_ids[l]): sum(v)/len(v) for l,v in rb.items()},
        "decode_B2_steps": decode_steps, "R_B_pending": decode_steps == 0,
        "R_B_nullreason": None if decode_steps else "declared two-decode pair evidence or overlapping decode routes unavailable",
        "unbound_decode_B2_steps": unbound_decode_steps, "two_decode_pairs": pairs, "two_decode_pair_steps": pair_steps,
        "completion_distribution": distribution(completions),
        "completion_gt_233_fraction": sum(n > 233 for n in completions)/len(completions) if completions else None,
        "cap_2048_truncations": sum(row["max_tokens"] == 2048 and row["completion_tokens"] == 2048
            and row["finish_reason"] == "length" for row in trace_rows.values()),
        "completions": trace_rows, "completion_count": len(completions), "completion_le_64": sum(x <= 64 for x in completions), "completion_gt_233": sum(x > 233 for x in completions), "length_truncations": sum(row["finish_reason"] == "length" for row in trace_rows.values()),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("route_dir", type=Path)
    parser.add_argument("--traces", nargs="*", default=[])
    parser.add_argument("--ordinary-traces", nargs="*", default=[])
    parser.add_argument("--serve-log")
    parser.add_argument("--two-decode", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    args.out.write_text(json.dumps(analyze(args.route_dir, args.traces, args.serve_log, args.two_decode, args.ordinary_traces),
        indent=2, sort_keys=True, allow_nan=False)+"\n", encoding="utf-8")

if __name__ == "__main__": main()
