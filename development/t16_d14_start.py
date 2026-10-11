"""Launch the reviewed D14 stage and retain its authoritative process receipt."""
import hashlib
import json
from pathlib import Path
import subprocess
import re
import shlex

HERE = Path(__file__).resolve().parent
cpu = json.loads((HERE / "t16_d14_cpu_receipt.json").read_text(encoding="utf-8"))
stage = cpu["stage"]
if not re.fullmatch(r"/data2/FreeToken/runs/dev_D14/t16_[0-9a-f]{12}", stage):
    raise ValueError("the reviewed CPU stage changed")
for name, digest in cpu["report"]["files"].items():
    path = HERE / name
    if name == "tests/engine/test_layer_major_tracks.py":
        source = subprocess.check_output(['git', '-C', str(HERE/'e2d14'), 'show',
            'e4f32022a5aa4d8734d87d9f6eb15e98c1edde42:' + name])
    elif name == "t16_legacy_base_runner.py":
        source = (HERE.parent/'plan/01_测试与调研/batches/t16_runner.py').read_bytes()
    else:
        source = path.read_bytes()
    if hashlib.sha256(source).hexdigest() != digest:
        raise ValueError("local reviewed tooling changed: " + name)
for path in HERE.glob("t16_d14_E2-R*-gate-D14_launch_receipt.json"):
    prior = json.loads(path.read_text())
    if prior.get('cpu_stage_sha256') == cpu['report_sha256']:
        raise ValueError("this frozen stage already has a launch receipt; inspect its process")
    # A new round after a terminal harness failure is a deliberate protocol
    # correction, never a restart because an observation timed out.
    program = "\n".join([
        "import json,pathlib",
        "prior=" + repr(prior),
        "status=json.loads((pathlib.Path('/data2/_shared/runs/ft_rounds')/prior['rid']/('status_batch'+str(prior['batch'])+'.json')).read_text())",
        "assert status['state']=='failed' and status['rid']==prior['rid'] and status['batch_pid']==prior['batch_pid'],status",
        "p=pathlib.Path('/proc')/str(prior['batch_pid'])/'stat'",
        "assert not p.exists() or p.read_text().rpartition(') ')[2].split()[0]=='Z','prior batch remains live'",
    ])
    subprocess.run(['ssh','-o','BatchMode=yes','9','/data2/FreeToken/venv/bin/python','-c',
                    shlex.quote(program)], check=True)
process = subprocess.run([
    "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "9",
    "/data2/FreeToken/venv/bin/python", stage + "/t16_d14_launch.py",
    "--stage", stage, "--launch",
], capture_output=True)
print(process.stdout.decode(errors="replace"), end="")
if process.returncode:
    print(process.stderr.decode(errors="replace"))
    raise SystemExit(process.returncode)
receipt = json.loads(process.stdout.decode().splitlines()[-1])
if receipt.get("state") != "launched" or not isinstance(receipt.get("batch_pid"), int):
    raise ValueError("remote response did not prove a launched process")
with (HERE / ("t16_d14_" + receipt["rid"] + "_launch_receipt.json")).open("x", encoding="utf-8") as stream:
    stream.write(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
