"""Bind the three frozen ordinary requests to D12's actual worker admissions.

This does not infer generation counts, alter sampling, or install an API route.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_replay_binding(root, expected_sha):
    root = Path(root).absolute()
    if root.resolve() != root or root.is_symlink():
        raise ValueError("D12 input bundle must be a physical directory")

    def read(relative, digest):
        rel = PurePosixPath(relative)
        if rel.is_absolute() or ".." in rel.parts or str(rel) != relative:
            raise ValueError("invalid D12 input relative path")
        path = root.joinpath(*rel.parts)
        if path.resolve() != path or path.is_symlink() or not path.is_file():
            raise ValueError("D12 input must be a physical regular file")
        raw = path.read_bytes()
        if _sha(raw) != digest:
            raise ValueError("D12 input SHA mismatch: " + relative)
        return raw

    bundle = json.loads(read("binding.json", expected_sha))
    if bundle["schema"] != "ft_d12_sealed_segment_inputs/v1":
        raise ValueError("D12 input bundle schema differs")
    replay = bundle["replay_contract"]
    if (replay["ordinary_sse_only"] is not True or replay["order"] != [0, 1, 2]
            or replay["payload_changes"] != []):
        raise ValueError("D12 ordinary replay contract differs")
    selected = bundle["selected_history"]
    if [(row["group"], row["round"], row["uid"]) for row in selected] != [
            ("G_seed12k", i, i) for i in range(3)]:
        raise ValueError("D12 frozen request order differs")
    requests = []
    for row in selected:
        uid = row["uid"]
        if type(uid) is not int:
            raise ValueError("D12 UID must be an integer")
        raw_ids = read(row["input_ids_path"], row["input_ids_sha256"])
        ids = json.loads(raw_ids)
        if (not isinstance(ids, list) or len(ids) != row["input_tokens"] or not ids
                or any(type(n) is not int or not 0 <= n < 2**31 for n in ids)
                or json.dumps(ids, separators=(",", ":")).encode() != raw_ids):
            raise ValueError("D12 frozen token IDs differ")
        payload = json.loads(read(row["payload_path"], row["payload_sha256"]))
        if (payload["model"] != "Qwen3.8-Flash-Next-NVFP4" or payload["stream"] is not True
                or payload["stream_options"] != {"include_usage": True}
                or type(payload["max_tokens"]) is not int or payload["max_tokens"] != 2048
                or type(payload["temperature"]) not in (int, float) or payload["temperature"] != 0
                or not payload.get("tools")):
            raise ValueError("D12 original ordinary payload differs")
        requests.append({"uid": uid, "input_ids": ids, "max_tokens": payload["max_tokens"],
                         "temperature": payload["temperature"], "payload_sha256": row["payload_sha256"],
                         "input_ids_json_sha256": row["input_ids_sha256"]})
    return {"bundle_sha256": expected_sha, "requests": requests}


def load_from_env(*, required=False):
    root, digest = os.environ.get("FT_D12_REPLAY_INPUT_DIR"), os.environ.get("FT_D12_REPLAY_INPUT_SHA256")
    if root is None and digest is None and not required:
        return None  # Existing direct CPU worker fixtures have no ordinary-API claim.
    if not root or not digest:
        raise ValueError("D12 ordinary launcher requires input directory and binding SHA")
    return load_replay_binding(root, digest)


def install_admission_guard(adapter, binding):
    """Check inputs before native admission; leave D16 delivery criteria intact."""
    from equiv_suite.service_capture import ServiceCaptureError, _ids, _sampling

    requests = binding["requests"]
    if set(item["uid"] for item in adapter.expected_queries) != set(row["uid"] for row in requests):
        raise ValueError("D12 input UIDs differ from the D16 capture declaration")
    original = adapter.admit_user_msg
    admitted = 0

    def admit(message):
        nonlocal admitted
        try:
            uid = getattr(message, "uid", None)
            if admitted >= len(requests) or type(uid) is not int or uid != requests[admitted]["uid"]:
                raise ValueError("D12 admission order or UID differs from frozen inputs")
            expected = requests[admitted]
            sampling, _ = _sampling(message)
            if _ids(message) != expected["input_ids"]:
                raise ValueError("D12 actual admission token IDs differ from frozen inputs")
            if (sampling["max_tokens"] != expected["max_tokens"]
                    or sampling["temperature"] != expected["temperature"]
                    or sampling["ignore_eos"] is not False or sampling["stop_strs"] != []):
                raise ValueError("D12 actual sampling differs from ordinary replay")
            result = original(message)
            admitted += 1
            return result
        except Exception as exc:
            adapter.record_observer_error(f"D12 frozen input binding failed: {type(exc).__name__}: {exc}")
            raise ServiceCaptureError(str(exc)) from exc

    adapter.admit_user_msg = admit

    def restore():
        if adapter.admit_user_msg is not admit:
            raise RuntimeError("D12 admission guard ownership changed")
        adapter.admit_user_msg = original

    return restore
