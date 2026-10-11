"""Read-only terminal analysis for a completed D15 window A/B run.

The helper never starts or stops anything and never writes inside ``--run-dir``.
It reports evidence gaps rather than inferring a kept/product verdict.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [_json_line(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _json_line(line: str) -> dict[str, Any]:
    value = json.loads(line)
    if not isinstance(value, dict):
        raise ValueError("JSONL row is not an object")
    return value


def _metric_files(arm: Path, prefix: str) -> list[Path]:
    return sorted(arm.glob(f"{prefix}*.metrics.json"))


def _pooled(rows: list[dict[str, Any]]) -> float | None:
    numerator = sum(int(row.get("completion_tokens", 0)) - 1 for row in rows)
    denominator = sum(float(row.get("decode_elapsed_s", 0)) for row in rows)
    return numerator / denominator if numerator >= 0 and denominator > 0 else None


def _arm(arm: Path) -> dict[str, Any]:
    a = [_json(path) for path in _metric_files(arm, "A")]
    b = [_json(path) for path in _metric_files(arm, "B")]
    cold_files = _metric_files(arm, "cold")
    cold = _json(cold_files[0]) if len(cold_files) == 1 else None
    observer = arm / "observer"
    inputs, tokens = _rows(observer / "inputs.jsonl"), _rows(observer / "tokens.jsonl")
    input_by_uid = {row.get("uid"): row for row in inputs}
    token_uids = {row.get("uid") for row in tokens}
    uid_checks = []
    for row in [*a, *b, *([cold] if cold else [])]:
        uid = row.get("uid")
        observed = input_by_uid.get(uid, {})
        uid_checks.append({"uid": uid, "observer_input_present": uid in input_by_uid,
                           "observer_token_present": uid in token_uids,
                           "input_hash_equal": observed.get("input_ids_sha256") == row.get("input_ids_sha256")})
    logs = (arm / "serve.log").read_text(encoding="utf-8", errors="replace") if (arm / "serve.log").is_file() else ""
    return {"arm": arm.name, "a": a, "b": b, "cold": cold, "a_pooled_decode_tok_s": _pooled(a),
            "observer": {"inputs": len(inputs), "tokens": len(tokens), "uid_checks": uid_checks},
            "oom_markers": [marker for marker in ("out of memory", "cuda oom", "cuda error: out of memory") if marker in logs.lower()],
            "ownership": {"owned_process": (arm / "owned_process.json").is_file(), "serve_log": bool(logs),
                          "observer_shutdown": (observer / "shutdown.json").is_file()},
            "telemetry_rows": len(_rows(arm.parent / "telemetry_1hz.jsonl"))}


def analyse(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve(strict=True)
    result = run_dir / "result.json"
    failure = run_dir / "failure.json"
    terminal = _json(result) if result.is_file() else (_json(failure) if failure.is_file() else None)
    arms = {name: _arm(run_dir / name) if (run_dir / name).is_dir() else None for name in ("W98K", "W128K")}
    a98, a128 = (arms["W98K"] or {}).get("a", []), (arms["W128K"] or {}).get("a", [])
    rate98, rate128 = _pooled(a98), _pooled(a128)
    decline = (1 - rate128 / rate98) * 100 if rate98 and rate128 else None
    equality = [{"index": index + 1, "equal": left.get("native_token_sha256") == right.get("native_token_sha256"),
                 "left": left.get("native_token_sha256"), "right": right.get("native_token_sha256")}
                for index, (left, right) in enumerate(zip(a98, a128))]
    cold = (arms["W128K"] or {}).get("cold")
    band = None if decline is None else ("<=6%" if decline <= 6 else ("6-12%" if decline <= 12 else ">12%"))
    return {"schema": "ft_d15_window_terminal_analysis/v1", "analysed_at": datetime.now().astimezone().isoformat(),
            "run_dir": str(run_dir), "terminal": terminal, "actual_counts": {"A_W98K": len(a98), "A_W128K": len(a128),
            "B_W128K": len((arms["W128K"] or {}).get("b", [])), "cold_W128K": bool(cold)},
            "A_pooled_decode_tok_s": {"W98K": rate98, "W128K": rate128, "decline_pct": decline, "band": band,
                                         "formula": "sum(completion_tokens-1)/sum(decode_elapsed_s)"},
            "A_native_token_equality": equality, "arms": arms,
            "cold_checks": None if cold is None else {"planned_input_tokens": cold.get("planned_input_tokens"),
                "expected_input_tokens": 129024, "max_tokens": cold.get("completion_tokens"), "cached_tokens": cold.get("cached_tokens"),
                "min_free_gpu_mib": cold.get("min_free_gpu_mib"), "input_fit": cold.get("planned_input_tokens") == 129024 and int(cold.get("planned_input_tokens", 0)) + 256 <= 131072},
            "prefill_scope": "async Engine.forward_batch stream interval through original forward return; includes sampling/copy enqueue and CPU waits; not a kernel sum or TTFT",
            "analysis_verdict": "ANALYSIS_ONLY_NO_KEPT_OR_PRODUCT_ACCEPTANCE_LABEL"}


def markdown(report: dict[str, Any]) -> str:
    counts, rates, cold = report["actual_counts"], report["A_pooled_decode_tok_s"], report["cold_checks"]
    lines = ["# D15 Window Terminal Analysis", "", f"Analysed: {report['analysed_at']}", f"Run: `{report['run_dir']}`", "",
             f"Terminal: `{report['terminal'] and report['terminal'].get('verdict')}`", f"Counts: A98={counts['A_W98K']}, A128={counts['A_W128K']}, B={counts['B_W128K']}, cold={counts['cold_W128K']}",
             f"A pooled decode tok/s: W98={rates['W98K']}, W128={rates['W128K']}, decline={rates['decline_pct']} ({rates['band']})", f"A native equality: {all(row['equal'] for row in report['A_native_token_equality']) if report['A_native_token_equality'] else None}",
             f"Cold: {cold}", "", f"Prefill scope: {report['prefill_scope']}", "", "Verdict: ANALYSIS_ONLY — no kept or product-acceptance label."]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="optional task-owned output prefix; never inside run-dir")
    args = parser.parse_args()
    report = analyse(args.run_dir)
    if args.output:
        output = args.output.resolve()
        if output.is_relative_to(args.run_dir.resolve()):
            raise RuntimeError("output must not be inside the reviewed run directory")
        output.with_suffix(".json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        output.with_suffix(".md").write_text(markdown(report), encoding="utf-8")
    else:
        print(markdown(report), end="")


if __name__ == "__main__":
    main()
