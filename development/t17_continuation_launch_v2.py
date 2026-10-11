"""Produce a reviewable launch document for the versioned continuation runner; never starts GPU."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import t17_continuation_runner_v2 as runner

def main(argv=None):
 p=argparse.ArgumentParser(); p.add_argument("--output",type=Path,required=True); p.add_argument("runner_args",nargs=argparse.REMAINDER); a=p.parse_args(argv)
 if not a.runner_args: p.error("runner arguments required after --")
 value={"schema":"ft_t17_continuation_v2_launch_request/v1","runner":"development/t17_continuation_runner_v2.py","argv":a.runner_args,"gpu_started":False,"review_required":True}
 a.output.parent.mkdir(parents=True,exist_ok=True)
 with a.output.open("x",encoding="utf-8") as f: json.dump(value,f,indent=2);f.write("\n")
 print(json.dumps(value,sort_keys=True))
if __name__=="__main__": main()