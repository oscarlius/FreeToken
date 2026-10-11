set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 timeout 180s /data2/FreeToken/venv/bin/python -S - <<'PY'
import hashlib,json,os,pathlib,runpy,subprocess,sys
root=pathlib.Path('/data2/FreeToken')
candidate=root/'wt/e2d03-continuation'
commit='f5067bbe05da51d5f78185213435a8be095a684a'
assert subprocess.check_output(['git','-C',str(candidate),'rev-parse','HEAD'],text=True).strip()==commit
assert not subprocess.check_output(['git','-C',str(candidate),'status','--porcelain','--untracked-files=no'],text=True).strip()
for key in list(os.environ):
 if key.startswith(('FT_DEV_','FT_D3_')):os.environ.pop(key)
sys.path[:0]=[str(candidate/'python'),str(candidate)]
packages=root/'venv/lib/python3.10/site-packages'
assert packages.is_dir()
sys.path.append(str(packages))
import freetoken
assert freetoken.__file__==str(candidate/'python/freetoken/__init__.py')
sha=lambda path:hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
helper_path=root/'runs/dev_D03/selfcheck_f506_96db3ca/d03_gpu_selfcheck_f506.py'
helper_bytes=helper_path.read_bytes()
assert hashlib.sha256(helper_bytes).hexdigest()=='96db3ca98bf40a629342586061b5d0acd21d1fb4e1c47fb8bef0e9b8ea56715b'
helper={'__file__':str(helper_path),'__name__':'ft_f506_input_preparation'}
exec(compile(helper_bytes,str(helper_path),'exec'),helper)
protocol=helper['_protocol']
trace_path=protocol['TRACE']
trace,record,messages=protocol['trace_record'](trace_path)
legacy_path=protocol['LEGACY_REPLAY']
payload=protocol['historical_payload'](trace,messages,json.loads(legacy_path.read_text()))
original_path=root/'scripts/agent_trace.py'
assert hashlib.md5(original_path.read_bytes()).hexdigest()=='f81acb79c3dbc89999f5f76de4c9a070'
original=runpy.run_path(str(original_path),run_name='frozen_trace_input_builder')
assert payload==original['build_payload'](messages,protocol['MODEL'],trace['tools'],True,32)
from freetoken.server.api_models import ChatCompletionRequest
from freetoken.server.openai_api import chat_request_to_genspec
from freetoken.message import TokenizeMsg
from freetoken.tokenizer.tokenize import TokenizeManager
from freetoken.utils import load_tokenizer
print('CPU_TOKENIZER_LOAD',flush=True)
tokenizer=load_tokenizer(str(helper['MODEL_PATH']))
print('CPU_TOKENIZE_BEGIN',flush=True)
spec=chat_request_to_genspec(ChatCompletionRequest.model_validate(payload),{})
message=TokenizeMsg(uid=1,text=spec.messages,sampling_params=spec.sampling_params,
                   chat_template_kwargs=spec.chat_template_kwargs,tools=spec.template_tools)
ids=TokenizeManager(tokenizer).tokenize([message])[0].input_ids.tolist()
print('CPU_TOKENIZE_COMPLETE',len(ids),flush=True)
assert len(ids)==record['prompt_tokens']==21976
vocab_total=len(tokenizer)
assert all(type(value) is int and 0<=value<vocab_total for value in ids)
digest=hashlib.sha256(b''.join(value.to_bytes(4,'little',signed=True) for value in ids)).hexdigest()
data={'schema':helper['RAW_SCHEMA'],'ids':ids,'candidate_commit':commit,
 'candidate_worktree':str(candidate),'trace_sha256':sha(trace_path),'messages_sha':record['messages_sha'],
 'request_sha256':protocol['request_sha'](payload),'raw_ids_sha256':digest,'input_length':len(ids),
 'candidate_tokenizer':{'manager_module':'freetoken.tokenizer.tokenize.TokenizeManager',
  'construction':helper['TOKENIZER_CONSTRUCTION'],
  'source_sha256':{str(relative):sha(candidate/relative) for relative in helper['TOKENIZER_SOURCES']},
  'model_files_sha256':{name:sha(helper['MODEL_PATH']/name) for name in helper['TOKENIZER_FILES'] if (helper['MODEL_PATH']/name).is_file()},
  'absent_model_files':[name for name in helper['TOKENIZER_FILES'] if not (helper['MODEL_PATH']/name).exists()],
  'encoded_ids_sha256_int32le':digest},
 'legacy_replay_sha256':sha(legacy_path),'source_agent_trace_sha256':sha(original_path),
 'imported_freetoken':freetoken.__file__,'gpu_started':False}
output=root/'runs/dev_D03/historical_raw_ids_f5067bb_v2.json'
with output.open('x',encoding='utf-8') as sink:sink.write(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
helper['raw_binding'](output,sha(trace_path),record,protocol['request_sha'](payload),64)
print(json.dumps({'path':str(output),'sha256':sha(output),**{key:value for key,value in data.items() if key!='ids'}},ensure_ascii=False))
PY
