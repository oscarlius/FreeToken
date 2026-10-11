import importlib.util, json, os, socket
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('d10v4',Path(__file__).with_name('d10_prototype_owned_parent_v4.py')); m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def free_port():
 s=socket.socket();s.bind(('127.0.0.1',0));p=s.getsockname()[1];s.close();return p
class Life:
 def verified_module(self,*_):return self
 def next_batch(self,*_):return 3
 def reserve_process(self,_,batch,rid,argv,receipt,reserved): receipt.write_text(json.dumps(reserved|{'state':'launched','batch_pid':77,'child':{'pid':77,'start_ticks':1}}));return {'batch_pid':77}
 def stop_owned_process(self,*_):pass
 def owned_group_alive(self,*_):return False
class Gate:
 ATOMIC_HELPER_SHA='x';ROUNDS=Path('x')
 def __init__(self,root):self.root=root;self.LOCK=root/'lock';self.life=Life();self.released=False
 def load_owned_lifecycle(self):return self.life
 def process_birth(self,pid=None):return {'pid':77 if pid is None else pid,'start_ticks':1}
 def process_identity(self,pid):return {'pid':pid,'start_ticks':1}
 def argv_sha256(self,a):return 'x'
 def take_d07_gpu_lock(self,*_):self.LOCK.write_text('x');return 'x'
 def release_d07_gpu_lock(self,*_):self.released=True;self.LOCK.unlink()
 def clean_environment(self,*_):return {}
 def require_gpu_idle(self):return {}
class Run:
 def __init__(self,doc):self.doc=doc
 def require_admission(self,_):return self.doc
class Proc:
 pid=55
 def poll(self):return None
class Deps:
 def __init__(self,root,doc):self.root=root;self.gate=Gate(root);self.run=Run(doc)
 def start(self,*_):return Proc()
 def health(self,*_):return {'status':'ok'}
 def aiperf(self,_,__,out):
  out.mkdir()
  for i in range(4):
   p=out/f'profile{i}';p.mkdir();(out/f'profile{i}.exit.json').write_text('{"exit_code":0}')
   tokens=64 if i<2 else 256
   (p/'raw.jsonl').write_text('\n'.join(json.dumps({'request_id':f'{i}-{j}','usage':{'completion_tokens':tokens},'ttft':.1,'decode_tokens_per_second':2}) for j in range(2)))
  event=Path(self.run.doc['prototype_output'])/'d10_branch_event.json';event.write_text(json.dumps({'method':'Engine._forward_d10_staggered_decode','actual_batch_reqs':2,'actual_can_use_d10_staggered':True,'candidate_commit':m.CANDIDATE,'engine_birth':{'pid':66,'start_ticks':2},'engine_pgid':55}))
 def stop(self,*_):pass
 def alive(self,*_):return False
def setup(tmp):
 api=free_port(); out=tmp/'out'; argv=['ft','serve','--port',str(api),m.FLAG]
 doc={'admit':True,'prototype_rid':m.RID,'candidate':m.CANDIDATE,'d10_flag':m.FLAG,'calls_max':8,'services_max':1,'service':{'argv':argv,'api_port':api,'tcpstore_port':api+1,'endpoint':f'http://127.0.0.1:{api}','cwd':str(tmp)},'prototype_output':str(out),'native_provenance_sha256':m.sha(m.PROVENANCE),'t16_closure':{'kept':True},'d09_completed_terminals':[{'safe_owned_cleanup':True}], 'source_sha256':{n:m.sha(m.HERE/n) for n in ('d10_prototype_owned_parent_v4.py','d10_branch_startup_v4.py','d10_branch_probe_v4.py','d10_aiperf_parse_v4.py','d10_aiperf_runner_v5.py')}}
 admission=tmp/'admission';admission.write_text('{}');os.chmod(admission,0o444);return Deps(tmp,doc),admission,out
def test_v4_uses_ft_serve_and_actual_worker_evidence(tmp_path):
 deps,admission,out=setup(tmp_path);receipt=tmp_path/'launch.json';receipt.write_text(json.dumps({'state':'launched','batch':3,'child':{'pid':77,'start_ticks':1}}));result=m.child(admission,3,receipt,deps);v=json.loads(result.read_text());assert v['verdict']=='not_met' and deps.gate.released
def test_rejects_cli_tcpstore(tmp_path):
 deps,admission,_=setup(tmp_path);deps.run.doc['service']['argv'] += ['--tcpstore-port','5'];
 with pytest.raises(RuntimeError,match='TCPStore'):m.require_admission(admission,deps.run)
def test_raw_parser_rejects_summary_only(tmp_path):
 for i in range(4):
  p=tmp_path/f'profile{i}';p.mkdir();(p/'summary.json').write_text(json.dumps({'completion_tokens':256}))
 with pytest.raises(RuntimeError,match='actual raw response'):m.parser().validate_profiles(tmp_path)
