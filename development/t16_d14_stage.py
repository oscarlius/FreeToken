"""Retain exact T16 D14 tooling and run CPU replay before any GPU launch."""
import base64
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE_NAMES = (
    "t16_d14_runner.py", "t16_d14_cpu_stage.py", "t16_d14_launch.py",
    "t16_candidate_runner_full_tail.py", "t16_full_tail_base_runner.py",
    "t16_candidate_launch_full_tail.py",
    "t16_legacy_base_runner.py", "tests/test_t16_shared_prefill.py",
    "tests/test_t16_full_tail.py", "tests/test_t16_candidate_runner_full_tail.py",
    "tests/fixtures/t16_failed_full_tail.json",
)
files = {name: (ROOT / "development" / name).read_bytes() for name in SOURCE_NAMES
         if name != "t16_legacy_base_runner.py"}
files["t16_legacy_base_runner.py"] = (ROOT / "plan/01_测试与调研/batches/t16_runner.py").read_bytes()
files["tests/engine/test_layer_major_tracks.py"] = subprocess.check_output([
    "git", "-C", str(ROOT / "development/e2d14"), "show",
    "e4f32022a5aa4d8734d87d9f6eb15e98c1edde42:tests/engine/test_layer_major_tracks.py",
])
files["stage_source.py"] = Path(__file__).read_bytes()
identity = hashlib.sha256(b"".join(name.encode() + files[name] for name in sorted(files))).hexdigest()
stage = "/data2/FreeToken/runs/dev_D14/t16_" + identity[:12]
payload = {"stage": stage, "files": {name: base64.b64encode(data).decode() for name, data in files.items()}}
program = r'''
import base64,hashlib,json,os,pathlib,subprocess,sys
data=json.load(sys.stdin);stage=pathlib.Path(data['stage']);stage.mkdir(parents=True,exist_ok=False)
for name,encoded in data['files'].items():
 relative=pathlib.PurePosixPath(name)
 assert not relative.is_absolute() and '..' not in relative.parts
 path=stage/name;path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('xb') as stream:stream.write(base64.b64decode(encoded))
env=dict(os.environ,CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',TOKENIZERS_PARALLELISM='false')
try:
 process=subprocess.run(['/data2/FreeToken/venv/bin/python',str(stage/'t16_d14_cpu_stage.py'),'--stage',str(stage)],env=env,capture_output=True,timeout=420)
 (stage/'cpu_stage.log').write_bytes(process.stdout+process.stderr)
 if process.returncode:
  print((process.stdout+process.stderr).decode(errors='replace')[-8000:],file=sys.stderr)
  raise SystemExit(process.returncode)
 report=json.loads((stage/'cpu_validation.json').read_text())
 assert report['gpu_started'] is False
 print(json.dumps({'stage':str(stage),'report':report,'report_sha256':hashlib.sha256((stage/'cpu_validation.json').read_bytes()).hexdigest()}))
finally:
 for path in reversed([stage,*sorted(stage.rglob('*'))]):
  assert not path.is_symlink()
  path.chmod(path.stat().st_mode & ~0o222)
'''
result = subprocess.run([
    "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "9",
    "/data2/FreeToken/venv/bin/python", "-c", shlex.quote(program),
], input=json.dumps(payload).encode(), capture_output=True)
if result.returncode:
    print("Retained failed CPU stage:", stage)
    print(result.stderr.decode(errors="replace"))
    raise SystemExit(result.returncode)
receipt = json.loads(result.stdout)
old_path = ROOT / "development/t16_d14_cpu_receipt.json"
if old_path.exists():
    old_bytes = old_path.read_bytes()
    archive = old_path.with_name("t16_d14_cpu_receipt_" + hashlib.sha256(old_bytes).hexdigest()[:12] + ".json")
    if archive.exists():
        if archive.read_bytes() != old_bytes:
            raise ValueError("old CPU receipt archive changed")
    else:
        with archive.open("xb") as stream:
            stream.write(old_bytes)
(ROOT / "development/t16_d14_cpu_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"stage": stage, "report_sha256": receipt["report_sha256"],
                  "steps": [{"commit": step["commit"], "pytest": step["pytest"], "returncode": step["returncode"]}
                            for step in receipt["report"]["steps"]],
                  "raw_replay": receipt["report"]["r020_read_only_replay"]["replay"]}, indent=2))
