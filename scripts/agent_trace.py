#!/usr/bin/env python3
"""真实 Agent 轨迹生成/回放工装（D3 与 E1-R003 验收用）。

为什么要有它
------------
`d3_trace.py` 只有 3 轮、纯文本、无工具调用，达不到 `DEV_NEXT_D3_20261003.md` 验收 2
与 E1-R003 要求的「不少于 10 轮、含工具调用和思考段的真实轨迹」。本脚本让模型自己发
`tool_calls`，工装在实验机上真执行**只读**动作再喂回去，跑满 N 轮，轨迹里因此天然有
工具结果消息（锚点之后的内容可被中途编辑）与 reasoning 段。

三个子命令
----------
1. `generate`  现场跑一条真实轨迹存成 JSON（每轮存"发出去的那份 messages 快照"）。
2. `replay`    读回轨迹，逐轮只发前缀（`messages` 快照原样，字节序不变，否则前缀不命中），
               temp 0 / max_tokens 32，量 `ttft_any_s` / `ttft_content_s` /
               `prompt_tokens` / `cached_tokens` / `recomputed_tokens`，并把流式增量
               逐片存下来（一片≈一个 token，所以前 32 片就是前 32 token）。
3. `compare`   拿两份 `replay` 产物（命中路径 vs 全量重算路径，或 D3 树 vs 控制树）做
               前 N token 一致性判定，并一次性给出全部验收门的 PASS / NOT MET。

口径（与 `probe_ft_cold32k.py` / `cold_eq.py` 对齐，别混用）
----------------------------------------------------------
- 首 token 一律用流式：`ttft_any_s` = 第一个非空增量（reasoning / 正文 / 工具参数都算），
  `ttft_content_s` = 第一个非空正文增量，`ttft_s`（generate 记录）= 第一个正文或工具参数增量。
- `cached_tokens` 取 `usage.prompt_tokens_details.cached_tokens`；服务端没开
  `--enable-cache-report` 时取不到，记 0（此时命中类判据不成立，`compare` 会标 NOT MET）。
- 「锚命中」在客户端唯一可见的证据就是 `cached_tokens` / `recomputed_tokens`；槽号、64 边界、
  捐赠与否只有服务端 `FT_D3_TRACE` 日志里才有，本工装不读远端日志，判定要和那份日志对着看。
- `recomputed_tokens = prompt_tokens - cached_tokens`。
- `thinking` 必须与 generate 时一致：generate 默认开思考（请求里**不带**
  `chat_template_kwargs.enable_thinking=false`），回放若改了这个开关，聊天模板就变了、
  前缀必然不命中。`replay --thinking auto`（默认）直接从轨迹 meta 里读。

「全量重算」怎么取
----------------
工装是纯客户端，服务端没有暴露清缓存接口（`/v1/cache/rebuild` 是改池大小，不是 flush）。
所以全量重算路径 = **冷进程**里跑一遍 `replay`（用 `--fresh-note` 写明），命中路径 =
**热进程**里按升序跑一遍 `replay`，两份 JSON 交给 `compare` 比前 32 token。
注意同一进程内升序回放时，第 k 轮的前缀已被前一轮写进缓存，因此同一轮 `replay`
里只有第一个请求是真正的全量重算 —— 这也是必须分两次跑、并且必须写 `--fresh-note` 的原因。

安全（硬要求）
--------------
- 三个工具全部只读：`read_file` / `list_dir` / `search_code`，没有写、没有删、没有执行。
- 路径先用 `os.path.realpath` 规范化，再判断是否仍落在 `--root` 内；越界返回错误**文本**
  给模型，不抛异常、不中断轨迹。
- `search_code` 走 `subprocess.run(argv 列表, shell=False)`，pattern/glob 作为独立 argv 传入，
  绝不拼进 shell（无 `os.system`、无 `shell=True`、不接受任意命令），并带超时与输出截断。

用法
----
    python3 scripts/agent_trace.py generate --out /data2/FreeToken/runs/dev_d3/trace.json \
        --rounds 12
    python3 scripts/agent_trace.py replay --trace .../trace.json --out .../replay_cold.json \
        --edit-at-idx 7 --fresh-note "冷进程：serve 刚起，未发过任何请求"
    python3 scripts/agent_trace.py replay --trace .../trace.json --out .../replay_hot.json \
        --edit-at-idx 7 --fresh-note "热进程：已按升序预热过 0..11 轮"
    python3 scripts/agent_trace.py compare --a .../replay_hot.json --b .../replay_cold.json \
        --trace .../trace.json --out .../verdict.json
    # 不开 GPU 也能校验构造：三条子命令都支持 --dry-run（不联网，用确定性桩响应）

依赖：Python 3.10 标准库即可（`urllib`，不需要 `requests`）。
"""
import argparse
import copy
import hashlib
import io as _io
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

VERSION = "1.0.0"

BASE_URL_DEFAULT = "http://127.0.0.1:8095/v1"
MODEL_DEFAULT = "Qwen3.8-Flash-Next-NVFP4"
ROOT_DEFAULT = "/data2/FreeToken/src/FreeToken"

MAX_ROUNDS_DEFAULT = 12
GENERATE_MAX_TOKENS_DEFAULT = 128
# 32 片会被思考段吃满，正文口径取不到读数；回放预算要能越过思考段才可比较正文前缀。
REPLAY_MAX_TOKENS = int(os.environ.get("FT_REPLAY_MAX_TOKENS", "32"))
TOKEN_PREFIX_GATE = 32
TTFT_GATE_S = 4.0
MIN_TRACE_ROUNDS = 10
TOOL_OUTPUT_CAP = 20000
HTTP_TIMEOUT_S = 1800
GREP_TIMEOUT_S = 60

TASK_PROMPT = (
    "这份仓库里层优先长预填（prefill layer-major / 分块预填）是怎么实现的？"
    "先用 list_dir 列出 scheduler 和 engine 相关文件，再用 search_code 定位关键函数，"
    "然后用 read_file 读出关键函数，逐步给我证据（文件名+行号+你读到的代码要点）。"
    "每轮最多调用一个工具，不要一次性铺开。"
)
FOLLOW_UPS = [
    "继续。上面结论还缺证据：换一个角度再用一次工具（list_dir / search_code / read_file 任选），"
    "读完再给下一步推断。",
    "还要核实一处：把刚才提到的函数里的关键分支再读一遍（用 read_file 或 search_code），"
    "指出它在层优先路径下会不会走到。",
    "最后交叉验证：列一下这个函数被谁调用（search_code 找调用点），然后总结成三句话。",
]
DEFAULT_EDIT_TEXT = (
    "【工装注入】本条工具结果已在锚点之后被改写，用于验证多锚检查点的中途编辑恢复："
    "原始输出已作废。改写后的命中记录：scheduler.py 与 engine.py 中层优先分块、"
    "快照槽与锚点封顶的相关行被逐行重排并补了注释，行号与真实文件不再对应。"
) * 24

DRY_STEPS = ("list_dir", "search_code", "read_file", "final")


# --------------------------------------------------------------------------- #
# 流式请求与增量累积
# --------------------------------------------------------------------------- #
def chat_url(base_url):
    base = base_url.rstrip("/")
    return base if base.endswith("/chat/completions") else base + "/chat/completions"


def post_events(url, payload, timeout):
    """POST 一次流式请求，逐条 yield 解析后的 SSE 事件 dict。"""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line or not line.startswith("data:"):
                continue
            chunk = line[5:].strip()
            if chunk == "[DONE]":
                return
            try:
                yield json.loads(chunk)
            except ValueError:
                continue


def consume_stream(events, t0):
    """累积事件流：文本分片、tool_calls 重建、usage、三个首 token 时刻。"""
    reasoning, content, parts = [], [], []
    calls = {}
    usage, finish = {}, None
    t_any = t_content = t_main = None

    for evt in events:
        now = time.perf_counter()
        if evt.get("usage"):
            usage = evt["usage"]
        for ch in evt.get("choices") or []:
            if ch.get("finish_reason"):
                finish = ch["finish_reason"]
            delta = ch.get("delta") or {}
            piece = delta.get("reasoning_content") or delta.get("reasoning")
            if piece:
                if t_any is None:
                    t_any = now
                reasoning.append(piece)
                parts.append(piece)
            piece = delta.get("content")
            if piece:
                if t_any is None:
                    t_any = now
                if t_content is None:
                    t_content = now
                if t_main is None:
                    t_main = now
                content.append(piece)
                parts.append(piece)
            for item in delta.get("tool_calls") or []:
                idx = item.get("index") or 0
                slot = calls.setdefault(idx, {"id": None, "name": "", "args": ""})
                if item.get("id"):
                    slot["id"] = item["id"]
                fn = item.get("function") or {}
                if fn.get("name") and not slot["name"]:
                    slot["name"] = fn["name"]
                frag = fn.get("arguments")
                if frag:
                    if t_any is None:
                        t_any = now
                    if t_main is None:
                        t_main = now
                    slot["args"] += frag
                    parts.append(frag)

    tool_calls = [
        {
            "id": slot["id"] or "call_no_id_%d" % idx,
            "type": "function",
            "function": {"name": slot["name"], "arguments": slot["args"]},
        }
        for _, slot in sorted(calls.items())
        if slot["name"]
    ]
    secs = lambda t: round(t - t0, 3) if t is not None else None  # noqa: E731
    return {
        "reasoning_text": "".join(reasoning),
        "content_text": "".join(content),
        "content_parts": content,
        "tool_calls": tool_calls,
        "parts": parts,
        "usage": usage or {},
        "finish_reason": finish,
        "ttft_any_s": secs(t_any),
        "ttft_content_s": secs(t_content),
        "ttft_s": secs(t_main),
    }


def messages_digest(msgs):
    """请求 messages 的规范化摘要：证明回放发的字节序与生成时一致（前缀命中的前提）。

    sort_keys=True 只规范键顺序（键顺序不影响分词），列表顺序与内容任何变动都会变摘要。
    """
    return hashlib.sha256(
        json.dumps(msgs, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]


def usage_counts(usage):
    prompt = int(usage.get("prompt_tokens") or 0)
    cached = int((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    return prompt, cached, completion


def build_payload(messages, model, tools, thinking, max_tokens, temperature=0):
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if tools:
        payload["tools"] = tools
    if not thinking:
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    return payload


# --------------------------------------------------------------------------- #
# 只读工具：schema + 执行（路径限制在 root 内，命令走 argv 列表）
# --------------------------------------------------------------------------- #
def tool_specs():
    return [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "读取工作根目录下的文本文件（只读）。越界路径会被拒绝。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "相对工作根或绝对路径"},
                        "max_bytes": {
                            "type": "integer",
                            "description": "最多读取字节数，默认 %d，硬上限 %d"
                            % (TOOL_OUTPUT_CAP, TOOL_OUTPUT_CAP),
                        },
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_dir",
                "description": "列出工作根目录下某个目录的条目（只读），标注目录/文件与大小。",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string", "description": "目录路径，可传 ."}},
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_code",
                "description": "在工作根内用 grep -rn --include 搜代码（只读），结果截断到 %d 字节。"
                % TOOL_OUTPUT_CAP,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "固定字符串模式（不是 shell 命令）"},
                        "path": {"type": "string", "description": "搜索起点目录或文件，默认工作根"},
                        "glob": {"type": "string", "description": "文件名过滤，例如 *.py"},
                    },
                    "required": ["pattern"],
                },
            },
        },
    ]


def _cap(text, cap=TOOL_OUTPUT_CAP):
    data = text.encode("utf-8")
    if len(data) <= cap:
        return text
    clipped = data[:cap].decode("utf-8", errors="replace")
    return clipped + "\n...[截断：共 %d 字节]" % len(data)


def resolve_in_root(root, path, need_exist=True):
    """返回 (真实路径, 错误文本)。越界 / 不存在都只回错误文本，不抛异常。"""
    if not isinstance(path, str) or not path.strip():
        return None, "ERROR: path 必须是非空字符串"
    real_root = os.path.realpath(root)
    cand = path if os.path.isabs(path) else os.path.join(real_root, path)
    real = os.path.realpath(cand)
    if real != real_root and not real.startswith(real_root + os.sep):
        return None, "ERROR: 路径 %s 越出工作根 %s，拒绝访问" % (path, real_root)
    if need_exist and not os.path.exists(real):
        return None, "ERROR: 路径不存在 %s" % real
    return real, None


def tool_read_file(root, args):
    path = args.get("path")
    real, err = resolve_in_root(root, path)
    if err:
        return err
    if not os.path.isfile(real):
        return "ERROR: %s 不是普通文件" % real
    cap = TOOL_OUTPUT_CAP
    try:
        req = int(args.get("max_bytes") or cap)
        if 0 < req < cap:
            cap = req
    except (TypeError, ValueError):
        pass
    try:
        with open(real, "rb") as fh:
            data = fh.read(cap + 1)
    except OSError as exc:
        return "ERROR: 读取失败 %s" % exc
    truncated = len(data) > cap
    text = data[:cap].decode("utf-8", errors="replace")
    head = "# read_file %s (%d 字节%s)\n" % (
        os.path.relpath(real, os.path.realpath(root)),
        len(data[:cap]),
        "，已截断" if truncated else "",
    )
    return _cap(head + text)


def tool_list_dir(root, args):
    path = args.get("path") or "."
    real, err = resolve_in_root(root, path)
    if err:
        return err
    if not os.path.isdir(real):
        return "ERROR: %s 不是目录" % real
    try:
        names = sorted(os.listdir(real))
    except OSError as exc:
        return "ERROR: 列目录失败 %s" % exc
    lines = ["# list_dir %s（%d 条目）" % (os.path.relpath(real, os.path.realpath(root)), len(names))]
    for name in names[:500]:
        full = os.path.join(real, name)
        if os.path.isdir(full):
            lines.append("%s/  (dir)" % name)
        else:
            try:
                size = os.path.getsize(full)
            except OSError:
                size = -1
            lines.append("%s  %d B" % (name, size))
    if len(names) > 500:
        lines.append("...[条目过多，仅前 500]")
    return _cap("\n".join(lines))


def tool_search_code(root, args):
    pattern = args.get("pattern")
    if not isinstance(pattern, str) or not pattern:
        return "ERROR: pattern 必须是非空字符串"
    grep = shutil.which("grep")
    if not grep:
        return "ERROR: 本机没有 grep，search_code 不可用"
    target, err = resolve_in_root(root, args.get("path") or ".")
    if err:
        return err
    argv = [grep, "-rn"]
    glob = args.get("glob")
    if isinstance(glob, str) and glob.strip():
        argv.append("--include=%s" % glob.strip())
    argv += ["-e", pattern, target]
    try:
        # shell=False + argv 列表：pattern/glob 永远进不了 shell。
        proc = subprocess.run(
            argv,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=GREP_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return "ERROR: search_code 超时（>%d s），换个更窄的 pattern/glob" % GREP_TIMEOUT_S
    except OSError as exc:
        return "ERROR: search_code 起进程失败 %s" % exc
    if proc.returncode not in (0, 1):
        return "ERROR: grep 返回 %d %s" % (
            proc.returncode,
            proc.stderr.decode("utf-8", errors="replace")[:500],
        )
    if proc.returncode == 1:
        return "（无匹配）pattern=%r path=%s" % (pattern, os.path.relpath(target, os.path.realpath(root)))
    real_root = os.path.realpath(root)
    out = proc.stdout.decode("utf-8", errors="replace").replace(real_root + os.sep, "")
    return _cap("# search_code %r\n" % pattern + out)


TOOL_IMPLS = {"read_file": tool_read_file, "list_dir": tool_list_dir, "search_code": tool_search_code}


def exec_tool_call(root, call):
    fn = (call.get("function") or {})
    name = fn.get("name")
    if name not in TOOL_IMPLS:
        return "ERROR: 未知工具 %s（只有 read_file/list_dir/search_code）" % name
    raw = fn.get("arguments")
    if isinstance(raw, dict):
        args = raw
    else:
        try:
            args = json.loads(raw) if raw else {}
        except ValueError:
            return "ERROR: 工具参数不是合法 JSON：%r" % (str(raw)[:200],)
        if not isinstance(args, dict):
            return "ERROR: 工具参数必须是 JSON 对象"
    try:
        return TOOL_IMPLS[name](root, args)
    except Exception as exc:  # 工装绝不因模型给的脏参数而中断轨迹
        return "ERROR: 工具执行异常 %s: %s" % (type(exc).__name__, exc)


def assistant_message(res):
    msg = {"role": "assistant", "content": res["content_text"]}
    if res["tool_calls"]:
        msg["tool_calls"] = res["tool_calls"]
    return msg


def apply_edit(messages, idx, text):
    """在 messages[idx] 处替换内容（通常是 role==tool 的工具结果，即锚点之后）。"""
    if idx is None:
        return False, None
    if idx < 0 or idx >= len(messages):
        return False, "下标 %d 不在本轮 0..%d 范围内，本轮保持原样" % (idx, len(messages) - 1)
    target = messages[idx]
    role = target.get("role")
    original_len = len(str(target.get("content") or ""))
    if isinstance(target.get("content"), str) or target.get("content") is None:
        target["content"] = text
    elif role == "assistant" and target.get("tool_calls"):
        # 少数模型会把结果塞在 assistant.tool_calls 里，改参数文本等效。
        target["tool_calls"][0]["function"]["arguments"] = json.dumps(
            {"path": ".", "content": text}, ensure_ascii=False
        )
    else:
        return False, "下标 %d 处内容不是字符串，跳过编辑" % idx
    return True, "在 idx=%d role=%s 处把 %d 字符替换为 %d 字符" % (
        idx,
        role,
        original_len,
        len(text),
    )


# --------------------------------------------------------------------------- #
# 桩响应（--dry-run）：不联网，确定性，够把构造跑通
# --------------------------------------------------------------------------- #
def dry_generate_events(step, round_i):
    def evt(d):
        return {"choices": [{"delta": d, "finish_reason": None}]}

    events = [evt({"reasoning_content": "[dry] 第%d轮思考片段。" % (round_i + 1)})]
    if step == "final":
        events.append(evt({"content": "第%d轮的阶段性结论：层优先在子块构建时冻结快照槽。" % round_i}))
    else:
        args = {"path": "python/freetoken"} if step == "list_dir" else (
            {"pattern": "layer_major", "path": "python/freetoken", "glob": "*.py"}
            if step == "search_code"
            else {"path": "README.md", "max_bytes": 4000}
        )
        events.append(
            evt(
                {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_dry_%d" % round_i,
                            "function": {"name": step, "arguments": json.dumps(args, ensure_ascii=False)},
                        }
                    ]
                }
            )
        )
    events.append({"choices": [{"delta": {}, "finish_reason": "tool_calls" if step != "final" else "stop"}]})
    return events


def dry_replay_events(key):
    """桩回放：同 key 必然给同文本，因此前 N token 一致性门可以独立于缓存数据被校验。

    cached_tokens 固定 0 —— 桩没有服务端缓存可问，命中类判据只能由真实运行给出。
    """
    events = [{"choices": [{"delta": {"reasoning_content": "[dry] %s 思考。" % key}, "finish_reason": None}]}]
    for i in range(REPLAY_MAX_TOKENS):
        events.append({"choices": [{"delta": {"content": "%s#%02d " % (key, i)}, "finish_reason": None}]})
    events.append({"choices": [{"delta": {}, "finish_reason": "length"}]})
    events.append(
        {
            "choices": [],
            "usage": {
                "prompt_tokens": 9000 + len(key),
                "completion_tokens": REPLAY_MAX_TOKENS,
                "prompt_tokens_details": {"cached_tokens": 0},
            },
        }
    )
    return events


# --------------------------------------------------------------------------- #
# generate
# --------------------------------------------------------------------------- #
def cmd_generate(a):
    _SEEDTEXT = None
    if a.seed_file:
        import os as _os
        rp=_os.path.realpath(a.seed_file); root=_os.path.realpath(a.root)
        if not (rp==root or rp.startswith(root.rstrip("/")+"/")): raise SystemExit("seed-file 越界: %s" % rp)
        _SEEDTEXT=_io.open(rp,encoding="utf-8",errors="ignore").read()[:120000]

    tools = tool_specs()
    if a.thinking == "on" and a.no_think:
        raise SystemExit("--no-think 与 --thinking on 冲突，二选一")
    thinking = not (a.no_think or a.thinking == "off")
    _up = TASK_PROMPT
    if _SEEDTEXT:
        _up = TASK_PROMPT + chr(10)*2 + "以下是待分析的原文（真实文件内容）：" + chr(10) + _SEEDTEXT
    messages = [{"role": "user", "content": _up}]
    rounds_out = []
    url = chat_url(a.base_url)

    for round_i in range(a.rounds):
        snapshot = copy.deepcopy(messages)
        payload = build_payload(snapshot, a.model, tools, thinking, a.max_tokens)
        t0 = time.perf_counter()
        error = None
        if a.dry_run:
            step = DRY_STEPS[round_i % len(DRY_STEPS)]
            res = consume_stream(dry_generate_events(step, round_i), t0)
        else:
            try:
                res = consume_stream(post_events(url, payload, a.timeout), t0)
            except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as exc:
                detail = ""
                body = getattr(exc, "read", None)
                if callable(body):
                    try:
                        detail = body().decode("utf-8", errors="replace")[:500]
                    except Exception:
                        detail = ""
                error = "%s: %s %s" % (type(exc).__name__, exc, detail)
                res = consume_stream([], t0)

        prompt, cached, completion = usage_counts(res["usage"])
        calls = res["tool_calls"]
        record = {
            "round": round_i,
            "messages_sha": messages_digest(snapshot),
            "elapsed_s": round(time.perf_counter() - t0, 3),
            "ttft_s": res["ttft_s"],
            "ttft_basis": "stream_first_content_or_tool_call",
            "ttft_any_s": res["ttft_any_s"],
            "ttft_content_s": res["ttft_content_s"],
            "prompt_tokens": prompt,
            "cached_tokens": cached,
            "recomputed_tokens": prompt - cached,
            "completion_tokens": completion,
            "has_reasoning": bool(res["reasoning_text"]),
            "reasoning_chars": len(res["reasoning_text"]),
            "content_chars": len(res["content_text"]),
            "tool_calls": [c["function"]["name"] for c in calls],
            "finish_reason": res["finish_reason"],
            "continued": False,
            "dry_run": bool(a.dry_run),
            "error": error,
        }

        if error:
            # 请求失败就不要往历史里塞空 assistant 消息，那会把后续轮次的快照弄脏。
            rounds_out.append({"messages": snapshot, "record": record})
            print("[generate] 本轮请求失败，停止跑后续轮次：%s" % error, file=sys.stderr)
            break

        messages.append(assistant_message(res))
        if calls:
            for c in calls:
                content = (
                    "[dry-run 未真执行] 目标 %s" % c["function"]["name"]
                    if a.dry_run
                    else exec_tool_call(a.root, c)
                )
                tool_msg = {
                    "role": "tool",
                    "tool_call_id": c["id"],
                    "content": content,
                }
                messages.append(tool_msg)
                record.setdefault("tool_result_chars", []).append(len(content))
        else:
            record["tool_result_chars"] = []
            # 模型提前收单：为凑够 >=10 轮的真实多轮轨迹，注入跟进提问继续。
            if round_i + 1 < a.rounds:
                messages.append(
                    {"role": "user", "content": FOLLOW_UPS[round_i % len(FOLLOW_UPS)]}
                )
                record["continued"] = True

        rounds_out.append({"messages": snapshot, "record": record})
        print(
            "[generate] round=%d ttft_s=%s prompt=%s cached=%s tools=%s reasoning=%d%s"
            % (
                round_i,
                record["ttft_s"],
                prompt,
                cached,
                record["tool_calls"] or "-",
                record["reasoning_chars"],
                " continued" if record["continued"] else "",
            ),
            file=sys.stderr,
        )

    tool_rounds = sum(1 for r in rounds_out if r["record"]["tool_calls"])
    think_rounds = sum(1 for r in rounds_out if r["record"]["has_reasoning"])
    meta = {
        "kind": "agent_trace",
        "script": os.path.basename(__file__),
        "script_version": VERSION,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "params": {
            "rounds": a.rounds,
            "base_url": a.base_url,
            "model": a.model,
            "thinking": thinking,
            "max_tokens": a.max_tokens,
            "root": a.root,
            "temperature": 0,
            "dry_run": bool(a.dry_run),
            "timeout_s": a.timeout,
        },
        "task_prompt": _up,
        "seed_file": a.seed_file,
        "seed_chars": len(_up) - len(TASK_PROMPT),
        "follow_ups": FOLLOW_UPS,
        "summary": {
            "rounds_recorded": len(rounds_out),
            "rounds_with_tool_calls": tool_rounds,
            "rounds_with_reasoning": think_rounds,
            "tool_result_messages": sum(
                len(r["record"].get("tool_result_chars") or []) for r in rounds_out
            ),
            "meets_min_rounds": len(rounds_out) >= MIN_TRACE_ROUNDS,
            "meets_tools_and_thinking": tool_rounds >= 1
            and (think_rounds >= 1 if thinking else True),
        },
    }
    doc = {"meta": meta, "tools": tools, "rounds": rounds_out}
    write_json(a.out, doc)
    print("[generate] 写出 %s（%d 轮，含工具 %d 轮，含思考 %d 轮）"
          % (a.out, len(rounds_out), tool_rounds, think_rounds))
    if not a.dry_run and not meta["summary"]["meets_min_rounds"]:
        print("[generate] 警告：轮数 < %d，达不到验收 2，请加大 --rounds 或换任务"
              % MIN_TRACE_ROUNDS, file=sys.stderr)
    return 0


# --------------------------------------------------------------------------- #
# replay
# --------------------------------------------------------------------------- #
def parse_rounds(spec, total):
    if not spec:
        return list(range(total))
    picked = []
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            idx = int(part)
        except ValueError:
            raise SystemExit("--rounds 只接受逗号分隔的整数下标，收到 %r" % part)
        if 0 <= idx < total and idx not in picked:
            picked.append(idx)
    return sorted(picked)


def cmd_replay(a):
    trace = load_json(a.trace)
    rounds = trace.get("rounds") or []
    if not rounds:
        raise SystemExit("轨迹里没有 rounds：先用 generate 产出（或检查 --trace 路径）")
    tools = trace.get("tools") or tool_specs()
    thinking = {"auto": bool((trace.get("meta") or {}).get("params", {}).get("thinking", True)),
                "on": True, "off": False}[a.thinking]
    url = chat_url(a.base_url)
    selected = parse_rounds(a.rounds, len(rounds))
    edit_text = a.edit_text if a.edit_text is not None else DEFAULT_EDIT_TEXT

    out_rounds = []
    tool_msg_idx = []
    if a.edit_at_idx is not None and selected:
        longest = rounds[max(selected)]["messages"]
        tool_msg_idx = [i for i, m in enumerate(longest) if m.get("role") == "tool"]
        role_at = longest[a.edit_at_idx].get("role") if 0 <= a.edit_at_idx < len(longest) else None
        if role_at != "tool":
            print(
                "[replay] 提醒：--edit-at-idx=%d 指向 role=%s，不是工具结果。验收要的是"
                "「在某个锚点之后改写一个工具结果」，可选下标见 meta.tool_message_indexes=%s"
                % (a.edit_at_idx, role_at, tool_msg_idx),
                file=sys.stderr,
            )
    for k in selected:
        msgs = copy.deepcopy(rounds[k]["messages"])
        applied, note = apply_edit(msgs, a.edit_at_idx, edit_text)
        payload = build_payload(msgs, a.model, tools, thinking, REPLAY_MAX_TOKENS)
        t0 = time.perf_counter()
        error = None
        if a.dry_run:
            # key 只由「轮次 + 本轮是否真被编辑」决定：两次 dry 跑（命中路径/重算路径）
            # 在同参数下必然同 key，前 N token 一致性门因此可被独立校验。
            key = "dry_r%02d_%s" % (k, "edit" if applied else "plain")
            res = consume_stream(dry_replay_events(key), t0)
        else:
            try:
                res = consume_stream(post_events(url, payload, a.timeout), t0)
            except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as exc:
                error = "%s: %s" % (type(exc).__name__, exc)
                res = consume_stream([], t0)

        prompt, cached, completion = usage_counts(res["usage"])
        parts = res["parts"]
        text = "".join(parts)
        rec = {
            "round": k,
            "message_count": len(msgs),
            "messages_sha": messages_digest(msgs),
            "trace_messages_sha": (rounds[k].get("record") or {}).get("messages_sha"),
            "edit_applied": applied,
            "edit_note": note,
            "edit_at_idx": a.edit_at_idx,
            "elapsed_s": round(time.perf_counter() - t0, 3),
            "ttft_any_s": res["ttft_any_s"],
            "ttft_content_s": res["ttft_content_s"],
            "ttft_s": res["ttft_s"],
            "ttft_basis": "ttft_any_s=首个非空增量(含 reasoning/工具参数)；ttft_content_s=首个正文增量",
            "prompt_tokens": prompt,
            "cached_tokens": cached,
            "recomputed_tokens": prompt - cached,
            "completion_tokens": completion,
            "n_delta_parts": len(parts),
            "first32": "".join(parts[:TOKEN_PREFIX_GATE]),
            "first32_content": "".join(res["content_parts"][:TOKEN_PREFIX_GATE]),
            "content_parts": res["content_parts"],
            "text": text,
            "parts": parts,
            "reasoning_chars": len(res["reasoning_text"]),
            "content_chars": len(res["content_text"]),
            "tool_calls": [c["function"]["name"] for c in res["tool_calls"]],
            "finish_reason": res["finish_reason"],
            "dry_run": bool(a.dry_run),
            "error": error,
        }
        out_rounds.append(rec)
        print(
            "[replay] round=%d ttft_any=%s ttft_content=%s prompt=%s cached=%s recomputed=%s edit=%s%s"
            % (
                k,
                rec["ttft_any_s"],
                rec["ttft_content_s"],
                prompt,
                cached,
                rec["recomputed_tokens"],
                "Y" if applied else "n",
                " ERROR=%s" % error if error else "",
            ),
            file=sys.stderr,
        )

    meta = {
        "kind": "agent_replay",
        "script": os.path.basename(__file__),
        "script_version": VERSION,
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "trace_path": os.path.abspath(a.trace),
        "trace_meta": trace.get("meta"),
        "fresh_note": a.fresh_note or "未说明（默认按热进程理解：同一进程内升序回放，"
        "除第一个请求外都可能吃到前面写进缓存的前缀）",
        "params": {
            "base_url": a.base_url,
            "model": a.model,
            "thinking": thinking,
            "thinking_mode": a.thinking,
            "max_tokens": REPLAY_MAX_TOKENS,
            "temperature": 0,
            "rounds": selected,
            "edit_at_idx": a.edit_at_idx,
            "tool_message_indexes": tool_msg_idx,
            "edit_text_chars": len(edit_text) if a.edit_at_idx is not None else 0,
            "dry_run": bool(a.dry_run),
            "timeout_s": a.timeout,
        },
        "caveat": "全量重算基线请在冷服务进程里单独跑一次 replay 并用 --fresh-note 标注；"
        "同一进程内只有第一个请求是真正的全量重算。",
    }
    write_json(a.out, {"meta": meta, "rounds": out_rounds})
    print("[replay] 写出 %s（%d 轮）" % (a.out, len(out_rounds)))
    return 0


# --------------------------------------------------------------------------- #
# compare（验收门，失败即关闭）
# --------------------------------------------------------------------------- #
def cmd_compare(a):
    hit = load_json(a.a)
    recompute = load_json(a.b)
    trace = load_json(a.trace) if a.trace else None
    n_tokens = a.tokens

    def by_round(doc):
        return {r["round"]: r for r in doc.get("rounds") or []}

    H, R = by_round(hit), by_round(recompute)
    common = sorted(set(H) & set(R))
    if not common:
        raise SystemExit("两份回放没有共同轮次，比不了")

    gates = []
    rows = []
    dry_seen = False

    def add(name, ok, detail, skipped=False):
        gates.append({"gate": name, "result": "SKIP" if skipped else ("PASS" if ok else "NOT MET"),
                      "detail": detail})

    # 门 0：轨迹真实性（验收 2 的前半）
    if trace:
        smry = (trace.get("meta") or {}).get("summary") or {}
        n_rounds = smry.get("rounds_recorded", len(trace.get("rounds") or []))
        tool_rounds = smry.get("rounds_with_tool_calls", 0)
        think_rounds = smry.get("rounds_with_reasoning", 0)
        thinking_on = bool(((trace.get("meta") or {}).get("params") or {}).get("thinking", True))
        add(
            "轨迹轮数 >= %d" % a.min_rounds,
            n_rounds >= a.min_rounds,
            "实际 %d 轮" % n_rounds,
        )
        add("含工具调用", tool_rounds >= 1, "有工具调用的轮数 %d" % tool_rounds)
        add(
            "含思考段" if thinking_on else "含思考段（轨迹关思考，此门不适用）",
            think_rounds >= 1 if thinking_on else True,
            "有 reasoning 的轮数 %d（thinking=%s）" % (think_rounds, thinking_on),
            skipped=not thinking_on,
        )
        dry_seen = dry_seen or any(
            (r.get("record") or {}).get("dry_run") for r in trace.get("rounds") or []
        )
    else:
        add("轨迹真实性（轮数/工具/思考）", True, "没给 --trace，未评估", skipped=True)

    dry_seen = dry_seen or any(
        H[k].get("dry_run") or R[k].get("dry_run") for k in common
    ) or bool(
        (hit.get("meta") or {}).get("params", {}).get("dry_run")
        or (recompute.get("meta") or {}).get("params", {}).get("dry_run")
    )

    # 门 1：temp 0 前 N token 一致（命中路径 vs 全量重算）
    eq_fail, eq_short, eq_body_fail = [], [], []
    sha_pair_fail, sha_trace_fail, sha_seen, sha_trace_seen = [], [], 0, 0
    for k in common:
        th, tr = H[k].get("parts") or [], R[k].get("parts") or []
        ph, pr = "".join(th[:n_tokens]), "".join(tr[:n_tokens])
        bh, br = H[k].get("content_parts"), R[k].get("content_parts")
        avail = min(len(th), len(tr))
        # 可比片数不足 N 时，只有「整段输出也逐字相同且收尾原因一致」才算证据成立，
        # 否则按未达标处理（片数不够时"前 32 token 一致"是无法断言的）。
        whole_equal = (
            H[k].get("finish_reason") == R[k].get("finish_reason") and "".join(th) == "".join(tr)
        )
        if avail < n_tokens and not whole_equal:
            eq_short.append(k)
        if ph != pr:
            eq_fail.append(k)
        # 正文口径单独比一次：开思考时前 N 片多半是 reasoning，正文也一致才算硬证据。
        # 两侧都有正文才判（老产物没存 content_parts 时退到 first32_content）。
        if bh is None and br is None:
            bh, br = H[k].get("first32_content"), R[k].get("first32_content")
            body_pair = bh is not None and br is not None
            body_equal = bh == br if body_pair else None
        else:
            bh = "".join((bh or [])[:n_tokens])
            br = "".join((br or [])[:n_tokens])
            body_pair = bool(bh) and bool(br)
            body_equal = bh == br if body_pair else None
        if body_pair and not body_equal:
            eq_body_fail.append(k)
        # 摘要核对：两份必须发同一份请求字节，否则"前 32 token 比较"比的是两个不同提示。
        sha_h, sha_r = H[k].get("messages_sha"), R[k].get("messages_sha")
        if sha_h and sha_r:
            sha_seen += 1
            if sha_h != sha_r:
                sha_pair_fail.append(k)
        if H[k].get("trace_messages_sha"):
            sha_trace_seen += 1
            # 编辑过的轮次本来就该与 generate 时不同，只有未编辑轮必须逐字相同。
            if H[k].get("edit_applied") is False and sha_h != H[k].get("trace_messages_sha"):
                sha_trace_fail.append(k)
        rows.append(
            {
                "round": k,
                "hit_messages_sha": sha_h,
                "recompute_messages_sha": sha_r,
                "trace_messages_sha": H[k].get("trace_messages_sha"),
                "hit_ttft_any_s": H[k].get("ttft_any_s"),
                "hit_ttft_content_s": H[k].get("ttft_content_s"),
                "recompute_ttft_any_s": R[k].get("ttft_any_s"),
                "recompute_ttft_content_s": R[k].get("ttft_content_s"),
                "hit_prompt_tokens": H[k].get("prompt_tokens"),
                "hit_cached_tokens": H[k].get("cached_tokens"),
                "hit_recomputed_tokens": H[k].get("recomputed_tokens"),
                "recompute_cached_tokens": R[k].get("cached_tokens"),
                "recompute_recomputed_tokens": R[k].get("recomputed_tokens"),
                "first_n_equal": ph == pr,
                "first_n_content_equal": body_equal,
                "available_parts": avail,
                "hit_edit_applied": H[k].get("edit_applied"),
                "first_n_hit": ph,
                "first_n_recompute": pr,
            }
        )
    add(
        "temp0 前 %d token 一致" % n_tokens,
        not eq_fail and not eq_short and not eq_body_fail,
        "整体前缀不一致轮 %s；正文前缀不一致轮 %s；可比片数不足 %d 片且整段也不相同的轮 %s"
        % (eq_fail or "无", eq_body_fail or "无", n_tokens, eq_short or "无"),
    )

    # 门 1b：两份回放必须发同一份请求字节，否则比的是两个不同提示
    add(
        "两份回放请求逐字一致",
        bool(sha_seen) and not sha_pair_fail,
        "双方都有摘要 %d/%d 轮；不一致轮 %s（多半是 --edit-at-idx 或 --thinking 两次没对齐）"
        % (sha_seen, len(common), sha_pair_fail or "无"),
        skipped=not sha_seen,
    )

    # 门 1c：未编辑轮的请求必须与 generate 发出去时一致（回放没弄脏字节）
    add(
        "未编辑轮请求与 generate 时一致",
        bool(sha_trace_seen) and not sha_trace_fail,
        "有轨迹摘要的轮 %d，其中对不上的轮 %s（对不上说明回放改了不该改的字节，前缀必然不命中）"
        % (sha_trace_seen, sha_trace_fail or "无"),
        skipped=not sha_trace_seen,
    )

    # 门 2：编辑之后的轮次首 token <= 4 s（ttft_any 口径）
    post = [k for k in common if H[k].get("edit_applied")]
    slow = [
        (k, H[k].get("ttft_any_s"))
        for k in post
        if H[k].get("ttft_any_s") is None or H[k].get("ttft_any_s") > a.ttft_gate
    ]
    add(
        "编辑后首 token <= %.1f s" % a.ttft_gate,
        bool(post) and not slow,
        "编辑后轮 %s，超时/缺读数 %s" % (post or "无（没带 --edit-at-idx 跑回放）", slow or "无"),
        skipped=not post,
    )

    # 门 3：前缀命中量（DEV_NEXT_D3 验收 2 的 >=8704 token，默认只报不门）
    if a.min_cached is None:
        add("编辑后前缀命中量（本次未设门，只记录）", True,
            "各轮 cached_tokens：%s" % ({k: H[k].get("cached_tokens") for k in post} or "无编辑轮"),
            skipped=True)
    else:
        low = [(k, H[k].get("cached_tokens")) for k in post if (H[k].get("cached_tokens") or 0) < a.min_cached]
        add("编辑后前缀命中 >= %d token" % a.min_cached, bool(post) and not low,
            "偏低 %s" % (low or "无"), skipped=not post)

    # 门 4：命中不是假命中（参与判定的各轮 cached_tokens 必须 > 0）
    # 本次回放的第一个请求必然无前缀可命中（缓存还没被它自己填上），一律不参与判定；
    # 若你在另一个进程里已经预热过，多出来的仍是"编辑后那些轮"的命中证据。
    probe_rounds = [k for k in (post or common) if k != common[0]]
    zero = [k for k in probe_rounds if (H[k].get("cached_tokens") or 0) <= 0]
    add(
        "命中路径 cached_tokens > 0",
        bool(probe_rounds) and not zero,
        "参与判定轮 %s，其中 cached=0 的轮 %s（服务端没开 --enable-cache-report 就是全 0，"
        "此时命中类判据不成立）" % (probe_rounds, zero or "无"),
        skipped=not probe_rounds,
    )

    required_gates = ("轨迹真实性", "两份回放请求", "未编辑轮请求")
    skipped_required = [g for g in gates if g["result"] == "SKIP" and g["gate"].startswith(required_gates)]
    failed = [g for g in gates if g["result"] == "NOT MET"]
    verdict = "NOT MET" if (failed or skipped_required or dry_seen) else "PASS"

    report = {
        "meta": {
            "kind": "agent_trace_verdict",
            "script_version": VERSION,
            "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "a_path(命中路径)": os.path.abspath(a.a),
            "b_path(全量重算路径)": os.path.abspath(a.b),
            "trace_path": os.path.abspath(a.trace) if a.trace else None,
            "a_fresh_note": (hit.get("meta") or {}).get("fresh_note"),
            "b_fresh_note": (recompute.get("meta") or {}).get("fresh_note"),
            "gates": {
                "tokens": n_tokens,
                "ttft_gate_s": a.ttft_gate,
                "min_rounds": a.min_rounds,
                "min_cached": a.min_cached,
            },
            "dry_run_data": dry_seen,
        },
        "verdict": verdict,
        "gates": gates,
        "rounds": rows,
    }
    if a.out:
        write_json(a.out, report)
    print(json.dumps({"verdict": verdict, "gates": gates}, ensure_ascii=False, indent=1))
    if dry_seen:
        print("数据含 --dry-run 桩响应，不能当验收证据（判 NOT MET）", file=sys.stderr)
    for r in rows:
        print(
            "  round=%-3d cached(hit)=%-6s recomputed(hit)=%-6s ttft_any(hit)=%-8s "
            "ttft_any(recompute)=%-8s first%d=%s"
            % (
                r["round"],
                r["hit_cached_tokens"],
                r["hit_recomputed_tokens"],
                r["hit_ttft_any_s"],
                r["recompute_ttft_any_s"],
                n_tokens,
                "一致" if r["first_n_equal"] else "不一致",
            )
        )
    from pathlib import Path

    label_ref = a.label_ref or "/".join(Path(a.a).resolve().parts[-2:])
    label_test = a.label_test or "/".join(Path(a.b).resolve().parts[-2:])
    print("结论（%s 对 %s）：%s" % (label_ref, label_test, verdict))
    return 0 if verdict == "PASS" else 1


# --------------------------------------------------------------------------- #
# IO 与入口
# --------------------------------------------------------------------------- #
def write_json(path, doc):
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def add_common(p, base=True):
    if base:
        p.add_argument("--base-url", default=BASE_URL_DEFAULT)
        p.add_argument("--model", default=MODEL_DEFAULT)
        p.add_argument("--timeout", type=float, default=HTTP_TIMEOUT_S)
    p.add_argument("--dry-run", action="store_true", help="不联网，用确定性桩响应校验构造")


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="agent_trace.py",
        description="真实 Agent 轨迹（>=10 轮、含工具调用与思考）生成/回放/一致性判定工装",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="现场跑一条真实轨迹并保存")
    g.add_argument("--out", required=True)
    g.add_argument("--rounds", type=int, default=MAX_ROUNDS_DEFAULT)
    g.add_argument("--thinking", choices=("on", "off"), default=None,
                   help="默认就是 on（请求里不加 chat_template_kwargs.enable_thinking）；off 等价 --no-think")
    g.add_argument(
        "--no-think",
        action="store_true",
        help="关闭思考（请求里加 chat_template_kwargs.enable_thinking=false）；默认是开的",
    )
    g.add_argument("--max-tokens", type=int, default=GENERATE_MAX_TOKENS_DEFAULT)
    g.add_argument("--seed-file", default=None, help="把该真实文件内联进首条 user 消息，用于把前缀顶到验收需要的长度")
    g.add_argument("--root", default=ROOT_DEFAULT, help="工具的工作根，只允许在其内只读访问")
    add_common(g)
    g.set_defaults(func=cmd_generate)

    r = sub.add_parser("replay", help="逐轮重放前缀并测量")
    r.add_argument("--trace", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--edit-at-idx", type=int, default=None, help="在第几条消息处替换工具结果内容")
    r.add_argument("--edit-text", default=None, help="不给就用内置的加长占位文本")
    r.add_argument("--rounds", default=None, help="逗号分隔的轮次下标子集，默认全部")
    r.add_argument("--fresh-note", default=None, help="写明本次是冷进程还是热进程")
    r.add_argument("--thinking", choices=("auto", "on", "off"), default="auto",
                   help="auto=跟着轨迹的 meta 走，保证聊天模板字节序一致，否则前缀必然不命中")
    add_common(r)
    r.set_defaults(func=cmd_replay)

    c = sub.add_parser("compare", help="命中路径 vs 全量重算：前 N token 一致性与验收门")
    c.add_argument("--a", required=True, help="命中路径的 replay 产物（热进程）")
    c.add_argument("--b", required=True, help="全量重算路径的 replay 产物（冷进程）")
    c.add_argument("--label-ref")
    c.add_argument("--label-test")
    c.add_argument("--trace", default=None, help="轨迹 JSON，用于评估轮数/工具/思考三扇门")
    c.add_argument("--out", default=None)
    c.add_argument("--tokens", type=int, default=TOKEN_PREFIX_GATE)
    c.add_argument("--ttft-gate", type=float, default=TTFT_GATE_S)
    c.add_argument("--min-rounds", type=int, default=MIN_TRACE_ROUNDS)
    c.add_argument("--min-cached", type=int, default=None, help="例如 8704（DEV_NEXT_D3 验收 2）")
    add_common(c, base=False)
    c.set_defaults(func=cmd_compare)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
