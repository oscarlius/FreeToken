"""Read completed T07/T08/T09 measurements and write one new review-only JSON."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import tempfile


RID = {"T07": "E2-R003", "T08": "E2-R009", "T09": "E2-R010"}
ARM_FILES = ("SERVE_CMD.txt", "serve.log", "serve_args.txt", "ENV.txt")
COMMIT = re.compile(r"[0-9a-f]{40}")
EXPECTED_COMMIT = "23f2e2caa3395837c9474735ffc83321f3b9b5a1"
CREATED = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} CST$")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def number(value, name):
    if not finite(value):
        raise ValueError(f"non-finite numeric field: {name}")
    return value


def numeric_tree(value, name):
    if finite(value):
        return value
    if isinstance(value, list):
        return [numeric_tree(item, name) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError(f"non-string statistic key: {name}")
        return {key: numeric_tree(item, name) for key, item in value.items()}
    raise ValueError(f"non-numeric statistic: {name}")


def record(value, name):
    if not isinstance(value, dict):
        raise ValueError(f"missing record: {name}")
    for key in ("ttft_s", "decode_tps"):
        if not finite(value.get(key)) or value[key] <= 0:
            raise ValueError(f"invalid {key}: {name}")
    return value


def write_new(path, value):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def status_admission(directory, card, rid):
    if directory.name != rid:
        raise ValueError(f"{card} requires exact RID directory {rid}")
    statuses = list(directory.glob("status_batch*.json"))
    if len(statuses) != 1:
        raise ValueError("exactly one status_batchN.json is required")
    status = read(statuses[0])
    batch = status.get("batch")
    if (status.get("state") != "complete_measurements_pending_review" or status.get("gate") != card
            or status.get("rid") != rid or type(batch) is not int or batch <= 0
            or statuses[0].name != f"status_batch{batch}.json"):
        raise ValueError("terminal status/card/batch is not admitted")
    admission_path = directory / "admission.json"
    if not admission_path.is_file():
        raise ValueError("admission missing")
    admission = read(admission_path)
    commit, tag = admission.get("commit"), admission.get("code_version")
    if (admission.get("rid") != rid or admission.get("card") != card or commit != EXPECTED_COMMIT
            or not COMMIT.fullmatch(commit) or tag != f"E2-base@{commit[:7]}"):
        raise ValueError("admission must bind full commit and short E2 tag")
    return admission, status


def arm(directory, name):
    result = directory / name
    if not result.is_dir() or any(not (result / file).is_file() or not (result / file).stat().st_size for file in ARM_FILES):
        raise ValueError(f"missing active arm evidence: {name}")
    return result


def created_at(arms):
    values = []
    for path in arms:
        first = (path / "ENV.txt").read_text(encoding="utf-8").splitlines()
        if not first or not CREATED.fullmatch(first[0]):
            raise ValueError(f"invalid first ENV timestamp: {path}")
        values.append(first[0])
    return min(values)


def archive(directory, card):
    names = ("admission.json", "batch.sh", f"{card.lower()}_runner.py", "e2_runtime.py", "t16_runner.py", "t00_runner.py")
    missing = [name for name in names if not (directory / name).is_file()]
    if missing:
        raise ValueError(f"actual source archive missing: {missing}")
    return {name: digest(directory / name) for name in names}


def base(directory, card, rid, arms):
    admission, status = status_admission(directory, card, rid)
    return {"schema": "ft_round/v2", "round_id": rid, "epoch": 2, "card": card,
            "created_at": created_at(arms), "base": {"commit": admission["commit"], "code_version": admission["code_version"]},
            "serve": {"arms": {path.name: {"serve_cmd": f"{path.name}/SERVE_CMD.txt", "serve_log": f"{path.name}/serve.log",
                                             "serve_args": f"{path.name}/serve_args.txt", "env": f"{path.name}/ENV.txt"} for path in arms}},
            "verdict": "pending_review", "proposed_verdict": None, "verdict_history": [], "retractions": [],
            "evidence": {"status": status, "archive_sha256": archive(directory, card)}}


def t07(directory):
    names = tuple(f"{letter}_d0{'on' if letter == 'A' else 'off'}_p{phase}" for phase in range(1, 4) for letter in "AB")
    arms = [arm(directory, name) for name in names]
    summary = read(directory / "measurement_summary.json")
    if summary.get("code_version") != status_admission(directory, "T07", RID["T07"])[0]["code_version"]:
        raise ValueError("T07 summary code version differs")
    results, diagnostics = {}, summary.get("text_comparisons")
    if not isinstance(diagnostics, list):
        raise ValueError("T07 text diagnostics missing")
    for target, item in (summary.get("results") or {}).items():
        if not isinstance(item, dict) or not re.fullmatch(r"\d+", target):
            raise ValueError("invalid T07 target result")
        output = {"prediction_s": number(item.get("prediction_s"), "prediction_s"),
                  "holdout_relative": number(item.get("holdout_relative"), "holdout_relative")}
        samples = item.get("samples")
        if not isinstance(samples, dict):
            raise ValueError("T07 samples missing")
        for metric in ("ttft_s", "decode_tps"):
            delta = item.get(metric)
            if not isinstance(delta, dict) or not isinstance(delta.get("interval"), list) or len(delta["interval"]) != 2:
                raise ValueError("T07 delta/CI missing")
            output[metric] = {key: number(delta.get(key), key) for key in ("difference", "relative")}
            output[metric]["interval"] = [number(x, "interval") for x in delta["interval"]]
            for group in ("A", "B"):
                rows = samples.get(group)
                if not isinstance(rows, list) or len(rows) != 6:
                    raise ValueError("T07 requires six actual samples per group")
                output[f"{group}_{metric}"] = [record(row, "T07 sample")[metric] for row in rows]
        results[target] = output
    if set(results) != {"8000", "16000", "32052", "48000"}:
        raise ValueError("T07 required holdout lengths missing")
    first = {path.name: record(read(path / "first_shot.json").get("record"), path.name) for path in arms}
    document = base(directory, "T07", RID["T07"], arms)
    document.update(results={"lengths": results}, first_shots=first,
                    diagnostics={"text_comparisons": diagnostics}, sources={"measurement_summary_sha256": digest(directory / "measurement_summary.json")})
    return document


def replay(path):
    rows = read(path).get("rounds")
    if not isinstance(rows, list) or len(rows) != 12:
        raise ValueError("agent replay needs 12 records")
    indexed = {row.get("round"): row for row in rows if isinstance(row, dict)}
    if set(indexed) != set(range(12)):
        raise ValueError("agent replay indices differ")
    values = [number(indexed[index].get("ttft_any_s"), "agent ttft") for index in range(1, 12)]
    return {"indices": list(range(1, 12)), "mean_ttft_s": statistics.mean(values), "max_ttft_s": max(values)}


def list_metrics(rows, name):
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"missing {name} samples")
    valid = [record(row, name) for row in rows]
    return {"ttft_s": [row["ttft_s"] for row in valid], "decode_tps": [row["decode_tps"] for row in valid],
            "median_ttft_s": statistics.median(row["ttft_s"] for row in valid), "median_decode_tps": statistics.median(row["decode_tps"] for row in valid)}


def t08_optional(values):
    quality, soak = values.get("quality60", {}), values.get("soak", {})
    if type(quality.get("returncode")) is not int or type(soak.get("returncode")) is not int:
        raise ValueError("T08 quality/soak return code missing")
    optional = {"quality60": {"returncode": quality["returncode"]}, "soak": {"returncode": soak["returncode"]}}
    diagnostics = {}
    if quality["returncode"] == 0:
        statuses, path = quality.get("statuses"), quality.get("path")
        if (not isinstance(path, str) or not path or not isinstance(statuses, dict) or not statuses
                or not all(isinstance(key, str) and type(value) is int and value >= 0 for key, value in statuses.items())
                or quality.get("total") != sum(statuses.values()) or not finite(quality.get("pass_rate"))):
            raise ValueError("successful quality run lacks path/score/count/statuses")
        optional["quality60"].update(total=quality["total"], pass_rate=quality["pass_rate"])
        diagnostics.update(quality60_path=path, quality60_statuses=statuses)
    else:
        diagnostics["quality60_gap"] = "nonzero returncode"
    if soak["returncode"] == 0:
        required = ("total_requests", "successful_requests", "errors", "actual_duration_s")
        if (any(not finite(soak.get(key)) for key in required) or type(soak.get("usable_number_gate")) is not bool):
            raise ValueError("successful soak run lacks count/duration/gate")
        optional["soak"].update({key: soak[key] for key in required})
        diagnostics["soak_usable_number_gate"] = soak["usable_number_gate"]
    else:
        diagnostics["soak_gap"] = "nonzero returncode"
    for value in optional.values():
        if any(not finite(item) for item in value.values()):
            raise ValueError("T08 optional metric is non-finite")
    return optional, diagnostics


def verify_p1_binding(parent, binding):
    hashes = binding.get("parent_files_sha256")
    expected_keys = {"admission.json", "measurement_summary.json", "t08_runner.py", "e2_runtime.py", "P1/measurements.json"}
    if binding.get("parent_rid") != RID["T08"] or not isinstance(hashes, dict) or set(hashes) != expected_keys:
        raise ValueError("P2 source binding missing")
    if not hashes or any(not isinstance(key, str) or not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
                         for key, value in hashes.items()):
        raise ValueError("P2 source binding hashes invalid")
    for relative, expected in hashes.items():
        path = parent / relative
        if Path(relative).is_absolute() or ".." in Path(relative).parts or not path.is_file() or digest(path) != expected:
            raise ValueError(f"P2 binding source differs: {relative}")
    return hashes


def t08(directory, phase, parent=None):
    if phase == "P1":
        rid, name = RID["T08"], "P1"
    elif phase == "P2":
        rid, name = RID["T08"] + "-p64k", "P2"
    else:
        raise ValueError("T08 phase must be P1 or P2")
    current = arm(directory, name)
    admission, _ = status_admission(directory, "T08", rid)
    values = read(current / "measurements.json")
    document = base(directory, "T08", rid, [current])
    if phase == "P1":
        optional, optional_diagnostics = t08_optional(values)
        document.update(results={"cold32": list_metrics(values.get("cold32k"), "P1 cold32"),
                                 "short": list_metrics([values.get("short")], "P1 short"),
                                 "agent": {entry: replay(current / f"{entry}.json") for entry in ("agent_coldfirst", "agent_warm", "agent_edit")}},
                        first_shots={"P1": record(values.get("first_shot"), "P1 first")},
                        diagnostics={"two_decode": values.get("two_decode"), "D06_gap": "pending; D06 is not inferred", **optional_diagnostics},
                        optional=optional, sources={"measurements_sha256": digest(current / "measurements.json")})
        return document
    parent = parent or directory.parent / RID["T08"]
    parent_admission, _ = status_admission(parent, "T08", RID["T08"])
    if (parent_admission.get("commit") != admission.get("commit")
            or parent_admission.get("code_version") != admission.get("code_version")):
        raise ValueError("P1/P2 baseline fields differ")
    binding = read(directory / "parent_p1_binding.json")
    document.update(results={"cold64": list_metrics(values.get("cold64k"), "P2 cold64"),
                             "cold32": list_metrics(values.get("cold32k"), "P2 cold32")},
                    first_shots={"P2": record(values.get("first_shot"), "P2 first")},
                    diagnostics={"D06_gap": "pending; D06 is not inferred"},
                    sources={"parent_p1_binding": binding, "verified_parent_sha256": verify_p1_binding(parent, binding),
                             "measurements_sha256": digest(current / "measurements.json")})
    return document


def t09(directory):
    result = read(directory / "t09_result.json")
    if result.get("variants") != ["V0", "A", "B", "C"]:
        raise ValueError("T09 variant declaration differs")
    active, gaps, first = [], {}, {}
    outputs = {}
    for name in ("V0", "A", "B", "C"):
        candidate = directory / name
        skipped, not_ready = directory / "C_skipped.json", candidate / "NOT_READY.json"
        if name == "C" and (skipped.is_file() or not_ready.is_file()):
            if skipped.is_file() and not_ready.is_file():
                raise ValueError("T09 C has mutually exclusive gap markers")
            gap = read(skipped) if skipped.is_file() else read(not_ready)
            expected_state = "skipped_insufficient_node1_memory" if skipped.is_file() else "NOT-READY"
            if gap.get("state") != expected_state:
                raise ValueError("T09 C gap marker is not an allowed state")
            gaps[name] = gap
            continue
        path = arm(directory, name); active.append(path)
        summary = read(path / "summary.json")
        samples = summary.get("samples")
        if summary.get("variant") != name or not isinstance(samples, dict):
            raise ValueError("T09 active variant summary invalid")
        outputs[name] = {"cold32": list_metrics([samples.get("dec32k_s3A"), samples.get("dec32k_s3B")], name + " cold32"),
                         "short": list_metrics([samples.get("short")], name + " short"),
                         "hybrid": {key: numeric_tree(value, key) for key, value in (summary.get("d0", {}).get("hybrid") or {}).items()}}
        if not outputs[name]["hybrid"]:
            raise ValueError("T09 actual D0 hybrid stats missing")
        first[name] = record(samples.get("first_shot"), name + " first")
    document = base(directory, "T09", RID["T09"], active)
    document.update(results={"variants": outputs}, first_shots=first,
                    diagnostics={"optional_variant_gaps": gaps, "pending": result.get("pending")}, sources={"t09_result_sha256": digest(directory / "t09_result.json")})
    return document


def summarize(card, directory, phase=None, parent=None):
    if card == "T07": return t07(directory)
    if card == "T08":
        if phase is None: raise ValueError("T08 requires --phase P1 or P2")
        return t08(directory, phase, parent)
    if card == "T09": return t09(directory)
    raise ValueError("unsupported card")


def self_test():
    assert not finite(True) and finite(1.0)
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp); path = root / "agent.json"
        path.write_text(json.dumps({"rounds": [{"round": index, "ttft_any_s": float(index + 1)} for index in range(12)]}))
        assert replay(path) == {"indices": list(range(1, 12)), "mean_ttft_s": 7.0, "max_ttft_s": 12.0}
        path.write_text(json.dumps({"rounds": [{"round": 0, "ttft_any_s": float("nan")}] * 12}, allow_nan=True))
        try: replay(path)
        except ValueError: pass
        else: raise AssertionError("invalid replay accepted")
        directory = root / "E2-R010"; directory.mkdir()
        commit, tag = EXPECTED_COMMIT, "E2-base@23f2e2c"
        (directory / "admission.json").write_text(json.dumps({"rid": "E2-R010", "card": "T09", "commit": commit, "code_version": tag}))
        (directory / "status_batch7.json").write_text(json.dumps({"rid": "E2-R010", "batch": 7, "gate": "T09", "state": "complete_measurements_pending_review"}))
        for name in ("batch.sh", "t09_runner.py", "e2_runtime.py", "t16_runner.py", "t00_runner.py"):
            (directory / name).write_text(name)
        sample = {"ttft_s": 1.0, "decode_tps": 2.0}
        for name in ("V0", "A", "B"):
            arm_dir = directory / name; arm_dir.mkdir()
            for file in ARM_FILES:
                (arm_dir / file).write_text("2026-10-04 10:00:00 CST\n" if file == "ENV.txt" else file)
            (arm_dir / "summary.json").write_text(json.dumps({"variant": name, "samples": {"first_shot": sample,
                "dec32k_s3A": sample, "dec32k_s3B": sample, "short": sample}, "d0": {"hybrid": {"h2d_bytes": 1, "cpu_per_layer": [1.0]}}}))
        (directory / "C_skipped.json").write_text(json.dumps({"state": "skipped_insufficient_node1_memory"}))
        (directory / "t09_result.json").write_text(json.dumps({"variants": ["V0", "A", "B", "C"], "pending": ["D06"]}))
        summary = t09(directory)
        assert summary["diagnostics"]["optional_variant_gaps"]["C"]["state"] == "skipped_insufficient_node1_memory"
        (directory / "C").mkdir()
        (directory / "C" / "NOT_READY.json").write_text(json.dumps({"state": "NOT-READY"}))
        try: t09(directory)
        except ValueError: pass
        else: raise AssertionError("double C gap marker accepted")
        (directory / "C" / "NOT_READY.json").unlink()
        (directory / "C_skipped.json").write_text(json.dumps({"state": "other"}))
        try: t09(directory)
        except ValueError: pass
        else: raise AssertionError("invalid C gap marker accepted")
        (directory / "C_skipped.json").write_text(json.dumps({"state": "skipped_insufficient_node1_memory"}))
        (directory / "status_batch7.json").unlink()
        try: t09(directory)
        except ValueError: pass
        else: raise AssertionError("missing status accepted")
        (directory / "status_batch7.json").write_text(json.dumps({"rid": "E2-R010", "batch": 7, "gate": "wrong", "state": "complete_measurements_pending_review"}))
        try: t09(directory)
        except ValueError: pass
        else: raise AssertionError("wrong card accepted")
        (directory / "status_batch7.json").write_text(json.dumps({"rid": "E2-R010", "batch": 7, "gate": "T09", "state": "complete_measurements_pending_review"}))
        invalid = read(directory / "A" / "summary.json")
        invalid["samples"]["short"]["ttft_s"] = float("nan")
        (directory / "A" / "summary.json").write_text(json.dumps(invalid, allow_nan=True))
        try: t09(directory)
        except ValueError: pass
        else: raise AssertionError("non-finite measurement accepted")
        invalid["samples"]["short"]["ttft_s"] = 1.0
        (directory / "A" / "summary.json").write_text(json.dumps(invalid))
        (directory / "A" / "SERVE_CMD.txt").unlink()
        try: t09(directory)
        except ValueError: pass
        else: raise AssertionError("arm gap accepted")

        def round_fixture(rid, arm_name):
            directory = root / rid; directory.mkdir()
            (directory / "admission.json").write_text(json.dumps({"rid": rid, "card": "T08", "commit": commit, "code_version": tag}))
            (directory / "status_batch9.json").write_text(json.dumps({"rid": rid, "batch": 9, "gate": "T08", "state": "complete_measurements_pending_review"}))
            for name in ("batch.sh", "t08_runner.py", "e2_runtime.py", "t16_runner.py", "t00_runner.py"):
                (directory / name).write_text(name)
            current = directory / arm_name; current.mkdir()
            for file in ARM_FILES:
                (current / file).write_text("2026-10-04 10:00:00 CST\n" if file == "ENV.txt" else file)
            return directory, current
        p1dir, p1arm = round_fixture("E2-R009", "P1")
        p1record = {"ttft_s": 1.0, "decode_tps": 2.0}
        p1values = {"first_shot": p1record, "cold32k": [p1record, p1record], "short": p1record,
                    "two_decode": {"status": "pending"}, "quality60": {"returncode": 1}, "soak": {"returncode": 1}}
        (p1arm / "measurements.json").write_text(json.dumps(p1values))
        for name in ("agent_coldfirst", "agent_warm", "agent_edit"):
            (p1arm / f"{name}.json").write_text(json.dumps({"rounds": [{"round": i, "ttft_any_s": 1.0} for i in range(12)]}))
        (p1dir / "measurement_summary.json").write_text(json.dumps({"phase": "P1"}))
        p2dir, p2arm = round_fixture("E2-R009-p64k", "P2")
        p2values = {"first_shot": p1record, "cold64k": [p1record, p1record], "cold32k": [p1record, p1record]}
        (p2arm / "measurements.json").write_text(json.dumps(p2values))
        binding_files = ("admission.json", "measurement_summary.json", "t08_runner.py", "e2_runtime.py", "P1/measurements.json")
        binding = {name: digest(p1dir / name) for name in binding_files}
        (p2dir / "parent_p1_binding.json").write_text(json.dumps({"parent_rid": "E2-R009", "parent_files_sha256": binding}))
        assert t08(p1dir, "P1")["round_id"] == "E2-R009"
        assert t08(p2dir, "P2", p1dir)["round_id"] == "E2-R009-p64k"
        binding["admission.json"] = "0" * 64
        (p2dir / "parent_p1_binding.json").write_text(json.dumps({"parent_rid": "E2-R009", "parent_files_sha256": binding}))
        try: t08(p2dir, "P2", p1dir)
        except ValueError: pass
        else: raise AssertionError("wrong P1 binding hash accepted")
        binding.pop("admission.json")
        (p2dir / "parent_p1_binding.json").write_text(json.dumps({"parent_rid": "E2-R009", "parent_files_sha256": binding}))
        try: t08(p2dir, "P2", p1dir)
        except ValueError: pass
        else: raise AssertionError("truncated P1 binding accepted")
        try: t08_optional({"quality60": {"returncode": 0, "total": 1, "pass_rate": 1.0}, "soak": {"returncode": 1}})
        except ValueError: pass
        else: raise AssertionError("successful quality without statuses accepted")
        try: t08_optional({"quality60": {"returncode": 1}, "soak": {"returncode": 0, "total_requests": 1, "errors": 0}})
        except ValueError: pass
        else: raise AssertionError("successful soak without fields accepted")
        optional, diagnostics = t08_optional({"quality60": {"returncode": 0, "path": "quality_results_1.jsonl", "total": 2, "pass_rate": .5, "statuses": {"PASS": 1, "FAIL": 1}},
                                                "soak": {"returncode": 0, "total_requests": 2, "successful_requests": 2, "errors": 0,
                                                         "actual_duration_s": 1800.0, "usable_number_gate": True}})
        assert optional["quality60"]["total"] == 2 and diagnostics["quality60_path"] == "quality_results_1.jsonl" and diagnostics["soak_usable_number_gate"] is True
    print("production_measurement_summarize self-test: PASS")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--card", choices=tuple(RID))
    parser.add_argument("--round", type=Path)
    parser.add_argument("--phase", choices=("P1", "P2"))
    parser.add_argument("--parent-round", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test(); return
    if not args.card or args.round is None or args.out is None or args.out.exists():
        parser.error("card, round, and a new --out are required")
    if args.card != "T08" and (args.phase or args.parent_round):
        parser.error("--phase/--parent-round apply only to T08")
    write_new(args.out, summarize(args.card, args.round, args.phase, args.parent_round))


if __name__ == "__main__":
    main()
