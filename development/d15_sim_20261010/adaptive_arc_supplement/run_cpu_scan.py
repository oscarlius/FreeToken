"""Default-inert, CPU-only ARC supplement for the D15 review traces."""
import argparse
import hashlib
import json
import pickle
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent
BASE = ROOT.parent
GROUPS = ("G_seed12k", "G_seed_45k", "G_seed_real", "G_two")
SLOTS = (2700, 2401)
EXPECTED_LRU_2700 = {"G_seed12k": (579863, 1545120), "G_seed_45k": (670309, 1885920),
                     "G_seed_real": (208366, 540000), "G_two": (29955, 70334)}
sys.path.insert(0, str(ROOT))
from adaptive_arc import E, NL, PREFILL_SLOTS, replay as arc_replay


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_reference():
    source = BASE / "strategy_predictability_2033" / "run_cpu_scan.py"
    namespace = {}
    exec(compile(source.read_text(encoding="utf-8"), str(source), "exec"), namespace)
    return source, namespace


def fixed_replay_with_turns(ops, slots, policy):
    """Reviewed LRU/LRFU replay with added per-decode-operation deltas."""
    ids = np.full(slots, -1, dtype=np.int64)
    slot_for_id = np.full(NL * E, -1, dtype=np.int64)
    last_call = np.zeros(slots, dtype=np.int64)
    last_step = np.full(slots, -1, dtype=np.int64)
    crf = np.zeros(slots, dtype=np.float64)
    positions = np.arange(slots, dtype=np.int64)
    half_life = 384 if policy == "lrfu384" else None
    alpha = np.log(2.0) / half_life if half_life else 0.0
    clock, step, missing, active = 0, -1, 0, 0
    turns = []
    for op, *rest in ops:
        if op == "p":
            old = ids[:PREFILL_SLOTS]
            slot_for_id[old[old >= 0]] = -1
            ids[:PREFILL_SLOTS] = -1
            last_call[:PREFILL_SLOTS] = 0
            last_step[:PREFILL_SLOTS] = -1
            crf[:PREFILL_SLOTS] = 0.0
            continue
        step += 1
        before_missing, before_active = missing, active
        for layer in range(NL):
            clock += 1
            routed = np.unique(rest[0][layer]).astype(np.int64)
            base = layer * E
            resident = slot_for_id[base + routed]
            hit = resident >= 0
            hit_slots = resident[hit]
            if half_life:
                crf[hit_slots] = 1.0 + crf[hit_slots] * np.exp(-alpha * (clock - last_call[hit_slots]))
            last_call[hit_slots] = clock
            last_step[hit_slots] = step
            active += routed.size
            misses = routed[~hit]
            missing += misses.size
            if not misses.size:
                continue
            if policy == "lru":
                key = last_call * 4096 + positions
            elif half_life:
                key = crf * np.exp(-alpha * (clock - last_call))
                key = np.where(ids < 0, -1.0, key)
            else:
                raise ValueError(policy)
            key = key.copy()
            key[hit_slots] = np.inf if half_life else (1 << 60)
            for expert in misses:
                victim = int(key.argmin())
                old_id = ids[victim]
                if old_id >= 0:
                    slot_for_id[old_id] = -1
                ids[victim] = base + expert
                slot_for_id[base + expert] = victim
                last_call[victim] = clock
                last_step[victim] = step
                crf[victim] = 1.0
                key[victim] = np.inf if half_life else (1 << 60)
        turns.append({"turn": step, "missing": missing - before_missing, "active": active - before_active})
    return missing, active, turns


def previous_topk(ops, topk=10):
    prior, hits, total = [None] * NL, 0, 0
    for op, *rest in ops:
        if op != "s":
            prior = [None] * NL
            continue
        for layer in range(NL):
            current = set(np.unique(rest[0][layer]).astype(int).tolist())
            if prior[layer] is not None:
                hits, total = hits + len(current & prior[layer]), total + len(current)
            prior[layer] = set(sorted(current)[:topk])
    return None if total == 0 else hits / total


def fit_markov(ops):
    transitions, prior = [defaultdict(Counter) for _ in range(NL)], [None] * NL
    for op, *rest in ops:
        if op != "s":
            prior = [None] * NL
            continue
        for layer in range(NL):
            current = set(np.unique(rest[0][layer]).astype(int).tolist())
            if prior[layer] is not None:
                for previous in prior[layer]:
                    transitions[layer][previous].update(current)
            prior[layer] = current
    return transitions


def markov_recall(ops, model):
    prior, hits, total = [None] * NL, 0, 0
    for op, *rest in ops:
        if op != "s":
            prior = [None] * NL
            continue
        for layer in range(NL):
            current = set(np.unique(rest[0][layer]).astype(int).tolist())
            if prior[layer] is not None:
                predicted = {counts.most_common(1)[0][0] for previous in prior[layer]
                             if (counts := model[layer].get(previous))}
                hits, total = hits + len(current & predicted), total + len(current)
            prior[layer] = current
    return None if total == 0 else hits / total


def role(group):
    return "training_only" if group == "G_seed12k" else (
        "independent_heldout_diagnostic" if group == "G_seed_real" else "same_origin_or_short_diagnostic")


def aggregate_prefill_rounds(ops, decode_steps):
    """Aggregate decode steps into the original prefill-delimited message rounds."""
    index, round_number, current, rounds = 0, 0, None, []
    for op, *_ in ops:
        if op == "p":
            if current is not None:
                rounds.append(current)
            round_number += 1
            current = {"round": round_number, "decode_steps": 0, "missing": 0, "active": 0}
            continue
        if current is None:
            round_number += 1
            current = {"round": round_number, "decode_steps": 0, "missing": 0, "active": 0}
        step = decode_steps[index]
        index += 1
        current["decode_steps"] += 1
        current["missing"] += step["missing"]
        current["active"] += step["active"]
    if current is not None:
        rounds.append(current)
    return rounds


def write_one_page(report):
    lines = ["# ARC adaptive-cache CPU supplement", "", "This is exploratory CPU evidence only. It is not the unarchived 20:30 formal full grid, does not set a GPU threshold, and is not a formal pass or acceptance decision.", "", "ARC follows Megiddo and Modha, *ARC: A Self-Tuning, Low Overhead Replacement Cache* (USENIX FAST 2003, Figure 4): L1=T1+B1 is bounded by c, all lists by 2c, Case IV A/B handles a new page, and B1/B2 p adjustments retain the paper ratio as a float. [Primary paper](https://www.usenix.org/legacy/event/fast03/tech/full_papers/megiddo/megiddo.pdf).", "", "The replay uses global physical slots, sorted unique routed experts, and physical prefill clearing `[0,1024)`. Two explicit extensions are outside that paper: all already-resident experts in a layer call are refreshed before misses and protected from that call's replacement; bounded ghosts retain identities displaced by the physical prefill clear. The production recipe has no ARC ghost-state contract. Thus the physical clear is exact, while those extensions are implementation limits rather than runtime-equivalence claims.", "", "The Markov predictor fitted only `G_seed12k`; all other trace values are diagnostic. No heldout data selected ARC settings or supports a throughput claim.", "", "|slots|group|LRU miss rate|LRFU H384|ARC|", "|---:|---|---:|---:|---:|"]
    for slots in SLOTS:
        for group in GROUPS:
            table = {r["policy"]: r for r in report["rows"] if r["slots"] == slots and r["group"] == group}
            lines.append("|{}|{}|{:.4%}|{:.4%}|{:.4%}|".format(slots, group, table["lru"]["miss_rate"], table["lrfu_h384"]["miss_rate"], table["arc"]["miss_rate"]))
    lines.extend(["", "LRU exact baseline at 2700: **{}**.".format("passed" if report["lru_baseline_exact"] else "FAILED"), "Per-decode-step and prefill-delimited message-round missing/active deltas are retained in `results_v3.json`."])
    (ROOT / "ONE_PAGE_CONCLUSION_v3.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run():
    started, started_utc = time.monotonic(), datetime.now(timezone.utc).isoformat()
    source, reference = load_reference()
    blobs, inputs = {}, {}
    for group in GROUPS:
        path = BASE / "review_r4" / f"stream_{group}.pkl"
        blobs[group], inputs[group] = pickle.loads(path.read_bytes()), {"path": str(path), "sha256": sha256(path)}
    model, rows = fit_markov(blobs["G_seed12k"]["ops"]), []
    for slots in SLOTS:
        for group, blob in blobs.items():
            print(f"scan slots={slots} group={group}", flush=True)
            policy_runs = {"lru": fixed_replay_with_turns(blob["ops"], slots, "lru"), "lrfu384": fixed_replay_with_turns(blob["ops"], slots, "lrfu384"), "arc": arc_replay(blob["ops"], slots, with_turns=True)}
            for fixed_policy in ("lru", "lrfu384"):
                if policy_runs[fixed_policy][:2] != reference["replay"](blob["ops"], slots, fixed_policy):
                    raise AssertionError(f"fixed clone drift: {slots} {group} {fixed_policy}")
            lru_turns = policy_runs["lru"][2]
            for policy, (missing, active, turns) in policy_runs.items():
                rounds = aggregate_prefill_rounds(blob["ops"], turns)
                lru_rounds = aggregate_prefill_rounds(blob["ops"], lru_turns)
                rows.append({"slots": slots, "group": group, "role": role(group), "policy": "lrfu_h384" if policy == "lrfu384" else policy, "missing": missing, "active": active, "miss_rate": missing / active, "decode_steps": turns, "missing_minus_lru_by_decode_step": [turn["missing"] - lru_turns[i]["missing"] for i, turn in enumerate(turns)], "prefill_delimited_rounds": rounds, "missing_minus_lru_by_round": [round_["missing"] - lru_rounds[i]["missing"] for i, round_ in enumerate(rounds)]})
    actual = {r["group"]: (r["missing"], r["active"]) for r in rows if r["slots"] == 2700 and r["policy"] == "lru"}
    report = {"purpose": "exploratory CPU ARC supplement only; not formal 20:30 grid or acceptance", "started_utc": started_utc, "finished_utc": datetime.now(timezone.utc).isoformat(), "wall_seconds": time.monotonic() - started, "source": {"reference": str(source), "sha256": sha256(source)}, "inputs": inputs, "physical_semantics": "global physical slots; sorted unique route ids; prefill clears physical [0,1024)", "arc_prefill_limit": "physical clear is exact; retained bounded ARC ghosts after it are exploratory and unproven in production", "predictors": {"previous_topk": {g: previous_topk(b["ops"]) for g, b in blobs.items()}, "markov_one_successor": {g: markov_recall(b["ops"], model) for g, b in blobs.items()}, "training": "G_seed12k only; no heldout tuning"}, "lru_baseline_expected_2700": EXPECTED_LRU_2700, "lru_baseline_actual_2700": actual, "lru_baseline_exact": actual == EXPECTED_LRU_2700, "rows": rows}
    (ROOT / "results_v3.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    write_one_page(report)
    print(json.dumps({"lru_baseline_exact": report["lru_baseline_exact"], "rows": len(rows), "wall_seconds": report["wall_seconds"]}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true", help="perform the explicit CPU replay")
    if not parser.parse_args().run:
        print("inert: pass --run for CPU-only replay; no GPU, server, or HTTP operation is performed")
        return
    run()


if __name__ == "__main__":
    main()
