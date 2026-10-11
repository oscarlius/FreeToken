"""FILEdry-only materialization for R067c retry1; no --run path exists."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
RID = "E2-R067c-d20-short-tail-retry1"
ARTIFACTS = ("t17_d14_startup.py", "t17_d14_exact_ids.py", "t17_d14_observe.py")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def filedry(out: Path) -> dict:
    config = json.loads((HERE / "RETRY1_CONFIG_CPU_ONLY.json").read_text())
    manifest = json.loads((HERE / "RETRY1_UPLOAD_MANIFEST.json").read_text())
    if out.exists():
        raise RuntimeError("fresh FILEdry output is required")
    assert config["rid"] == RID and not config["admission"]["admit"]
    assert config["retry"]["retry_index"] == 1 and not config["retry"]["automatic_retry"]
    assert config["scope"] == {"services": 10, "generation_calls": 14, "generation_calls_upper": 14}
    for name, digest in manifest["files"].items():
        assert sha(HERE / name) == digest, name
    out.mkdir(parents=True)
    for service in config["services"]:
        arm = out / service["name"]
        arm.mkdir()
        for artifact in ARTIFACTS:
            source = HERE / "tooling" / artifact
            assert sha(source) == config["tooling"][artifact]
            shutil.copyfile(source, arm / artifact)
            (arm / artifact).chmod(0o444)
        (arm / "no_start.json").write_text(json.dumps({"service": service["name"], "popen": False,
            "service_started": False, "http_generation": False, "gpu_started": False, "admit": False}) + "\n")
    receipt = {"schema": "ft_r067c_retry1_filedry/v1", "rid": RID, "output": str(out),
               "services": 10, "calls": 14, "artifacts": 30, "admit": False,
               "gpu_started": False, "service_started": False, "http_generation": False,
               "config_sha256": sha(HERE / "RETRY1_CONFIG_CPU_ONLY.json")}
    (out / "receipt.json").write_text(json.dumps(receipt, sort_keys=True) + "\n")
    receipt["receipt_sha256"] = sha(out / "receipt.json")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--filedry", action="store_true"); parser.add_argument("--out", type=Path); parser.add_argument("--run", action="store_true")
    args = parser.parse_args(argv)
    if args.run:
        raise RuntimeError("--run is prohibited in retry1 CPU validation")
    if not args.filedry or args.out is None:
        parser.error("--filedry and --out are required")
    print(json.dumps(filedry(args.out), sort_keys=True)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
