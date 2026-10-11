"""Runtime-only Python operator-boundary evidence for T17 schedule diagnosis."""
from __future__ import annotations
import hashlib, inspect, json, math, types
from pathlib import Path
from typing import Any, Callable
SCHEMA='t17_operator_observe/v2'
def _sha(x): return hashlib.sha256(x).hexdigest()
def _class(x): return f'{type(x).__module__}.{type(x).__qualname__}'
def _bytes(t):
 if not hasattr(t,'detach'): raise TypeError('real tensor byte view required')
 import torch
 # Token-ID leaf rows are scalar integers. Flatten before reinterpreting their
 # storage: PyTorch rejects changing element size on a zero-dimensional view.
 raw=t.detach().to('cpu').contiguous().reshape(-1).view(torch.uint8).flatten()
 try:return raw.numpy().tobytes() # uint8 is safe; never NumPy BF16 conversion.
 except Exception:
  try:return bytes(raw.tolist())
  except Exception as exc:raise TypeError('cannot obtain exact tensor bytes') from exc
def _row_hashes(host,rows):
 """Hash selected leading rows from one contiguous CPU uint8 wire buffer."""
 if not hasattr(host,'detach'):raise TypeError('real tensor byte view required')
 import torch
 row_bytes=math.prod(tuple(int(x) for x in host.shape[1:]))*host.element_size()
 wire=host.view(torch.uint8).reshape(-1)
 try:
  raw=wire.numpy().tobytes()
 except Exception:
  try:raw=bytes(wire.tolist())
  except Exception as exc:raise TypeError('cannot obtain exact tensor row bytes') from exc
 view=memoryview(raw)
 return [_sha(view[i*row_bytes:(i+1)*row_bytes]) for i in rows]
def _source(owner,name):
 cls=type(owner);out={'class':_class(owner),'method':name,'qualname':getattr(getattr(cls,name,None),'__qualname__',name)}
 p=inspect.getsourcefile(cls)
 if p and Path(p).is_file():out.update(source_file=str(p),source_sha256=_sha(Path(p).read_bytes()))
 return out

class OperatorObserver:
 def __init__(self,output_dir,*,boundary,query_tokens,target_input_sha,snapshot_rows=64,sink=lambda _:None):
  self.output_dir=Path(output_dir);self.boundary=int(boundary);self.query_tokens=int(query_tokens);self.target_input_sha=str(target_input_sha);self.snapshot_rows=int(snapshot_rows);self.sink=sink
  self.bindings={};self.identity=None;self.records=[];self.errors=[];self._wrapped=set();self._occ={};self._final=False
 def bind_query(self,uid,input_sha,input_numel):
  if not isinstance(input_numel,int) or input_numel!=self.query_tokens or not input_sha:raise ValueError('exact TokenizerMsg query binding required')
  if str(input_sha)!=self.target_input_sha:raise ValueError('TokenizerMsg token SHA differs')
  key=str(uid)
  if key in self.bindings:raise ValueError('duplicate TokenizerMsg UID binding')
  self.bindings[key]={'input_sha':str(input_sha),'input_numel':input_numel}
 def _active(self,batch):
  if bool(getattr(batch,'is_decode',False)) or getattr(batch,'is_prefill',True) is False:return None
  reqs=getattr(batch,'reqs',None)
  if not reqs:return None
  targets=[r for r in reqs if str(getattr(r,'uid',object())) in self.bindings]
  # A donor or another request in the physical batch is not evidence about the
  # bound query.  Only multiple *bound* requests make attribution ambiguous.
  if not targets:return None
  if len(targets)!=1:raise ValueError('multiple bound target UIDs in one operator batch')
  r=targets[0]
  try:uid=str(r.uid);cached=int(r.cached_len);device=int(r.device_len);extend=int(r.extend_len);slot=int(r.linear_slot_idx)
  except Exception:return None
  if cached<0 or device<cached or device-cached!=extend:raise ValueError('incoherent target batch coordinates')
  # Scheduled references use the query UID for donor segments too. The donor
  # computes L+1 before rewinding to L; its overlapping row is not continuation.
  if cached<self.boundary:return None
  start,stop=max(cached,self.boundary),min(device,self.query_tokens)
  if start>=stop:return None
  ident={'uid':uid,'slot':slot}
  if self.identity is None:self.identity=ident
  elif self.identity!=ident:raise ValueError('UID/slot drift')
  return r,list(range(start-cached,stop-cached)),list(range(start,stop))
 def capture(self,owner,path,method,phase,value,batch):
  try:
   selected=self._active(batch)
   if selected is None:return
   req,rows,positions=selected
   # Model graph wrappers also see weights, routing tables, and reduced outputs.
   # This observer records only Python leaf boundaries whose leading dimension is
   # the actual token-row extent; other values are explicitly out of scope.
   if not hasattr(value,'shape') or len(value.shape)<1 or int(value.shape[0])!=int(req.extend_len):
    self.sink({'kind':'operator-skip','path':path,'operator':method,'phase':phase,
               'absolute_positions':positions,'reason':'not-token-row-leaf',
               'shape':list(getattr(value,'shape',()))});return
   host=value.detach().to('cpu').contiguous()
   row_hash=_row_hashes(host,rows)
   combined=_sha(''.join(row_hash).encode())
   keep=rows[:min(self.snapshot_rows,len(rows))]; snap=host[keep].clone()
   key=(path,method,phase);occ=self._occ.get(key,0)+1;self._occ[key]=occ
   self.output_dir.mkdir(parents=True,exist_ok=True);name=f'op_{self.identity["uid"]}_{len(self.records)}_{phase}.pt';file=self.output_dir/name
   if file.exists():raise ValueError('refusing to replace operator snapshot')
   import torch
   with file.open('xb') as f:torch.save(snap,f)
   rec={'event':len(self.records),'path':path,'layer_idx':_layer(path),'operator':_source(owner,method),'phase':phase,'occurrence':occ,
        'uid':self.identity['uid'],'slot':self.identity['slot'],'cached_tokens':int(req.cached_len),'device_tokens':int(req.device_len),'extend_tokens':int(req.extend_len),
        'absolute_positions':positions,'shape':list(value.shape),'dtype':str(value.dtype),'row_sha256':row_hash,'byte_sha256':combined,
        'snapshot_rows':len(keep),'file':name,'file_sha256':_sha(file.read_bytes())}
   self.records.append(rec);self.sink({'kind':'operator-capture',**rec})
  except Exception as exc:self.errors.append(str(exc))
 def finalize(self,uid):
  if self._final:raise ValueError('operator observer finalized twice')
  self._final=True
  if self.errors:raise ValueError('; '.join(self.errors))
  if self.identity is None or str(uid)!=self.identity['uid'] or not self.records:raise ValueError('no target physical operator evidence')
  receipt={'schema':SCHEMA,'boundary':self.boundary,'query_tokens':self.query_tokens,'target_input_sha':self.target_input_sha,**self.identity,'records':self.records,'scope':'Python method boundaries only; internal CUDA kernels are not observed'}
  p=self.output_dir/f'op_{uid}_receipt.json'
  with p.open('x',encoding='utf8') as f:json.dump(receipt,f,sort_keys=True,indent=2);f.write('\n')
  receipt.update(receipt_file=p.name,receipt_sha256=_sha(p.read_bytes()));return receipt

def _layer(path):
 for part in path.split('.'):
  if part.isdigit():return int(part)
 return None
def _wrap(obs,owner,path,name,get_batch):
 if (id(owner),name) in obs._wrapped:return
 original=getattr(owner,name,None)
 if not callable(original):return
 def wrapped(this,*args,**kw):
  batch=get_batch();value=args[0] if args else kw.get('x')
  if value is not None:obs.capture(owner,path,name,'input',value,batch)
  result=original(*args,**kw);out=result[0] if isinstance(result,tuple) and result else result
  if out is not None:obs.capture(owner,path,name,'output',out,batch)
  return result
 setattr(owner,name,types.MethodType(wrapped,owner));obs._wrapped.add((id(owner),name))
def _walk(value,path='model',seen=None):
 seen=set() if seen is None else seen
 if id(value) in seen:return
 seen.add(id(value));yield path,value
 if isinstance(value,(list,tuple)):
  for i,x in enumerate(value):yield from _walk(x,f'{path}.{i}',seen)
 elif hasattr(value,'__dict__'):
  for k,x in value.__dict__.items():
   if isinstance(x,(str,bytes,int,float,bool,type(None))):continue
   if isinstance(x,dict):
    for n,y in x.items():yield from _walk(y,f'{path}.{k}.{n}',seen)
   else:yield from _walk(x,f'{path}.{k}',seen)
def install(model,get_batch:Callable[[],Any],output_dir,boundary,query_tokens,target_input_sha,*,snapshot_rows=64,sink=lambda _:None):
 obs=OperatorObserver(output_dir,boundary=boundary,query_tokens=query_tokens,target_input_sha=target_input_sha,snapshot_rows=snapshot_rows,sink=sink);wrapped=[]
 for path,obj in _walk(model):
  # Graph path, not module-name filtering: includes LinearReplicated/embedding.
  if callable(getattr(obj,'forward',None)):_wrap(obs,obj,path,'forward',get_batch);wrapped.append(path+'.forward')
  for name in ('mix','combine','_down','_short_conv'):
   if callable(getattr(obj,name,None)):_wrap(obs,obj,path,name,get_batch);wrapped.append(path+'.'+name)
  for attr in ('kernel','quant_method','method'):
   child=getattr(obj,attr,None)
   if child is not None and callable(getattr(child,'forward',None)):_wrap(obs,child,path+'.'+attr,'forward',get_batch);wrapped.append(path+'.'+attr+'.forward')
 if not wrapped:raise ValueError('no physical Python operator graph was discoverable')
 obs.structure={'wrapped':wrapped,'scope':'Python leaf method boundaries with token-row outputs only; internal CUDA kernels, non-token tensors, and unwrapped native calls are not observed'};return obs
def _load(directory):
 paths=sorted(Path(directory).glob('op_*_receipt.json'))
 if len(paths)!=1:raise ValueError('exactly one operator receipt required')
 data=json.loads(paths[0].read_text())
 calls={}
 for index,rec in enumerate(data.get('records',[])):
  logical=(rec.get('path'),rec.get('operator',{}).get('method'),rec.get('phase'))
  calls[logical]=calls.get(logical,0)+1
  if rec.get('event')!=index or rec.get('occurrence')!=calls[logical]:
   raise ValueError('duplicate or reordered physical operator capture')
  p=Path(directory)/rec['file']
  if not p.is_file() or p.is_symlink() or _sha(p.read_bytes())!=rec.get('file_sha256'):raise ValueError('physical snapshot checksum differs')
  if len(rec.get('row_sha256',[]))!=len(rec.get('absolute_positions',[])):raise ValueError('incomplete token-row hash coverage')
  if len(set(rec.get('absolute_positions',[])))!=len(rec.get('absolute_positions',[])):raise ValueError('duplicate absolute row in one operator capture')
 return data
def compare(warmdir,refdir):
 warm,ref=_load(warmdir),_load(refdir)
 for k in ('boundary','query_tokens','target_input_sha'):
  if warm.get(k)!=ref.get(k):raise ValueError('incompatible operator receipts: '+k)
 # A long layer-major request may split differently, but its observed operator
 # rows must still cover precisely the same absolute positions.  Keep warm's
 # physical event order for first-difference attribution; never sort topology.
 def rows(records):
  out={};ordered=[];calls={}
  for record in records:
   logical=(record.get('path'),record.get('layer_idx'),json.dumps(record.get('operator'),sort_keys=True),record.get('phase'))
   meta=(record.get('dtype'),tuple(record.get('shape',[])[1:]))
   for position,digest in zip(record.get('absolute_positions',[]),record.get('row_sha256',[])):
    # A rotary/HC module may legitimately run several times for one row.
    # Count calls per absolute row, so Q/K calls remain distinct while a
    # different physical chunk partition can still align the same token rows.
    identity=(logical,position);calls[identity]=calls.get(identity,0)+1
    key=(logical,position,calls[identity]);out[key]=(meta,digest)
    ordered.append(key)
  return out,ordered
 left,warm_order=rows(warm['records']);right,_=rows(ref['records'])
 if not left or not right:raise ValueError('nonempty operator evidence required')
 if set(left)!=set(right):raise ValueError('operator absolute-row coverage differs')
 for key in left:
  if left[key][0]!=right[key][0]:raise ValueError('operator dtype or per-row shape differs')
 first=None
 for key in warm_order:
  if left[key][1]!=right[key][1]:
    (path,layer,operator,phase),position,ordinal=key
    first={'path':path,'layer_idx':layer,'operator':json.loads(operator),'phase':phase,
           'absolute_tokenrow':position,'call_ordinal':ordinal,'warm_row_sha256':left[key][1],
           'reference_row_sha256':right[key][1]};break
 return {'schema':SCHEMA,'first_layer_operator_difference':first,'equal':first is None,'scope':'Python method boundaries only; not CUDA kernel proof'}
