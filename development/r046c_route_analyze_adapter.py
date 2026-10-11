#!/usr/bin/env python3
"""Adapt real R046c ordinary-v3 receipts to the stable route_analyze output schema.

This is not an ft_dev ACK shim: it reads the ordinary driver's saved worker
UserMsg/Detokenize bindings and asks the existing analyzer for route totals.
"""
from __future__ import annotations
import argparse, importlib.util, json
from pathlib import Path


def load_analyzer(path: Path):
    if path.is_symlink() or not path.is_file(): raise RuntimeError("R046c route_analyze source unavailable")
    spec = importlib.util.spec_from_file_location("r046c_route_analyze", path); module = importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(module); return module


def ordinary_rows(trace: Path):
    doc = json.loads(trace.read_text(encoding="utf-8"))
    if doc.get("schema") != "ft_r046c_ordinary_seed_trace/v1" or not isinstance(doc.get("rounds"), list):
        raise RuntimeError("R046c ordinary trace schema differs")
    rows = {}
    for number, item in enumerate(doc["rounds"]):
        record = item.get("record", {}); uid = record.get("api_uid"); binding = record.get("actual_input_binding", {})
        worker, events = binding.get("worker_input"), binding.get("token_sidecar", {}).get("events")
        if (type(uid) is not int or uid < 0 or uid in rows or not isinstance(worker, dict) or not isinstance(events, list)
                or not events or any(event.get("uid") != uid for event in events)):
            raise RuntimeError("R046c ordinary trace UID/token binding differs")
        completion = record.get("completion_tokens")
        if type(completion) is not int or completion <= 0 or len(events) != completion or events[-1].get("finished") is not True:
            raise RuntimeError("R046c ordinary trace completion differs")
        rows[uid] = {"trace": str(trace), "round": number, "completion_tokens": completion,
                     "max_tokens": 2048, "finish_reason": record.get("finish_reason"),
                     "worker_input_ids_sha256": worker.get("input_ids_sha256"), "worker_input_tokens": worker.get("input_tokens")}
    return rows


def analyze(route: Path, trace: Path, analyzer_path: Path, serve_log: Path | None = None) -> dict:
    analyzer = load_analyzer(analyzer_path)
    raw = analyzer.analyze(route, (), serve_log, None)
    trace_rows = ordinary_rows(trace)
    missing = sorted(set(trace_rows) - {int(uid) for uid in raw.get("raw_suffix_tokens", {})})
    if missing: raise RuntimeError("R046c ordinary business UID lacks route evidence")
    raw["analysis_scope"] = "ordinary_worker_token_bound_requests"
    raw["business_uids"] = sorted(trace_rows)
    raw["missing_business_routes"] = []
    raw["completions"] = {str(uid): value for uid, value in trace_rows.items()}
    raw["completion_count"] = len(trace_rows)
    raw["completion_distribution"] = analyzer.distribution([value["completion_tokens"] for value in trace_rows.values()])
    raw["ordinary_worker_token_bound"] = True
    return raw


def main(argv=None):
    p = argparse.ArgumentParser(); p.add_argument("route", type=Path); p.add_argument("--trace", type=Path, required=True); p.add_argument("--analyzer", type=Path, required=True); p.add_argument("--serve-log", type=Path); p.add_argument("--out", type=Path, required=True)
    a = p.parse_args(argv); result = analyze(a.route, a.trace, a.analyzer, a.serve_log); a.out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8"); return 0

if __name__ == "__main__": raise SystemExit(main())
