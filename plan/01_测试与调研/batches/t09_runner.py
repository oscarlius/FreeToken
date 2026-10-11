#!/usr/bin/env python3
"""Dormant T09 single-request hybrid diagnostic runner.

No GPU work occurs unless a root-assigned RID is supplied with ``--run`` on the
Linux host.  The runner intentionally does not enable D08 HYB_TRACE or any D06
two-request experiment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys

from e2_runtime import CardRunner
from t16_runner import PY, ROOT, SCR, TOOL_MD5, command, write_new


RID_PATTERN = r"E2-R010"
NODE1 = (1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23,
         25, 27, 29, 31, 33, 35, 37, 39, 41, 43, 45, 47)
V0 = tuple(range(48))
A = tuple(cpu for cpu in V0 if cpu not in (0, 2, 24, 26))
MEMORY_FLOOR_KB = 120_586_240
PIN_LINE = re.compile(
    r"CPU MoE executor ready: threads=(?P<threads>[1-9]\d*) "
    r"\(pinned to cores (?P<cpus>\d+(?:\.\.\d+|(?:,\d+)*))\)"
)
OOM_LINE = re.compile(r"out of memory|\bKilled\b", re.I)

VARIANTS = {
    "V0": ["numactl", "--cpunodebind=0,1", "--interleave=all"],
    "A": ["numactl", "--interleave=all", "taskset", "-c", "1,3-23,25,27-47"],
    "B": ["numactl", "--interleave=all", "taskset", "-c", ",".join(map(str, NODE1))],
    "C": ["numactl", "--membind=1", "taskset", "-c", ",".join(map(str, NODE1))],
}
EXPECTED_AFFINITY = {"V0": set(V0), "A": set(A), "B": set(NODE1), "C": set(NODE1)}


def finite_positive(value):
    return type(value) in (float, int) and math.isfinite(value) and value > 0


def cold_record(path: Path, cold_id: str, target: int, completion: int) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    record = value.get("record") or {}
    diagnostic = value.get("diag") or {}
    if (record.get("cold_id") != cold_id or record.get("cached_tokens") != 0
            or abs(record.get("prompt_tokens", 0) - target) >= 2000
            or record.get("completion_tokens") != completion or not finite_positive(record.get("ttft_s"))
            or not finite_positive(record.get("decode_tps")) or diagnostic.get("built_tokens") != target
            or diagnostic.get("enable_thinking") is not False or not diagnostic.get("cache_ok")
            or not diagnostic.get("prompt_len_ok") or not diagnostic.get("decode_ok")):
        raise ValueError(f"invalid cold sample: {path}")
    return record


def node1_memory() -> dict[str, int]:
    values: dict[str, int] = {}
    for line in Path("/sys/devices/system/node/node1/meminfo").read_text(encoding="utf-8").splitlines():
        match = re.search(r"(?:Node 1 )?(MemFree|FilePages):\s+(\d+) kB", line)
        if match:
            values[match.group(1)] = int(match.group(2))
    if set(values) != {"MemFree", "FilePages"}:
        raise ValueError("node1 MemFree/FilePages topology fields absent")
    values["total_kB"] = values["MemFree"] + values["FilePages"]
    return values


def executor_cpu_labels(raw: str, threads: int, allowed: set[int]) -> dict:
    """Validate a CPU pin label without inventing gapped endpoint members."""
    if ".." in raw:
        if raw.count("..") != 1:
            raise ValueError(f"invalid executor CPU range: {raw!r}")
        first, last = raw.split("..")
        if not first.isdecimal() or not last.isdecimal():
            raise ValueError(f"invalid executor CPU range: {raw!r}")
        start, end = int(first), int(last)
        if end < start:
            raise ValueError(f"descending executor CPU range: {raw!r}")
        span = list(range(start, end + 1))
        if threads > len(span) or start not in allowed or end not in allowed:
            raise ValueError(
                f"executor CPU range cannot describe selected variant: {raw!r}"
            )
        in_span = [cpu for cpu in span if cpu in allowed]
        if threads == len(span):
            if len(in_span) != len(span):
                raise ValueError(f"executor CPU range leaves selected variant: {raw!r}")
            return {
                "pins": span,
                "syntax": "range",
                "pin_list_complete": True,
                "endpoints": [start, end],
                "raw_span": raw,
            }
        if len(in_span) < threads:
            raise ValueError(
                f"executor CPU endpoint span has too few selected CPUs: {raw!r}"
            )
        return {
            "pins": None,
            "syntax": "endpoint_span",
            "pin_list_complete": False,
            "endpoints": [start, end],
            "raw_span": raw,
            "diagnostic": (
                "logger records only range endpoints; intermediate worker CPU IDs "
                "are not claimed"
            ),
        }
    else:
        parts = raw.split(",")
        if not parts or any(not part.isdecimal() for part in parts):
            raise ValueError(f"invalid executor CPU list: {raw!r}")
        labels = [int(part) for part in parts]

    if len(labels) != threads or len(set(labels)) != len(labels):
        raise ValueError(
            f"executor thread/pin labels disagree: threads={threads}, labels={raw!r}"
        )
    if not set(labels) <= allowed:
        raise ValueError(f"executor pins do not match selected variant: {sorted(set(labels))}")
    return {
        "pins": sorted(labels),
        "syntax": "list",
        "pin_list_complete": True,
        "endpoints": [labels[0], labels[-1]],
        "raw_span": None,
    }


def executor_pins(arm: Path, allowed: set[int]) -> dict:
    text = (arm / "serve.log").read_text(encoding="utf-8", errors="replace")
    matches = [(line, PIN_LINE.search(line)) for line in text.splitlines(keepends=True)]
    matches = [(line, match) for line, match in matches if match]
    if not matches:
        raise ValueError(f"executor pin log absent: {arm}")
    literal_line, match = matches[-1]
    threads = int(match["threads"])
    detail = executor_cpu_labels(match["cpus"], threads, allowed)
    detail.update({"threads": threads, "allowed": sorted(allowed),
                   "raw_log": literal_line.rstrip("\r\n")})
    with (arm / "executor_pin.txt").open("x", encoding="utf-8", newline="") as handle:
        handle.write(literal_line)
    write_new(arm / "executor_pin.json", detail)
    return detail


def d0_evidence(arm: Path) -> dict:
    directory = arm / "d0"
    files = sorted(path for path in directory.rglob("*") if path.is_file()) if directory.is_dir() else []
    if not files:
        raise ValueError("D0 output directory is empty")
    aggregate = next((p for p in files if p.name == "d0_decode.json"), None)
    steps = next((p for p in files if p.name == "d0_decode_steps.jsonl"), None)
    prefill = next((p for p in files if p.name == "d0_prefill.jsonl"), None)
    if not aggregate or not steps or not prefill or not steps.read_text(encoding="utf-8").strip() or not prefill.read_text(encoding="utf-8").strip():
        raise ValueError("D0 aggregate/steps/prefill evidence incomplete")
    document = json.loads(aggregate.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("D0 aggregate schema is not an object")
    # Preserve only actually emitted hybrid measurements; do not invent D08 fields.
    hybrid = {key: value for key, value in document.items() if key in {"miss_rate", "cpu_per_layer", "cpu_experts", "h2d_bytes"}}
    if not hybrid:
        raise ValueError("D0 aggregate contains no hybrid statistics")
    return {"paths": {p.name: str(p.relative_to(arm)) for p in (aggregate, steps, prefill)},
            "sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (aggregate, steps, prefill)},
            "hybrid": hybrid}


def c_timeout_may_skip(variant: str, entered_service: bool, log: Path) -> bool:
    """The sole soft path: C timed out before the service context yielded."""
    tail = "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]) if log.is_file() else ""
    if OOM_LINE.search(tail):
        raise RuntimeError(f"{variant} owned service OOM")
    return variant == "C" and not entered_service


class HybridRunner(CardRunner):
    def topology(self) -> dict:
        siblings = {cpu: Path(f"/sys/devices/system/cpu/cpu{cpu}/topology/thread_siblings_list").read_text().strip()
                    for cpu in (0, 2)}
        if siblings != {0: "0,24", 2: "2,26"}:
            raise ValueError(f"unexpected SMT topology: {siblings}")
        llama = command(["ps", "-eo", "pid,psr,pcpu,comm"])
        return {"siblings": siblings, "node1_memory": node1_memory(),
                "llama_server": [line for line in llama.splitlines() if "llama-server" in line]}

    def probe(self, arm: Path, env: dict, variant: str) -> dict:
        cases = (("first_shot", f"{self.options.rid}-first-{variant}", 2000, 64),
                 ("dec32k_s3A", "s3A", 32052, 128), ("dec32k_s3B", "s3B", 32052, 128),
                 ("short", f"{self.options.rid}-short-{variant}", 2000, 512))
        results = {}
        for label, cold_id, target, completion in cases:
            target_path = arm / f"{label}.json"
            with (arm / f"{label}.stdout").open("x", encoding="utf-8") as stdout, (arm / f"{label}.err").open("x", encoding="utf-8") as stderr:
                subprocess.run([PY, str(SCR / "cold_eq.py"), cold_id, str(target_path), str(target), str(completion)],
                               cwd=ROOT / "wt/e2base", env=env, stdout=stdout, stderr=stderr, check=True, timeout=1800)
            results[label] = cold_record(target_path, cold_id, target, completion)
        return results

    def run_variant(self, variant: str, reference: Path | None, topology: dict) -> Path:
        if variant == "C" and topology["node1_memory"]["total_kB"] < MEMORY_FLOOR_KB:
            write_new(self.directory / "C_skipped.json", {"state": "skipped_insufficient_node1_memory",
                      "node1_memory": topology["node1_memory"], "required_kB": MEMORY_FLOOR_KB})
            return self.directory / "C"
        entered_service = False
        try:
            with self.service(variant, d0=True, strategy="hybrid", layer_major=False, launch=VARIANTS[variant],
                              reference=reference, allowed_differences={}) as (arm, env):
                entered_service = True
                affinity = json.loads((arm / "affinity.json").read_text(encoding="utf-8"))["actual"]
                if set(affinity) != EXPECTED_AFFINITY[variant]:
                    raise ValueError(f"process affinity differs for {variant}: {affinity}")
                pin = executor_pins(arm, EXPECTED_AFFINITY[variant])
                samples = self.probe(arm, env, variant)
                d0 = d0_evidence(arm)
                write_new(arm / "probe_hashes.json", {name: hashlib.md5((SCR / name).read_bytes()).hexdigest()
                          for name in ("cold_eq.py", "serve_args_diff.py")})
                write_new(arm / "summary.json", {"variant": variant, "executor_pin": pin, "samples": samples,
                          "d0": d0, "pending": ["D08 service-time decomposition", "D06 two-request end-to-end"]})
                return arm
        except TimeoutError:
            arm = self.directory / variant
            if c_timeout_may_skip(variant, entered_service, arm / "serve.log") and arm.is_dir():
                write_new(arm / "NOT_READY.json", {"state": "NOT-READY", "known_risk": "node1 membind startup"})
                return arm
            raise

    def execute(self) -> None:
        if sys.platform != "linux":
            raise RuntimeError("--run is Linux-host only")
        topology = self.topology()  # read-only before the shared admission/gate.
        with self.round_scope() as proof:
            if proof is None:
                return
            write_new(self.directory / "original_topology.json", topology)
            hashes = {name: hashlib.md5((SCR / name).read_bytes()).hexdigest() for name in ("cold_eq.py", "serve_args_diff.py")}
            required = {name: TOOL_MD5[name] for name in hashes}
            if hashes != required:
                raise ValueError(f"original probe hashes differ before launch: {hashes}")
            write_new(self.directory / "probe_hashes_before_launch.json", hashes)
            reference = self.run_variant("V0", None, topology)
            if not reference.is_dir():
                raise RuntimeError("V0 failed; T09 round is void")
            for variant in ("A", "B", "C"):
                self.run_variant(variant, reference, topology)
            write_new(self.directory / "t09_result.json", {"proposed_verdict": "measured", "pending":
                      ["D08 service-time decomposition", "D06 two-request end-to-end"], "variants": list(VARIANTS)})
            self.set_status(state="complete_measurements_pending_review")


def self_test() -> None:
    assert set(A).isdisjoint({0, 2, 24, 26}) and EXPECTED_AFFINITY["B"] == set(NODE1)
    if not re.fullmatch(RID_PATTERN, "E2-R010") or re.fullmatch(RID_PATTERN, "E1-R002b") or re.fullmatch(RID_PATTERN, "E2-R005"):
        raise AssertionError("T09 RID admission accepts an unassigned round")
    with __import__("tempfile").TemporaryDirectory() as temporary:
        arm = Path(temporary) / "arm"; arm.mkdir()
        (arm / "serve.log").write_text(
            "CPU MoE executor ready: threads=23 (pinned to cores 0..22) isa=avx512\n",
            encoding="utf-8",
        )
        range_pins = executor_pins(arm, set(V0))
        assert range_pins["pins"] == list(range(23)) and range_pins["pin_list_complete"]
        assert (arm / "executor_pin.txt").read_text(encoding="utf-8") == (
            "CPU MoE executor ready: threads=23 (pinned to cores 0..22) isa=avx512\n"
        )
        for name, threads, labels, allowed in (
            ("A", 22, "1..47", set(A)),
            ("B", 23, "1..47", set(NODE1)),
        ):
            endpoint = Path(temporary) / name; endpoint.mkdir()
            endpoint_line = f"CPU MoE executor ready: threads={threads} (pinned to cores {labels})\n"
            (endpoint / "serve.log").write_text(endpoint_line, encoding="utf-8")
            endpoint_pins = executor_pins(endpoint, allowed)
            assert endpoint_pins["pins"] is None
            assert endpoint_pins["endpoints"] == [1, 47]
            assert endpoint_pins["raw_span"] == labels
            assert endpoint_pins["pin_list_complete"] is False
            assert (endpoint / "executor_pin.txt").read_text(encoding="utf-8") == endpoint_line
        listed = Path(temporary) / "listed"; listed.mkdir()
        (listed / "serve.log").write_text(
            "CPU MoE executor ready: threads=3 (pinned to cores 1,3,5)\n",
            encoding="utf-8",
        )
        listed_pins = executor_pins(listed, set(NODE1))
        assert listed_pins["pins"] == [1, 3, 5] and listed_pins["pin_list_complete"]
        malformed = Path(temporary) / "malformed"; malformed.mkdir()
        for labels in ("5..1", "1..3,5", "1,1,3"):
            (malformed / "serve.log").write_text(
                f"CPU MoE executor ready: threads=3 (pinned to cores {labels})\n",
                encoding="utf-8",
            )
            try:
                executor_pins(malformed, set(V0))
            except ValueError:
                pass
            else:
                raise AssertionError(f"ambiguous executor labels accepted: {labels}")
        try:
            executor_pins(arm, {0})
        except ValueError:
            pass
        else:
            raise AssertionError("invalid executor affinity accepted")
        sample = {"record": {"cold_id": "x", "cached_tokens": 0, "prompt_tokens": 2000, "completion_tokens": 64,
                  "ttft_s": 1.0, "decode_tps": 2.0}, "diag": {"built_tokens": 2000, "enable_thinking": False,
                  "cache_ok": True, "prompt_len_ok": True, "decode_ok": True}}
        path = arm / "sample.json"; path.write_text(json.dumps(sample), encoding="utf-8")
        assert cold_record(path, "x", 2000, 64)["cached_tokens"] == 0
        assert c_timeout_may_skip("C", False, arm / "missing.log")
        assert not c_timeout_may_skip("C", True, arm / "missing.log")
        oom = arm / "oom.log"; oom.write_text("CUDA out of memory\n", encoding="utf-8")
        try:
            c_timeout_may_skip("C", False, oom)
        except RuntimeError:
            pass
        else:
            raise AssertionError("C OOM was allowed to skip")
        try:
            try:
                raise ValueError("C probe/D0 failure")
            except TimeoutError:
                raise AssertionError("measurement failure must not take C timeout path")
        except ValueError:
            pass
        else:
            raise AssertionError("C measurement failure was swallowed")
    print("SELFTEST PASS: topology sets, executor pin, cold cached-zero validation")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--rid")
    parser.add_argument("--batch", type=int)
    parser.add_argument("--run", action="store_true")
    options = parser.parse_args()
    if options.self_test:
        self_test(); return
    if not (options.rid and options.batch is not None and re.fullmatch(RID_PATTERN, options.rid)):
        parser.error("root-assigned --rid and --batch are required; --run starts measurements")
    options.gate = "T09"  # CardRunner uses this only for status/lock metadata.
    options.runner_file = __file__
    HybridRunner(options).execute()


if __name__ == "__main__":
    main()
