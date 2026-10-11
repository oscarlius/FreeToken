"""Repair r3 metadata/CSV and add the omitted profile-quota pinned sensitivity."""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import pickle
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("stage", HERE / "run_stage0_review_r3.py")
stage = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(stage)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--profile", type=Path, required=True)
    args = ap.parse_args()
    doc = json.loads((args.out / "corrected_results.json").read_text())
    doc["pa_selected_candidate"] = doc.pop("pa_selected_theoretical")
    for row in doc["rows"]:
        if row["tag"] == "FIXED_LAYER@2700":
            row["tag"] = "EQUAL_LAYER_QUOTA@2700"
            row["kind"] = "equal_layer_quota"
    ranked = stage.kimi.read_strp_ranked(args.profile)
    for group in stage.kimi.GROUPS:
        ops = pickle.loads((args.out / f"stream_{group}.pkl").read_bytes())["ops"]
        got = stage.replay(ops, 2700, "pinned", ranked)
        base = next(row for row in doc["rows"] if row["group"] == group and row["tag"] == "LRU@2700")
        got.update({"group": group, "tag": "PROFILE_QUOTA_PINNED@2700", "kind": "profile_quota_pinned",
                    "size": 2700, "every": None, "swaps": None, "theoretical": False,
                    "in_sample": group == stage.kimi.IN_SAMPLE, "preload_bytes": (2700-stage.kimi.PF)*stage.kimi.EXPERT_BYTES,
                    "delta_pp_vs_lru": (got["miss_rate"]-base["miss_rate"])*100,
                    "swap_b_per_step": 0, "L_ktok": doc["context_ktok"][group]})
        got["R_b1"] = stage.kimi.speed(got["miss_rate"], 0, got["L_ktok"], 1)
        got["R_b2"] = stage.kimi.speed(got["miss_rate"], 0, got["L_ktok"], 2)
        doc["rows"].append(got)
    (args.out / "corrected_results_r4.json").write_text(json.dumps(doc, indent=2) + "\n")
    fields = sorted({key for row in doc["rows"] for key in row})
    with (args.out / "corrected_results_r4.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(doc["rows"])


if __name__ == "__main__":
    main()
