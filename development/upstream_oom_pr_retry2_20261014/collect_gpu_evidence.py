"""Copy terminal window and restoration evidence without changing remote artifacts."""
import hashlib
import importlib.util
import json
from pathlib import Path
import stat

ROOT = Path(__file__).resolve().parent
REMOTE = "/data2/FreeToken/development/" + ROOT.name
OUT = ROOT / "gpu_evidence"
OUT.mkdir(exist_ok=True)
spec = importlib.util.spec_from_file_location("ops", ROOT.parent / "r067c_retry2_production_control_20261009/ssh_ops.py")
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)
client = ops.connect()
manifest = {}
try:
    sftp = client.open_sftp()

    def copy(remote, local):
        local.parent.mkdir(parents=True, exist_ok=True)
        sftp.get(remote, str(local))
        manifest[remote] = {"local": local.relative_to(OUT).as_posix(),
                           "sha256": hashlib.sha256(local.read_bytes()).hexdigest()}

    def tree(remote, local):
        for entry in sftp.listdir_attr(remote):
            if stat.S_ISDIR(entry.st_mode):
                tree(remote + "/" + entry.filename, local / entry.filename)
            elif stat.S_ISREG(entry.st_mode):
                copy(remote + "/" + entry.filename, local / entry.filename)

    for name in ("GPU_WINDOW_TERMINAL.json", "window.log", "stop_e3.log", "restore_start.log",
                 "restore_smoke.log", "WINDOW_AUTHORIZATION.json", "WINDOW_RUN_CONSUMED.json"):
        copy(REMOTE + "/" + name, OUT / name)
    for name in ("window_events.jsonl", "WINDOW_PHASE_ERROR.json"):
        try:
            sftp.stat(REMOTE + "/" + name)
        except FileNotFoundError:
            continue
        copy(REMOTE + "/" + name, OUT / name)
    tree(REMOTE + "/gpu_results", OUT / "gpu_results")
    copy("/data2/FreeToken/run/production.active.json", OUT / "production.active.json")
    active = json.loads((OUT / "production.active.json").read_text())
    for name in ("owner.json", "smoke_execution_result.json", "smoke_invocation.json", "serve.log",
                 "deployment_approval.json", "root_final_review.json", "serving_ready.json"):
        copy(active["run_dir"] + "/" + name, OUT / "restored_production" / name)
    tree(active["run_dir"] + "/smoke_first", OUT / "restored_production/smoke_first")
    sftp.close()
finally:
    client.close()
with (OUT / "DOWNLOAD_MANIFEST.json").open("x") as handle:
    json.dump(manifest, handle, indent=2)
print(json.dumps({"files": len(manifest), "out": str(OUT), "terminal":
                  json.loads((OUT / "GPU_WINDOW_TERMINAL.json").read_text())}, indent=2))
