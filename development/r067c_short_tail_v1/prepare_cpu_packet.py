"""Materialize the R067c CPU-only packet. This program never starts a service."""
from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "r067b_short_tail_v1"
RID = "E2-R067c-d20-short-tail"
RUN = f"/data2/FreeToken/runs/dev_R067/{RID}"
MANIFEST = "/data2/FreeToken/runs/dev_release/release_e2_ops_v8_20261009_smoke_guarded/source/development/release_e2_ops_v2/binary_manifest.json"
MANIFEST_SHA256 = "a8e70aef8a555b86cb9c4bd281d3f98939995cdee4799ff1a4c1368970993a18"
CPU_MOE_SHA256 = "10a2bd8311b9569bd03a6569db59da707699a44e67d7b677c35c3547d77855b4"
PINNED_SHA256 = "07701be28030c4ebf63c210804b6eba2556cc0f4d2f1e5ed80b9d423ebfe7e68"
PRODUCTION_PORTS = (8095, 8096)
ARTIFACTS = ("t17_d14_startup.py", "t17_d14_exact_ids.py", "t17_d14_observe.py")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace(value):
    if isinstance(value, dict):
        return {key: replace(item) for key, item in value.items()}
    if isinstance(value, list):
        return [replace(item) for item in value]
    if isinstance(value, str):
        return (value.replace("E2-R067b", RID)
                     .replace("r067b_short_tail_v1", "r067c_short_tail_v1"))
    return value


def materialization_source() -> str:
    return """from pathlib import Path
import hashlib
import json
import shutil

CONFIG = Path('/data2/FreeToken/development/r067c_short_tail_v1/R067C_CONFIG_CPU_ONLY.json')
TOOLING = Path('/data2/FreeToken/development/r067c_short_tail_v1/tooling')
PRODUCTION_PORTS = {8095, 8096}
ARTIFACTS = ('t17_d14_startup.py', 't17_d14_exact_ids.py', 't17_d14_observe.py')
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
config = json.loads(CONFIG.read_text())
assert config['rid'] == 'E2-R067c-d20-short-tail'
assert config['admission']['admit'] is False
assert config['scope'] == {'services': 10, 'generation_calls': 14, 'generation_calls_upper': 14}
assert sha(TOOLING/'t17_d14_startup.py') == config['tooling']['t17_d14_startup.py']
for service in config['services']:
    assert service['port_pair']['api'] not in PRODUCTION_PORTS
    assert service['port_pair']['tcpstore'] not in PRODUCTION_PORTS
    arm = Path(service['service_dir'])
    for artifact_name in ARTIFACTS:
        shutil.copyfile(TOOLING/artifact_name, arm/artifact_name)
        (arm/artifact_name).chmod(0o444)
"""


def prepared_runner_packet(config_sha256: str) -> dict:
    """Bind the reviewed R067b-v2 controller source without admitting it.

    This deliberately creates an inspectable sealed source packet instead of
    invoking it.  Root must replace the two signed placeholders only after the
    later remote FILEdry and independent startup review.
    """
    source = json.loads((SOURCE / "R067B_COMMAND_TEMPLATE_V2_CPU_ONLY.json").read_text())

    def retarget(text: str) -> str:
        return (text.replace("E2-R067b", RID)
                    .replace("r067b_short_tail_v1", "r067c_short_tail_v1")
                    .replace("R067B_CONFIG.json", "R067C_CONFIG_CPU_ONLY.json")
                    .replace("R067B_ROOT_STARTUP_ADMISSION.json", "R067C_ROOT_STARTUP_ADMISSION.json")
                    .replace("release_e2_ops_v5_20261009_review", "release_e2_ops_v8_20261009_smoke_guarded"))

    child = retarget(source["child_source"])
    parent_tail = retarget(source["parent_tail"])
    child = child.replace("assert sha(FD)=='cec8abe8a5bde97928fb4a644319a75834f16bb82117eeee08db65c14af9bb01'",
                          f"assert sha(FD)=='{config_sha256}'")
    parent_tail = parent_tail.replace("assert sha(FD)=='cec8abe8a5bde97928fb4a644319a75834f16bb82117eeee08db65c14af9bb01'",
                                      f"assert sha(FD)=='{config_sha256}'")
    ast.parse(child.replace("__ADMISSION_SHA256__", "0" * 64))
    ast.parse(parent_tail.replace("__ADMISSION_SHA256__", "0" * 64))
    assert "for name in" not in child
    assert "for artifact_name in" in child
    return {
        "schema": "ft_r067c_prepared_runner_packet/v1",
        "rid": RID,
        "status": "prepared_but_execution_prohibited",
        "execution_prohibited": True,
        "source_origin": "E2-R067b corrected V2 controller; retargeted only for R067c paths and frozen v8 manifest",
        "config_sha256": config_sha256,
        "child_source": child,
        "parent_tail": parent_tail,
        "required_root_gates": [
            "R045 sequence permits R067c",
            "fresh remote FILEdry proof bound to this packet",
            "independent startup review",
            "signed FD and ADMIT SHA bindings",
            "root-owned production stop and post-round restoration plan",
        ],
        "runtime_contract": {
            "scope": {"services_max": 10, "generation_calls_max": 14},
            "cold_ab_difference": "failed_harness; controller stops first divergence; root may create at most two new tooling retry rounds",
            "hot_difference_after_equal_ab": "not_met; controller stops at first differing token; root restores production",
            "owned_service_cleanup": "controller stops each owned service and releases its GPU lock before terminal receipt",
            "production_restore": "root-owned operation; not executed by this packet",
        },
    }


def build_config() -> dict:
    source = json.loads((SOURCE / "R067B_CONFIG.json").read_text())
    inherited_cpu_proof = copy.deepcopy(source["cpu_file_dry_proof"])
    config = replace(copy.deepcopy(source))
    config.update({
        "schema": "ft_r067c_cpu_only_packet/v1",
        "rid": RID,
        "admission_state": "pending_stop_approval_and_independent_startup_review",
        "separate_round": True,
        "not_a_replay_or_residual_of": "E2-R067b",
        "binary_manifest": {
            "path": MANIFEST,
            "sha256": MANIFEST_SHA256,
            "required_entries": {"cpu_moe": CPU_MOE_SHA256, "pinned": PINNED_SHA256},
            "forbidden_entries": ["row_store"],
            "remote_validation": "pending_root_remote_validation",
        },
        "admission": {
            "admit": False,
            "state": "pending_stop_approval_and_independent_startup_review",
            "required_before_execution": [
                "R045 sequence permits R067c and root-owned production stop/restore is active",
                "independent startup review",
                "root remote binary-manifest and worktree validation",
                "fresh file-dry proof and signed FD/ADMIT SHA bindings",
            ],
        },
        "execution_contract": {
            "hot": "481 P8192/P8256 seed then tails T1/T64",
            "cold": "eight fresh D20 d50be0 A/B services; one-shot donor [0,P+1), rewind P, ordinary [P,P+T)",
            "cold_ab_difference": "failed_harness; maximum two root-controlled tooling retry rounds",
            "equal_ab_hot_difference": "not_met; stop first divergence then root restores production",
        },
        "root_retry_ledger": {
            "path": "/data2/FreeToken/development/r067c_short_tail_v1/R067C_ROOT_RETRY_LEDGER_TEMPLATE.json",
            "sha256": sha(HERE / "R067C_ROOT_RETRY_LEDGER_TEMPLATE.json"),
            "owner": "root",
            "automatic_retry": False,
            "maximum_failed_harness_retries_across_r067c_rounds": 2,
            "not_met": "terminal_no_retry_root_restores_production",
        },
        "remote_proof": {"status": "pending_root_remote_validation", "fabricated": False},
        "tooling": {artifact: sha(HERE / "tooling" / artifact) for artifact in ARTIFACTS},
        "cpu_file_dry_proof": {
            "inherited_unchanged_tooling_proof": {
                "from_rid": "E2-R067b", "new_r067c_signature": False,
                "note": "Historical CPU evidence retained for unchanged tooling only; it is not R067c remote validation.",
            },
            "schedule_parse_admit": inherited_cpu_proof["schedule_parse_admit"],
            "startup_spawn": inherited_cpu_proof["startup_spawn"],
            "local_packet": {
                "status": "materialized_locally", "gpu_started": False,
                "service_started": False, "http_generation": False,
                "checks": ["AST materialization", "ten services", "fourteen calls", "production ports excluded"],
            },
            "remote_file_dry": {"status": "pending_root_remote_validation", "fabricated": False},
        },
        "cpu_validation": {
            "local_status": "materialized_only",
            "remote_status": "pending_root_remote_validation",
            "no_gpu": True, "no_service": True, "no_http_generation": True,
        },
    })
    config.pop("retry_of", None)
    config.pop("retry_index", None)
    config["worktree_binding"]["hot"]["commit"] = "481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9"
    config["worktree_binding"]["cold"]["commit"] = "d50be0f8f84ab1105f788be8f1354773ad539b63"
    for service in config["services"]:
        service["service_dir"] = service["service_dir"].replace("E2-R067b", RID)
        service["cwd"] = service["cwd"].replace("E2-R067b", RID)
        service["argv_sha256"] = hashlib.sha256(
            json.dumps(service["argv"], separators=(",", ":")).encode()
        ).hexdigest()
        assert service["port_pair"]["api"] not in PRODUCTION_PORTS
        assert service["port_pair"]["tcpstore"] not in PRODUCTION_PORTS
    assert len(config["services"]) == 10
    assert config["scope"] == {"services": 10, "generation_calls": 14, "generation_calls_upper": 14}
    return config


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def upload_manifest() -> dict:
    """Return the exact non-cache packet files eligible for a new remote directory."""
    files = {}
    for path in sorted(HERE.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if path.name in {"R067C_CPU_UPLOAD_MANIFEST.json", "R067C_CPU_UPLOAD_RECEIPT.json",
                         "R067C_CPU_FILEDRY_EXECUTION_RECEIPT.json"}:
            continue
        files[path.relative_to(HERE).as_posix()] = sha(path)
    return {
        "schema": "ft_r067c_cpu_upload_manifest/v1",
        "rid": RID,
        "remote_directory": "/data2/FreeToken/development/r067c_short_tail_v1",
        "files": files,
        "upload_is_not_remote_filedry": True,
    }


def main() -> None:
    config = build_config()
    config_path = HERE / "R067C_CONFIG_CPU_ONLY.json"
    write_json(config_path, config)
    source = materialization_source()
    ast.parse(source)
    template = {
        "schema": "ft_r067c_cpu_only_materialization_template/v1",
        "rid": RID,
        "admission": "not_admitted",
        "execution_prohibited": True,
        "allowed_action": "root-only remote file-dry materialization after approval gates",
        "materialization_source": source,
        "config_sha256": sha(config_path),
        "forbidden_operations": ["Popen", "HTTP generation", "GPU lock", "service stop", "deployment", "push"],
    }
    write_json(HERE / "R067C_COMMAND_TEMPLATE_CPU_ONLY.json", template)
    runner_packet = prepared_runner_packet(sha(config_path))
    write_json(HERE / "R067C_PREPARED_RUNNER_PACKET.json", runner_packet)
    write_json(HERE / "R067C_ROOT_EXECUTION_COMMAND_CONFIG.json", {
        "schema": "ft_r067c_root_execution_placeholder/v1", "rid": RID,
        "admission": "pending_stop_approval_and_independent_startup_review",
        "fd_sha256": "__PENDING_SIGNED_FD_SHA256__",
        "admit_sha256": "__PENDING_SIGNED_ADMIT_SHA256__",
        "must_not_run": True,
        "root_only_after_all_gates": "__ROOT_ONLY_AFTER_R045_FILEDRY_REVIEW_AND_PRODUCTION_RESTORE_PLAN__",
        "config_sha256": sha(config_path),
        "prepared_runner_packet_sha256": sha(HERE / "R067C_PREPARED_RUNNER_PACKET.json"),
        "cpu_validator_sha256": sha(HERE / "r067c_cpu_validate.py"),
        "root_retry_ledger_template_sha256": sha(HERE / "R067C_ROOT_RETRY_LEDGER_TEMPLATE.json"),
    })
    write_json(HERE / "CPU_PREPARATION_PROOF.json", {
        "schema": "ft_r067c_cpu_preparation_proof/v1", "rid": RID,
        "config_sha256": sha(config_path),
        "template_sha256": sha(HERE / "R067C_COMMAND_TEMPLATE_CPU_ONLY.json"),
        "prepared_runner_packet_sha256": sha(HERE / "R067C_PREPARED_RUNNER_PACKET.json"),
        "cpu_validator_sha256": sha(HERE / "r067c_cpu_validate.py"),
        "root_retry_ledger_template_sha256": sha(HERE / "R067C_ROOT_RETRY_LEDGER_TEMPLATE.json"),
        "remote_proof": "pending_root_remote_validation", "gpu_started": False,
        "service_started": False, "http_generation": False, "admit": False,
    })
    # The proof is written first so the upload manifest can hash it without a
    # recursive proof/manifest hash dependency.
    write_json(HERE / "R067C_CPU_UPLOAD_MANIFEST.json", upload_manifest())


if __name__ == "__main__":
    main()
