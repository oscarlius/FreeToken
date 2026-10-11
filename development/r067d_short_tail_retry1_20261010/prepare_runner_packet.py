"""Generate the real frozen runner. CPU preparation never executes its top level."""
from __future__ import annotations
import ast, copy, hashlib, json, shutil
from pathlib import Path
from r067d_cpu_prep import HERE, RID, services, now
OLD='E2-R067d-d20-short-tail-v1'
OLD_DIR=HERE.parent/'r067d_short_tail_v1'
def replace(v):
 if isinstance(v,dict): return {k:replace(x) for k,x in v.items()}
 if isinstance(v,list): return [replace(x) for x in v]
 if isinstance(v,str): return v.replace(OLD,RID).replace('r067d_short_tail_v1','r067d_short_tail_retry1_20261010').replace('R067D_CONFIG_CPU_ONLY.json','R067D_RETRY1_CONFIG_CPU_ONLY.json').replace('R067D_ROOT_STARTUP_ADMISSION.json','R067D_RETRY1_ROOT_STARTUP_ADMISSION.json')
 return v
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def once(s,needle,new):
 assert s.count(needle)==1,(needle,s.count(needle))
 return s.replace(needle,new)
RUNTIME_HELPERS = r"""
def start_prepared_service(service,env,log,*,probe=None,popen=None):
 if probe is None: probe=r067d_tools.probe_or_capture
 if popen is None: popen=subprocess.Popen
 r067d_tools.verify_service_binding(service)
 argv=r067d_tools.actual_argv(service)
 assert all(env.get(k)==v for k,v in r067d_tools.actual_environment(service).items())
 probe((service['port_pair']['api'],service['port_pair']['tcpstore']),Path(service['service_dir']).parent.parent/'port_failures'/service['name'],120)
 return popen(argv,cwd=Path(service['service_dir']),env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
def judge_prepared_window(service,item,ids,window,raw,prefix,tail,*,post_marker=b'POST /internal/t17/exact-ids HTTP/1.1" 200 OK'):
 expected=prefix if service['kind']=='hot' and item['role']!='seed' else 0
 rows=r067d_tools.parse_rows(window.decode(errors='strict'))
 try:
  rows=r067d_tools.validate_runtime_window(window.decode(errors='strict'),expected_new=(tail if expected else len(ids)),expected_cache=expected,token_budget=len(ids),raw_usage=raw['response']['usage'],prompt_tokens=len(ids),expected_completion=item['max_tokens'],post_count=window.count(post_marker))
 except AssertionError:
  return rows,False
 return rows,True
"""
def main():
 cfg=replace(copy.deepcopy(json.loads((OLD_DIR/'R067D_CONFIG_CPU_ONLY.json').read_text())))
 cfg.update(schema='ft_r067d_retry1_config/v1',rid=RID,created_utc=now(),services=services(),admission={'admit':False,'state':'future_root_admission_only'},retry={'retry_index':1,'retry_of':OLD,'classification':'failed_harness','used':1,'max_failed_harness_retries':2},root_retry_ledger={'round':RID,'used':1,'maximum_retries':2},supersedes={'rid':OLD,'reason':'recorded cold arm used naive cache and deterministically failed its schedule harness'},budget={'services':10,'generation_calls':14})
 cfg['geometry_fix']['parser_consumer']='judge_prepared_window -> r067d_tools.validate_runtime_window'
 tooling=HERE/'tooling';tooling.mkdir(exist_ok=True)
 for item in (OLD_DIR/'tooling').glob('*.py'): shutil.copyfile(item,tooling/item.name)
 cp=HERE/'R067D_RETRY1_CONFIG_CPU_ONLY.json';cp.write_text(json.dumps(cfg,sort_keys=True,indent=2)+'\n')
 frozen=json.loads((OLD_DIR/'R067D_PREPARED_RUNNER_PACKET.json').read_text());old_sha=frozen['config_sha256']
 child=replace(frozen['child_source']).replace(old_sha,sha(cp))
 # The original R067d packet already uses the two helpers below.  Retain the
 # same control chain rather than attempting a second textual conversion.
 assert child.count('start_prepared_service(service,env,log)')==1
 assert child.count('rows,valid_geometry=judge_prepared_window(service,item,ids,window,raw,prefix,tail)')==1
 parent=replace(frozen['parent_tail']).replace(old_sha,sha(cp));ast.parse(child);ast.parse(parent)
 packet={'schema':'ft_r067d_retry1_prepared_runner/v1','rid':RID,'config_sha256':sha(cp),'execution_prohibited':True,'child_source':child,'parent_tail':parent,'base_r067d_packet_sha256':sha(OLD_DIR/'R067D_PREPARED_RUNNER_PACKET.json'),'helper_sha256':sha(HERE/'r067d_cpu_prep.py'),'runtime_helpers':['start_prepared_service','judge_prepared_window'],'change_scope':'scheduled cold arms omit --cache-type naive; all inputs, ports, service/call budgets, and observations remain bound','future_admission':'Root verifies actual observation submission + independent review, seals preflight bindings, then replaces admission SHA placeholder. CPU does not admit GPU.'}
 (HERE/'R067D_RETRY1_PREPARED_RUNNER_PACKET.json').write_text(json.dumps(packet,sort_keys=True,indent=2)+'\n')
if __name__=='__main__': main()
