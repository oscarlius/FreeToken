set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONPATH=/data2/FreeToken/wt/e1r003st/python /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib, json, os, pathlib, runpy, struct, subprocess
for key in list(os.environ):
 if key.startswith(('FT_DEV_', 'FT_D3_')): os.environ.pop(key)
root=pathlib.Path('/data2/FreeToken')
wt=root/'wt/e1r003st'
commit='c30ae0d7003c3bbbf56867ce74da797332fa7ed5'
assert subprocess.check_output(['git','-C',str(wt),'rev-parse','HEAD'],text=True).strip()==commit
assert not subprocess.check_output(['git','-C',str(wt),'status','--porcelain','--untracked-files=no'],text=True).strip()
source=root/'scripts/agent_trace.py'
assert hashlib.md5(source.read_bytes()).hexdigest()=='f81acb79c3dbc89999f5f76de4c9a070'
agent=runpy.run_path(str(source),run_name='frozen_agent_library')
from freetoken.server.api_models import ChatCompletionRequest
from freetoken.server.openai_api import chat_request_to_genspec
from freetoken.message import TokenizeMsg
from freetoken.tokenizer.tokenize import TokenizeManager
from freetoken.utils import load_tokenizer
model=root/'models/Qwen3.8-Flash-Next-NVFP4-overlay'
manager=TokenizeManager(load_tokenizer(str(model)))
roundroot=pathlib.Path('/data2/_shared/runs/ft_rounds/E1-R003-v2')
forward_path,reverse_path=roundroot/'trace.json',roundroot/'trace_rev.json'
forward=json.loads(forward_path.read_text());reverse=json.loads(reverse_path.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
message_sha=lambda messages:hashlib.sha256(json.dumps(messages,ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:16]
assert len(forward['rounds'])==len(reverse['rounds'])==12
assert {message_sha(r['messages']) for r in forward['rounds']}=={message_sha(r['messages']) for r in reverse['rounds']}
assert forward['tools']==reverse['tools']
rows=[]
for position,item in enumerate(forward['rounds']):
 messages=item['messages'];record=item['record']
 digest=message_sha(messages)
 assert digest==record['messages_sha'] and record['round']==position
 payload=agent['build_payload'](messages,'Qwen3.8-Flash-Next-NVFP4',forward['tools'],True,200)
 spec=chat_request_to_genspec(ChatCompletionRequest.model_validate(payload),{})
 msg=TokenizeMsg(uid=position,text=spec.messages,sampling_params=spec.sampling_params,
                 chat_template_kwargs=spec.chat_template_kwargs,tools=spec.template_tools)
 ids=manager.tokenize([msg])[0].input_ids.tolist()
 assert len(ids)==record['prompt_tokens']
 ids_sha=hashlib.sha256(struct.pack(f'<{len(ids)}i',*ids)).hexdigest()
 rows.append({'round':position,'messages_sha':digest,'prompt_ids':ids,'prompt_length':len(ids),
              'prompt_ids_sha256_int32le':ids_sha,
              'request_sha256':hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest()})
data={'schema':'t10_frontend_tokens/v1','candidate_commit':commit,'rounds':rows,
      'forward_trace_path':str(forward_path),'forward_trace_sha256':sha(forward_path),
      'reverse_trace_path':str(reverse_path),'reverse_trace_sha256':sha(reverse_path),
      'source_agent_trace_sha256':sha(source),'source_agent_trace_md5':hashlib.md5(source.read_bytes()).hexdigest(),
      'construction':'frozen agent build_payload -> ChatCompletionRequest -> chat_request_to_genspec -> TokenizeManager.tokenize',
      'tokenizer_files_sha256':{name:sha(model/name) for name in ['tokenizer.json','tokenizer_config.json','chat_template.jinja']}}
out=root/'runs/dev_D03/t10_frontend_tokens_c30ae0d.json'
with out.open('x',encoding='utf-8') as f: json.dump(data,f,ensure_ascii=False,indent=2);f.write('\n')
print('T10_FRONTEND_MANIFEST',out,sha(out))
print('T10_INPUT_BINDINGS',json.dumps([{k:v for k,v in row.items() if k!='prompt_ids'} for row in rows]))
PY
