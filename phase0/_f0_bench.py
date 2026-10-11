import hashlib, json, time, urllib.request
from tokenizers import Tokenizer

OUT = "/home/dell/moe-bench-20260929-054443"
LOG = OUT + "/logs/F0-bench.log"
JSONL = OUT + "/results/F0-bench.jsonl"
URL = "http://127.0.0.1:1919/v1/chat/completions"
enc = Tokenizer.from_file("/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4/tokenizer.json")
UNIT = "测试材料保持固定。这段文字只用于对齐输入长度，不包含新的任务信息。"


def log(msg):
    line = time.strftime("%H:%M:%S") + " " + msg
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def ntok(s):
    return len(enc.encode(s).ids)


def make_text(target):
    unit_n = max(ntok(UNIT), 1)
    text = UNIT * (target // unit_n + 2)
    lo, hi = 0, len(text)
    best = text[:1]
    while lo <= hi:
        mid = (lo + hi) // 2
        piece = text[: max(mid, 1)]
        n = ntok(piece)
        if n <= target:
            best = piece
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def post(content, max_tokens, tag):
    payload = {
        "model": "Qwen3.8-Flash-Next-NVFP4",
        "messages": [{"role": "user", "content": content + "\n请用三句话总结上文要点。"}],
        "max_tokens": max_tokens,
        "temperature": 0,
        "top_p": 1,
        "top_k": 1,
        "reasoning_effort": "off",
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    req = urllib.request.Request(
        URL, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    t0 = time.time()
    t_first = None
    usage = None
    finish = None
    chars = 0
    reason_chars = 0
    err = None
    try:
        resp = urllib.request.urlopen(req, timeout=900)
        for line in resp:
            s = line.decode().strip()
            if not s.startswith("data:"):
                continue
            if "[DONE]" in s:
                break
            try:
                ev = json.loads(s[5:])
            except Exception:
                continue
            if ev.get("usage"):
                usage = ev["usage"]
            ch = (ev.get("choices") or [{}])[0]
            finish = ch.get("finish_reason") or finish
            delta = ch.get("delta") or {}
            c = delta.get("content") or ""
            r = delta.get("reasoning_content") or ""
            if c:
                if t_first is None:
                    t_first = time.time()
                chars += len(c)
            reason_chars += len(r)
    except Exception as e:
        err = repr(e)[:300]
    tend = time.time()
    comp = (usage or {}).get("completion_tokens")
    prompt = (usage or {}).get("prompt_tokens")
    span = (tend - t_first) if t_first and comp and comp > 1 else None
    rec = {
        "tag": tag,
        "total_s": round(tend - t0, 2),
        "ttft_s": round(t_first - t0, 2) if t_first else None,
        "prompt_tokens": prompt,
        "completion_tokens": comp,
        "finish_reason": finish,
        "content_chars": chars,
        "reason_chars": reason_chars,
        "decode_tps": round((comp - 1) / span, 2) if span and comp and comp > 1 else None,
        "err": err,
    }
    with open(JSONL, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    log("%s %s" % (tag, json.dumps(rec, ensure_ascii=False)))
    return rec


def calibrate(name, target):
    text = make_text(target)
    wrapped = text + "\n请用三句话总结上文要点。"
    path = OUT + "/outputs/F0-%s-prompt.txt" % name
    open(path, "w").write(wrapped)
    digest = hashlib.sha256(wrapped.encode()).hexdigest()
    rec = post(text, 1, "calibrate-" + name)
    log("%s local_tokens=%s server_prompt=%s sha=%s" % (name, ntok(wrapped), rec.get("prompt_tokens"), digest))
    got = rec.get("prompt_tokens") or ntok(wrapped)
    if abs(got - target) > max(32, target // 20):
        text = make_text(max(8, int(ntok(text) * target / max(got, 1))))
        wrapped = text + "\n请用三句话总结上文要点。"
        open(path, "w").write(wrapped)
        digest = hashlib.sha256(wrapped.encode()).hexdigest()
        rec = post(text, 1, "calibrate2-" + name)
        log("%s adjusted server_prompt=%s sha=%s" % (name, rec.get("prompt_tokens"), digest))
    return text


log("F0 bench start")
s_text = calibrate("S", 512)
l_text = calibrate("L", 8192)
post(s_text, 512, "warmup-S")
post(l_text, 512, "warmup-L")
for i in (1, 2, 3):
    post(s_text, 512, "S-r%s" % i)
    post(l_text, 512, "L-r%s" % i)
log("F0 bench done")
