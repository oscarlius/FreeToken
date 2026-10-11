"""T03 cut-switch runner.

This is deliberately a Linux-host-only executor.  It performs no work unless
``--run`` is supplied after the E2-base, D00, and T00 admissions have passed.
The CPU-only ``--self-test`` exercises the fail-closed parsers only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import time

import e2_runtime
from t16_runner import (FT, LOCK, MODEL, PY, ROOT, ROUNDS, SCR, TOOL_MD5,
                        Runner, command, events, rows, write_new)


COMMIT = "23f2e2c"
WT = ROOT / "wt/e2base"
TRACE = ROUNDS / "E1-R003" / "trace.json"
ARMS = ("A_cut_on_p1", "B_cut_off_p1", "A_cut_on_p2", "B_cut_off_p2",
        "A_cut_on_p3", "B_cut_off_p3")
REASONS = {"anchor_cap", "token_budget", "layer_major_whole", "continuation", "other"}
SNAPSHOT_LINE = re.compile(r"D0 anchor_snapshots_taken=(\d+)")


def finite_positive(value):
    return type(value) in (float, int) and math.isfinite(value) and value > 0


def classify_tax(value):
    """Keep probe pair zero cold; pairs one through four are hot observations."""
    if value.get("reps") != 5:
        raise ValueError("checkpoint probe must contain exactly one cold and four hot pairs")
    for key in ("single", "multi"):
        values = value.get(key)
        if not isinstance(values, list) or len(values) != 5 or not all(finite_positive(v) for v in values):
            raise ValueError(f"invalid checkpoint tax {key}")
    return {"cold": {key: value[key][0] for key in ("single", "multi")},
            "hot": {key: value[key][1:] for key in ("single", "multi")}}


def strict_pair(left, right, ab=False):
    """Parsed-argument union gate: only PID and the declared cut switch may vary."""
    required = {"model_path", "server_port", "special_token_ckpt", "mamba_host_slots",
                "prefill_anchor_cut", "_unique_suffix"}
    if required - left.keys() or required - right.keys():
        raise ValueError(f"missing parsed fields: {(required - left.keys()) | (required - right.keys())}")
    differences = {}
    for key in left.keys() | right.keys():
        a, b = left.get(key), right.get(key)
        if a == b:
            continue
        if key == "_unique_suffix":
            for value in (a, b):
                if not isinstance(value, str) or not re.fullmatch(r"'\.pid=\d+'", value):
                    raise ValueError(f"invalid service PID suffix: {value!r}")
            differences[key] = [a, b]
            continue
        if ab and key == "prefill_anchor_cut" and {a, b} == {"True", "False"}:
            differences[key] = [a, b]
            continue
        raise ValueError(f"unexpected parsed-argument difference {key}: {a!r} -> {b!r}")
    expected = {"_unique_suffix", "prefill_anchor_cut"} if ab else {"_unique_suffix"}
    if set(differences) != expected:
        raise ValueError(f"parsed-argument union is not exact: {set(differences)!r}")
    return differences


def trace_round_digests(path):
    """Use the original trace's recorded digests; never recreate its hash algorithm."""
    document = json.loads(path.read_text())
    rounds = document.get("rounds") if isinstance(document, dict) else None
    if not isinstance(rounds, list):
        raise ValueError(f"invalid trace schema: {path}")
    result = {}
    for entry in rounds:
        record = entry.get("record") if isinstance(entry, dict) else None
        if not isinstance(record, dict) or type(record.get("round")) is not int:
            raise ValueError("trace record/round missing")
        digest = record.get("messages_sha")
        if not isinstance(digest, str) or not digest or record["round"] in result:
            raise ValueError("trace digest missing or duplicate round")
        result[record["round"]] = digest
    if set(result) != set(range(12)):
        raise ValueError(f"trace rounds are not exactly 0..11: {sorted(result)}")
    return result


def replay_by_sha(path, expected):
    """Validate each live replay row against the immutable trace round/digest map."""
    value = json.loads(path.read_text())
    rounds = value.get("rounds") if isinstance(value, dict) else None
    if not isinstance(rounds, list) or not rounds:
        raise ValueError(f"invalid replay schema: {path}")
    result = {}
    for row in rounds:
        if not isinstance(row, dict):
            raise ValueError("replay row is not an object")
        for key in ("round", "messages_sha", "trace_messages_sha", "cached_tokens", "ttft_any_s", "dry_run", "error"):
            if key not in row:
                raise ValueError(f"replay field missing: {key}")
        digest, trace_digest, round_number = row["messages_sha"], row["trace_messages_sha"], row["round"]
        if not isinstance(digest, str) or not digest or digest != trace_digest or expected.get(round_number) != digest:
            raise ValueError("replay input digest differs from its trace round")
        if (round_number in result or type(round_number) is not int or type(row["cached_tokens"]) is not int
                or row["cached_tokens"] < 0 or row["dry_run"] is not False or row["error"] is not None
                or not finite_positive(row["ttft_any_s"])):
            raise ValueError("duplicate digest or invalid/non-live replay record")
        # Cached-token counts and timings are live measurement outputs.  They
        # must validate above but are not immutable replay-input identity.
        result[round_number] = digest
    if set(result) != set(expected):
        raise ValueError(f"replay rounds are not the immutable trace set: {sorted(result)}")
    return result


def compare_replays(trace, *paths):
    expected = trace_round_digests(trace)
    maps = [replay_by_sha(path, expected) for path in paths]
    if any(value != maps[0] for value in maps[1:]):
        raise ValueError("replays did not preserve the same input mapping")
    return maps[0]


def validate_d0(arm, p0, p1, p2):
    """Validate every scheduled segment while the service remains alive.

    The records are schedule-time metadata: a request ID may appear in multiple
    segments, so tax request groups are built from actual ``rid`` values rather
    than an assumed one-line-per-request layout.
    """
    sequence = events(arm / "serve.log")
    records = rows(arm / "d0_prefill.jsonl")
    if len(records) != len(sequence) or not (0 <= p0 <= p1 <= p2 == len(sequence)):
        raise ValueError("D0 final row missing/extra or invalid P0/P1/P2 markers")
    tax = {}
    first_order = []
    for index, (record, expected) in enumerate(zip(records, sequence)):
        reqs = record.get("reqs")
        actual = (len(reqs) if isinstance(reqs, list) else -1,
                  sum(r.get("new_tokens", -1) for r in reqs) if isinstance(reqs, list) else -1,
                  sum(r.get("cached_tokens", -1) for r in reqs) if isinstance(reqs, list) else -1)
        if (record.get("chunk") != index or not reqs or actual != expected
                or record.get("seg_reason") not in REASONS
                or any(type(record.get(key)) is not int or record[key] < 0 for key in ("h2d_bytes", "d2d_bytes"))
                or not all(isinstance(record.get(key), (float, int)) and math.isfinite(record[key])
                           for key in ("t_start", "t_end")) or record["t_end"] < record["t_start"]):
            raise ValueError(f"D0 metadata mismatch at row {index}")
        if index < p1 or index >= p2:
            continue
        for request in reqs:
            if set(("rid", "new_tokens", "cached_tokens")) - request.keys():
                raise ValueError(f"D02 request metadata missing at row {index}")
            rid = request["rid"]
            if type(rid) not in (int, str) or type(request["new_tokens"]) is not int or type(request["cached_tokens"]) is not int:
                raise ValueError("invalid D02 request metadata type")
            if rid not in tax:
                tax[rid] = []
                first_order.append(rid)
            tax[rid].append({"row": index, "new_tokens": request["new_tokens"],
                             "cached_tokens": request["cached_tokens"], "seg_reason": record["seg_reason"]})
    # The unchanged tax probe alternates single,multi exactly five times.
    if len(first_order) != 10:
        raise ValueError(f"tax telemetry has {len(first_order)} unique request IDs, expected 10")
    multi_rids = [first_order[i] for i in (1, 3, 5, 7, 9)]
    cold_rid = multi_rids[0]
    for rid, segments in tax.items():
        # D02 reports prefix-cache hits only at admission. Continuations
        # contribute zero cached tokens, matching the original Prefill log.
        for current in segments[1:]:
            if current["cached_tokens"] != 0:
                raise ValueError(f"continuation reports an admission cache hit for request {rid!r}")
    if tax[cold_rid][0]["cached_tokens"] > 64:
        raise ValueError("cold multi request first segment has cached_tokens > 64")
    return {"p0": p0, "p1": p1, "p2": p2, "tax_request_order": first_order,
            "tax_multi": {"cold_rid": cold_rid, "hot_rids": multi_rids[1:],
                          "by_rid": {str(rid): tax[rid] for rid in multi_rids}}}


def snapshot_count(arm):
    values = [int(value) for value in SNAPSHOT_LINE.findall((arm / "serve.log").read_text())]
    if len(values) != 1:
        raise ValueError("expected exactly one final successful snapshot count log")
    return values[0]


class T03Runner(Runner):
    def __init__(self, options):
        options.gate = "T03"
        super().__init__(options)
        self.status = self.directory / f"status_batch{options.batch}.json"
        self.parsed_arms = {}

    def set_status(self, **values):
        super().set_status(rid=self.options.rid, **values)

    def lock_take(self):
        self.token = json.dumps({"owner": self.options.rid, "card": "T03", "pid": os.getpid(),
                                 "since": time.strftime("%F %T %Z")})
        fd = os.open(LOCK, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, "w") as handle:
            handle.write(self.token)
        self.lock_inode = LOCK.stat().st_ino

    def prerequisites(self):
        proof = e2_runtime.admission()
        full_commit, tag = proof["commit"], proof["code_version"]
        if not TRACE.is_file():
            raise RuntimeError("original E1-R003 trace is missing")
        hashes = {name: hashlib.md5((SCR / name).read_bytes()).hexdigest() for name in TOOL_MD5}
        if hashes != TOOL_MD5:
            raise ValueError(f"original tool hash differs: {hashes}")
        source = self.gate(WT, COMMIT)
        command(["numactl", "--cpunodebind=0,1", "--interleave=all", FT, "--help"], env=self.environment(WT), cwd=WT)
        return {**proof, "rid": self.options.rid, "card": "T03", "trace": str(TRACE),
                "commit": full_commit, "tag": tag, "source": source, "tools_md5": hashes,
                "agent_trace_sha256": hashlib.sha256((SCR / "agent_trace.py").read_bytes()).hexdigest(),
                "trace_sha256": hashlib.sha256(TRACE.read_bytes()).hexdigest(),
                "trace_round_digests": trace_round_digests(TRACE)}

    def run_arm(self, name):
        source = self.gate(WT, COMMIT)
        arm = self.directory / name
        arm.mkdir(exist_ok=False)
        cut_on = name.startswith("A_")
        env = self.environment(WT, arm, d0=True)
        argv = ["numactl", "--cpunodebind=0,1", "--interleave=all", FT, "serve",
                "--model-path", str(ROOT / "models/Qwen3.8-Flash-Next-NVFP4-overlay"),
                "--served-model-name", MODEL, "--host", "0.0.0.0", "--port", "8095", "--memory-ratio", "0.88",
                "--moe-cache-auto", "--moe-prefill-hit-d2d", "--ple-backend", "pinned", "--moe-strategy", "offload",
                "--quant-backend", "moe.nvfp4=triton", "--max-running-requests", "2", "--cuda-graph-max-bs", "2",
                "--kv-reserve-tokens", "49152", "--max-seq-len-override", "49152", "--max-prefill-length", "4096",
                "--enable-cache-report", "--enable-special-token-ckpt", "--prefill-layer-major", "--mamba-host-slots", "0",
                "--tool-call-parser", "qwen3_coder", "--reasoning-parser", "qwen3"]
        if not cut_on:
            argv.append("--no-prefill-anchor-cut")
        selected = ("PYTHONPATH", "PYTHONUNBUFFERED", "VIRTUAL_ENV", "PATH", "LD_LIBRARY_PATH", "FT_DEV_D0", "FT_DEV_D0_PATH")
        (arm / "SERVE_CMD.txt").write_text("env " + " ".join(k + "=" + shlex.quote(env[k]) for k in selected) + " " + shlex.join(argv) + "\n")
        (arm / "ENV.txt").write_text(time.strftime("%F %T CST") + "\n" + source + "\n"
                                     + command(["hostname"]) + "\n"
                                     + command(["git", "-C", str(WT), "log", "-1", "--format=%H %s"]) + "\n"
                                     + command(["nvidia-smi"]) + "\n" + command(["numactl", "-H"]) + "\n"
                                     + "\n".join(command(["ps", "-eo", "pid,pcpu,pmem,comm", "--sort=-pcpu"]).splitlines()[:9]) + "\n")
        extensions = command([PY, "-c", "import hashlib,json,freetoken.kernel._cpu_moe as a,freetoken.kernel._pinned_tensor as b;"
                              "print(json.dumps([{\"path\":m.__file__,\"sha256\":hashlib.sha256(open(m.__file__,\"rb\").read()).hexdigest()} for m in (a,b)]))"],
                             env=env, cwd=WT)
        write_new(arm / "compiled_extensions.json", json.loads(extensions))
        with (arm / "serve.log").open("x") as log:
            self.proc = subprocess.Popen(argv, env=env, cwd=WT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                if os.getpgid(self.proc.pid) != self.proc.pid or os.getsid(self.proc.pid) != self.proc.pid:
                    raise RuntimeError("owned service process group/session mismatch")
                self.set_status(state="loading", arm=name, service_pid=self.proc.pid)
                self.ready(arm)
                parsed = self.parser(str(arm / "serve.log"))
                if parsed.get("_unique_suffix") != repr(".pid=" + str(self.proc.pid)) or parsed.get("prefill_anchor_cut") != str(cut_on):
                    raise ValueError("service PID or cut-switch parsed argument differs")
                text = (arm / "serve.log").read_text()
                (arm / "serve_args.txt").write_text("\n".join(text[text.index("Parsed arguments"):].splitlines()[:2]) + "\n")
                # The relevant union is checked before either replay or tax probe.
                checks = {}
                if name.startswith("B_"):
                    reference = "A_cut_on_p" + name.rsplit("p", 1)[1]
                    checks["AB"] = strict_pair(self.parsed_arms[reference], parsed, ab=True)
                    if name != "B_cut_off_p1":
                        checks["B_p1"] = strict_pair(self.parsed_arms["B_cut_off_p1"], parsed)
                elif name != "A_cut_on_p1":
                    checks["A_p1"] = strict_pair(self.parsed_arms["A_cut_on_p1"], parsed)
                else:
                    checks["self"] = {"_unique_suffix": [parsed["_unique_suffix"], parsed["_unique_suffix"]]}
                self.parsed_arms[name] = parsed
                write_new(arm / "args_preprobe_checked.json", checks)
                p0 = len(events(arm / "serve.log"))
                self.set_status(state="probing", arm=name, service_pid=self.proc.pid)
                for suffix, fresh_note in (("T1_replay", f"{self.options.rid}-{name}"),
                                           ("T1_replay_pass2", f"{self.options.rid}-{name}-pass2")):
                    with (arm / (suffix + ".log")).open("x") as out:
                        subprocess.run([PY, str(SCR / "agent_trace.py"), "replay", "--trace", str(TRACE), "--out", str(arm / (suffix + ".json")), "--fresh-note", fresh_note], env=env, cwd=WT, stdout=out, stderr=subprocess.STDOUT, check=True, timeout=3600)
                p1 = len(events(arm / "serve.log"))
                compare_replays(TRACE, arm / "T1_replay.json", arm / "T1_replay_pass2.json")
                with (arm / "tax.log").open("x") as out:
                    subprocess.run([PY, str(SCR / "ft_probe_ckpt_tax.py"), str(arm / "tax.json"), name], env=env, cwd=WT, stdout=out, stderr=subprocess.STDOUT, check=True, timeout=1800)
                p2 = len(events(arm / "serve.log"))
                tax = classify_tax(json.loads((arm / "tax.json").read_text()))
                telemetry = validate_d0(arm, p0, p1, p2)
                if self.proc.poll() is not None:
                    raise RuntimeError("service died before final D0 telemetry verification")
                write_new(arm / "markers.json", {"P0": p0, "P1": p1, "P2": p2})
                write_new(arm / "tax_classification.json", tax)
                write_new(arm / "tax_metadata.json", telemetry)
                write_new(arm / "d0_while_alive.json", {"service_pid": self.proc.pid, "process_alive": True,
                                                           "prefill_events": len(events(arm / "serve.log"))})
            finally:
                self.stop()
        write_new(arm / "snapshot_count.json", {"actual_successful_snapshots": snapshot_count(arm)})
        return arm

    def execute(self):
        admission = self.prerequisites()
        print("T03 PREFLIGHT PASS " + json.dumps(admission), flush=True)
        if not self.options.run:
            return
        self.lock_take()
        created = False
        try:
            # A collision never writes a status into another owner's round.
            self.directory.mkdir(exist_ok=False)
            created = True
            write_new(self.directory / "admission.json", admission)
            for source, destination in ((Path(__file__), "runner.py"), (Path(e2_runtime.__file__), "e2_runtime.py"),
                                        (Path(__file__).with_name("t16_runner.py"), "t16_runner.py")):
                with (self.directory / destination).open("xb") as target:
                    target.write(source.read_bytes())
            wrapper = Path(__file__).with_name(f"batch{self.options.batch}_{self.options.rid}_python.sh")
            if not wrapper.is_file():
                raise RuntimeError(f"actual batch wrapper missing: {wrapper}")
            with (self.directory / "batch.sh").open("xb") as target:
                target.write(wrapper.read_bytes())
            self.set_status(state="running")
            arms = [self.run_arm(name) for name in ARMS]
            parsed = {arm.name: self.parser(str(arm / "serve.log")) for arm in arms}
            diffs = {}
            for number in range(1, 4):
                a, b = f"A_cut_on_p{number}", f"B_cut_off_p{number}"
                diffs[f"AB_p{number}"] = strict_pair(parsed[a], parsed[b], ab=True)
            diffs["A_p1_p3"] = strict_pair(parsed["A_cut_on_p1"], parsed["A_cut_on_p3"])
            diffs["B_p1_p3"] = strict_pair(parsed["B_cut_off_p1"], parsed["B_cut_off_p3"])
            # Input equality crosses arms by digest; fresh-note is metadata only.
            arm_inputs = {arm.name: compare_replays(TRACE, arm / "T1_replay.json", arm / "T1_replay_pass2.json") for arm in arms}
            if any(value != arm_inputs[arms[0].name] for value in arm_inputs.values()):
                raise ValueError("T1 arms did not replay the same inputs")
            write_new(self.directory / "args_checked.json", diffs)
            write_new(self.directory / "input_sha_checked.json", arm_inputs)
            self.set_status(state="complete_measurements_pending_review")
            print("T03 MEASUREMENTS COMPLETE; verdict remains pending independent review", flush=True)
        except BaseException as exc:
            if created:
                self.set_status(state="failed", error=repr(exc))
            raise
        finally:
            try:
                self.stop()
            finally:
                if self.proc is None:
                    self.lock_release()


def self_test():
    from unittest.mock import patch
    options = argparse.Namespace(rid="E2-R001", batch=28, run=False)
    with patch("t16_runner.runpy.run_path", return_value={"parse": lambda _: {}}):
        initialized = T03Runner(options)
    assert initialized.options.gate == "T03" and initialized.allowed == {}
    base = {"model_path": "'/model'", "server_port": "8095", "special_token_ckpt": "True", "mamba_host_slots": "0", "prefill_anchor_cut": "True", "_unique_suffix": "'.pid=1'"}
    cut_off = {**base, "prefill_anchor_cut": "False", "_unique_suffix": "'.pid=2'"}
    strict_pair(base, cut_off, ab=True)
    strict_pair(base, {**base, "_unique_suffix": "'.pid=3'"})
    for bad in ({**cut_off, "server_port": "8096"}, {**cut_off, "mamba_host_slots": "1"}, {**cut_off, "_unique_suffix": "'wrong'"}):
        try:
            strict_pair(base, bad, ab=True)
        except ValueError:
            pass
        else:
            raise AssertionError("argument pollution accepted")
    tax = classify_tax({"reps": 5, "single": [1, 2, 3, 4, 5], "multi": [2, 3, 4, 5, 6]})
    assert tax["cold"]["multi"] == 2 and tax["hot"]["multi"] == [3, 4, 5, 6]
    with __import__("tempfile").TemporaryDirectory() as temporary:
        directory = Path(temporary)
        path = directory / "replay.json"
        trace = directory / "trace.json"
        trace.write_text(json.dumps({"rounds": [{"record": {"round": i, "messages_sha": f"a{i}"}}
                                                for i in range(12)]}))
        good_replay = {"rounds": [{"round": i, "messages_sha": f"a{i}", "trace_messages_sha": f"a{i}",
                                    "cached_tokens": 0, "ttft_any_s": 1.0, "dry_run": False, "error": None}
                                   for i in range(12)]}
        path.write_text(json.dumps(good_replay))
        changed_metrics = json.loads(json.dumps(good_replay))
        changed_metrics["rounds"][0]["cached_tokens"] = 99
        changed_metrics["rounds"][0]["ttft_any_s"] = 9.0
        metric_path = directory / "replay_metrics_differ.json"
        metric_path.write_text(json.dumps(changed_metrics))
        assert compare_replays(trace, path, metric_path) == {i: f"a{i}" for i in range(12)}
        bad_replay = json.loads(json.dumps(good_replay))
        bad_replay["rounds"][0]["trace_messages_sha"] = "b"
        path.write_text(json.dumps(bad_replay))
        try:
            replay_by_sha(path, trace_round_digests(trace))
        except ValueError:
            pass
        else:
            raise AssertionError("mismatched trace digest accepted")
        path.write_text(json.dumps(good_replay))
        wrong_trace = directory / "wrong_trace.json"
        wrong_trace.write_text(json.dumps({"rounds": [{"record": {"round": i, "messages_sha": f"wrong{i}"}}
                                                      for i in range(12)]}))
        try:
            compare_replays(wrong_trace, path)
        except ValueError:
            pass
        else:
            raise AssertionError("wrong trace accepted")
        duplicate = json.loads(json.dumps(good_replay))
        duplicate["rounds"][1]["round"] = 0
        path.write_text(json.dumps(duplicate))
        try:
            compare_replays(trace, path)
        except ValueError:
            pass
        else:
            raise AssertionError("duplicate replay round accepted")
        arm = directory / "arm"
        arm.mkdir()

        def write_tax_telemetry(first_cached):
            entries = [(100, 1, 0), (101, 6400, first_cached), (101, 624, 0)]
            entries += [(rid, 1, 0) for rid in range(102, 110)]
            log, telemetry = [], []
            for chunk, (rid, new_tokens, cached_tokens) in enumerate(entries):
                log.append(f"#new-seq: 1, #new-token: {new_tokens}, #cached-token: {cached_tokens}\n")
                telemetry.append({"chunk": chunk, "h2d_bytes": 0, "d2d_bytes": 0, "seg_reason": "other",
                                  "t_start": float(chunk), "t_end": float(chunk + 1),
                                  "reqs": [{"rid": rid, "new_tokens": new_tokens, "cached_tokens": cached_tokens}]})
            (arm / "serve.log").write_text("".join(log))
            (arm / "d0_prefill.jsonl").write_text("".join(json.dumps(row) + "\n" for row in telemetry))

        write_tax_telemetry(0)
        metadata = validate_d0(arm, 0, 0, 11)
        assert metadata["tax_multi"]["cold_rid"] == 101
        assert metadata["tax_multi"]["by_rid"]["101"][1]["cached_tokens"] == 0
        corrupted = rows(arm / "d0_prefill.jsonl")
        corrupted[2]["reqs"][0]["cached_tokens"] = 6400
        log = (arm / "serve.log").read_text().replace("#new-token: 624, #cached-token: 0", "#new-token: 624, #cached-token: 6400")
        (arm / "serve.log").write_text(log)
        (arm / "d0_prefill.jsonl").write_text("".join(json.dumps(row) + "\n" for row in corrupted))
        try:
            validate_d0(arm, 0, 0, 11)
        except ValueError:
            pass
        else:
            raise AssertionError("continuation admission-cache hit accepted")
        write_tax_telemetry(128)
        try:
            validate_d0(arm, 0, 0, 11)
        except ValueError:
            pass
        else:
            raise AssertionError("cold first-segment cache breach accepted")
    print("T03 SELFTEST PASS: AB union, cold/hot separation, segmented coldness, replay schema fail closed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rid", help="assigned E2-R identifier; no directory is created without --run")
    parser.add_argument("--batch", type=int)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    options = parser.parse_args()
    if options.self_test:
        self_test()
        return
    if not options.rid or not re.fullmatch(r"E2-R\d+", options.rid) or options.batch is None:
        parser.error("assigned --rid E2-R### and --batch are required")
    if sys.platform != "linux":
        parser.error("remote preflight/run require the Linux test host")
    runner = T03Runner(options)
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda signum, frame: (_ for _ in ()).throw(InterruptedError(f"signal {signum}")))
    runner.execute()


if __name__ == "__main__":
    main()
