"""Stage the reviewed inert packet; --ack seals and starts only after user acknowledgement."""
import argparse
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REMOTE = "/data2/FreeToken/development/upstream_oom_pr_20261014"
parser = argparse.ArgumentParser()
parser.add_argument("--ack", help="Exact user acknowledgement received in this chat")
args = parser.parse_args()
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
stamp = datetime.datetime.now().astimezone().isoformat()
auth = json.loads((ROOT / "WINDOW_PROPOSED.json").read_text())
auth.update(authorized=bool(args.ack), recorded_at=stamp,
            independent_controller_review={"verdict": "NO_UNRESOLVED_SOURCE_BLOCKER",
                "path": REMOTE + "/INDEPENDENT_OOM_REVIEW_20261014.md",
                "sha256": sha(ROOT / "INDEPENDENT_OOM_REVIEW_20261014.md")})
approval_path = ROOT / "restore_e3/DEPLOYMENT_APPROVAL.json"
approval = json.loads(approval_path.read_text())
for key in ("window_authorization_sha256", "observation_until", "push_approved", "post_success_test_downtime_approved"):
    approval.pop(key, None)
approval.update(conditions_met=bool(args.ack), recorded_at=stamp,
    user_authority=args.ack or "Pending user acknowledgement for this OOM validation window",
    conditions={"root_final_review": "PASS" if args.ack else "PENDING", "restore_attempts_permitted": 1,
                "same_candidate_retry_permitted": False, "gpu_continuation_permitted": False})
approval_path.write_text(json.dumps(approval, indent=2) + "\n")
if args.ack:
    ack_path = ROOT / "USER_WINDOW_ACKNOWLEDGEMENT.json"
    with ack_path.open("x", encoding="utf-8") as handle:
        json.dump({"at": stamp, "user_reply": args.ack, "services": 3, "calls": 10,
                   "max_pending_http": 2, "worker_replacements": 1, "restore_services": 1,
                   "restore_sdk_calls": 2, "hard_seconds": 2700}, handle, indent=2, ensure_ascii=False)
    review = {"verdict": "PASS", "at": stamp,
              "approval_sha256": sha(approval_path),
              "package_source_manifest_sha256": sha(ROOT / "restore_e3/SOURCE_MANIFEST.json"),
              "source_independent_review_sha256": sha(ROOT / "INDEPENDENT_OOM_REVIEW_20261014.md"),
              "user_acknowledgement_sha256": sha(ack_path)}
    with (ROOT / "restore_e3/ROOT_FINAL_REVIEW.json").open("x") as handle:
        json.dump(review, handle, indent=2)

spec = importlib.util.spec_from_file_location("ops", ROOT.parent / "r067c_retry2_production_control_20261009/ssh_ops.py")
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)
client = ops.connect()
try:
    sftp = client.open_sftp()
    staged = ["gpu_window_oom.py", "gpu_http_check.py", "gpu_fault_probe.py", "recovery_guard.py",
              "INDEPENDENT_OOM_REVIEW_20261014.md", "GPU_CPU_PREFLIGHT.json",
              "candidate_eb9e70f.receipt.json", "candidate_eb9e70f.stdout.log",
              "restore_e3/DEPLOYMENT_APPROVAL.json"]
    if args.ack:
        staged += ["USER_WINDOW_ACKNOWLEDGEMENT.json", "restore_e3/ROOT_FINAL_REVIEW.json"]
    for name in staged:
        path = ROOT / name
        remote = REMOTE + "/" + name
        with sftp.open(remote, "wb") as handle:
            handle.write(path.read_bytes())
        auth["source_sha256_pins"][remote] = sha(path)
    local_auth = ROOT / ("WINDOW_AUTHORIZATION.json" if args.ack else "WINDOW_PROPOSED.json")
    local_auth.write_text(json.dumps(auth, indent=2) + "\n")
    with sftp.open(REMOTE + "/" + local_auth.name, "wx" if args.ack else "wb") as handle:
        handle.write(local_auth.read_bytes())
    sftp.close()
    code = r'''
import importlib.util,json,os,pathlib,subprocess,time
root=pathlib.Path('/data2/FreeToken/development/upstream_oom_pr_20261014')
spec=importlib.util.spec_from_file_location('controller',root/'gpu_window_oom.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
auth=json.loads((root/AUTH_NAME).read_text())
module.verify_pins(auth);package=module.verify_restore_package()
if not auth['authorized']:
 print('INERT_PACKET_SOURCE_VERIFIED; production actions=0')
else:
 module.verify_restore_admission(package)
 active=json.loads(pathlib.Path('/data2/FreeToken/run/production.active.json').read_text())
 assert active==auth['active_snapshot']
 helper_path=pathlib.Path(auth['frozen_ops']['helper_path'])
 helper=module.load_module(helper_path,'frozen_helper')
 assert module.active_owner_is_live(helper,active)
 assert subprocess.check_output(['docker','inspect','-f','{{.State.Running}}','ollama'],text=True).strip()=='false'
 for name in ('GPU_WINDOW_TERMINAL.json','WINDOW_RUN_CONSUMED.json','window.log'):
  assert not (root/name).exists(),name
 env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1')
 with (root/'window.log').open('xb') as log:
  child=subprocess.Popen(['/data2/FreeToken/venv/bin/python','-u',str(root/'gpu_window_oom.py'),'--run'],cwd=root,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 print(json.dumps({'controller_pid':child.pid,'launched_at':time.time(),'authorization':str(root/'WINDOW_AUTHORIZATION.json')}))
'''.replace("AUTH_NAME", repr(local_auth.name))
    ops.run(client, code)
finally:
    client.close()
