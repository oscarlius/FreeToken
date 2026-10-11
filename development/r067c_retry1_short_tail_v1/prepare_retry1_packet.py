"""Build the non-admitted R067c retry-1 CPU packet; it never launches a process."""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
from pathlib import Path
import shutil


HERE = Path(__file__).resolve().parent
ORIGINAL = HERE.parent / "r067c_short_tail_v1"
RID0 = "E2-R067c-d20-short-tail"
RID = "E2-R067c-d20-short-tail-retry1"
ARTIFACTS = ("t17_d14_startup.py", "t17_d14_exact_ids.py", "t17_d14_observe.py")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def replace(value):
    if isinstance(value, dict):
        return {key: replace(item) for key, item in value.items()}
    if isinstance(value, list):
        return [replace(item) for item in value]
    return value.replace(RID0, RID) if isinstance(value, str) else value


def copy_tooling() -> dict[str, str]:
    target = HERE / "tooling"
    target.mkdir(exist_ok=True)
    hashes = {}
    for name in ARTIFACTS:
        source = ORIGINAL / "tooling" / name
        destination = target / name
        if destination.exists():
            if sha(destination) != sha(source):
                raise RuntimeError(f"frozen retry tooling differs: {destination}")
        else:
            shutil.copyfile(source, destination)
            destination.chmod(0o444)
        hashes[name] = sha(destination)
    return hashes


def patch_geometry(source: str) -> str:
    old = ("valid_geometry=valid_geometry and sum(r['new_tokens'] for r in rows)==(tail if expected else len(ids)) "
           "and sum(r['new_sequences'] for r in rows)==1")
    new = ("valid_geometry=valid_geometry and sum(r['new_tokens'] for r in rows)==(tail if expected else len(ids)) "
           "and all(r['new_sequences']==1 for r in rows)\n"
           "    valid_geometry=valid_geometry and raw['response']['usage']['prompt_tokens']==len(ids) and window.count(b'POST /internal/t17/exact-ids HTTP/1.1\" 200 OK')==1")
    if source.count(old) != 1:
        raise RuntimeError("expected original single-request geometry predicate once")
    return source.replace(old, new)


def packet_files() -> dict[str, str]:
    excluded = {"RETRY1_UPLOAD_MANIFEST.json", "RETRY1_CPU_FILEDRY_RECEIPT.json"}
    return {path.relative_to(HERE).as_posix(): sha(path)
            for path in sorted(HERE.rglob("*"))
            if path.is_file() and "__pycache__" not in path.parts and path.name not in excluded}


def main() -> None:
    tooling = copy_tooling()
    original_config = json.loads((ORIGINAL / "R067C_CONFIG_CPU_ONLY.json").read_text())
    config = replace(copy.deepcopy(original_config))
    config.update({
        "schema": "ft_r067c_retry1_cpu_packet/v1",
        "rid": RID,
        "retry": {
            "retry_index": 1,
            "retry_of": RID0,
            "prior_terminal": str(ORIGINAL / "raw_evidence" / RID0 / "terminal.json"),
            "prior_terminal_sha256": "37760091fb935714606713e9e0628d84ddd26adc881f9333b50b2b9e4f8bd3ab",
            "classification": "failed_harness",
            "root_shared_retry_ledger": "/data2/FreeToken/development/r067c_production_control_20261009/ROOT_ATTEMPT_LEDGER.jsonl",
            "max_failed_harness_retries": 2,
            "automatic_retry": False,
        },
        "admission": {"admit": False, "state": "pending_root_r045_restore_and_independent_review"},
        "cpu_validation": {"local_status": "prepared", "remote_status": "pending", "no_gpu": True,
                           "no_service": True, "no_http_generation": True},
        "geometry_fix": {
            "scope": "controller logging predicate only",
            "from": "sum prefill-row new_sequences equals one",
            "to": "each prefill row represents the same logical request and has new_sequences equals one",
            "retained": ["sum new_tokens", "cached-token equality", "API usage validation", "request_evidence UID/input/observation association"],
        },
        "tooling": tooling,
    })
    config["root_retry_ledger"] = {
        "path": "/data2/FreeToken/development/r067c_production_control_20261009/ROOT_ATTEMPT_LEDGER.jsonl",
        "owner": "root", "retry1_does_not_reset_or_copy_the_ledger": True,
    }
    config_path = HERE / "RETRY1_CONFIG_CPU_ONLY.json"
    write_json(config_path, config)
    config_sha = sha(config_path)

    original_packet = json.loads((ORIGINAL / "R067C_PREPARED_RUNNER_PACKET.json").read_text())
    def retarget(source: str) -> str:
        source = (source.replace(RID0, RID)
                    .replace("/development/r067c_short_tail_v1/", "/development/r067c_retry1_short_tail_v1/")
                    .replace("R067C_CONFIG_CPU_ONLY.json", "RETRY1_CONFIG_CPU_ONLY.json")
                    .replace("R067C_ROOT_STARTUP_ADMISSION.json", "RETRY1_ROOT_STARTUP_ADMISSION.json"))
        source = re.sub(r"assert sha\(FD\)=='[0-9a-f]{64}'", f"assert sha(FD)=='{config_sha}'", source)
        return source
    child = patch_geometry(retarget(original_packet["child_source"]))
    parent = retarget(original_packet["parent_tail"])
    ast.parse(child.replace("__ADMISSION_SHA256__", "0" * 64))
    ast.parse(parent.replace("__ADMISSION_SHA256__", "0" * 64))
    assert "sum(r['new_sequences'] for r in rows)==1" not in child
    assert "all(r['new_sequences']==1 for r in rows)" in child
    packet = {
        "schema": "ft_r067c_retry1_prepared_runner/v1", "rid": RID,
        "execution_prohibited": True, "status": "prepared_cpu_only",
        "config_sha256": config_sha, "child_source": child, "parent_tail": parent,
        "cause": "failed_harness: a segmented seed request emitted two prefill log rows, each reporting the same one logical sequence",
        "fix": config["geometry_fix"],
    }
    write_json(HERE / "RETRY1_PREPARED_RUNNER_PACKET.json", packet)
    write_json(HERE / "RETRY1_ROOT_EXECUTION_CONFIG.json", {
        "schema": "ft_r067c_retry1_root_placeholder/v1", "rid": RID, "must_not_run": True,
        "config_sha256": config_sha, "runner_sha256": sha(HERE / "RETRY1_PREPARED_RUNNER_PACKET.json"),
        "root_shared_retry_ledger": config["retry"]["root_shared_retry_ledger"],
        "requires": ["R045 restore passes", "root ledger permits retry1", "fresh FILEdry", "independent review", "signed FD/ADMIT"],
    })
    write_json(HERE / "RETRY1_UPLOAD_MANIFEST.json", {
        "schema": "ft_r067c_retry1_upload_manifest/v1", "rid": RID,
        "remote_directory": "/data2/FreeToken/development/r067c_retry1_short_tail_v1",
        "files": packet_files(), "execution_prohibited": True,
    })


if __name__ == "__main__":
    main()
