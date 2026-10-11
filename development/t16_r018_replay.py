"""Read-only CPU replay audit for the archived R018 runner and eight arms."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, runpy, subprocess, sys, tempfile
from pathlib import Path
RID="E2-R018-gate-D03"; RUNNER_SHA="29fa24ed89a3e35ddd0c426c67fa9c481f85d1700a5498a7c0abc8daab01e0c6"; BASE_SHA="51d8216e14417a6d922c44f3048082f985dfb59d8872dfc78ac0984f027fcd16"; PARSER_MD5="ce123cb0af201d99baac91f7f8e4f8c7"
ARMS=("PARENT_b46","NEW_b46","PARENT_P_b46","NEW_P_b46","CHUNK_PARENT_b46","CHUNK_NEW_b46","CHUNK_PARENT_P_b46","CHUNK_NEW_P_b46")
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text())
def require(p):
 p=Path(p)
 if not p.is_file() or p.is_symlink():raise ValueError(f"missing archival artifact: {p}")
 return p
def restore_and_selftest(d):
 runner=require(d/"runner_batch46.py");base=require(d/"base_runner_batch46.py")
 runner_bytes=runner.read_bytes();base_bytes=base.read_bytes()
 if hashlib.sha256(runner_bytes).hexdigest()!=RUNNER_SHA or hashlib.sha256(base_bytes).hexdigest()!=BASE_SHA:raise ValueError("archived runner/base SHA mismatch")
 with tempfile.TemporaryDirectory(prefix="t16-r018-replay-") as temp:
  stage=Path(temp); (stage/"t16_candidate_runner.py").write_bytes(runner_bytes);(stage/"t16_base_runner.py").write_bytes(base_bytes)
  # Canonical sibling name is restored only in this private temporary stage.
  run=subprocess.run([sys.executable,str(stage/"t16_candidate_runner.py"),"--self-test"],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=60)
  if run.returncode:raise RuntimeError("archived CPU selftest failed: "+run.stdout[-2000:])
  spec=importlib.util.spec_from_file_location("t16_r018_archived_runner",stage/"t16_candidate_runner.py"); module=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(module)
  return {"runner_sha256":hashlib.sha256(runner_bytes).hexdigest(),"base_runner_sha256":hashlib.sha256(base_bytes).hexdigest(),"selftest_output":run.stdout[-1000:]},module
def audit(directory,parser_path=None):
 d=Path(directory).resolve(strict=True)
 if d.name!=RID:raise ValueError("exact R018 directory required")
 parser=Path(parser_path or (Path(__file__).resolve().parents[1]/"scripts/serve_args_diff.py")).resolve(strict=True)
 parser_bytes=require(parser).read_bytes()
 if hashlib.md5(parser_bytes).hexdigest()!=PARSER_MD5:raise ValueError("frozen serve-args parser MD5 mismatch")
 restored_result=restore_and_selftest(d)
 if not isinstance(restored_result,tuple): raise RuntimeError("archived runner was not restored for recomputation")
 restored,module=restored_result;gate=require(d/"gate_batch46.json");binding=require(d/"candidate_binding.json");wrapper=require(d/"batch46.sh")
 raw=load(gate)
 if raw.get("arms")!=list(ARMS):raise ValueError("eight raw arms required")
 evidence={}
 for arm in ARMS:
  ad=d/arm; payloads=("short.json","chunked.json") if arm.startswith("CHUNK_") else ("det.json",); files={n:require(ad/n) for n in (*payloads,"tax.json","prefill_seq.txt","serve.log","serve_args.txt","ENV.txt")}
  seq=files["prefill_seq.txt"].read_bytes()
  if not seq:raise ValueError(f"empty prefill sequence: {arm}")
  evidence[arm]={"fulltext_sha256":{name:sha(path) for name,path in files.items() if name.endswith(".json")},"prefill_sha256":sha(files["prefill_seq.txt"]),"event_sha256":sha(files["serve.log"]),"h2d_d2d_source":str(files["serve.log"].relative_to(d))}
 # Recompute equality directly from all four parent/new pairs rather than trust gate summaries.
 for a,b in (("PARENT_b46","NEW_b46"),("PARENT_P_b46","NEW_P_b46"),("CHUNK_PARENT_b46","CHUNK_NEW_b46"),("CHUNK_PARENT_P_b46","CHUNK_NEW_P_b46")):
  if (d/a/"prefill_seq.txt").read_bytes()!=(d/b/"prefill_seq.txt").read_bytes():raise ValueError(f"raw prefill mismatch: {a}/{b}")
 parser_scope={'__file__':str(parser),'__name__':'ft_r018_archived_args_parser'}
 exec(compile(parser_bytes,str(parser),'exec'),parser_scope)
 parsed=parser_scope["parse"]
 replay=object.__new__(module.CandidateRunner); replay.parser=parsed
 lm=module.CandidateRunner.compare(replay,d/"PARENT_b46",d/"NEW_b46",d/"PARENT_P_b46",d/"NEW_P_b46")
 ordinary=module.CandidateRunner.compare(replay,d/"CHUNK_PARENT_b46",d/"CHUNK_NEW_b46",d/"CHUNK_PARENT_P_b46",d/"CHUNK_NEW_P_b46",[("short","",2000,128),("chunked","",32052,128)])
 # The runner returns request tuples; the recorded gate encodes them as JSON arrays.
 recomputed=json.loads(json.dumps({"layer_major":lm,"non_layer_major":ordinary},allow_nan=False))
 if any(recomputed[name]!=raw.get(name) for name in recomputed):raise ValueError("recomputed archived outcomes differ from raw gate")
 return {"schema":"ft_t16_r018_archival_cpu_replay/v1","scope":"archival CPU audit; no GPU/resource gate/model replay","gate_sha256":sha(gate),"candidate_binding_sha256":sha(binding),"wrapper_sha256":sha(wrapper),"archived":restored,"arms":evidence,"recomputed":{"layer_major":lm,"non_layer_major":ordinary},"matched_gate_outcomes":True}
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument("--round-dir",type=Path,required=True);p.add_argument("--parser-path",type=Path,required=True);a=p.parse_args(argv);print(json.dumps(audit(a.round_dir,a.parser_path),indent=2))
if __name__=="__main__":main()
