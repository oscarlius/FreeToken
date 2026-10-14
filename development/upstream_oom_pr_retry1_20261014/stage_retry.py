"""Stage and verify the corrected inert retry packet without controlling production."""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REMOTE = "/data2/FreeToken/development/" + ROOT.name
spec = importlib.util.spec_from_file_location("ops", ROOT.parent / "r067c_retry2_production_control_20261009/ssh_ops.py")
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)
client = ops.connect()
try:
    auth = json.loads((ROOT / "WINDOW_PROPOSED.json").read_text())
    auth["baseline_main_summary"] = auth.pop("reference_main_summary", REMOTE + "/reference_main_SUMMARY.json")
    auth["baseline_main_summary_sha256"] = auth.pop("reference_main_summary_sha256", hashlib.sha256((ROOT / "reference_main_SUMMARY.json").read_bytes()).hexdigest())
    files = ["gpu_window_oom.py", "gpu_http_check.py", "gpu_fault_probe.py", "test_gpu_window_oom.py",
             "test_gpu_fault_probe.py", "recovery_guard.py", "inputs.json", "fault_site/sitecustomize.py",
             "reference_main_SUMMARY.json"]
    files += [path.relative_to(ROOT).as_posix() for path in (ROOT / "restore_e3").iterdir() if path.is_file()]
    sftp = client.open_sftp()
    try:
        sftp.mkdir(REMOTE)
    except OSError:
        sftp.stat(REMOTE)
    for name in files:
        path, remote = ROOT / name, REMOTE + "/" + name
        try:
            sftp.mkdir(remote.rsplit("/", 1)[0])
        except OSError:
            sftp.stat(remote.rsplit("/", 1)[0])
        with sftp.open(remote, "wb") as handle:
            handle.write(path.read_bytes())
        auth["source_sha256_pins"][remote] = hashlib.sha256(path.read_bytes()).hexdigest()
    with sftp.open(REMOTE + "/WINDOW_PROPOSED.json", "wb") as handle:
        handle.write(json.dumps(auth, indent=2).encode())
    sftp.close()
    ops.run(client, r'''
import datetime,hashlib,importlib.util,json,os,pathlib,subprocess
root=pathlib.Path('/data2/FreeToken/development/upstream_oom_pr_retry1_20261014')
auth=json.loads((root/'WINDOW_PROPOSED.json').read_text())
for field in ('main_archive','candidate_archive','old_stop_adapter'):
 path=pathlib.Path(auth[field]);auth['source_sha256_pins'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
shared=root.parent/'upstream_layer_major_pr_20261014'
for name in ('gpu_window_ready.py','gpu_client.py','native_observer.py','recovery_guard.py'):
 path=shared/name;auth['source_sha256_pins'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
helper=pathlib.Path(auth['frozen_ops']['helper_path']);auth['source_sha256_pins'][str(helper)]=hashlib.sha256(helper.read_bytes()).hexdigest()
spec=importlib.util.spec_from_file_location('controller',root/'gpu_window_oom.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.verify_pins(auth);package=m.verify_restore_package();ref=m.load_external_baseline(auth)
assert auth['authorized'] is False
env=dict(os.environ,CUDA_VISIBLE_DEVICES='',PYTHONPATH=str(root),PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
unit=subprocess.run(['/data2/FreeToken/venv/bin/python','-m','unittest','-v','test_gpu_window_oom.py','test_gpu_fault_probe.py'],cwd=root,env=env,capture_output=True,text=True,timeout=60)
assert unit.returncode==0,unit.stdout+unit.stderr
report={'at':datetime.datetime.now().astimezone().isoformat(),'private_unit_exit':unit.returncode,'private_unit_output':unit.stdout+unit.stderr,'source_tree_and_native':'PASS','restore_package':'PASS','baseline_sha256':auth['baseline_main_summary_sha256'],'baseline_lengths':{k:len(v) for k,v in ref.items()},'cuda_visible_devices':'','production_control_actions':0}
(root/'WINDOW_PROPOSED.json').write_text(json.dumps(auth,indent=2))
with (root/'GPU_CPU_PREFLIGHT_CLOSEOUT.json').open('x') as handle:json.dump(report,handle,indent=2)
print(json.dumps(report,indent=2))
''')
    sftp = client.open_sftp()
    for name in ("WINDOW_PROPOSED.json", "GPU_CPU_PREFLIGHT_CLOSEOUT.json"):
        sftp.get(REMOTE + "/" + name, str(ROOT / name))
    sftp.close()
finally:
    client.close()
