import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("terminal_analysis", HERE / "terminal_analysis.py")
analysis = importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(analysis)


def _metric(uid, token, *, cold=False):
    return {"uid": uid, "input_ids_sha256": f"i{uid}", "native_token_sha256": token, "completion_tokens": 5,
            "decode_elapsed_s": 2, "planned_input_tokens": 129024 if cold else 100, "cached_tokens": 0,
            "min_free_gpu_mib": 10}


def test_analysis_reads_raw_a_b_cold_and_never_labels_kept(tmp_path):
    run = tmp_path / "run"; run.mkdir(); (run / "result.json").write_text(json.dumps({"verdict": "completed"}))
    for name in ("W98K", "W128K"):
        arm = run / name; observer = arm / "observer"; observer.mkdir(parents=True)
        rows = [{"uid": 1, "input_ids_sha256": "i1"}]
        (observer / "inputs.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n")
        (observer / "tokens.jsonl").write_text(json.dumps({"uid": 1}) + "\n")
        (arm / "A0.api.metrics.json").write_text(json.dumps(_metric(1, "same")))
        (arm / "serve.log").write_text("ok")
        (arm / "owned_process.json").write_text("{}")
    (run / "W128K" / "B09.api.metrics.json").write_text(json.dumps(_metric(1, "same")))
    (run / "W128K" / "cold.api.metrics.json").write_text(json.dumps(_metric(1, "cold", cold=True)))
    report = analysis.analyse(run)
    assert report["actual_counts"] == {"A_W98K": 1, "A_W128K": 1, "B_W128K": 1, "cold_W128K": True}
    assert report["cold_checks"]["input_fit"] is True
    assert report["analysis_verdict"].startswith("ANALYSIS_ONLY")
