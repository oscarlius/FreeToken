set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 TOKENIZERS_PARALLELISM=false timeout 180s /data2/FreeToken/venv/bin/python -S - <<'PY'
import hashlib,json,pathlib,runpy,struct,subprocess,sys
root=pathlib.Path('/data2/FreeToken');tree=root/'wt/e2base'
round_dir=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R002')
sha=lambda path:hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
assert subprocess.check_output(['git','-C',str(tree),'rev-parse','HEAD'],text=True).strip()=='23f2e2caa3395837c9474735ffc83321f3b9b5a1'
assert sha(round_dir/'round.json')=='53b1849cc68584d488ae7f7388e91c169c20575d9bb0f2b64a52d80692c38427'
assert sha(round_dir/'MANIFEST.sha256')=='116114bb330db38c4f1163a972fe5d4c7a8da9b943719950e79b3a39e5bb3ad6'
sys.path[:0]=[str(tree/'python'),str(tree)]
sys.path.append(str(root/'venv/lib/python3.10/site-packages'))
import freetoken,torch
assert freetoken.__file__==str(tree/'python/freetoken/__init__.py')
from freetoken.server.api_models import ChatCompletionRequest
from freetoken.server.openai_api import chat_request_to_genspec
from freetoken.message import TokenizeMsg
from freetoken.tokenizer.tokenize import TokenizeManager
from freetoken.utils import load_tokenizer
builder_path=root/'scripts/agent_trace.py'
assert hashlib.md5(builder_path.read_bytes()).hexdigest()=='f81acb79c3dbc89999f5f76de4c9a070'
builder=runpy.run_path(str(builder_path),run_name='read_only_historical_input_builder')
trace_path=round_dir.parent/'E1-R003-v2/trace_rev.json'
trace=json.loads(trace_path.read_text());thinking=bool(trace.get('meta',{}).get('params',{}).get('thinking',True))
tokenizer_path=root/'models/Qwen3.8-Flash-Next-NVFP4-overlay'
tokenizer=load_tokenizer(str(tokenizer_path));manager=TokenizeManager(tokenizer)
arm_docs={name:json.loads((round_dir/name/'replay.json').read_text()) for name in ('R4096','RLM')}
report={'schema':'ft_p0_ngram_input_read/v1','gpu_started':False,'server_files_mutated':False,
 'source_commit':'23f2e2caa3395837c9474735ffc83321f3b9b5a1','imported_freetoken':freetoken.__file__,
 'trace_sha256':sha(trace_path),'builder_sha256':sha(builder_path),'thinking':thinking,
 'tokenizer_files':{name:sha(tokenizer_path/name) for name in ('tokenizer.json','tokenizer_config.json','special_tokens_map.json','chat_template.jinja') if (tokenizer_path/name).is_file()},
 'replay_meta':{name:doc.get('meta') for name,doc in arm_docs.items()},'inputs':[],'donations':{},'semantic_comparison':[]}
for index,record in enumerate(trace['rounds']):
 messages=record['messages'];digest=builder['messages_digest'](messages)
 assert digest==record['record']['messages_sha']
 replay={}
 for name,doc in arm_docs.items():
  found=[row for row in doc['rounds'] if row.get('messages_sha')==digest]
  assert len(found)==1 and found[0].get('trace_messages_sha')==digest and found[0]['round']==index
  replay[name]={key:found[0].get(key) for key in ('round','prompt_tokens','cached_tokens','completion_tokens','messages_sha','dry_run','error')}
 payload=builder['build_payload'](messages,'Qwen3.8-Flash-Next-NVFP4',trace.get('tools') or builder['tool_specs'](),thinking,32)
 spec=chat_request_to_genspec(ChatCompletionRequest.model_validate(payload),{})
 msg=TokenizeMsg(uid=index,text=spec.messages,sampling_params=spec.sampling_params,
  chat_template_kwargs=spec.chat_template_kwargs,tools=spec.template_tools)
 ids=manager.tokenize([msg])[0].input_ids.tolist()
 assert all(row['prompt_tokens']==len(ids) and row['dry_run'] is False and not row['error'] for row in replay.values())
 length=(len(ids)//64)*64
 report['inputs'].append({'trace_index':index,'messages_sha':digest,'actual_frontend_length':len(ids),
  'ids_int32le_sha256':hashlib.sha256(struct.pack(f'<{len(ids)}i',*ids)).hexdigest(),
  'deepest_aligned_length':length,'expected_last_two_at_aligned_length':ids[length-2:length],
  'selected_boundary_contexts':{str(L):ids[L-2:L] for L in (12416,18944,12736) if L<=len(ids)},'replay_binding':replay})
for name in ('R4096','RLM'):
 path=round_dir/name/'dump/index.jsonl'
 rows=[json.loads(line) for line in path.read_text().splitlines() if line]
 report['donations'][name]={'index_sha256':sha(path),
  'selected_rows':[row for row in rows if row.get('kind')=='donate' and row.get('length') in (12416,18944,12736)]}
 for row in rows:
  if row.get('kind')!='donate':continue
  candidates=[item for item in report['inputs'] if item['deepest_aligned_length']==row['length']]
  assert len(candidates)==1
  expected=candidates[0]
  tensor_path=path.parent/row['files']['slot:ple_ngram_ctx']
  tensor=torch.load(tensor_path,map_location='cpu',weights_only=True)
  assert tensor.dtype==torch.int32 and list(tensor.shape)==[1,1,2]
  actual=tensor.flatten().tolist()
  admissible={tuple(item['selected_boundary_contexts'][str(row['length'])]) for item in report['inputs']
   if str(row['length']) in item['selected_boundary_contexts']}
  report['semantic_comparison'].append({'arm':name,'length':row['length'],'uid':row['uid'],'seq':row['seq'],
   'trace_index':expected['trace_index'],'messages_sha':expected['messages_sha'],'input_ids_sha256':expected['ids_int32le_sha256'],
   'expected':expected['expected_last_two_at_aligned_length'],'actual':actual,
   'equal':actual==expected['expected_last_two_at_aligned_length'],'tensor_sha256':sha(tensor_path),
   'eligible_trace_prefix_contexts':sorted([list(value) for value in admissible])})
assert not torch.cuda.is_initialized()
print(json.dumps(report,ensure_ascii=False,allow_nan=False))
PY
