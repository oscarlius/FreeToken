"""CPU-only V2 packet proof.  It extracts and invokes exact prepared-child helpers."""
from __future__ import annotations
import argparse, ast, hashlib, io, json, re, shutil, subprocess, sys
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
import r067d_retry1_v2_tools as tools

HERE=Path(__file__).resolve().parent
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main(out: Path):
 cfg=json.loads((HERE/'R067D_RETRY1_CONFIG_CPU_ONLY.json').read_text()); pkt=json.loads((HERE/'R067D_RETRY1_PREPARED_RUNNER_PACKET_V2.json').read_text())
 assert pkt['config_sha256']==sha(HERE/'R067D_RETRY1_CONFIG_CPU_ONLY.json') and pkt['helper_sha256']==sha(HERE/'r067d_retry1_v2_tools.py')
 tree=ast.parse(pkt['child_source']); wanted={'verify_runtime_environment','start_prepared_service','judge_prepared_window'}
 nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in wanted]; assert {n.name for n in nodes}==wanted
 # The frozen child runs on Linux; use POSIX path semantics for a Windows CPU
 # replay so its exact `Path('/data2/...')` guards have the same meaning.
 ns={'Path':PurePosixPath,'subprocess':subprocess,'r067d_tools':tools,'d07':__import__('r067d_cpu_prep'),'json':json}
 exec(compile(ast.Module(nodes,[]),'<R067d-V2-exact-child-helpers>','exec'),ns)
 assert not out.exists(); out.mkdir(parents=True)
 spawns=[]; probes=[]; judgments=[]
 def probe(ports,evidence_dir,timeout): probes.append({'ports':list(ports),'timeout_s':timeout})
 def popen(argv,**kw):
  spawns.append({'argv':argv,'env':kw['env'],'cwd':str(kw['cwd']),'argv_sha256':tools.argv_sha256(argv)})
  return SimpleNamespace(pid=-1)
 for service in cfg['services']:
  arm=PurePosixPath(service['service_dir']); rendered=ns['verify_runtime_environment'](service,arm)
  assert rendered==tools.actual_environment(service)
  ns['start_prepared_service'](service,rendered,io.BytesIO(),probe=probe,popen=popen)
  prefix=int(re.search(r'_p(\d+)',service['name']).group(1)); requests=service['requests'] if service['kind']=='hot' else [service['request']]
  for item in requests:
   tail=item.get('tail',int(re.search(r'_t(\d+)',service['name']).group(1)) if service['kind']=='cold' else 1); prompt=prefix+1 if item['role']=='seed' else prefix+tail; cached=prefix if service['kind']=='hot' and item['role']!='seed' else 0; new=tail if cached else prompt
   window=(f'Prefill batch, #new-seq: 1, #new-token: {new}, #cached-token: {cached}\nPOST /internal/t17/exact-ids HTTP/1.1" 200 OK\n').encode(); raw={'response':{'usage':{'prompt_tokens':prompt,'cached_tokens':cached,'completion_tokens':item['max_tokens']}}}
   rows,ok=ns['judge_prepared_window'](service,item,range(prompt),window,raw,prefix,tail); assert rows and ok
   judgments.append({'service':service['name'],'role':item['role'],'valid':ok})
 assert len(spawns)==10 and len(probes)==10 and len(judgments)==14
 for s in spawns:
  assert tools.RID in json.dumps(s['env'],sort_keys=True) and 'E2-R067d-d20-short-tail-v1' not in json.dumps({k:s['env'][k] for k in ('FT_DEV_STATE_DUMP','FT_T17_INPUT_RECEIPTS','FT_T17_OBSERVATIONS','PYTHONPATH')},sort_keys=True)
 (out/'prepared_child_cpu_mode.json').write_text(json.dumps({'fake_popen':True,'real_popen':False,'synthetic_transport':True,'spawns':spawns,'probes':probes,'judgments':judgments},sort_keys=True)+'\n')
 receipt={'schema':'ft_r067d_retry1_v2_cpu_filedry/v1','rid':tools.RID,'services':10,'calls':14,'guard_all_10':True,'actual_child_helpers':sorted(wanted),'actual_popen_calls':10,'actual_http_calls':0,'synthetic_transport':True,'gpu_started':False,'service_started':False,'http_generation':False,'config_sha256':pkt['config_sha256'],'packet_sha256':sha(HERE/'R067D_RETRY1_PREPARED_RUNNER_PACKET_V2.json'),'helper_sha256':pkt['helper_sha256'],'v1_packet_sha256':pkt['supersedes_packet_sha256'],'admit':False}
 (out/'receipt.json').write_text(json.dumps(receipt,sort_keys=True)+'\n'); receipt['receipt_sha256']=sha(out/'receipt.json'); print(json.dumps(receipt,sort_keys=True))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();main(a.out)
