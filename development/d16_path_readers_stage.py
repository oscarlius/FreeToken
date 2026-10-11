"""Freeze and run the D16 path-reader CPU evidence suite on the Linux candidate."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "e2d16-readers"
TARGET = "/data2/FreeToken/wt/e2d14-schedule"
CANDIDATE = "e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7"
D03_TOOL = HERE / "e2d03/scripts/logits_probe.py"
TESTS = (
    "tests/scripts/test_equiv_suite.py",
    "tests/scripts/test_equiv_continuation.py",
    "tests/scripts/test_equiv_path_readers.py",
    "tests/scripts/test_equiv_retained_d03.py",
)
SCHEMA = "ft_d16_path_readers_cpu/v1"
SUITE_SOURCES = (
    "__init__.py", "__main__.py", "cases.py", "continuation.py", "gate.py",
    "historical.py", "path_readers.py", "raw.py", "retained_d03.py", "schedule.py",
)

PROGRAM = r'''
import base64, hashlib, json, os, pathlib, re, subprocess, sys
x=json.load(sys.stdin); stage=pathlib.Path(x['stage'])
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path, raw):
 path.parent.mkdir(parents=True, exist_ok=True)
 with path.open('xb') as stream: stream.write(raw)
def emit(report):
 print(json.dumps({'stage':str(stage),'report_sha256':sha(stage/'cpu_validation.json'),**report}))
def replay():
 report_path=stage/'cpu_validation.json'
 if stage.is_symlink() or not report_path.is_file() or report_path.is_symlink(): raise ValueError('existing stage is not a retained regular directory')
 report=json.loads(report_path.read_text())
 if any(path.is_symlink() or path.stat().st_mode & 0o222 for path in [stage,*stage.rglob('*')]): raise ValueError('existing stage is not immutable')
 if report.get('schema')!='ft_d16_path_readers_cpu/v1' or report.get('verdict')!='PASS' or report.get('sources')!=x['source_sha256'] or report.get('d03_tool_sha256')!=x['source_sha256'].get('d03_tools/logits_probe.py') or report.get('gpu_started') is not False or report.get('requests_sent') is not False: raise ValueError('existing stage report is not a passed matching CPU receipt')
 files=report.get('files')
 actual={path.relative_to(stage).as_posix():sha(path) for path in stage.rglob('*') if path.is_file() and not path.is_symlink() and path!=report_path}
 if not isinstance(files,dict) or files!=actual: raise ValueError('existing stage declared files differ')
 candidate=report.get('candidate',{})
 if candidate.get('commit')!=x['candidate_commit'] or candidate.get('clean') is not True or candidate.get('freetoken')!=str(pathlib.Path(x['candidate_tree'])/'python/freetoken/__init__.py') or candidate.get('cuda_initialized') is not False: raise ValueError('existing stage candidate binding differs')
 steps=report.get('steps',{})
 for name in ('candidate_binding','regression'):
  step=steps.get(name); log=name+'.log'
  if not isinstance(step,dict) or step.get('returncode')!=0 or step.get('log_sha256')!=actual.get(log): raise ValueError('existing stage step log differs: '+name)
 output=(stage/'regression.log').read_text(errors='replace'); passed=re.findall(r'(\d+) passed',output)
 if type(report.get('passed')) is not int or report['passed']<=0 or passed!=[str(report['passed'])] or re.search(r'\d+ (failed|skipped|error)',output): raise ValueError('existing stage regression result differs')
 return report
if stage.exists():
 emit(replay())
 raise SystemExit(0)
stage.mkdir(parents=True)
report={'schema':'ft_d16_path_readers_cpu/v1','gpu_started':False,'requests_sent':False,'steps':{},'sources':x['source_sha256'],'d03_tool_sha256':x['source_sha256']['d03_tools/logits_probe.py']}
try:
 for name, encoded in x['files'].items(): write(stage/name,base64.b64decode(encoded))
 tree=pathlib.Path(x['candidate_tree'])
 head=subprocess.check_output(['git','-C',str(tree),'rev-parse','HEAD'],text=True).strip()
 clean=subprocess.check_output(['git','-C',str(tree),'status','--porcelain'],text=True).strip()
 if head!=x['candidate_commit'] or clean: raise ValueError('candidate must be exact and clean: '+head)
 env={key:value for key,value in os.environ.items() if key!='PYTHONPATH' and not key.startswith('FT_')}
 env.update(CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',TOKENIZERS_PARALLELISM='false',PYTHONPATH=str(stage/'scripts')+':'+str(tree/'python'),FT_D16_D03_TOOL=str(stage/'d03_tools/logits_probe.py'))
 def run(name, argv):
  completed=subprocess.run([sys.executable,*argv],cwd=stage,env=env,capture_output=True,timeout=240)
  log=stage/(name+'.log'); write(log,completed.stdout+completed.stderr)
  report['steps'][name]={'argv':[sys.executable,*argv],'returncode':completed.returncode,'log_sha256':sha(log)}
  if completed.returncode: raise ValueError(name+' failed: '+(completed.stdout+completed.stderr).decode(errors='replace')[-4000:])
  return completed.stdout.decode()
 binding=json.loads(run('candidate_binding',['-c',"import json,pathlib,torch,freetoken; origin=pathlib.Path(freetoken.__file__).resolve(); expected=pathlib.Path('"+str(tree/'python/freetoken')+"').resolve(); assert origin.is_relative_to(expected),origin; assert not torch.cuda.is_initialized(); print(json.dumps({'freetoken':str(origin),'cuda_initialized':torch.cuda.is_initialized()}))"]))
 report['candidate']={'commit':head,'clean':True,'freetoken':binding['freetoken'],'cuda_initialized':binding['cuda_initialized']}
 output=run('regression',['-m','pytest','-q','-p','no:cacheprovider',*x['tests']])
 passed=re.findall(r'(\d+) passed',output)
 if len(passed)!=1 or re.search(r'\d+ (failed|skipped|error)',output): raise ValueError('complete four-test CPU suite required')
 report.update(verdict='PASS',passed=int(passed[0]))
except BaseException as error:
 report.update(verdict='FAIL',error=repr(error))
finally:
 report['files']={path.relative_to(stage).as_posix():sha(path) for path in stage.rglob('*') if path.is_file() and not path.is_symlink()}
 write(stage/'cpu_validation.json',(json.dumps(report,indent=2)+'\n').encode())
 for path in sorted(stage.rglob('*'),reverse=True):
  if not path.is_symlink(): path.chmod(0o444 if path.is_file() else 0o555)
 stage.chmod(0o555)
emit(report)
'''


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _path_sha(path: Path) -> str:
    return sha(path.read_bytes())


def validate_existing_stage(stage: Path, source_sha256: dict[str, str], *, candidate_tree: str = TARGET,
                            candidate_commit: str = CANDIDATE, require_immutable: bool = True) -> dict:
    report_path = stage / "cpu_validation.json"
    if stage.is_symlink() or not report_path.is_file() or report_path.is_symlink():
        raise ValueError("existing stage is not a retained regular directory")
    if require_immutable and any(path.is_symlink() or path.stat().st_mode & 0o222 for path in [stage, *stage.rglob("*")]):
        raise ValueError("existing stage is not immutable")
    report = json.loads(report_path.read_text())
    if (report.get("schema") != SCHEMA or report.get("verdict") != "PASS"
            or report.get("sources") != source_sha256 or report.get("gpu_started") is not False
            or report.get("requests_sent") is not False
            or report.get("d03_tool_sha256") != source_sha256.get("d03_tools/logits_probe.py")):
        raise ValueError("existing stage report is not a passed matching CPU receipt")
    actual = {path.relative_to(stage).as_posix(): _path_sha(path) for path in stage.rglob("*")
              if path.is_file() and not path.is_symlink() and path != report_path}
    if not isinstance(report.get("files"), dict) or report["files"] != actual:
        raise ValueError("existing stage declared files differ")
    candidate = report.get("candidate", {})
    if (candidate.get("commit") != candidate_commit or candidate.get("clean") is not True
            or candidate.get("freetoken") != str(Path(candidate_tree) / "python/freetoken/__init__.py")
            or candidate.get("cuda_initialized") is not False):
        raise ValueError("existing stage candidate binding differs")
    steps = report.get("steps", {})
    for name in ("candidate_binding", "regression"):
        step, log = steps.get(name), f"{name}.log"
        if not isinstance(step, dict) or step.get("returncode") != 0 or step.get("log_sha256") != actual.get(log):
            raise ValueError(f"existing stage step log differs: {name}")
    output = (stage / "regression.log").read_text(errors="replace")
    passed = re.findall(r"(\d+) passed", output)
    if (type(report.get("passed")) is not int or report["passed"] <= 0
            or passed != [str(report["passed"])] or re.search(r"\d+ (failed|skipped|error)", output)):
        raise ValueError("existing stage regression result differs")
    return report


def source_files() -> dict[str, bytes]:
    files = {}
    for name in SUITE_SOURCES:
        path = SOURCE / "scripts/equiv_suite" / name
        files[path.relative_to(SOURCE).as_posix()] = path.read_bytes()
    for name in (*TESTS, "tests/conftest.py"):
        files[name] = (SOURCE / name).read_bytes()
    files["d03_tools/logits_probe.py"] = D03_TOOL.read_bytes()
    files["stage_source.py"] = Path(__file__).read_bytes()
    files["stage_program.py"] = PROGRAM.encode()
    return files


def main() -> None:
    files = source_files()
    identity = sha(b"".join(name.encode() + files[name] for name in sorted(files)))
    payload = {
        "stage": f"/data2/FreeToken/runs/dev_D16/path_readers_cpu_{identity[:12]}",
        "candidate_tree": TARGET,
        "candidate_commit": CANDIDATE,
        "tests": list(TESTS),
        "source_sha256": {name: sha(raw) for name, raw in files.items()},
        "files": {name: base64.b64encode(raw).decode() for name, raw in files.items()},
    }
    program = "import io,sys\nsys.stdin=io.StringIO(" + repr(json.dumps(payload)) + ")\n" + PROGRAM
    completed = subprocess.run([
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "9",
        "/data2/FreeToken/venv/bin/python", "-",
    ], input=program.encode(), capture_output=True)
    result = {"returncode": completed.returncode, "stdout": completed.stdout.decode(), "stderr": completed.stderr.decode()}
    if completed.returncode == 0:
        result.update(json.loads(completed.stdout))
    receipt = HERE / f"d16_path_readers_cpu_{identity[:12]}.json"
    if not receipt.exists():
        with receipt.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
    print(json.dumps({"receipt": str(receipt), "stage": payload["stage"], "verdict": result.get("verdict"), "passed": result.get("passed")}))
    if completed.returncode or result.get("verdict") != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
