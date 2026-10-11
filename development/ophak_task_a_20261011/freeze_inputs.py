#!/usr/bin/env python3
"""H1 输入冻结（op-hak 任务 A，锚点切段开/关）。

只能在服务器上运行（release-e2 的分词器与渲染函数只在那里）：
  cd /data2/FreeToken/development/ophak_task_a_20261011
  taskset -c 0,2 env OMP_NUM_THREADS=2 RAYON_NUM_THREADS=2 PYTHONDONTWRITEBYTECODE=1 \
      /data2/FreeToken/venv/bin/python -B freeze_inputs.py

做四件事：
1. 核对源文件 SHA256：切段模拟器、预登记、T2 trace。
2. 生成 20 个 payload：seed_real 8 个（原样，只把 max_tokens 改为 32）、T2 12 个（trace 的 messages + tools）。
3. 用 segment_sim.render()（与预登记同一函数）计数，逐轮断言 prompt_tokens 与 ids 的哈希和预登记相等；
   再用 segment_sim.replay() 复现预登记的切段与 cached（prod 与 off 两种策略）。
4. 全部断言通过才写 inputs/ 与 INPUTS.json；任何一项不符，退出码非零，什么都不写。

本脚本只读源文件，不发送任何请求，不占 GPU。
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

WORK = Path(__file__).resolve().parent
OUT = WORK / "inputs"
SIM_PATH = Path("/data2/FreeToken/development/anchor_cut_accounting_20261011/segment_sim.py")
PREREG_PATH = Path("/data2/FreeToken/development/anchor_cut_accounting_20261011/PREREG_TASK_A.json")
TRACE_PATH = Path("/data2/_shared/runs/ft_rounds/E1-R003-v2/trace.json")
SEED_DIR = Path("/data2/_shared/runs/ft_rounds/E2-R046g/G_seed_real")
RELEASE_DIR = Path("/data2/FreeToken/wt/release-e2")
SOURCE_SHA = {
    SIM_PATH: "ac954ce80b1c802c30396ab1330fc6a62d1cd57515ac70f2b8968efe03bc3e7b",
    PREREG_PATH: "0e1708bf033f26ec5f5cde94a1cd3ff86e786c854990033df8246a04006814b9",
    TRACE_PATH: "055ea005aadcbda32625f585a01f10e63d46cd1b87a88be769ec19144d68f899",
}
MODEL = "Qwen3.8-Flash-Next-NVFP4"
MAX_TOKENS = 32
SEED_ROUNDS = 8
T2_ROUNDS = 12
WARMUP_PAYLOAD = {
    "model": MODEL,
    "messages": [{"role": "user", "content": "warmup"}],
    "temperature": 0,
    "max_tokens": 8,
    "stream": True,
    "stream_options": {"include_usage": True},
}


class FreezeError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def messages_sha256(messages: list[dict]) -> str:
    """Canonical hash used by the stub server to map a request back to its round."""
    return sha256_bytes(json.dumps(messages, sort_keys=True, ensure_ascii=False).encode("utf-8"))


def check_sources() -> None:
    for path, expected in SOURCE_SHA.items():
        actual = sha256_bytes(path.read_bytes())
        if actual != expected:
            raise FreezeError(f"源文件 SHA 不符：{path} 实际 {actual}，预期 {expected}")


def load_sim():
    spec = importlib.util.spec_from_file_location("segment_sim", SIM_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def anchors_for(sim, tokenizer) -> frozenset[int]:
    """与 segment_sim.main() 的锚点集合相同（segment_sim 把它写在 main 里，无法直接调用）。"""
    anchors = set()
    for marker in ("</think>", "<|im_end|>"):
        ids = tokenizer.encode(marker, add_special_tokens=False)
        if len(ids) == 1:
            anchors.add(ids[0])
    tool_call = sim.load_toolcall_anchor_id(tokenizer, sim.toolcall_opener_for("qwen3_coder"))
    if tool_call is not None:
        anchors.add(tool_call)
    return frozenset(anchors)


def lcp(a: list[int], b: list[int]) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def release_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "-C", str(RELEASE_DIR), "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def build_payloads(trace: dict) -> dict[str, list[dict]]:
    seed = []
    for i in range(SEED_ROUNDS):
        src = SEED_DIR / f"round-{i:02d}.payload.json"
        payload = json.loads(src.read_bytes())
        payload["max_tokens"] = MAX_TOKENS
        seed.append({"source": str(src), "source_sha256": sha256_bytes(src.read_bytes()), "payload": payload})
    t2 = []
    for k, rnd in enumerate(trace["rounds"][:T2_ROUNDS]):
        payload = {
            "model": MODEL,
            "messages": rnd["messages"],
            "tools": trace["tools"],
            "temperature": 0,
            "max_tokens": MAX_TOKENS,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        t2.append({"source": f"{TRACE_PATH}#rounds[{k}]", "source_sha256": SOURCE_SHA[TRACE_PATH], "payload": payload})
    return {"seed_real": seed, "T2": t2}


def check_against_prereg(sim, tokenizer, manager, anchors, im_start, prereg, payloads) -> tuple[dict, dict]:
    report: dict = {}
    ids_by_traj: dict[str, list[list[int]]] = {}
    for traj, items in payloads.items():
        expected = prereg["trajectories"][traj]
        rows_expected = expected["rounds"]
        ids_list = []
        for k, item in enumerate(items):
            p = item["payload"]
            ids = sim.render(manager, tokenizer, p["messages"], p.get("tools"))
            ids_list.append(ids)
            ids_hash = sha256_bytes(json.dumps(ids).encode())[:16]
            if ids_hash != expected["ids_sha256_16"][k]:
                raise FreezeError(f"{traj} 第 {k} 轮 ids 哈希与预登记不符：{ids_hash}")
            if len(ids) != rows_expected[k]["prompt_tokens"]:
                raise FreezeError(f"{traj} 第 {k} 轮 prompt_tokens={len(ids)}，预登记为 {rows_expected[k]['prompt_tokens']}")
            item["prompt_tokens"] = len(ids)
            item["ids_sha256_16"] = ids_hash
        ids_by_traj[traj] = ids_list

        for policy, key in (("prod", "on_segments"), ("off", "off_segments")):
            rows = sim.replay(ids_list, anchors, im_start, policy)
            for k, row in enumerate(rows):
                if row["segments"] != rows_expected[k][key]:
                    raise FreezeError(f"{traj} 第 {k} 轮 {policy} 切段 {row['segments']} 与预登记 {rows_expected[k][key]} 不符")
                if row["cached"] != rows_expected[k]["cached"]:
                    raise FreezeError(f"{traj} 第 {k} 轮 {policy} cached {row['cached']} 与预登记 {rows_expected[k]['cached']} 不符")
        report[traj] = {"rounds_checked": len(items), "segments_and_cached_match_prereg": True}

    # 跨轨迹复用上界：seed_real 与 T2 第 0 轮共享的最长前缀。预登记假设两条轨迹各自从冷缓存开始。
    seed_ids = ids_by_traj["seed_real"]
    t2_first = ids_by_traj["T2"][0]
    max_shared = max(lcp(s[:-1], t2_first[:-1]) for s in seed_ids)
    report["cross_trajectory"] = {
        "max_shared_prefix_seed_vs_T2_round0": max_shared,
        "note": "若该值 ≥ 64，则 T2 第 0 轮可能复用 seed_real 留下的快照，预登记的 cached=0 需要复核",
    }
    return report, ids_by_traj


def write_outputs(payloads: dict[str, list[dict]], warmup_bytes: bytes, report: dict, sources: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=False)
    rounds = []
    warm_path = OUT / "warmup.json"
    warm_path.write_bytes(warmup_bytes)
    warm_path.chmod(0o444)
    for traj, prefix in (("seed_real", "seed"), ("T2", "t2")):
        for k, item in enumerate(payloads[traj]):
            name = f"{prefix}_round_{k:02d}.json"
            data = (json.dumps(item["payload"], ensure_ascii=False) + "\n").encode("utf-8")
            path = OUT / name
            path.write_bytes(data)
            path.chmod(0o444)
            rounds.append({
                "trajectory": traj,
                "round": k,
                "file": f"inputs/{name}",
                "sha256": sha256_bytes(data),
                "source": item["source"],
                "source_sha256": item["source_sha256"],
                "messages_sha256": messages_sha256(item["payload"]["messages"]),
                "tools_present": "tools" in item["payload"],
                "max_tokens": item["payload"]["max_tokens"],
                "prompt_tokens": item["prompt_tokens"],
                "ids_sha256_16": item["ids_sha256_16"],
            })
    doc = {
        "schema": "ophak_task_a_inputs/v1",
        "created_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
        "release_commit": release_commit(),
        "sources": sources,
        "warmup": {"file": "inputs/warmup.json", "sha256": sha256_bytes(warmup_bytes),
                   "messages_sha256": messages_sha256(WARMUP_PAYLOAD["messages"]), "tools_present": False},
        "rounds": rounds,
        "checks": report,
        "assertions_passed": True,
    }
    (WORK / "INPUTS.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    (WORK / "INPUTS.json").chmod(0o444)


def main() -> int:
    check_sources()
    trace = json.loads(TRACE_PATH.read_bytes())
    if not trace.get("tools"):
        raise FreezeError("trace 没有 tools，预登记里的 T2 渲染规则不成立")
    prereg = json.loads(PREREG_PATH.read_bytes())
    sim = load_sim()
    tokenizer = sim.load_tokenizer(sim.MODEL)
    manager = sim.TokenizeManager(tokenizer)
    im_start = tokenizer.convert_tokens_to_ids("<|im_start|>")
    anchors = anchors_for(sim, tokenizer)

    payloads = build_payloads(trace)
    report, _ = check_against_prereg(sim, tokenizer, manager, anchors, im_start, prereg, payloads)
    warmup_bytes = (json.dumps(WARMUP_PAYLOAD, ensure_ascii=False) + "\n").encode("utf-8")
    sources = {str(p): sha for p, sha in SOURCE_SHA.items()}
    write_outputs(payloads, warmup_bytes, report, sources)
    print(json.dumps({"ok": True, "report": report}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FreezeError as exc:
        print(f"FREEZE FAILED: {exc}", file=sys.stderr)
        raise SystemExit(2)
