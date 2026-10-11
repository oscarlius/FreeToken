#!/usr/bin/env python3
"""Seed-aware, hash-pinned wrapper around the D07 candidate agent_trace client."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, sys
from pathlib import Path

PIN="332a1870378d5bffa4891180280060e70f6135b6acff21b48603a5fc98ad44d9"
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(client):
 client=Path(client); raw=client.with_name("_agent_trace_original.py")
 if sha(raw)!=PIN: raise RuntimeError("candidate frozen agent-trace bytes differ")
 spec=importlib.util.spec_from_file_location("t06_candidate_agent_trace",client); m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def main(argv=None):
 p=argparse.ArgumentParser(add_help=False);p.add_argument("--seed-file",required=True);p.add_argument("--client",required=True);p.add_argument("--out",required=True);p.add_argument("--rounds",type=int,required=True);p.add_argument("--max-tokens",type=int,required=True)
 a,rest=p.parse_known_args(argv)
 if a.rounds!=12 or a.max_tokens!=2048: raise ValueError("T06 requires exactly 12 rounds and 2048 max tokens")
 seed=Path(a.seed_file).read_text(encoding="utf-8")
 if not seed: raise ValueError("empty T06 seed")
 m=load(a.client); original=m._ns["TASK_PROMPT"]; m._ns["TASK_PROMPT"]=seed+"\n\n"+original
 old=sys.argv[:];sys.argv=[str(a.client),"generate","--route-evidence","--out",a.out,"--rounds","12","--max-tokens","2048",*rest]
 try: rc=m.main()
 finally: sys.argv=old;m._ns["TASK_PROMPT"]=original
 doc=json.loads(Path(a.out).read_text(encoding="utf-8")); first=doc["rounds"][0]["messages"][0]["content"]
 if not first.startswith(seed) or original not in first: raise RuntimeError("actual wire first request did not bind seed plus task prompt")
 binding={"schema":"ft_t06_seed_trace_binding/v1","seed_path":str(Path(a.seed_file)),"seed_raw_sha256":sha(a.seed_file),"actual_wire_first_content_sha256":hashlib.sha256(first.encode()).hexdigest(),"actual_wire_messages_sha256":doc["rounds"][0]["record"]["messages_sha"],"rounds":12,"max_tokens":2048,"client":str(a.client),"client_frozen_sha256":PIN}
 Path(a.out).with_suffix(".seed_binding.json").write_text(json.dumps(binding,indent=2)+"\n")
 return rc
if __name__=="__main__": raise SystemExit(main())
