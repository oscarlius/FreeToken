"""Bundle-sync the D16 batch observer and freeze a no-CUDA CPU verification stage."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import subprocess


HERE = Path(__file__).resolve().parent
TREE = HERE / "e2d16-readers"
PARENT = "bde6283c68c0ad153dcd727a14f631244819b535"
INVOKER_SOURCE = None


REMOTE_PROGRAM = r'''
import base64, hashlib, json, os, pathlib, re, subprocess, sys

payload = json.loads(sys.stdin.read())
stage = pathlib.Path(payload["stage"])
assert payload['tree_name'] in ('e2d16-readers', 'e2base1')
tree = pathlib.Path("/data2/FreeToken/wt") / payload['tree_name']
repo = pathlib.Path("/data2/FreeToken/src/FreeToken")

def sha(raw): return hashlib.sha256(raw).hexdigest()
def git(*args): return subprocess.check_output(["git", "-C", str(tree), *args], text=True).strip()
def write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle: handle.write(raw)

assert not stage.exists()
stage.mkdir(parents=True)
write(stage/'stage_source.py',base64.b64decode(payload['stage_source']))
write(stage/'sync_program.py',base64.b64decode(payload['sync_program']))
if payload.get('invoker_source'):
    write(stage/'invoker_source.py',base64.b64decode(payload['invoker_source']))
reports = {}
try:
    remote_head = git("rev-parse", "HEAD")
    assert remote_head in (payload["parent"], payload["commit"])
    assert not git("status", "--porcelain")
    bundle = stage / "observer.bundle"
    raw_bundle = base64.b64decode(payload["bundle"])
    assert sha(raw_bundle) == payload["bundle_sha256"]
    write(bundle, raw_bundle)
    subprocess.run(["git", "-C", str(repo), "bundle", "verify", str(bundle)], check=True, capture_output=True)
    if remote_head == payload["parent"]:
        subprocess.run(["git", "-C", str(repo), "fetch", str(bundle), "HEAD"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(tree), "merge", "--ff-only", payload["commit"]], check=True, capture_output=True)
    assert git("rev-parse", "HEAD") == payload["commit"] and not git("status", "--porcelain")

    source_sha = {}
    for name, expected in payload["source_sha256"].items():
        path = tree / name
        assert path.is_file() and not path.is_symlink()
        raw = path.read_bytes()
        blob = subprocess.check_output(["git", "-C", str(tree), "show", "HEAD:" + name])
        assert sha(raw) == sha(blob) == expected, name
        write(stage / "sources" / name, raw)
        source_sha[name] = expected

    d03_tool = pathlib.Path("/data2/FreeToken/runs/dev_D16/path_readers_cpu_7b382efbb437/d03_tools/logits_probe.py")
    assert d03_tool.is_file() and not d03_tool.is_symlink()
    write(stage / "d03_tools" / "logits_probe.py", d03_tool.read_bytes())
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH" and not key.startswith("FT_")}
    env.update(CUDA_VISIBLE_DEVICES="", PYTHONPATH=str(tree / "scripts") + ":" + str(tree / "python"),
               PYTHONDONTWRITEBYTECODE="1", OMP_NUM_THREADS="2", FT_D16_D03_TOOL=str(stage / "d03_tools" / "logits_probe.py"))
    binding_argv = [sys.executable, "-c", "import json,pathlib,torch,freetoken,equiv_suite.service_capture as c; root=pathlib.Path(" + repr(str(tree)) + "); fp=pathlib.Path(freetoken.__file__).resolve(); cp=pathlib.Path(c.__file__).resolve(); assert fp.is_relative_to(root / 'python') and cp.is_relative_to(root / 'scripts'); assert not torch.cuda.is_initialized(); print(json.dumps({'freetoken':str(fp),'capture':str(cp),'cuda_initialized':False}))"]
    binding = subprocess.run(binding_argv, cwd=tree, env=env, capture_output=True)
    write(stage / "import_binding.log", binding.stdout + binding.stderr)
    assert binding.returncode == 0
    argv = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *payload["tests"]]
    tested = subprocess.run(argv, cwd=tree, env=env, capture_output=True, timeout=300)
    log = tested.stdout + tested.stderr
    write(stage / "pytest.log", log)
    text = log.decode(errors="replace")
    passed = re.search(r"(\d+) passed", text)
    assert tested.returncode == 0 and passed and "skipped" not in text.lower(), text[-2000:]
    reports = {"commit": payload["commit"], "clean": not git("status", "--porcelain"),
               "source_sha256": source_sha, "d03_tool_sha256": sha(d03_tool.read_bytes()), "argv": argv, "returncode": tested.returncode,
               "passed": int(passed.group(1)), "log_sha256": sha(log),
               "binding_argv": binding_argv, "binding_log_sha256": sha(binding.stdout + binding.stderr)}
    assert reports["clean"]
    verdict = "PASS"
except BaseException as error:
    verdict = "FAIL"
    reports = {**reports, "error": repr(error)}
finally:
    files = {path.relative_to(stage).as_posix(): sha(path.read_bytes()) for path in stage.rglob("*") if path.is_file()}
    report = {"schema": "ft_d16_batch_observer_cpu/v1", "verdict": verdict, "gpu_started": False,
              "service_started": False, "requests_sent": False, "tree": reports, "files": files}
    raw_report = json.dumps(report, sort_keys=True).encode()
    write(stage / "cpu_validation.json", raw_report)
    for path in sorted(stage.rglob("*"), reverse=True):
        assert not path.is_symlink()
        path.chmod(0o444 if path.is_file() else 0o555)
    stage.chmod(0o555)
    print(json.dumps({"stage": str(stage), "report_sha256": sha(raw_report), "verdict": verdict}), flush=True)
sys.exit(0 if verdict == "PASS" else 1)
'''


def main() -> None:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", "-C", str(TREE), *args], text=True).strip()

    commit = git("rev-parse", "HEAD")
    ancestor = subprocess.run(["git", "-C", str(TREE), "merge-base", "--is-ancestor", PARENT, commit])
    if ancestor.returncode != 0 or git("status", "--porcelain"):
        raise SystemExit("e2d16-readers must be clean and descend from the reviewed bde6283 parent")
    bundle = HERE / f"{TREE.name}_batch_observer_{commit[:12]}.bundle"
    if not bundle.exists():
        subprocess.run(["git", "-C", str(TREE), "bundle", "create", str(bundle), "HEAD", "^" + PARENT], check=True)
    if git("bundle", "list-heads", str(bundle)) != commit + " HEAD":
        raise SystemExit("bundle does not contain exactly the current observer commit")
    names = git("ls-files", "scripts/equiv_suite").splitlines()
    names += git("ls-files", "tests/scripts/test_equiv_*.py").splitlines()
    names += ["tests/conftest.py", "README.md"]
    source_sha = {name: hashlib.sha256(subprocess.check_output(["git", "-C", str(TREE), "show", "HEAD:" + name])).hexdigest() for name in names}
    payload = {
        "tree_name": TREE.name,
        "stage_source": base64.b64encode(Path(__file__).read_bytes()).decode(),
        "sync_program": base64.b64encode(REMOTE_PROGRAM.encode()).decode(),
        "invoker_source": base64.b64encode(INVOKER_SOURCE).decode() if INVOKER_SOURCE else None,
        "parent": PARENT, "commit": commit,
        "bundle": base64.b64encode(bundle.read_bytes()).decode(),
        "bundle_sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
        "source_sha256": source_sha,
        "tests": git("ls-files", "tests/scripts/test_equiv_*.py").splitlines(),
        "stage": f"/data2/FreeToken/runs/dev_D16/batch_observer_{commit[:12]}_cpu_{hashlib.sha256(Path(__file__).read_bytes() + (INVOKER_SOURCE or b'')).hexdigest()[:12]}",
    }
    code = "import io,sys\nsys.stdin=io.StringIO(" + repr(json.dumps(payload)) + ")\n" + REMOTE_PROGRAM
    result = subprocess.run(["ssh", "9", "/data2/FreeToken/venv/bin/python", "-"], input=code, text=True, capture_output=True)
    receipt = HERE / f"d16_batch_observer_{commit[:12]}_sync_cpu_{hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:12]}.json"
    with receipt.open("x", encoding="utf-8") as handle:
        json.dump({"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}, handle)
    print(result.stdout)
    print(result.stderr)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
