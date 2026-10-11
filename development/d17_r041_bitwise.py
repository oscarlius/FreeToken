"""SHA-pinned R041 restore diagnostics. This tool never admits any gate."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import struct

ROLES = ("conv_states", "recurrent_states", "slot:ple_conv", "slot:ple_ngram_ctx")
SAMPLE4 = ("prefix-8192-tail-65", "prefix-12416-tail-4097", "prefix-12736-tail-8193", "prefix-18944-tail-4097")

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def ids_sha(ids):
    if not isinstance(ids, list) or not ids or any(type(x) is not int or not 0 <= x < 2**31 for x in ids):
        raise ValueError("nonempty nonnegative int32 IDs required")
    return hashlib.sha256(struct.pack(f"<{len(ids)}i", *ids)).hexdigest()

def _safe(root, relative):
    root = Path(root)
    if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("unsafe raw path")
    path = root / relative
    for current in [path, *path.parents]:
        if current.is_symlink():
            raise ValueError("symlink evidence is forbidden")
    if not path.is_file() or path.stat().st_mode & 0o222:
        raise ValueError("regular readonly evidence required")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("evidence escapes root")
    return path

def _json(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("evidence object required")
    return value

def load_raw(receipt_path, *, expected_receipt_sha256, manifest_path, manifest_sha256):
    receipt_path, manifest_path = Path(receipt_path), Path(manifest_path)
    root = manifest_path.parent
    manifest_path = _safe(root, manifest_path.name)
    if sha(manifest_path) != manifest_sha256:
        raise ValueError("manifest SHA differs")
    manifest = _json(manifest_path)
    files = manifest.get("files")
    if manifest.get("schema") != "ft_r041_restore_manifest/v1" or not isinstance(files, dict):
        raise ValueError("restore manifest required")
    try:
        relative = receipt_path.relative_to(root).as_posix()
    except ValueError as error:
        raise ValueError("receipt outside manifest root") from error
    receipt_path = _safe(root, relative)
    if files.get(relative) != expected_receipt_sha256 or sha(receipt_path) != expected_receipt_sha256:
        raise ValueError("external receipt SHA differs")
    def pinned(name):
        path = _safe(root, name)
        if files.get(name) != sha(path):
            raise ValueError("manifest payload SHA differs")
        return path
    d = _json(receipt_path)
    if (d.get("schema") != "ft_r041_restore_diagnostic/v1" or d.get("mode") != "restore"
            or d.get("case") not in SAMPLE4 or not isinstance(d.get("rid"), str)
            or re.fullmatch(r"E2-R[0-9]{3}[a-z]?(?:-[A-Za-z0-9-]+)?", d["rid"]) is None
            or not isinstance(d.get("candidate_commit"), str)
            or re.fullmatch(r"[0-9a-f]{40}", d["candidate_commit"]) is None):
        raise ValueError("restore case/RID/candidate binding differs")
    inputs = _json(pinned(d.get("input_path")))
    ids = inputs.get("input_ids")
    if inputs.get("uid") != d.get("uid") or ids_sha(ids) != d.get("input_ids_sha256"):
        raise ValueError("input binding differs")
    length, tail = map(int, re.findall(r"[0-9]+", d["case"]))
    if (len(ids) != length + tail or type(d.get("coordinate")) is not int
            or not 0 < d["coordinate"] <= len(ids)):
        raise ValueError("restore coordinate differs")
    output = _json(pinned(d.get("output_path")))
    tokens = output.get("token_ids")
    token_hash = ids_sha(tokens)
    if len(tokens) != 128 or token_hash != d.get("token_ids_sha256") or not isinstance(output.get("text"), str):
        raise ValueError("128 generated IDs and full text required")
    if output.get("uid") != d.get("uid"):
        raise ValueError("output UID differs")
    process = _json(pinned(d.get("process_path")))
    identity = process.get("process_identity")
    if (not isinstance(identity, dict) or any(type(identity.get(k)) is not int or identity[k] <= 0 for k in ("pid", "start_ticks"))
            or not isinstance(identity.get("execution_id"), str) or not identity["execution_id"]
            or process.get("candidate_commit") != d["candidate_commit"] or process.get("rid") != d["rid"]
            or process.get("case") != d["case"]):
        raise ValueError("physical process binding differs")
    roles = d.get("restore_roles")
    if not isinstance(roles, dict) or set(roles) != set(ROLES):
        raise ValueError("exact four restore roles required")
    paths = {}
    for role in ROLES:
        row = roles[role]
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise ValueError("role receipt differs")
        path = pinned(row["path"])
        if sha(path) != row["sha256"]:
            raise ValueError("role SHA differs")
        paths[role] = path
    if len(set(paths.values())) != 4:
        raise ValueError("role files must be distinct")
    return {"receipt": d, "process_identity": identity, "input_ids": ids,
            "token_ids": tokens, "text": output["text"], "role_paths": paths}

def compare_raw(left_path, right_path, *, left_binding, right_binding):
    a = load_raw(left_path, **left_binding)
    b = load_raw(right_path, **right_binding)
    pa, pb = a["process_identity"], b["process_identity"]
    if (pa["pid"], pa["start_ticks"]) == (pb["pid"], pb["start_ticks"]) or pa["execution_id"] == pb["execution_id"]:
        raise ValueError("independent physical processes required")
    for key in ("case", "coordinate", "input_ids_sha256"):
        if a["receipt"][key] != b["receipt"][key]:
            raise ValueError("cross-arm case/input/coordinate differs")
    import torch
    equal = a["token_ids"] == b["token_ids"] and a["text"] == b["text"]
    roles = {}
    for role in ROLES:
        x = torch.load(a["role_paths"][role], map_location="cpu", weights_only=True)
        y = torch.load(b["role_paths"][role], map_location="cpu", weights_only=True)
        if not isinstance(x, torch.Tensor) or not isinstance(y, torch.Tensor):
            raise ValueError("CPU tensor payload required")
        if not torch.isfinite(x).all().item() or not torch.isfinite(y).all().item():
            raise ValueError("finite state required")
        same = x.dtype == y.dtype and x.shape == y.shape and torch.equal(x.contiguous().view(torch.uint8), y.contiguous().view(torch.uint8))
        roles[role] = bool(same)
        equal = equal and bool(same)
    return {"verdict": "indeterminate", "admitted": False, "bitwise_equal": equal,
            "roles": roles, "reason": "diagnostic only; accepted T17/R041 closures and raw restore provenance remain unverified"}

def evaluate(*args, **kwargs):
    return {"verdict": "indeterminate", "admitted": False, "reason": "summary evidence is never admissible"}
