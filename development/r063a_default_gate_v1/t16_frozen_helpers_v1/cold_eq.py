"""E1 轮次用冷测探针：流式取 TTFT/解码，同时保存输出全文，供 temp0 前 N token 一致性判定。

用法: cold_eq.py <cold_id> <out.json> [target=32052] [max_tokens=128]
口径与 probe_ft_cold32k.py 完全一致（唯一 Cold-prefix 头、关思考、temperature 0、
首条正文 content 事件为 TTFT、解码 = (n-1)/(t_last - t_first)），差别只是额外存全文。
"""
import json
import sys
import time
import urllib.request

sys.path.insert(0, "/data2/FreeToken/scripts")
from probe_ft_cold32k import build_text, MODEL, MODEL_DIR, URL  # noqa: E402

from transformers import AutoTokenizer  # noqa: E402


def main():
    cold_id = sys.argv[1]
    out = sys.argv[2]
    target = int(sys.argv[3]) if len(sys.argv) > 3 else 32052
    max_tokens = int(sys.argv[4]) if len(sys.argv) > 4 else 128

    tok = AutoTokenizer.from_pretrained(MODEL_DIR, trust_remote_code=True)
    text, built = build_text(tok, target, cold_id)

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": text}],
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": True,
        "stream_options": {"include_usage": True},
        "chat_template_kwargs": {"enable_thinking": False},
    }
    req = urllib.request.Request(
        URL, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )

    t0 = time.perf_counter()
    t_first = t_last = None
    parts = []
    usage = {}
    finish = None
    with urllib.request.urlopen(req, timeout=1800) as r:
        for raw in r:
            line = raw.decode("utf-8", "ignore").strip()
            if not line.startswith("data:"):
                continue
            body = line[5:].strip()
            if body == "[DONE]":
                break
            evt = json.loads(body)
            u = evt.get("usage")
            if u:
                usage = u
            for ch in evt.get("choices") or []:
                if ch.get("finish_reason"):
                    finish = ch["finish_reason"]
                piece = (ch.get("delta") or {}).get("content")
                if piece:
                    now = time.perf_counter()
                    if t_first is None:
                        t_first = now
                    t_last = now
                    parts.append(piece)

    content = "".join(parts)
    n = len(parts)
    rec = {
        "cold_id": cold_id,
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "cached_tokens": int((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or n),
        "ttft_s": round(t_first - t0, 3) if t_first else None,
        "decode_tps": round((n - 1) / (t_last - t_first), 2) if n > 1 and t_last > t_first else None,
        "finish_reason": finish,
        "built_tokens": built,
        "content_chars": len(content),
    }
    json.dump({"record": rec, "text": content, "events": n},
              open(out, "w"), ensure_ascii=False)
    print(json.dumps(rec, ensure_ascii=False))


if __name__ == "__main__":
    main()
