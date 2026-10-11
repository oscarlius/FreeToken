"""Content-addressed, CPU-only stage for the D14 schedule T16 declaration."""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHARED = HERE / "t16_candidate_stage_shared.py"
D18_TEST = "tests/test_d18_client_params.py"
ENGINE_RECEIPT_SOURCE = "d14_ordinary_cpu_a9dca443cd07.json"
ENGINE_RECEIPT_FROZEN = "d14_schedule_cpu_receipt.json"
EXTRA = (
    "t16_d14_schedule_runner.py",
    "t16_d14_schedule_launch.py",
    "t16_d14_schedule_stage.py",
    "tests/test_t16_d14_schedule_runner.py",
    "tests/test_t16_d14_schedule_stage.py",
    "tests/test_t16_d14_schedule_launch.py",
    "d18_independent_cpu_receipt_20261005.json",
    "d18_independent_cpu_receipt_20261005.log",
    ENGINE_RECEIPT_FROZEN,
    D18_TEST,
    "stage_program.py",
)


def _load_shared(path: Path):
    spec = importlib.util.spec_from_file_location("schedule_shared_stage", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_shared = _load_shared(SHARED)
SOURCE_NAMES = (*_shared.NAMES, "t16_legacy_base_runner.py", *EXTRA)
TESTS = (
    *_shared.TESTS,
    "tests/test_t16_d14_schedule_runner.py",
    "tests/test_t16_d14_schedule_stage.py",
    "tests/test_t16_d14_schedule_launch.py",
)
assert len(SOURCE_NAMES) == len(set(SOURCE_NAMES))
assert len(TESTS) == len(set(TESTS))

# This is staged verbatim as ``stage_program.py``.  It always emits a receipt,
# including on a test failure or timeout, before making the stage read-only.
PROGRAM = r'''import base64,hashlib,json,os,pathlib,re,subprocess,sys,traceback
d=json.load(sys.stdin);p=pathlib.Path(d['target']);steps={};error=None;passed=0
p.mkdir(parents=True,exist_ok=False)
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write_log(name, body):
 q=p/(name+'.log');q.write_text(body);return {'returncode':None,'log_sha256':sha(q)}
def freeze():
 for q in sorted(p.rglob('*'),reverse=True):
  q.chmod(q.stat().st_mode&~0o222)
 p.chmod(p.stat().st_mode&~0o222)
try:
 for n,v in d['files'].items():
  q=p/n;q.parent.mkdir(parents=True,exist_ok=True)
  with q.open('xb') as f:f.write(base64.b64decode(v))
 env={k:v for k,v in os.environ.items() if not k.startswith(('FT_DEV_','FT_T17_','FT_D3_'))}
 env.update(CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1',
            PYTHONPATH='/data2/FreeToken/runs/dev_D16/exact_startup_cpu_3cc07ea9a740/sources:'+str(p))
 for name,argv in [('regression',[sys.executable,'-m','pytest','-q','-p','no:cacheprovider',*d['tests']]),('d18_binding',[sys.executable,'-c','import t16_d14_schedule_runner as r; print(r.d18_binding())'])]:
  try:r=subprocess.run(argv,cwd=p,env=env,capture_output=True,text=True,timeout=240)
  except BaseException:
   steps[name]=write_log(name,traceback.format_exc());raise
  log=p/(name+'.log');log.write_text(r.stdout+r.stderr)
  steps[name]={'returncode':r.returncode,'log_sha256':sha(log)}
  if r.returncode:raise RuntimeError(name+' failed')
 log=(p/'regression.log').read_text();matches=re.findall(r'(\d+) passed',log)
 if len(matches)!=1 or int(matches[0])<50 or re.search(r'\d+ (failed|skipped|error)',log):raise ValueError('incomplete successful CPU regression')
 passed=int(matches[-1])
except BaseException as exc:
 error=repr(exc)
finally:
 actual={n:sha(p/n) for n in d['files'] if (p/n).is_file()}
 if actual!=d['source_sha256'] and error is None:error='actual staged source differs'
 report={'schema':'ft_t16_d14_schedule_stage/v1','gpu_started':False,'requests_sent':False,'passed':passed,'tests':d['tests'],'steps':steps,'files':actual,'verdict':'PASS' if error is None else 'FAIL'}
 if error is not None:report['error']=error
 if p.exists():
  with (p/'cpu_validation.json').open('x') as f:json.dump(report,f,indent=2);f.write('\n')
  freeze()
  result={'stage':str(p),'receipt_sha256':sha(p/'cpu_validation.json'),'verdict':report['verdict']}
 else:result={'stage':str(p),'receipt_sha256':None,'verdict':'FAIL','error':error}
 print(json.dumps(result),flush=True)
'''


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _source_path(root: Path, name: str) -> Path:
    if name == ENGINE_RECEIPT_FROZEN:
        frozen = root / name
        return frozen if frozen.is_file() else root / ENGINE_RECEIPT_SOURCE
    if name == D18_TEST:
        staged = root / name
        return staged if staged.is_file() else root.parent / name
    return root / name


def source_manifest(root=None, extra_sources=()):
    """Return the exact source map that the frozen launcher's reader requires."""
    root = Path(root) if root else HERE
    shared = _load_shared(root / "t16_candidate_stage_shared.py")
    _, files = shared.source_manifest(root)
    extra = tuple(extra_sources)
    for name in (*EXTRA, *extra):
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("stage source must be a relative path: " + name)
        if name == "stage_program.py":
            files[name] = PROGRAM.encode()
            continue
        path = _source_path(root, name)
        if not path.is_file() or path.is_symlink():
            raise ValueError("required regular source missing: " + name)
        files[name] = path.read_bytes()
    if tuple(files) and set(files) != set((*SOURCE_NAMES, *extra)):
        raise AssertionError("stage source map differs from declared names")
    identity = _sha(b"".join(name.encode() + files[name] for name in sorted(files)))
    return identity, files


def stage(extra_sources=()):
    """Ask SSH9 to create one immutable CPU receipt; never reuse a stage."""
    identity, files = source_manifest(extra_sources=extra_sources)
    target = "/data2/FreeToken/runs/dev_D14/t16_schedule_" + identity[:12]
    tests = [*TESTS, *extra_sources]
    payload = {
        "target": target,
        "files": {name: base64.b64encode(data).decode() for name, data in files.items()},
        "source_sha256": {name: _sha(data) for name, data in files.items()},
        "tests": tests,
    }
    wire = "import io,sys\nsys.stdin=io.StringIO(" + repr(json.dumps(payload)) + ")\n" + PROGRAM
    run = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "9",
         "/data2/FreeToken/venv/bin/python", "-"],
        input=wire.encode(), capture_output=True,
    )
    result = None
    try:
        result = json.loads(run.stdout.decode().strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        pass
    local = HERE / ("t16_d14_schedule_stage_" + identity[:12] + ".json")
    local_receipt = {
        "schema": "ft_t16_d14_schedule_stage_transport/v1",
        "target": target,
        "returncode": run.returncode,
        "stdout": run.stdout.decode(errors="replace"),
        "stderr": run.stderr.decode(errors="replace"),
        "remote_result": result,
        "source_sha256": payload["source_sha256"],
        "program_sha256": _sha(PROGRAM.encode()),
        "program": PROGRAM,
    }
    with local.open("x") as stream:
        json.dump(local_receipt, stream, indent=2)
        stream.write("\n")
    if run.returncode or not result or result.get("verdict") != "PASS":
        raise RuntimeError("retained stage failed: " + target)
    return result


if __name__ == "__main__":
    print(json.dumps(stage()))
