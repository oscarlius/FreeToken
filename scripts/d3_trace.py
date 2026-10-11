"""D3 验收：多轮轨迹回放。R2_cold（全重算）→ R1（预热+锚捐赠）→ R2_warm（编辑后恢复）。"""
import json, sys, time, urllib.request
URL = "http://127.0.0.1:8095/v1/chat/completions"
MODEL = "Qwen3.8-Flash-Next-NVFP4"
mat = lambda i: f"第{i}部分验收记录。" + ("系统在某轮评测中完成端到端编码代理任务，工具调用可解析，修改落到指定文件与指定位置，隐藏测试全部通过，收尾由模型自行声明。" * 60)

def msgs_of(final):
    m = []
    for i in range(1, 8):
        m.append({"role": "user", "content": mat(i) if not (final and i == 5) else "第5部分验收记录。（内容已被截断重写）补充说明若干。"})
        m.append({"role": "assistant", "content": f"第{i}部分已分析完毕。"})
    m.append({"role": "user", "content": "基于以上全部材料，用一句话总结系统现状。" if not final else "重写后的最终问题：一句话总结系统现状。"})
    return m

def run(msgs, tag):
    body = json.dumps({"model": MODEL, "messages": msgs, "max_tokens": 32, "temperature": 0,
        "stream": True, "stream_options": {"include_usage": True},
        "chat_template_kwargs": {"enable_thinking": False}}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    first = None
    usage = None
    resp = urllib.request.urlopen(req, timeout=1800)
    for line in resp:
        line = line.decode("utf-8", errors="replace").strip()
        if not line.startswith("data:") or line[5:].strip() == "[DONE]":
            continue
        try:
            evt = json.loads(line[5:])
        except Exception:
            continue
        if evt.get("usage"):
            usage = evt["usage"]
        ch = evt.get("choices") or []
        if ch and ch[0].get("delta", {}).get("content") and first is None:
            first = time.perf_counter() - t0
    u = usage or {}
    return {"tag": tag, "ttft_s": round(first, 3) if first else None,
        "prompt_tokens": u.get("prompt_tokens"),
        "cached": (u.get("prompt_tokens_details") or {}).get("cached_tokens")}

out = []
out.append(run(msgs_of(final=True), "R2_cold"))
out.append(run(msgs_of(final=False), "R1_warm"))
out.append(run(msgs_of(final=True), "R2_warm_anchors"))
json.dump(out, open("/data2/FreeToken/runs/dev_d3/d3_trace.json", "w"), indent=1)
print(json.dumps(out, indent=1))
