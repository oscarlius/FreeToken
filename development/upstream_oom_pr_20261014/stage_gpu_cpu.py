"""Stage task-owned private files and run read-only, CUDA-hidden preflight."""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REMOTE = "/data2/FreeToken/development/upstream_oom_pr_20261014"
spec = importlib.util.spec_from_file_location("ops", ROOT.parent / "r067c_retry2_production_control_20261009/ssh_ops.py")
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)
client = ops.connect()
try:
    sftp = client.open_sftp()
    previous_path = "/data2/FreeToken/development/upstream_layer_major_pr_20261014/WINDOW_AUTHORIZATION.json"
    with sftp.open(previous_path) as handle:
        previous = json.load(handle)
    (ROOT / "PREVIOUS_WINDOW_SCOPE_READONLY.json").write_text(json.dumps(previous, indent=2))
    pins = {}
    files = ["gpu_window_oom.py", "gpu_http_check.py", "gpu_fault_probe.py", "test_gpu_fault_probe.py",
             "test_gpu_window_oom.py", "cpu_spawn_probe.py", "recovery_guard.py", "inputs.json",
             "fault_site/sitecustomize.py"]
    files += [path.relative_to(ROOT).as_posix() for path in (ROOT / "restore_e3").iterdir() if path.is_file()]
    for name in files:
        local = ROOT / name
        target = REMOTE + "/" + name
        parent = str(Path(target).parent).replace("\\", "/")
        try:
            sftp.mkdir(parent)
        except OSError:
            sftp.stat(parent)
        with sftp.open(target, "wb") as handle:
            handle.write(local.read_bytes())
        pins[target] = hashlib.sha256(local.read_bytes()).hexdigest()
    proposal = {
        "authorized": False,
        "independent_controller_review": None,
        "window_seconds": 2700,
        "measurement_seconds": 600,
        "test_python": "/data2/FreeToken/development/upstream_layer_major_pr_20261014/main-venv/bin/python",
        "active_snapshot": json.loads((ROOT / "ACTIVE_SNAPSHOT.json").read_text()),
        "frozen_ops": previous["frozen_ops"],
        "old_stop_adapter": "/data2/FreeToken/development/upstream_layer_major_pr_20261014/restore_e3/stop_approved_restore.py",
        "main_source": REMOTE + "/baseline_f02fbb1",
        "main_archive": REMOTE + "/baseline_f02fbb1.zip",
        "main_commit": "f02fbb16a213f5c81094e4017c988d41f0164141",
        "candidate_source": REMOTE + "/candidate_eb9e70f",
        "candidate_archive": REMOTE + "/candidate_eb9e70f.zip",
        "candidate_commit": "eb9e70f30ed7a714ce9918ff905e86d2628bc126",
        "native_modules": json.loads((ROOT / "NATIVE_BUILD.json").read_text())["native"],
        "source_sha256_pins": pins,
    }
    (ROOT / "WINDOW_PROPOSED.json").write_text(json.dumps(proposal, indent=2))
    with sftp.open(REMOTE + "/WINDOW_PROPOSED.json", "wb") as handle:
        handle.write((ROOT / "WINDOW_PROPOSED.json").read_bytes())
    sftp.close()
    ops.run(client, r'''
import datetime,hashlib,importlib.util,json,os,pathlib,shutil,subprocess
root=pathlib.Path('/data2/FreeToken/development/upstream_oom_pr_20261014')
auth=json.loads((root/'WINDOW_PROPOSED.json').read_text())
for name,digest in auth['native_modules'].items():
 source=pathlib.Path(auth['main_source'])/name; target=pathlib.Path(auth['candidate_source'])/name
 assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
 if target.exists():assert target.read_bytes()==source.read_bytes()
 else:shutil.copyfile(source,target)
def module(path,name):
 spec=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
controller=module(root/'gpu_window_oom.py','controller')
controller.verify_pins(auth)
package=controller.verify_restore_package()
approval=json.loads((package/'DEPLOYMENT_APPROVAL.json').read_text())
module(root/'recovery_guard.py','guard').verify_sources(approval)
assert auth['authorized'] is False and approval['conditions_met'] is False
env=dict(os.environ,CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(root),OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',HF_HUB_OFFLINE='1')
for key in list(env):
 if key.startswith(('FT_','RELEASE_SMOKE_')):env.pop(key)
unit=subprocess.run(['/data2/FreeToken/venv/bin/python','-m','unittest','-v','test_gpu_fault_probe.py','test_gpu_window_oom.py'],cwd=root,env=env,capture_output=True,text=True,timeout=60)
assert unit.returncode==0,unit.stdout+unit.stderr
env.update(PYTHONPATH=':'.join((str(root/'fault_site'),str(root),auth['candidate_source']+'/python')),FT_PR_OOM_ARTIFACTS=str(root/'cpu_hook_probe'),FT_PR_OOM_INJECT='1')
probe=subprocess.run([auth['test_python'],str(root/'cpu_spawn_probe.py')],cwd=root,env=env,capture_output=True,text=True,timeout=120)
assert probe.returncode==0,probe.stdout+probe.stderr
report={'at':datetime.datetime.now().astimezone().isoformat(),'native_copy_and_import_tree':'PASS','restore_source_guard':'PASS','private_unit_exit':unit.returncode,'private_unit_output':unit.stdout+unit.stderr,'spawn_hook_exit':probe.returncode,'spawn_hook_output':probe.stdout+probe.stderr,'cuda_visible_devices':'','production_control_actions':0}
for name in (auth['main_archive'],auth['candidate_archive']):
 auth['source_sha256_pins'][name]=hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest()
shared=root.parent/'upstream_layer_major_pr_20261014'
for name in ('gpu_window_ready.py','gpu_client.py','native_observer.py'):
 path=shared/name;auth['source_sha256_pins'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
helper=pathlib.Path(auth['frozen_ops'].get('helper_path') or pathlib.Path(auth['frozen_ops']['path']).parent/'d07_g3g4_prepare.py')
auth['frozen_ops']['helper_path']=str(helper)
auth['source_sha256_pins'][str(helper)]=hashlib.sha256(helper.read_bytes()).hexdigest()
stop=pathlib.Path(auth['old_stop_adapter']);auth['source_sha256_pins'][str(stop)]=hashlib.sha256(stop.read_bytes()).hexdigest()
(root/'WINDOW_PROPOSED.json').write_text(json.dumps(auth,indent=2))
with (root/'GPU_CPU_PREFLIGHT.json').open('x') as handle:json.dump(report,handle,indent=2)
print(json.dumps(report,indent=2))
''')
    sftp = client.open_sftp()
    for name in ("WINDOW_PROPOSED.json", "GPU_CPU_PREFLIGHT.json"):
        sftp.get(REMOTE + "/" + name, str(ROOT / name))
    sftp.close()
finally:
    client.close()
