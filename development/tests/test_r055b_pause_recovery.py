import importlib.util,json
from pathlib import Path
import pytest
ROOT=Path(__file__).parents[1];p=ROOT/'r055b_pause_recovery.py';s=importlib.util.spec_from_file_location('r055b',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Cuda:
 def mem_get_info(self,d):return 7,11
 def max_memory_allocated(self,d):return 13
 def max_memory_reserved(self,d):return 17
class Torch: cuda=Cuda()
def test_records_model_process_memory_before_after_and_error(tmp_path):
 mem=m.ModelProcessMemory(tmp_path/'cuda.jsonl',Torch(),device=2)
 assert m.request_with_memory(mem,'cold_before','u1',lambda:{'ok':True})=={'ok':True}
 with pytest.raises(ValueError):m.request_with_memory(mem,'recovery','u2',lambda:(_ for _ in ()).throw(ValueError('x')))
 rows=[json.loads(x) for x in (tmp_path/'cuda.jsonl').read_text().splitlines()]
 assert [x['event'] for x in rows]==['cold_before_before','cold_before_after','recovery_before','recovery_error']
 assert rows[0]['uid']=='u1' and rows[0]['device']==2 and rows[0]['allocated_peak_bytes']==13
def test_pause_chain_records_all_request_boundaries(tmp_path):
 mem=m.ModelProcessMemory(tmp_path/'cuda.jsonl',Torch())
 result=m.run_pause_cancel_recovery(memory=mem,cold_request=lambda:{'cold':1},pause_request=lambda a,b:{'seconds':a},uid_before='a',uid_pause='b',uid_recovery='c')
 assert result['built_tokens']==32052 and result['actual_input_tokens']==32064 and result['max_tokens']==128 and result['memory_ratio']=='0.88'
 assert [json.loads(x)['event'] for x in (tmp_path/'cuda.jsonl').read_text().splitlines()]==['cold_before_before','cold_before_after','pause_request_before','pause_request_after','pause_cancel_before','pause_cancel_after','recovery_request_before','recovery_request_after']
def test_file_dry_run_has_no_cuda_or_network(tmp_path):
 value=m.file_dry_run(tmp_path/'dry')
 assert all(value[k] is False for k in ('service_started','requests_sent','gpu_lock_taken','batch_allocated'))
 assert (tmp_path/'dry/model_process_cuda.jsonl').is_file()
