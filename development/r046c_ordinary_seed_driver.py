#!/usr/bin/env python3
"""R046c ordinary-SSE session driver.

The frozen agent-trace source supplies payload/session/tool semantics.  Transport
is replaced only with the R046c v3 ordinary client so no ft_dev ACK is requested
or synthesized.  Every dispatched request is bound to the Engine worker's
UserMsg input ids and DetokenizeMsg token sidecar before the session advances.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

WINDOW, RESERVE = 98304, 2048
LIMIT = WINDOW - RESERVE


def sha(path: Path) -> str: return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as h: json.dump(value, h, ensure_ascii=False, sort_keys=True, indent=2); h.write("\n")


def load_module(name: str, path: Path):
    if path.is_symlink() or not path.is_file(): raise RuntimeError(f"R046c source unavailable: {path}")
    spec = importlib.util.spec_from_file_location(name, path); module = importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(module); return module


def sse_events(raw: bytes):
    for line in raw.decode("utf-8", errors="strict").splitlines():
        if line.startswith("data:"):
            data = line[5:].strip()
            if data and data != "[DONE]": yield json.loads(data)


def input_ids_for_payload(frontend, payload: dict) -> list[int]:
    ids = frontend(payload)
    if not isinstance(ids, list) or any(type(token) is not int or token < 0 for token in ids):
        raise RuntimeError("R046c candidate frontend did not return canonical request ids")
    return ids


def _bound_request(client, base_url, payload, name, directory, d0, route, inputs, tokens):
    payload_path, api_path, binding_path = directory / f"{name}.payload.json", directory / f"{name}.api.json", directory / f"{name}.binding.json"
    write_new(payload_path, payload)
    api = client.ordinary_request(base_url, payload_path, api_path)
    binding = client.bind(payload_path, api_path, d0, route, inputs, tokens, binding_path)
    raw = Path(api["sse"]).read_bytes()
    return api, binding, raw


def generate_session(*, client, original, frontend, base_url: str, seed: str, seed_sha256: str,
                     directory: Path, d0: Path, route: Path, inputs: Path, tokens: Path,
                     model: str, tool_root: Path, rounds: int = 12, max_tokens: int = RESERVE) -> dict:
    if rounds != 12 or max_tokens != RESERVE: raise ValueError("R046c seed session requires 12 rounds and 2048 max tokens")
    if hashlib.sha256(seed.encode("utf-8")).hexdigest() != seed_sha256: raise RuntimeError("R046c seed bytes differ")
    tools, thinking = original.tool_specs(), True
    messages = [{"role": "user", "content": seed + "\n\n" + original.TASK_PROMPT}]
    rows, bindings, hit = [], [], None
    for index in range(rounds):
        snapshot = copy.deepcopy(messages); payload = original.build_payload(snapshot, model, tools, thinking, max_tokens)
        ids = input_ids_for_payload(frontend, payload)
        planned = {"request_k": index + 1, "actual_input_ids_sha256": hashlib.sha256(json.dumps(ids, separators=(",", ":")).encode()).hexdigest(), "actual_prompt_tokens": len(ids)}
        if len(ids) > LIMIT:
            hit = {"request_k": index + 1, "actual_prompt_tokens": len(ids), "planned_input_binding": planned, "payload": payload}
            break
        api, binding, raw = _bound_request(client, base_url, payload, f"round-{index:02d}", directory, d0, route, inputs, tokens)
        result = original.consume_stream(iter(sse_events(raw)), 0.0)
        if binding["worker_input"]["input_ids_sha256"] != planned["actual_input_ids_sha256"]:
            raise RuntimeError("R046c worker UserMsg ids differ from candidate frontend preflight")
        if binding["worker_input"]["input_tokens"] != planned["actual_prompt_tokens"]:
            raise RuntimeError("R046c worker UserMsg length differs from candidate frontend preflight")
        rows.append({"messages": snapshot, "record": {"round": index, "api_uid": api["uid"], "messages_sha": original.messages_digest(snapshot),
                    "prompt_tokens": api["usage"]["prompt_tokens"], "completion_tokens": api["usage"]["completion_tokens"],
                    "finish_reason": api["finish_reason"], "actual_input_binding": binding, "token_events": binding["token_sidecar"]["events"]},
                     "response": {"content_text": result["content_text"], "tool_calls": result["tool_calls"]}})
        bindings.append(planned)
        messages.append(original.assistant_message(result))
        if result["tool_calls"]:
            for call in result["tool_calls"]:
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": original.exec_tool_call(str(tool_root), call)})
        elif index + 1 < rounds:
            messages.append({"role": "user", "content": original.FOLLOW_UPS[index % len(original.FOLLOW_UPS)]})
    if not rows: raise RuntimeError("R046c seed first request exceeded the ordinary window")
    if hit is None and len(rows) != rounds: raise RuntimeError("R046c session stopped before natural terminal condition")
    return {"schema": "ft_r046c_ordinary_seed_trace/v1", "rounds": rows,
            "meta": {"window": WINDOW, "completion_reserve_tokens": RESERVE, "max_prompt_tokens": LIMIT,
                     "seed_raw_sha256": seed_sha256, "completed_k": len(rows), "completed_input_bindings": bindings,
                     "window_hit": hit, "window_hit_count": int(hit is not None),
                     "termination": "window_hit" if hit else "completed", "transport": "ordinary_sse_no_ft_dev_ack"}}


def two_decode(*, client, original, frontend, base_url: str, directory: Path, d0: Path, route: Path,
               inputs: Path, tokens: Path, model: str) -> dict:
    tools = original.tool_specs(); payloads = [
        original.build_payload([{"role": "user", "content": original.TASK_PROMPT}], model, tools, True, 256),
        original.build_payload([{"role": "user", "content": original.FOLLOW_UPS[0]}], model, tools, True, 256),
    ]
    if payloads[0]["messages"] == payloads[1]["messages"]: raise RuntimeError("R046c two-decode prompts are not different")
    for payload in payloads:
        if len(input_ids_for_payload(frontend, payload)) > LIMIT: raise RuntimeError("R046c two-decode exceeds ordinary window")
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_bound_request, client, base_url, payload, f"two-{index}", directory, d0, route, inputs, tokens) for index, payload in enumerate(payloads)]
        results = [future.result() for future in futures]
    records = []
    for index, (api, binding, raw) in enumerate(results):
        parsed = original.consume_stream(iter(sse_events(raw)), 0.0)
        records.append({"uid": api["uid"], "input_ids_sha256": binding["worker_input"]["input_ids_sha256"],
                        "completion_tokens": api["usage"]["completion_tokens"], "finish_reason": api["finish_reason"],
                        "full_text": parsed["content_text"], "tool_calls": parsed["tool_calls"], "binding": binding})
    if len({record["uid"] for record in records}) != 2: raise RuntimeError("R046c two-decode ordinary API UIDs are not distinct")
    return {"schema": "ft_r046c_ordinary_two_decode/v1", "same_prompt": False, "ctx": 8000, "max_tokens": 256,
            "parallel": True, "records": records, "transport": "ordinary_sse_no_ft_dev_ack"}


def candidate_frontend(worktree: Path, tokenizer_path: Path):
    """Use the candidate TokenizeManager; do not reconstruct a chat template here."""
    sys.path.insert(0, str(worktree / "python"))
    from freetoken.tokenizer.tokenize import TokenizeManager
    from transformers import AutoTokenizer
    manager = TokenizeManager(AutoTokenizer.from_pretrained(str(tokenizer_path), trust_remote_code=True))
    def render(payload):
        message = type("R046cMsg", (), {"uid": 0, "text": payload["messages"], "tools": payload.get("tools"),
                                          "chat_template_kwargs": payload.get("chat_template_kwargs") or {}, "images": None,
                                          "sampling_params": None})()
        ids = manager.tokenize([message])[0].input_ids
        return ids.tolist() if hasattr(ids, "tolist") else ids
    return render


def main(argv=None):
    p = argparse.ArgumentParser(); p.add_argument("--generate", action="store_true"); p.add_argument("--two", action="store_true")
    p.add_argument("--client", type=Path, required=True); p.add_argument("--original", type=Path, required=True)
    p.add_argument("--worktree", type=Path, required=True); p.add_argument("--tokenizer-path", type=Path, required=True); p.add_argument("--tool-root", type=Path, required=True)
    p.add_argument("--base-url", required=True); p.add_argument("--directory", type=Path, required=True); p.add_argument("--d0", type=Path, required=True); p.add_argument("--route", type=Path, required=True); p.add_argument("--inputs", type=Path, required=True); p.add_argument("--tokens", type=Path, required=True); p.add_argument("--model", required=True); p.add_argument("--out", type=Path, required=True)
    p.add_argument("--seed-file", type=Path); p.add_argument("--seed-sha256")
    a = p.parse_args(argv)
    if a.generate == a.two: p.error("select exactly one session mode")
    client, original = load_module("r046c_client", a.client), load_module("r046c_original_agent_trace", a.original)
    frontend = candidate_frontend(a.worktree, a.tokenizer_path)
    if a.generate:
        if a.seed_file is None or not a.seed_sha256: p.error("generate requires --seed-file and --seed-sha256")
        result = generate_session(client=client, original=original, frontend=frontend, base_url=a.base_url,
            seed=a.seed_file.read_text(encoding="utf-8"), seed_sha256=a.seed_sha256, directory=a.directory,
            d0=a.d0, route=a.route, inputs=a.inputs, tokens=a.tokens, model=a.model, tool_root=a.tool_root)
    else:
        result = two_decode(client=client, original=original, frontend=frontend, base_url=a.base_url,
            directory=a.directory, d0=a.d0, route=a.route, inputs=a.inputs, tokens=a.tokens, model=a.model)
    write_new(a.out, result); print(json.dumps(result, sort_keys=True)); return 0

if __name__ == "__main__": raise SystemExit(main())
