"""Standard OpenAI completion collection/projection; never launches a service."""
from __future__ import annotations

import json
import time
from typing import Any, Iterable


class CompletionCollectionError(ValueError):
    """A collection failure carrying the durable partial SDK observation."""

    def __init__(self, artifact: dict[str, Any], cause: BaseException):
        super().__init__(str(cause))
        self.artifact = artifact


def _usage(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        raise ValueError("completion stream ended without usage")
    result = {key: value.get(key) for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
    if any(type(number) is not int or number < 0 for number in result.values()):
        raise ValueError("invalid completion usage")
    if result["total_tokens"] != result["prompt_tokens"] + result["completion_tokens"]:
        raise ValueError("inconsistent completion usage")
    return result


def validate_request(request: dict[str, Any]) -> None:
    if not isinstance(request.get("model"), str) or not request["model"]:
        raise ValueError("completion model is required")
    if not isinstance(request.get("prompt"), str):
        raise ValueError("completion prompt must be mapped text")
    required = {"max_tokens": 128, "temperature": 0, "top_p": 1, "stream": True}
    if any(request.get(key) != value for key, value in required.items()):
        raise ValueError("D16 SDK request differs from fixed sampling")
    if request.get("stream_options") != {"include_usage": True}:
        raise ValueError("D16 SDK request requires streamed usage")
    if request.get("extra_body") != {"ignore_eos": True}:
        raise ValueError("D16 SDK request requires ignore_eos")


def project_completion_chunks(chunks: Iterable[dict[str, Any]]) -> dict[str, Any]:
    text, finish, usage, completion_id = [], None, None, None
    for chunk in chunks:
        current_id = chunk.get("id")
        if not isinstance(current_id, str) or not current_id:
            raise ValueError("completion chunk lacks id")
        if completion_id is None:
            completion_id = current_id
        elif completion_id != current_id:
            raise ValueError("completion id changed during stream")
        choices = chunk.get("choices")
        if not isinstance(choices, list) or len(choices) > 1:
            raise ValueError("invalid completion choices")
        if choices:
            if finish is not None:
                raise ValueError("choice follows terminal finish_reason")
            choice = choices[0]
            if choice.get("index") != 0 or not isinstance(choice.get("text"), str):
                raise ValueError("invalid completion choice")
            text.append(choice["text"])
            if choice.get("finish_reason") is not None:
                if choice["finish_reason"] not in ("stop", "length"):
                    raise ValueError("unsupported completion finish_reason")
                finish = choice["finish_reason"]
        if chunk.get("usage") is not None:
            if usage is not None:
                raise ValueError("duplicate completion usage")
            usage = _usage(chunk["usage"])
    if finish is None:
        raise ValueError("completion stream ended without finish_reason")
    usage = _usage(usage)
    if finish != "length" or usage["completion_tokens"] != 128:
        raise ValueError("D16 SDK completion must end at length with 128 tokens")
    return {"text": "".join(text), "finish_reason": finish, "usage": usage,
            "completion_id": completion_id}


def _wire_request(request: dict[str, Any]) -> dict[str, Any]:
    value = {key: item for key, item in request.items() if key != "extra_body"}
    value.update(request["extra_body"])
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def collect_completion(client: Any, request: dict[str, Any]) -> dict[str, Any]:
    validate_request(request)
    if client.max_retries != 0:
        raise ValueError("D16 SDK collection requires max_retries=0")
    started = time.monotonic()
    artifact = {"request": _wire_request(request), "response": None, "chunks": []}
    try:
        raw = client.with_raw_response.completions.create(**request)
        artifact["response"] = {"status_code": raw.status_code, "headers": dict(raw.headers),
                                "received_seconds": time.monotonic() - started}
        for chunk in raw.parse():
            artifact["chunks"].append({"arrival_seconds": time.monotonic() - started,
                                       "data": chunk.model_dump(mode="json")})
        artifact["projection"] = project_completion_chunks(row["data"] for row in artifact["chunks"])
        return artifact
    except BaseException as exc:
        artifact["error"] = {"type": type(exc).__name__, "message": str(exc),
                             "received_seconds": time.monotonic() - started}
        raise CompletionCollectionError(artifact, exc) from exc


def compare_completion(left: dict[str, Any], right: dict[str, Any]) -> None:
    for value in (left, right):
        if value.get("finish_reason") != "length":
            raise ValueError("D16 SDK projection finish_reason must be length")
        usage = value.get("usage")
        if not isinstance(usage, dict) or usage.get("completion_tokens") != 128:
            raise ValueError("D16 SDK projection usage must contain 128 completion tokens")
    for field in ("text", "finish_reason", "usage"):
        if left.get(field) != right.get(field):
            raise ValueError(f"D16 SDK comparable completion differs: {field}")
