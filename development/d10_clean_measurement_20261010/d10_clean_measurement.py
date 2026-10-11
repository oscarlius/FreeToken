"""Default-deny preparation for the one-service D10 clean measurement."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RID = "E2-D10-CLEAN-MEASURE-20261010"
CANDIDATE = "a51009eb4fc5ab5864648abe9484ba645a8f88b5"
WORKTREE = "/data2/FreeToken/wt/d10-step-metrics-20261010-v7"
MAX_WALL_SECONDS, CLEANUP_RESERVE_SECONDS = 1500, 150


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def payloads() -> list[dict]:
    return [
        {"model": "Qwen3.8-Flash-Next-NVFP4", "messages": [{"role": "user", "content": text}], "max_tokens": 512, "temperature": 0, "top_p": 1, "stream": True, "ignore_eos": True}
        for text in ("State A B C D in order.", "State 1 2 3 4 in order.")
    ]


def filedry() -> dict:
    """Materialize the exact route/payload plan without Popen, HTTP, GPU or lock."""
    return {
        "schema": "ft_d10_clean_measurement_filedry/v1", "rid": RID, "candidate": CANDIDATE,
        "service": {"count": 1, "argv": ["ft", "serve", "--d10-staggered-decode", "--max-running-requests", "2"], "route": "/v1/chat/completions"},
        "requests": payloads(), "barrier": {"parties": 2, "release_before_send": True},
        "warmup": {"paired_d10_steps": 16, "same_two_uids_continuous_trace": True, "restart_on": ["singleton", "ordinary", "counter_missing", "uid_change", "disconnect"]},
        "retained_trace": ["step_uid", "uids", "monotonic_start_ns", "monotonic_end_ns", "cpu_dispatch_ns", "gpu_completion_ms", "lanes.lookup_hit_miss_h2d"],
        "analysis": {"minimum_actual_tokens_per_lane": 256, "tokens_are_post_warmup": True, "denominator": "shared_decode_overlap_only", "retained_steps": "same UID pair only after warmup", "go": "both lanes TPS > 30 and later separate T16 pass"},
        "budget": {"services_max": 1, "wall_seconds_max": MAX_WALL_SECONDS, "cleanup_reserve_seconds": CLEANUP_RESERVE_SECONDS},
        "side_effects": {"popen": False, "http": False, "gpu": False, "gpu_lock": False},
    }


class Effects:
    """The real process boundary: construction/materialization never starts a child."""
    def __init__(self, worktree: Path, run_dir: Path):
        self.worktree, self.run_dir = Path(worktree), Path(run_dir)
        model = self.worktree / "python/freetoken/server/api_models.py"
        if not model.is_file() or self.worktree.name != "d10-step-metrics-20261010-v7":
            raise RuntimeError("a510 worktree/api model binding required")
        self.api_model_sha256 = sha(model)
    def materialize(self) -> dict:
        self.run_dir.mkdir(parents=True, exist_ok=False)
        plan = filedry(); (self.run_dir / "plan.json").write_text(json.dumps(plan, sort_keys=True))
        return plan
    def start(self, admission: Path):
        require_admission(admission)
        argv = ["ft", "serve", "--d10-staggered-decode", "--max-running-requests", "2"]
        return subprocess.Popen(argv, cwd=self.worktree, env={**os.environ, "FT_D10_STEP_METRICS":"1"}, start_new_session=True)
    def cleanup(self, process, deadline: float) -> None:
        process.terminate()
        try: process.wait(max(0, deadline-time.monotonic()))
        except subprocess.TimeoutExpired: process.kill(); process.wait(max(0, deadline-time.monotonic()))


def extract_shared_window(steps: list[dict], token_events: dict[int, list[dict]]) -> dict:
    """Reject anything except one continuous UID pair with 16 paired warm steps."""
    if len(steps) <= 16: raise RuntimeError("failed_harness: insufficient paired steps")
    pair = tuple(steps[0].get("uids", ()))
    if len(pair) != 2 or pair[0] == pair[1]: raise RuntimeError("failed_harness: UID pair")
    for row in steps:
        if tuple(row.get("uids", ())) != pair or not row.get("d10") or row["monotonic_end_ns"] <= row["monotonic_start_ns"]: raise RuntimeError("failed_harness: noncontinuous pair trace")
        if len(row.get("lanes", [])) != 2: raise RuntimeError("failed_harness: missing lane counters")
    kept=steps[16:]; start=max(kept[0]["monotonic_start_ns"], *(x["t_ns"] for x in (token_events[pair[0]][0],token_events[pair[1]][0])))
    end=min(token_events[pair[0]][-1]["t_ns"], token_events[pair[1]][-1]["t_ns"])
    if end <= start: raise RuntimeError("failed_harness: empty shared overlap")
    out={"uids":pair,"warmup_steps":16,"shared_start_ns":start,"shared_end_ns":end,"duration_s":(end-start)/1e9,"steps":kept}
    for uid in pair:
        count=sum(1 for e in token_events[uid] if start <= e["t_ns"] <= end)
        if count < 256: raise RuntimeError("failed_harness: fewer than256 postwarm tokens")
        out.setdefault("lane_tps",{})[uid]=count/out["duration_s"]
    return out


def require_admission(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222:
        raise RuntimeError("sealed root admission required")
    value = json.loads(path.read_text())
    if value.get("rid") != RID or value.get("admit") is not True or value.get("candidate") != CANDIDATE:
        raise RuntimeError("admission identity differs")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--filedry", action="store_true"); parser.add_argument("--run", type=Path)
    args = parser.parse_args()
    if args.filedry and args.run: parser.error("--filedry cannot mix --run")
    if args.filedry: print(json.dumps(filedry(), sort_keys=True)); return
    if args.run: require_admission(args.run); raise RuntimeError("root-owned GPU execution is intentionally not available in CPU preparation")
    parser.error("choose --filedry or --run")


if __name__ == "__main__": main()
