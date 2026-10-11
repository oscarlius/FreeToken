"""Seal a prepared R020 D06 gate through the published D04 closer."""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,os,subprocess,sys
from pathlib import Path
RID="E2-R020-gate-D06";BATCH=48
PREPARER_SHA="b1147d9fd9924739445b1cfed5c5033484e3bd069f89d18ac326a80899fd747e"
TOOLS={"round_json_append.py":"88178a9a3c83dec204e90e6dcf8c4db9","round_close.py":"415aa82b34c8fd82d09bfe8a8ce67eed","round_close.sh":"430693122ef66bb5a293fb421ff0f7fc"}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,data,created):
 with p.open("xb") as f:f.write(data)
 created.append(p)
def close(directory,root):
 prep_path=Path(__file__).with_name("t16_r020_prepare.py");source=prep_path.read_bytes()
 if hashlib.sha256(source).hexdigest()!=PREPARER_SHA:raise ValueError("reviewed R020 preparer changed")
 spec=importlib.util.spec_from_file_location("t16_r020_prepare_pinned",prep_path);prep=importlib.util.module_from_spec(spec);assert spec.loader;exec(compile(source,str(prep_path),"exec"),prep.__dict__)
 d=prep.exact_round(directory);root=prep.guarded_path(root)
 if any((d/x).exists() for x in ("round.json","round_history","MANIFEST.sha256")):raise ValueError("unsealed exact R020 directory required")
 review=d/f"review_batch{BATCH}.json";prep.validate(d,review);batch_log=d.parent/f"batch{BATCH}.log";prep.require(batch_log)
 sources={}
 for name,md5 in TOOLS.items():
  data=(root/"scripts"/name).read_bytes()
  if hashlib.md5(data).hexdigest()!=md5:raise ValueError(f"published D04 tool changed: {name}")
  if (d/name).exists():raise FileExistsError(f"existing archive retained: {name}")
  sources[name]=data
 if any((d/x).exists() for x in ("initial_metadata.json","d04_tool_versions.json")):raise FileExistsError("existing preparation retained")
 created=[]
 try:
  prep.prepare(d,review)
  for name,data in sources.items():write(d/name,data,created)
  write(d/"d04_tool_versions.json",prep.jb({n:{"md5":TOOLS[n],"sha256":hashlib.sha256(v).hexdigest()} for n,v in sources.items()}),created)
  meta=json.loads((d/"initial_metadata.json").read_text());meta["manifest"]="MANIFEST.sha256";meta["batch_logs"]=[{"path":str(batch_log),"sha256":sha(batch_log)}]
  write(d/"round.json",prep.jb(meta),created)
  subprocess.run(["bash",str(d/"round_close.sh"),RID,"--round-root",str(d.parent)],env={**os.environ,"FT_ROUND_PYTHON":sys.executable},check=True)
 except BaseException as exc:raise RuntimeError("R020 closure failed; all artifacts retained for inspection") from exc
 subprocess.run([sys.executable,str(d/"round_json_append.py"),str(d),"check"],check=True)
 if (d/"round.json").read_bytes()!=(d/"round_history/round.v001.json").read_bytes():raise ValueError("history differs")
 for line in (d/"MANIFEST.sha256").read_text().splitlines():
  expected,relative=line.split("  ",1);target=(d/relative).resolve(strict=True)
  if d not in target.parents or sha(target)!=expected:raise ValueError("sealed manifest differs")
 if any(p.stat().st_mode&0o222 for p in [d,*d.rglob("*")]):raise ValueError("D04 did not make closure readonly")
 return {"rid":RID,"batch":BATCH,"round_sha256":sha(d/"round.json"),"manifest_sha256":sha(d/"MANIFEST.sha256"),"formal_verdict":"pending_review"}
def main():
 p=argparse.ArgumentParser();p.add_argument("--close",action="store_true");p.add_argument("--round-dir",type=Path);p.add_argument("--root",type=Path);a=p.parse_args()
 if not a.close or sys.platform!="linux" or not a.round_dir or not a.root:p.error("--close, --round-dir, --root and Linux required")
 print(json.dumps(close(a.round_dir,a.root),sort_keys=True))
if __name__=="__main__":main()
