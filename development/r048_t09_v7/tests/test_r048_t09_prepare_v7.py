"""R048 v7 ordinary-wire and terminal CPU contracts; no network/GPU/service."""
from __future__ import annotations
import importlib.util, json, sys, types
from pathlib import Path
import pytest

HERE=Path(__file__).parents[1]
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,HERE/path);mod=importlib.util.module_from_spec(spec);assert spec.loader;sys.modules[name]=mod;spec.loader.exec_module(mod);return mod

def test_v7_closure_uses_sorted_candidate_wire_and_terminal_client():
 tool=load('r048_prepare_v7',Path('r048_t09_prepare_v7.py'))
 assert tool.ORDINARY_CLIENT.name=='r048_t09_ordinary_client_v3.py'
 assert tool.ORDINARY_ADAPTER.name=='r048_t09_ordinary_adapter_v3.py'
 assert tool.ORDINARY_CLIENT in tool.RUNTIME_SOURCES
 assert tool.ORDINARY_ADAPTER in tool.RUNTIME_SOURCES


def test_candidate_wire_is_sorted_before_actual_api_model_and_tokenizer(monkeypatch,tmp_path):
 tool=load('r048_prepare_wire',Path('r048_t09_prepare_v7.py'))
 root=tmp_path/'wt';(root/'python'/'freetoken'/'tokenizer').mkdir(parents=True);(root/'python'/'freetoken'/'server').mkdir(parents=True)
 # A minimal candidate-package fixture records the wire passed to model_validate.
 for rel in ('freetoken/__init__.py','freetoken/tokenizer/__init__.py','freetoken/server/__init__.py'):(root/'python'/rel).write_text('')
 (root/'python'/'freetoken'/'tokenizer'/'tokenize.py').write_text('class TokenizeManager:\n def __init__(self,x): pass\n def tokenize(self,msgs):\n  return [type("R",(),{"input_ids":[7,8,9]})()]\n')
 (root/'python'/'freetoken'/'server'/'api_models.py').write_text('class Request(dict):\n __getattr__=dict.__getitem__\nclass ChatCompletionRequest:\n @classmethod\n def model_validate(cls,x):\n  cls.wire=x; return Request(x)\n')
 (root/'python'/'freetoken'/'server'/'openai_api.py').write_text('def chat_request_to_genspec(x,_):\n p=type("P",(),{"ignore_eos":x["ignore_eos"],"max_tokens":x["max_tokens"],"stop_strs":[] if x["stop"] is None else [x["stop"]]})()\n return type("S",(),{"messages":x["messages"],"template_tools":None,"chat_template_kwargs":x["chat_template_kwargs"],"sampling_params":p})()\n')
 (root/'python'/'freetoken'/'message.py').write_text('class TokenizeMsg:\n def __init__(self,**kw): self.__dict__.update(kw)\n')
 fake=types.ModuleType('transformers');fake.AutoTokenizer=type('AutoTokenizer',(),{'from_pretrained':staticmethod(lambda *_a,**_k:object())});monkeypatch.setitem(sys.modules,'transformers',fake)
 for name in list(sys.modules):
  if name=='freetoken' or name.startswith('freetoken.'): monkeypatch.delitem(sys.modules,name,raising=False)
 payload=tool.exact_token_payload('fixture','x',64);payload['z']=1
 wire,binding=tool.candidate_frontend_binding(root,tmp_path/'tokenizer',payload)
 assert list(wire)==['chat_template_kwargs','ignore_eos','max_tokens','messages','model','stop','stream','stream_options','temperature','z']
 assert binding['input_tokens']==3 and len(binding['input_ids_sha256'])==64
 assert binding['exact_token_contract']=={'ignore_eos':True,'max_tokens':64,'stop_strs':[]}


def test_exact_token_payload_refuses_eos_or_custom_stop_drift(tmp_path):
 tool=load('r048_exact_wire',Path('r048_t09_prepare_v7.py'))
 payload=tool.exact_token_payload('fixture','text',512)
 assert payload['ignore_eos'] is True and payload['stop'] is None and payload['max_tokens']==512
 with pytest.raises(RuntimeError,match='exact-token payload'):
  tool.candidate_frontend_binding(tmp_path,tmp_path,payload|{'ignore_eos':False})


def test_tool_calls_normalizes_only_to_worker_stop_and_other_finish_rejects():
 client=load('r048_client_v3',Path('r048_t09_ordinary_client_v3.py'))
 assert client._terminal_binding('tool_calls','stop')['normalized']=='tool_calls_api_terminal_to_worker_decode_stop'
 assert client._terminal_binding('length','length')['normalized']=='identical'
 with pytest.raises(ValueError,match='incompatible'):client._terminal_binding('tool_calls','length')
 rows=[{'finished':False,'finish_reason':None},{'finished':True,'finish_reason':'stop'}]
 assert client._validate_terminal(rows,'tool_calls')['worker_finish_reason']=='stop'
 with pytest.raises(ValueError,match='before terminal'):client._validate_terminal([{'finished':False,'finish_reason':'stop'},{'finished':True,'finish_reason':'stop'}],'tool_calls')


def test_adapter_requires_explicit_normalized_terminal_binding():
 adapter=load('r048_adapter_v3',Path('r048_t09_ordinary_adapter_v3.py'))
 rows=[{'uid':3,'completion_tokens_delta':1,'next_token':1},{'uid':3,'completion_tokens_delta':1,'next_token':2,'finish_reason':'stop'}]
 binding={'schema':'ft_r048_t09_ordinary_binding/v3','verdict':'worker_input_uid_token_bound','worker_input':{'input_tokens':2,'input_ids_sha256':'a'*64},'api':{'uid':3,'usage':{'prompt_tokens':2,'completion_tokens':2},'finish_reason':'tool_calls'},'token_sidecar':{'events':rows},'terminal_binding':{'api_finish_reason':'tool_calls','worker_finish_reason':'stop','normalized':'tool_calls_api_terminal_to_worker_decode_stop'}}
 assert adapter.ordinary_binding(binding)['terminal_binding']['normalized'].startswith('tool_calls')
 binding['terminal_binding']['worker_finish_reason']='length'
 with pytest.raises(RuntimeError,match='terminal binding differs'):adapter.ordinary_binding(binding)


def test_v7_admission_requires_r049a_and_preserves_failed_r049_metadata():
 tool=load('r048_gate_v7',Path('r048_t09_prepare_v7.py'))
 assert tool.GATES==(("E2-R040","failed_harness"),("E2-R050-gate-D15","kept"),("E2-R051-gate-D08","kept"),("E2-R049a","measured"))
 assert tool.FAILED_METADATA_GATES==(("E2-R049","failed_harness"),)


def test_trace_rejects_all_zero_or_partial_zero_native_task(tmp_path):
 tool=load('r048_trace_v7',Path('r048_t09_prepare_v7.py'))
 def row(cpu):
  return {'trace_mode_perturbs_timing':True,'cpu_task':cpu,'pcie_copy':{'status':'measured_cuda_event','event_elapsed_ms':0.0,'completion_observed_host_ns':1}}
 path=tmp_path/'trace.jsonl';path.write_text(json.dumps(row({'start_ns':0,'end_ns':0,'barrier_wait_ns_total':0}))+'\n')
 with pytest.raises(RuntimeError,match='no candidate no-submit field'):tool.trace_evidence(path)
 path.write_text(json.dumps(row({'start_ns':1,'end_ns':1,'barrier_wait_ns_total':0}))+'\n')
 with pytest.raises(RuntimeError,match='invalid native completion state'):tool.trace_evidence(path)
