"""D16 exact-ID workload collector; diagnostic only, never starts a service."""
from __future__ import annotations
import concurrent.futures,hashlib,json,struct,uuid
from pathlib import Path
class WorkloadError(ValueError):pass
def _write(root,name,data):
 p=Path(root)/name;p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb') as stream:stream.write(data)
 return str(p.relative_to(root))
def collect(exact_id_request, inputs, *, slots, root, observations_path, mode='all', repetitions=2, repetition_start=0, slot_offset=0):
 """Call retained exact_id_request(ids,...); it owns /internal/t17/exact-ids."""
 if mode not in ('all','batch','alone') or type(repetitions)is not int or repetitions not in (1,2):
  raise WorkloadError('explicit batch/alone mode and one or two repetitions required')
 if type(repetition_start)is not int or repetition_start not in (0,1) or type(slot_offset)is not int or slot_offset<0:
  raise WorkloadError('explicit repetition index and nonnegative slot offset required')
 root=Path(root); root.mkdir(parents=True,exist_ok=False)
 (root/'responses').mkdir()
 def one(ids,label):
  if not isinstance(ids,list) or not ids or any(type(x)is not int for x in ids):raise WorkloadError('typed exact input IDs required')
  tag=str(uuid.uuid4()); req=_write(root,f'requests/{tag}.json',json.dumps({'label':label,'input_ids':ids}).encode())
  try:
   record=exact_id_request(ids,max_tokens=128,output_path=root/f'responses/{tag}.json',observations_path=Path(observations_path))
   response=record.get('response',{}) if isinstance(record,dict) else {}
   expected=hashlib.sha256(struct.pack('<%di'%len(ids),*ids)).hexdigest()
   if (record.get('status')!=200 or response.get('finished') is not True
       or type(response.get('uid')) is not int or response['uid']<0
       or response.get('input_ids_sha256')!=expected
       or response.get('usage',{}).get('completion_tokens')!=128):
    raise WorkloadError('actual exact-ID terminal/input/output binding differs')
  except BaseException as e:
   _write(root,f'failures/{tag}.txt',repr(e).encode());raise
  return {'label':label,'uid':response['uid'],'request':req,'response_path':f'responses/{tag}.json','input_ids_sha256':response['input_ids_sha256']}
 if len(inputs)!=slots:raise WorkloadError('slot count differs')
 batch=[]
 for rep in range(repetition_start,repetition_start+(repetitions if mode in ('all','batch') else 0)):
  with concurrent.futures.ThreadPoolExecutor(max_workers=slots) as pool:batch.append(list(pool.map(lambda a:one(a[1],f'batch-{rep}-slot-{a[0]+slot_offset}'),enumerate(inputs))))
 alone=[[one(ids,f'alone-{rep}-slot-{i+slot_offset}') for i,ids in enumerate(inputs)] for rep in range(repetition_start,repetition_start+(repetitions if mode in ('all','alone') else 0))]
 _write(root,'collection.json',json.dumps({'schema':'ft_d16_exact_id_collection/v1','admitted':False,'physical_batch_verified':False,'mode':mode,'slots':slots,'repetitions':repetitions,'observations_path':str(observations_path),'batch':batch,'alone':alone}).encode())
 return {'root':str(root),'batch':batch,'alone':alone}
def finalize(collection, request_evidence, native_capture):
 if not isinstance(native_capture,dict) or native_capture.get('terminal')!='complete':return {'verdict':'unverified','reason':'native capture incomplete'}
 try:
  for row in [x for group in collection['batch']+collection['alone'] for x in group]:request_evidence(row['uid'])
 except Exception:return {'verdict':'unverified','reason':'native observations do not bind collected UIDs'}
 return {'verdict':'unverified','reason':'concurrent observation ranges require UID-scoped native batch/slot reader; serial receipts cannot prove physical batching'}
def parking_or_interleave(*a,**k):return {'verdict':'unverified','reason':'no supported native lifecycle trigger'}
