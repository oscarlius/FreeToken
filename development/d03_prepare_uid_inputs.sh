set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONPATH=/data2/FreeToken/wt/e1r003st/python /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib, json, os, pathlib, runpy, subprocess
for key in list(os.environ):
 if key.startswith(('FT_DEV_', 'FT_D3_')):
  os.environ.pop(key)
root=pathlib.Path('/data2/FreeToken')
candidate=root/'wt/e1r003st'
commit='c30ae0d7003c3bbbf56867ce74da797332fa7ed5'
assert subprocess.check_output(['git','-C',str(candidate),'rev-parse','HEAD'],text=True).strip()==commit
assert not subprocess.check_output(['git','-C',str(candidate),'status','--porcelain','--untracked-files=no'],text=True).strip()
sha=lambda p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
source=root/'scripts/agent_trace.py'
assert hashlib.md5(source.read_bytes()).hexdigest()=='f81acb79c3dbc89999f5f76de4c9a070'
original=runpy.run_path(str(source),run_name='original_trace_library')
assert original['REPLAY_MAX_TOKENS']==32
helper=runpy.run_path(str(root/'runs/dev_D03/d03_gpu_selfcheck.py'),run_name='selfcheck_library')
assert helper['CANDIDATE_COMMIT']==commit
trace_path=helper['TRACE']
trace,record,messages=helper['trace_record'](trace_path)
legacy_path=helper['LEGACY_REPLAY']
legacy=json.loads(legacy_path.read_text(encoding='utf-8'))
payload=helper['historical_payload'](trace,messages,legacy)
expected=original['build_payload'](messages,helper['MODEL'],trace['tools'],True,32)
assert payload==expected,'G4/G5 request differs from actual frozen historical replay construction'

from freetoken.server.api_models import ChatCompletionRequest
from freetoken.server.openai_api import chat_request_to_genspec
from freetoken.message import TokenizeMsg
from freetoken.tokenizer.tokenize import TokenizeManager
from freetoken.utils import load_tokenizer
model=root/'models/Qwen3.8-Flash-Next-NVFP4-overlay'
tokenizer=load_tokenizer(str(model))
spec=chat_request_to_genspec(ChatCompletionRequest.model_validate(payload), {})
message=TokenizeMsg(uid=1,text=spec.messages,sampling_params=spec.sampling_params,
                    chat_template_kwargs=spec.chat_template_kwargs,tools=spec.template_tools)
ids=TokenizeManager(tokenizer).tokenize([message])[0].input_ids.tolist()
total_vocab=len(tokenizer)
print('CPU_TOKENIZER_INPUT',json.dumps({'input_length':len(ids),'expected_length':record['prompt_tokens'],
      'min_id':min(ids),'max_id':max(ids),'vocab_size':tokenizer.vocab_size,'tokenizer_length':total_vocab,
      'added_vocab_count':len(tokenizer.get_added_vocab()),
      'above_base_vocab_ids':sorted({value for value in ids if value>=tokenizer.vocab_size})}))
assert len(ids)==record['prompt_tokens'],(len(ids),record['prompt_tokens'])
assert all(type(value) is int and 0<=value<total_vocab for value in ids),'raw input contains IDs beyond complete tokenizer vocabulary'
packed=b''.join(value.to_bytes(4,'little',signed=True) for value in ids)
out=root/'runs/dev_D03/historical_raw_ids_c30ae0d.json'
data={'ids':ids,'trace_sha256':sha(trace_path),'messages_sha':record['messages_sha'],
      'request_sha256':helper['request_sha'](payload),'raw_ids_sha256':hashlib.sha256(packed).hexdigest(),
      'input_length':len(ids),'candidate_commit':commit,'source_agent_trace_sha256':sha(source),
      'legacy_replay_sha256':sha(legacy_path),
      'construction':'ChatCompletionRequest -> chat_request_to_genspec -> TokenizeManager.tokenize',
      'tokenizer_files_sha256':{name:sha(model/name) for name in
        ['tokenizer.json','tokenizer_config.json','special_tokens_map.json','chat_template.jinja'] if (model/name).is_file()}}
with out.open('x',encoding='utf-8') as f:
 json.dump(data,f,ensure_ascii=False,indent=2,allow_nan=False)
 f.write('\n')
helper['raw_binding'](out,sha(trace_path),record,helper['request_sha'](payload),64)
print('D03 EXACT HISTORICAL RAW INPUT PREPARED',out)
print(json.dumps({key:value for key,value in data.items() if key!='ids'},ensure_ascii=False))
print('RAW_MANIFEST_SHA256',sha(out))
PY
