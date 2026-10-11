"""Remote CPU-only FILEdry for the sealed R067c packet.

This entry point has no launch, network, GPU, admission, or retry operation.
It only verifies the uploaded packet and materializes per-service files into a
new evidence directory for independent review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys


HERE = Path(__file__).resolve().parent
RID = "E2-R067c-d20-short-tail"
ARTIFACTS = ("t17_d14_startup.py", "t17_d14_exact_ids.py", "t17_d14_observe.py")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")


def verify_packet() -> tuple[dict, dict]:
    config = json.loads((HERE / "R067C_CONFIG_CPU_ONLY.json").read_text())
    manifest = json.loads((HERE / "R067C_CPU_UPLOAD_MANIFEST.json").read_text())
    runner = json.loads((HERE / "R067C_PREPARED_RUNNER_PACKET.json").read_text())
    assert config["rid"] == RID and runner["rid"] == RID
    assert not config["admission"]["admit"] and runner["execution_prohibited"]
    assert config["scope"] == {"services": 10, "generation_calls": 14, "generation_calls_upper": 14}
    assert len(config["services"]) == 10
    assert config["binary_manifest"]["sha256"] == "a8e70aef8a555b86cb9c4bd281d3f98939995cdee4799ff1a4c1368970993a18"
    assert config["binary_manifest"]["forbidden_entries"] == ["row_store"]
    for relative, expected in manifest["files"].items():
        assert sha(HERE / relative) == expected, relative
    return config, manifest


def filedry(out: Path) -> dict:
    config, manifest = verify_packet()
    if out.exists():
        raise RuntimeError(f"fresh FILEdry directory required: {out}")
    out.mkdir(parents=True)
    for service in config["services"]:
        arm = out / "services" / service["name"]
        arm.mkdir(parents=True)
        for artifact_name in ARTIFACTS:
            source = HERE / "tooling" / artifact_name
            assert sha(source) == config["tooling"][artifact_name]
            shutil.copyfile(source, arm / artifact_name)
            (arm / artifact_name).chmod(0o444)
        write_new(arm / "argv.json", service["argv"])
        write_new(arm / "environment.json", service["env"])
        write_new(arm / "no_start.json", {
            "rid": RID, "service": service["name"], "filedry": True,
            "popen": False, "http_generation": False, "gpu_lock_taken": False,
            "service_started": False, "admit": False,
        })
    receipt = {
        "schema": "ft_r067c_remote_filedry/v1", "rid": RID,
        "config_sha256": sha(HERE / "R067C_CONFIG_CPU_ONLY.json"),
        "packet_manifest_sha256": sha(HERE / "R067C_CPU_UPLOAD_MANIFEST.json"),
        "prepared_runner_packet_sha256": sha(HERE / "R067C_PREPARED_RUNNER_PACKET.json"),
        "service_count": len(config["services"]), "generation_calls": 14,
        "materialized_artifact_count": len(config["services"]) * len(ARTIFACTS),
        "output": str(out), "admit": False, "gpu_started": False,
        "service_started": False, "http_generation": False, "gpu_lock_taken": False,
    }
    write_new(out / "R067C_REMOTE_FILEDRY_RECEIPT.json", receipt)
    receipt["receipt_sha256"] = sha(out / "R067C_REMOTE_FILEDRY_RECEIPT.json")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--filedry", action="store_true")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args(argv)
    if args.run:
        raise RuntimeError("--run is prohibited in the R067c CPU validator")
    if not args.filedry or args.out is None:
        parser.error("--filedry and --out are required")
    print(json.dumps(filedry(args.out), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
