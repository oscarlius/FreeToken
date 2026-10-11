"""比较 offload 与 hybrid 在相同 X 输入（temperature=0）下的生成文本（主会话，只读）。

从 AIPerf profile_export_raw.jsonl 的 SSE 包重建 reasoning_content + content，按 prompt_tokens 对齐请求，
报告首个分歧字符位置（None 表示逐字相同）。
"""
import json
import sys

RUNS = {
    "offload_two_2258_warm": "d10_reanalysis_20261010/closed_loop_20261010/raw_speed_2258/speed/X/profile_export_raw.jsonl",
    "offload_two_2308_fresh_d0": "d10_reanalysis_20261010/closed_loop_20261010/raw_d0_2308/metrics/d0/X/profile_export_raw.jsonl",
    "offload_single_0041_warm": "d08_d10_gpu_window_retry1_20261011/evidence/window02/offload_single/profile_export_raw.jsonl",
    "offload_single_fresh_d0": "d08_d10_gpu_retry2_20261011/evidence/window01/d0_single/profile_export_raw.jsonl",
    "hybrid_single": "d08_d10_gpu_retry2_20261011/evidence/window01/hybrid_single/profile_export_raw.jsonl",
    "hybrid_two": "d08_d10_gpu_retry2_20261011/evidence/window01/hybrid_two/profile_export_raw.jsonl",
}


def outputs(path):
    res = {}
    for line in open(path, encoding="utf-8"):
        rec = json.loads(line)
        text, prompt = "", None
        for chunk in rec["responses"]:
            for packet in chunk.get("packets", []):
                value = packet.get("value", "")
                if not value.startswith("{"):
                    continue
                data = json.loads(value)
                if data.get("usage"):
                    prompt = data["usage"]["prompt_tokens"]
                for choice in data.get("choices", []):
                    delta = choice.get("delta", {})
                    text += (delta.get("reasoning_content") or "") + (delta.get("content") or "")
        res[prompt] = text
    return res


def first_diff(a, b):
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            return i
    return None if len(a) == len(b) else min(len(a), len(b))


def main():
    o = {k: outputs(v) for k, v in RUNS.items()}
    pairs = [("offload_two_2258_warm", "offload_two_2308_fresh_d0"),
             ("offload_single_0041_warm", "offload_single_fresh_d0"),
             ("offload_single_fresh_d0", "hybrid_single"),
             ("offload_two_2258_warm", "hybrid_two"),
             ("offload_single_fresh_d0", "offload_two_2258_warm")]
    for a, b in pairs:
        for p in sorted(set(o[a]) & set(o[b])):
            print(f"{a} vs {b} prompt={p}: first_diff_char={first_diff(o[a][p], o[b][p])} len={len(o[a][p])}/{len(o[b][p])}")


if __name__ == "__main__":
    sys.exit(main())
