"""Build final R067c retry2 CPU packet, correcting retry1's stale argv digests."""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "r067c_retry1_short_tail_v1"
RID1 = "E2-R067c-d20-short-tail-retry1"
RID2 = "E2-R067c-d20-short-tail-retry2"
ARTIFACTS = ("t17_d14_startup.py", "t17_d14_exact_ids.py", "t17_d14_observe.py")

def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def write_json(path: Path, value: object) -> None: path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")

def replace(value):
    if isinstance(value, dict): return {k: replace(v) for k, v in value.items()}
    if isinstance(value, list): return [replace(v) for v in value]
    return value.replace(RID1, RID2) if isinstance(value, str) else value

def copy_tooling() -> dict[str, str]:
    target = HERE / "tooling"; target.mkdir(exist_ok=True); hashes = {}
    for name in ARTIFACTS:
        source, destination = PREVIOUS / "tooling" / name, target / name
        if destination.exists():
            if sha(source) != sha(destination): raise RuntimeError(f"frozen tooling differs: {name}")
        else:
            shutil.copyfile(source, destination); destination.chmod(0o444)
        hashes[name] = sha(destination)
    return hashes

def packet_files() -> dict[str, str]:
    return {p.relative_to(HERE).as_posix(): sha(p) for p in sorted(HERE.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts and p.name not in {"RETRY2_UPLOAD_MANIFEST.json", "RETRY2_CPU_FILEDRY_RECEIPT.json"}}

def main() -> None:
    tooling = copy_tooling()
    config = replace(copy.deepcopy(json.loads((PREVIOUS / "RETRY1_CONFIG_CPU_ONLY.json").read_text())))
    config.update({
        "schema": "ft_r067c_retry2_cpu_packet/v1", "rid": RID2,
        "retry": {"retry_index": 2, "retry_of": RID1,
                  "prior_terminal": "/data2/FreeToken/runs/dev_R067/E2-R067c-d20-short-tail-retry1/terminal.json",
                  "prior_terminal_sha256": "314f01f9b35c9c23f5908b7c5dabec1155c1eadb64a39fc5f29fe3ad62fea3c2",
                  "classification": "failed_harness", "automatic_retry": False,
                  "last_allowed_retry": True, "max_failed_harness_retries": 2,
                  "root_shared_retry_ledger": "/data2/FreeToken/development/r067c_production_control_20261009/ROOT_ATTEMPT_LEDGER.jsonl"},
        "admission": {"admit": False, "state": "pending_root_review_and_admission"}, "tooling": tooling,
        "retry2_fix": {"scope": "all ten argv_sha256 fields only", "cause": "retry1 replaced service paths after inherited digests were frozen",
                       "algorithm": "d07.argv_sha256: sha256(json.dumps(argv,separators=(',',':')).encode())"},
    })
    for service in config["services"]:
        service["argv_sha256"] = hashlib.sha256(json.dumps(service["argv"], separators=(",", ":")).encode()).hexdigest()
    config_path = HERE / "RETRY2_CONFIG_CPU_ONLY.json"; write_json(config_path, config); config_sha = sha(config_path)
    prior = json.loads((PREVIOUS / "RETRY1_PREPARED_RUNNER_PACKET.json").read_text())
    def retarget(source: str) -> str:
        source = (source.replace(RID1, RID2).replace("/development/r067c_retry1_short_tail_v1/", "/development/r067c_retry2_short_tail_v1/")
                  .replace("RETRY1_CONFIG_CPU_ONLY.json", "RETRY2_CONFIG_CPU_ONLY.json").replace("RETRY1_ROOT_STARTUP_ADMISSION.json", "RETRY2_ROOT_STARTUP_ADMISSION.json"))
        return re.sub(r"assert sha\(FD\)=='[0-9a-f]{64}'", f"assert sha(FD)=='{config_sha}'", source)
    child, parent = retarget(prior["child_source"]), retarget(prior["parent_tail"])
    lock = "owner=d07.take_d07_gpu_lock(RID,batch);d07.require_gpu_idle()"
    preflight = f"""for service in fd['services']:
  arm=RUN/'services'/service['name'];assert Path(service['service_dir'])==arm and Path(service['cwd'])==arm
  assert service['argv'][5]==str(arm/'t17_d14_startup.py') and d07.argv_sha256(service['argv'])==service['argv_sha256']
  assert '{RID1}' not in json.dumps((service['argv'],service['env']),sort_keys=True)
  for key in ('FT_DEV_STATE_DUMP','FT_T17_INPUT_RECEIPTS','FT_T17_OBSERVATIONS','PYTHONPATH'):assert str(arm) in service['env'][key]
 owner=d07.take_d07_gpu_lock(RID,batch);d07.require_gpu_idle()"""
    if child.count(lock) != 1: raise RuntimeError("GPU lock seam differs")
    child = child.replace(lock, preflight)
    ast.parse(child.replace("__ADMISSION_SHA256__", "0" * 64)); ast.parse(parent.replace("__ADMISSION_SHA256__", "0" * 64))
    assert "d07.argv_sha256(service['argv'])==service['argv_sha256']" in child
    packet = {"schema": "ft_r067c_retry2_prepared_runner/v1", "rid": RID2, "execution_prohibited": True,
              "config_sha256": config_sha, "child_source": child, "parent_tail": parent,
              "cause": config["retry2_fix"]["cause"], "fix": config["retry2_fix"]}
    write_json(HERE / "RETRY2_PREPARED_RUNNER_PACKET.json", packet)
    write_json(HERE / "RETRY2_ROOT_EXECUTION_CONFIG.json", {"schema": "ft_r067c_retry2_root_placeholder/v1", "rid": RID2,
        "must_not_run": True, "config_sha256": config_sha, "runner_sha256": sha(HERE / "RETRY2_PREPARED_RUNNER_PACKET.json"),
        "expected_admission": "/data2/FreeToken/development/r067c_retry2_short_tail_v1/RETRY2_ROOT_STARTUP_ADMISSION.json",
        "requires": ["root review", "fresh FILEdry", "shared ledger permits final retry", "signed FD/ADMIT"]})
    write_json(HERE / "RETRY2_UPLOAD_MANIFEST.json", {"schema": "ft_r067c_retry2_upload_manifest/v1", "rid": RID2,
        "remote_directory": "/data2/FreeToken/development/r067c_retry2_short_tail_v1", "files": packet_files(), "execution_prohibited": True})

if __name__ == "__main__": main()
