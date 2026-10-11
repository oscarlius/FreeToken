"""SDK transport and lossless chunk logging for the existing Quality60 grader.

This module has no benchmark loop, scoring rules, service lifecycle, or CLI.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


def capture_chat_stream(client: Any, request: dict[str, Any], destination: Path) -> dict[str, Any]:
    """Record SDK-decoded chunks, then project one completed text response.

    The exclusive-create log survives parse/transport/contract failures. It is
    decoded SDK evidence, not a byte-for-byte copy of the HTTP response.
    """
    if client.max_retries != 0:
        raise ValueError("Quality60 capture requires max_retries=0")
    if request.get("stream") is not True or request.get("n", 1) != 1:
        raise ValueError("Quality60 requires one streamed completion")
    if request.get("stream_options", {}).get("include_usage") is not True:
        raise ValueError("Quality60 requires explicit streamed usage")
    chunks = []
    with Path(destination).open("x", encoding="utf-8", newline="\n") as log:
        def record(value: dict[str, Any]) -> None:
            log.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
            log.flush()

        try:
            with client.chat.completions.create(**request) as stream:
                request_id = stream.response.headers.get("x-request-id")
                record({"kind": "response", "request_id": request_id})
                for chunk in stream:
                    data = chunk.model_dump(mode="json")
                    record({"kind": "chunk", "data": data})
                    chunks.append(data)
            result = project_chat_chunks(chunks)
            record({"kind": "complete"})
            return {**result, "request_id": request_id}
        except Exception as exc:
            record({"kind": "error", "error_type": type(exc).__name__})
            raise


def project_chat_chunks(chunks: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Preserve terminal metadata; never infer a successful stop or token count."""
    content, thinking = [], []
    finish_reason = None
    usage = None
    completion_id = None
    for chunk in chunks:
        current_id = chunk.get("id")
        if not isinstance(current_id, str) or not current_id:
            raise ValueError("missing completion id")
        if completion_id is None:
            completion_id = current_id
        elif current_id != completion_id:
            raise ValueError("completion id changed during stream")
        if chunk.get("usage") is not None:
            if usage is not None and usage != chunk["usage"]:
                raise ValueError("conflicting usage records")
            usage = chunk["usage"]
        choices = chunk.get("choices")
        if not isinstance(choices, list) or len(choices) > 1:
            raise ValueError("expected zero or one completion choice")
        if not choices:
            continue
        choice = choices[0]
        if choice.get("index") != 0:
            raise ValueError("unexpected choice index")
        if finish_reason is not None:
            raise ValueError("choice data follows terminal finish_reason")
        delta = choice.get("delta")
        if not isinstance(delta, dict):
            raise ValueError("missing delta object")
        if delta.get("tool_calls") or delta.get("function_call"):
            raise ValueError("native tool calls are outside the fixed text Quality60 contract")
        for field, target in (("content", content), ("reasoning_content", thinking)):
            value = delta.get(field)
            if value is not None:
                if not isinstance(value, str):
                    raise ValueError(f"non-text {field}")
                target.append(value)
        terminal = choice.get("finish_reason")
        if terminal is not None:
            if terminal not in ("stop", "length"):
                raise ValueError(f"unsupported Quality60 finish_reason: {terminal}")
            finish_reason = terminal
    if finish_reason is None:
        raise ValueError("stream ended without terminal finish_reason")
    if not isinstance(usage, dict):
        raise ValueError("stream ended without usage")
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = usage.get(key)
        if type(value) is not int or value < 0:
            raise ValueError(f"invalid usage.{key}")
    if usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]:
        raise ValueError("inconsistent usage token counts")
    return {"response": "".join(content), "thinking": "".join(thinking),
            "finish_reason": finish_reason, "usage": usage, "completion_id": completion_id}
