"""v5 actual entrypoint: the v4 owned lifecycle with parser-v5 admission pins."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os
from pathlib import Path

HERE=Path(__file__).resolve().parent
def load(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
base=load(HERE/'d10_prototype_owned_parent_v4.py','d10_parent_v4_body')
RID='E2-D10-PROTOTYPE-night-20261010-v5'
ACTUAL=('d10_prototype_owned_parent_v5.py','d10_branch_startup_v4.py','d10_branch_probe_v4.py','d10_aiperf_parse_v5.py','d10_aiperf_runner_v6.py')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def runner():return load(HERE/'d10_aiperf_runner_v6.py','d10_runner_v6')
def parser():return load(HERE/'d10_aiperf_parse_v5.py','d10_parser_v5')
def child_argv(admission,batch,receipt):return [str(base.ROOT/'venv/bin/python'),str(HERE/'d10_prototype_owned_parent_v5.py'),'--run','--owned-child','--admission',str(admission),'--batch',str(batch),'--launch-receipt',str(receipt)]
def require_admission(path,run):
 if path.is_symlink() or not path.is_file() or path.stat().st_mode&0o222:raise RuntimeError('sealed root admission required')
 doc=run.require_admission(path);want={'admit':True,'prototype_rid':RID,'candidate':base.CANDIDATE,'d10_flag':base.FLAG,'calls_max':8,'services_max':1}
 if any(doc.get(k)!=v for k,v in want.items()):raise RuntimeError('v5 admission binding differs')
 base.service_argv(doc['service']);files=doc.get('source_sha256',{})
 if set(files)!=set(ACTUAL) or any(files[n]!=sha(HERE/n) for n in ACTUAL):raise RuntimeError('actual v5 source admission SHA differs')
 if doc.get('native_provenance_sha256')!=sha(base.PROVENANCE) or not doc.get('t16_closure'):raise RuntimeError('native/T16 closure missing')
 terms=doc.get('d09_completed_terminals')
 if not isinstance(terms,list) or not terms:raise RuntimeError('prior D09 safe-cleanup terminal bindings missing')
 return doc
# These replacements affect the globals resolved by the retained v4 controller
# and child functions, preserving their D07 lifecycle rather than a parallel body.
base.RID=RID;base.runner=runner;base.parser=parser;base.require_admission=require_admission;base.child_argv=child_argv
controller=base.controller;child=base.child
def filedry():
 plan=runner().filedry()
 return {'schema':'ft_d10_parent_v5_filedry/v1','actual_entrypoint':Path(__file__).name,'parser_sha256':sha(HERE/'d10_aiperf_parse_v5.py'),'runner_sha256':sha(HERE/'d10_aiperf_runner_v6.py'),'plan':plan,'gpu_started':False,'http_started':False,'service_started':False,'compile_started':False}
def main():
 p=argparse.ArgumentParser();p.add_argument('--filedry',action='store_true');p.add_argument('--run',action='store_true');p.add_argument('--owned-child',action='store_true');p.add_argument('--admission',type=Path);p.add_argument('--batch',type=int);p.add_argument('--launch-receipt',type=Path);a=p.parse_args()
 if a.filedry and not a.run:print(json.dumps(filedry(),sort_keys=True));return
 if a.run and a.owned_child and a.admission and a.batch and a.launch_receipt:child(a.admission,a.batch,a.launch_receipt);return
 if a.run and a.admission and not a.owned_child:controller(a.admission);return
 p.error('select --filedry or guarded --run --admission')
if __name__=='__main__':main()
