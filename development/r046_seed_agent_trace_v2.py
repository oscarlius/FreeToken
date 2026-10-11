#!/usr/bin/env python3
"""Section 12 guard for the hash-pinned candidate agent client; old client stays sealed."""
from __future__ import annotations
import argparse, ast, copy, hashlib, importlib.util, inspect, json, sys
from pathlib import Path
from types import SimpleNamespace

PIN='332a1870378d5bffa4891180280060e70f6135b6acff21b48603a5fc98ad44d9'
WINDOW=98304
RESERVE=2048
LIMIT=WINDOW-RESERVE

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def load(client):
 client=Path(client);raw=client.with_name('_agent_trace_original.py')
 if sha(raw)!=PIN:raise RuntimeError('candidate frozen agent-trace bytes differ')
 spec=importlib.util.spec_from_file_location('t06_window_candidate_client',client);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 return module

def load_frontend(worktree,model_path):
 # Use the actual candidate manager, including effort sanitation and its encode path.
 sys.path.insert(0,str(Path(worktree)/'python'))
 from freetoken.tokenizer.tokenize import TokenizeManager
 from transformers import AutoTokenizer
 frontend=TokenizeManager(AutoTokenizer.from_pretrained(str(model_path),trust_remote_code=True))
 source=Path(worktree)/'python/freetoken/tokenizer/tokenize.py'
 if Path(inspect.getfile(TokenizeManager)).resolve()!=source.resolve():raise RuntimeError('frontend manager was imported from a different candidate')
 artifacts={name:sha(Path(model_path)/name) for name in ('config.json','tokenizer_config.json','chat_template.jinja') if (Path(model_path)/name).is_file()}
 return frontend,{'renderer_path':str(source),'renderer_sha256':sha(source),'model_path':str(model_path),'model_artifact_sha256':artifacts}

class WindowGuard:
 def __init__(self,frontend,seed_sha,frontend_binding,expected=None):
  self.frontend=frontend;self.seed_sha=seed_sha;self.frontend_binding=frontend_binding;self.expected=expected;self.checked=[];self.hit=None
 def check(self,payload,index):
  maximum=payload.get('max_tokens')
  if type(maximum) is not int or not 0<maximum<=RESERVE:raise RuntimeError('window guard completion budget differs')
  msg=SimpleNamespace(uid=0,text=payload['messages'],tools=payload.get('tools'),chat_template_kwargs=payload.get('chat_template_kwargs') or {},images=None,sampling_params=None)
  ids=self.frontend.tokenize([msg])[0].input_ids
  if hasattr(ids,'tolist'):ids=ids.tolist()
  if not isinstance(ids,list) or not ids or any(type(token) is not int or token<0 for token in ids):raise RuntimeError('candidate frontend did not return actual integer input IDs')
  proof={'schema':'ft_t06_actual_input_binding/v2','request_k':index+1,'actual_input_ids_sha256':digest(ids),'actual_prompt_tokens':len(ids),'messages_sha256':digest(payload['messages']),'payload_sha256':digest(payload),'max_tokens':maximum,'completion_reserve_tokens':RESERVE,'max_prompt_tokens':LIMIT,'seed_raw_sha256':self.seed_sha,**self.frontend_binding}
  if len(ids)>LIMIT:
   self.hit={'request_k':index+1,'actual_prompt_tokens':len(ids),'input_binding':proof,'payload':copy.deepcopy(payload)}
   return False
  self.checked.append(proof);return True
 def finish(self,doc):
  rows=doc.get('rounds')
  if not isinstance(rows,list) or len(rows)!=len(self.checked):raise RuntimeError('window checks do not bind every completed request')
  for row,proof in zip(rows,self.checked):
   target=row.get('record',row)
   if target.get('error') or target.get('prompt_tokens')!=proof['actual_prompt_tokens']:raise RuntimeError('service prompt tokens/error differs from actual candidate frontend')
   target['actual_input_binding']=proof
  if self.expected is not None:
   if len(rows)!=self.expected.get('completed_k'):raise RuntimeError('heldout replay completed count differs from producer')
   source_checks=self.expected.get('completed_input_bindings')
   if not isinstance(source_checks,list) or len(source_checks)!=len(self.checked) or any(actual['actual_input_ids_sha256']!=source['actual_input_ids_sha256'] or actual['actual_prompt_tokens']!=source['actual_prompt_tokens'] for actual,source in zip(self.checked,source_checks)):raise RuntimeError('heldout replay actual input IDs differ from producer')
   source_hit=self.expected.get('window_hit')
   if source_hit is not None:
    if not self.checked:raise RuntimeError('heldout producer has no completed request')
    payload=copy.deepcopy(source_hit['payload']);payload['max_tokens']=self.checked[0]['max_tokens']
    if self.check(payload,source_hit['request_k']-1):raise RuntimeError('heldout producer window hit now fits; frontend/source differs')
    if self.hit['input_binding']['actual_input_ids_sha256']!=source_hit['input_binding']['actual_input_ids_sha256'] or self.hit['actual_prompt_tokens']!=source_hit['actual_prompt_tokens']:raise RuntimeError('heldout window hit input IDs differ from producer')
   elif self.hit is not None:raise RuntimeError('heldout replay hit a different window')
  elif self.hit is None and len(rows)!=12:raise RuntimeError('seed trace ended before twelve requests without a window hit')
  result={'schema':'ft_t06_window_completion/v2','window':WINDOW,'completion_reserve_tokens':RESERVE,'max_prompt_tokens':LIMIT,'seed_raw_sha256':self.seed_sha,'completed_k':len(rows),'completed_input_bindings':self.checked,'window_hit':self.hit,'window_hit_count':int(self.hit is not None),'termination':'window_hit' if self.hit else 'completed','not_failure':True}
  doc.setdefault('meta',{})['window_completion']=result
  return result

def install(module,guard):
 """Insert one break before dispatch in the two exact, hash-pinned scientific loops.

 The original tools, histories, records, ACK companion and timed-capture seams
 execute unchanged. This splice is limited to the frozen PIN, not a future reader.
 """
 raw=Path(module._ns['__file__'])
 if sha(raw)!=PIN:raise RuntimeError('window splice source hash differs')
 tree=ast.parse(raw.read_text(encoding='utf-8'));functions=[]
 for name,index in [('cmd_generate','round_i'),('cmd_replay','k')]:
  function=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name==name)
  inserted=0
  for loop in [node for node in ast.walk(function) if isinstance(node,ast.For)]:
   for position,node in enumerate(loop.body):
    if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='payload' for target in node.targets):
     loop.body.insert(position+1,ast.parse(f'if not _section12_window_check(payload, {index}):\n break').body[0]);inserted+=1;break
  if inserted!=1:raise RuntimeError('pinned scientific client dispatch seam differs')
  if name=='cmd_generate':
   warnings=[node for node in function.body if isinstance(node,ast.If) and any(isinstance(part,ast.Constant) and part.value=='meets_min_rounds' for part in ast.walk(node.test))]
   if len(warnings)!=1:raise RuntimeError('pinned scientific client warning seam differs')
   warning=warnings[0]
   warning.test=ast.BoolOp(op=ast.And(),values=[warning.test,ast.UnaryOp(op=ast.Not(),operand=ast.Call(func=ast.Name(id='_section12_window_hit',ctx=ast.Load()),args=[],keywords=[]))])
  functions.append(function)
 module._ns['_section12_window_check']=guard.check
 module._ns['_section12_window_hit']=lambda:guard.hit is not None
 exec(compile(ast.fix_missing_locations(ast.Module(body=functions,type_ignores=[])),str(raw),'exec'),module._ns)
 original=module._write
 def write(path,doc):
  guard.finish(doc);return original(path,doc)
 module._write=write

def main(argv=None):
 parser=argparse.ArgumentParser(add_help=False)
 for flag in ('seed-file','seed-sha256','client','worktree','tokenizer-path','out'):parser.add_argument('--'+flag,required=True)
 parser.add_argument('--rounds',type=int,required=True);parser.add_argument('--max-tokens',type=int,required=True)
 args,rest=parser.parse_known_args(argv)
 if args.rounds!=12 or args.max_tokens!=RESERVE:raise ValueError('T06 requires 12 planned rounds and 2048 max tokens')
 raw=Path(args.seed_file).read_bytes()
 if hashlib.sha256(raw).hexdigest()!=args.seed_sha256:raise RuntimeError('original seed raw SHA differs; no trim or replacement permitted')
 seed=raw.decode('utf-8')
 if not seed:raise ValueError('empty T06 seed')
 module=load(args.client);original=module._ns['TASK_PROMPT'];module._ns['TASK_PROMPT']=seed+'\n\n'+original
 frontend,binding=load_frontend(args.worktree,args.tokenizer_path);guard=WindowGuard(frontend,args.seed_sha256,binding);install(module,guard)
 old=sys.argv[:];sys.argv=[args.client,'generate','--route-evidence','--out',args.out,'--rounds','12','--max-tokens','2048',*rest]
 try:rc=module.main()
 finally:sys.argv=old;module._ns['TASK_PROMPT']=original
 doc=json.loads(Path(args.out).read_text(encoding='utf-8'));rows=doc['rounds']
 if not rows:raise RuntimeError('original seed first request cannot complete in approved window')
 first=rows[0]['messages'][0]['content']
 if first!=seed+'\n\n'+original:raise RuntimeError('actual first wire seed was changed')
 result={'schema':'ft_t06_seed_trace_binding/v2','seed_path':str(Path(args.seed_file)),'seed_raw_sha256':args.seed_sha256,'actual_wire_first_content_sha256':hashlib.sha256(first.encode()).hexdigest(),'actual_wire_messages_sha256':rows[0]['record']['messages_sha'],'rounds':12,'max_tokens':RESERVE,'client_frozen_sha256':PIN,'window_client_sha256':sha(__file__),**doc['meta']['window_completion']}
 result['schema']='ft_t06_seed_trace_binding/v2'
 Path(args.out).with_suffix('.seed_binding.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 return rc

if __name__=='__main__':raise SystemExit(main())
