import importlib.util,json,sys
from pathlib import Path
from types import SimpleNamespace
import pytest
PATH=Path(__file__).parents[1]/'t17_operator_observe.py';SPEC=importlib.util.spec_from_file_location('operator_observe',PATH);MODULE=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(MODULE)

@pytest.mark.parametrize("dtype", ["int32", "int64", "float32", "bfloat16"])
def test_real_scalar_rows_keep_exact_storage_bytes(dtype):
 torch=pytest.importorskip('torch')
 value=torch.tensor(7,dtype=getattr(torch,dtype))
 expected=value.reshape(1).view(torch.uint8).numpy().tobytes()
 assert MODULE._bytes(value)==expected

@pytest.mark.parametrize("dtype", ["float32", "bfloat16"])
def test_row_hashes_match_legacy_bytes_for_contiguous_and_noncontiguous(dtype):
 torch=pytest.importorskip('torch')
 base=torch.arange(24,dtype=torch.float32).reshape(4,3,2).to(getattr(torch,dtype))
 for value in (base,base.transpose(1,2)):
  rows=[0,2,3]
  host=value.detach().to('cpu').contiguous()
  assert MODULE._row_hashes(host,rows)==[MODULE._sha(MODULE._bytes(value[i])) for i in rows]

def test_row_hashes_preserve_empty_inner_dimension_bytes():
 torch=pytest.importorskip('torch')
 value=torch.empty((3,0,4),dtype=torch.bfloat16)
 assert MODULE._row_hashes(value.contiguous(),[0,1,2])==[MODULE._sha(b'')]*3

def test_real_token_id_leaf_can_finalize_receipt(tmp_path):
 torch=pytest.importorskip('torch')
 observer=MODULE.OperatorObserver(tmp_path,boundary=10,query_tokens=14,target_input_sha='ids')
 observer.bind_query(7,'ids',14)
 class Owner:pass
 observer.capture(Owner(),'model.embedding','forward','input',torch.tensor([1,2,3,4],dtype=torch.int32),batch(10,14))
 receipt=observer.finalize(7)
 assert len(receipt['records'][0]['row_sha256'])==4
 assert (tmp_path/receipt['receipt_file']).is_file()

class Tensor:
 def __init__(self,rows):self.rows=list(rows);self.shape=(len(rows),1);self.dtype='fake'
 def __getitem__(self,k):return Tensor([self.rows[i] for i in k]) if isinstance(k,list) else Tensor([self.rows[k]])
 def detach(self):return self
 def to(self,*_):return self
 def contiguous(self):return self
 def clone(self):return Tensor(self.rows)
 def tobytes(self):return bytes(self.rows)
def stamp(records):
 calls={}
 for index,row in enumerate(records):
  key=(row.get('path'),row.get('operator',{}).get('method'),row.get('phase'))
  calls[key]=calls.get(key,0)+1;row.update(event=index,occurrence=calls[key])
def batch(cached,device,uid=7):
 class Req: cached_len=cached;device_len=device;extend_len=device-cached;linear_slot_idx=3
 Req.uid=uid
 class B:reqs=[Req()];is_decode=False;is_prefill=True;seg_reason='ordinary'
 return B()
def test_short_tail_uses_exact_binary_rows_and_binding(tmp_path,monkeypatch):
 monkeypatch.setitem(sys.modules,'torch',type('T',(),{'save':staticmethod(lambda t,f:f.write(t.tobytes()))})())
 monkeypatch.setattr(MODULE,'_bytes',lambda t:t.tobytes())
 monkeypatch.setattr(MODULE,'_row_hashes',lambda t,rows:[MODULE._sha(t[i].tobytes()) for i in rows])
 o=MODULE.OperatorObserver(tmp_path,boundary=10,query_tokens=14,target_input_sha='ids',snapshot_rows=64);o.bind_query(7,'ids',14)
 class Owner:pass
 o.capture(Owner(),'model.layers.op_list.2.linear_attn','forward','input',Tensor(range(4)),batch(10,14));r=o.finalize(7)
 assert r['records'][0]['absolute_positions']==[10,11,12,13]
 assert len(r['records'][0]['row_sha256'])==4 and r['records'][0]['snapshot_rows']==4
def test_interior_4096_chunk_and_unbound_uid_fail_closed(tmp_path,monkeypatch):
 monkeypatch.setattr(MODULE,'_bytes',lambda t:t.tobytes())
 o=MODULE.OperatorObserver(tmp_path,boundary=8192,query_tokens=20000,target_input_sha='x',snapshot_rows=64);o.bind_query(8,'x',20000)
 assert o._active(batch(8192,12288,uid=8)) is not None
 assert o._active(batch(8192,12288,uid=9)) is None
def test_child_batches_ignore_scheduled_donor_overlap_and_align_tail_rows(tmp_path):
 o=MODULE.OperatorObserver(tmp_path,boundary=10,query_tokens=14,target_input_sha='x');o.bind_query(8,'x',14)
 def active(cached,device):
  donor=SimpleNamespace(uid=7,cached_len=0,device_len=2,extend_len=2,linear_slot_idx=1)
  target=SimpleNamespace(uid=8,cached_len=cached,device_len=device,extend_len=device-cached,linear_slot_idx=3)
  return SimpleNamespace(reqs=[donor,target],is_decode=False,is_prefill=True)
 donor_overlap=o._active(active(0,11));first=o._active(active(10,12));tail=o._active(active(12,14))
 assert donor_overlap is None
 assert first[1:]==([0,1],[10,11]) and tail[1:]==([0,1],[12,13])
 assert o.identity=={'uid':'8','slot':3}
def test_compare_aligns_different_child_counts_by_operator_and_absolute_row(tmp_path):
 def receipt(d,digest,row='a'):
  f=d/'x.pt';f.write_bytes(b'x');data={'schema':MODULE.SCHEMA,'boundary':1,'query_tokens':2,'target_input_sha':'x','records':[{'event':0,'path':'model.2','layer_idx':2,'operator':{},'phase':'output','occurrence':1,'absolute_positions':[9],'shape':[1,1],'dtype':'x','row_sha256':[row],'byte_sha256':digest,'file':'x.pt','file_sha256':MODULE._sha(b'x')}]};(d/'op_1_receipt.json').write_text(json.dumps(data))
 a=tmp_path/'a';b=tmp_path/'b';a.mkdir();b.mkdir();receipt(a,'a','a');receipt(b,'b','b')
 assert MODULE.compare(a,b)['first_layer_operator_difference']['absolute_tokenrow']==9

def test_compare_rejects_empty_or_incomplete_operator_row_coverage(tmp_path):
 def receipt(directory,records):
  stamp(records)
  for index,row in enumerate(records):
   (directory/f'x{index}.pt').write_bytes(b'x');row.update(file=f'x{index}.pt',file_sha256=MODULE._sha(b'x'))
  (directory/'op_1_receipt.json').write_text(json.dumps({'schema':MODULE.SCHEMA,'boundary':1,'query_tokens':3,'target_input_sha':'x','records':records}))
 a,b=tmp_path/'a',tmp_path/'b';a.mkdir();b.mkdir()
 receipt(a,[]);receipt(b,[])
 with pytest.raises(ValueError,match='nonempty'):MODULE.compare(a,b)
 record={'path':'model.2','layer_idx':2,'operator':{},'phase':'output','absolute_positions':[1,2],'shape':[2,4],'dtype':'x','row_sha256':['a','b']}
 receipt(a,[record]);receipt(b,[{**record,'absolute_positions':[1],'row_sha256':['a']}])
 with pytest.raises(ValueError,match='coverage'):MODULE.compare(a,b)

def test_compare_rejects_dtype_and_preserves_warm_event_order(tmp_path):
 def receipt(directory,records):
  stamp(records)
  for index in range(len(records)):(directory/f'x{index}.pt').write_bytes(b'x')
  for index,row in enumerate(records):row.update(file=f'x{index}.pt',file_sha256=MODULE._sha(b'x'))
  (directory/'op_1_receipt.json').write_text(json.dumps({'schema':MODULE.SCHEMA,'boundary':1,'query_tokens':3,'target_input_sha':'x','records':records}))
 def row(path,pos,digest,dtype='x'):
  return {'path':path,'layer_idx':0,'operator':{},'phase':'output','absolute_positions':[pos],'shape':[1,4],'dtype':dtype,'row_sha256':[digest]}
 a,b=tmp_path/'a',tmp_path/'b';a.mkdir();b.mkdir();receipt(a,[row('z',1,'a'),row('a',2,'b')]);receipt(b,[row('z',1,'q'),row('a',2,'r')])
 assert MODULE.compare(a,b)['first_layer_operator_difference']['path']=='z'
 receipt(b,[row('z',1,'a','y'),row('a',2,'r')])
 with pytest.raises(ValueError,match='dtype'):MODULE.compare(a,b)
def test_bytes_has_no_repr_fallback():
 with pytest.raises(TypeError):MODULE._bytes(object())

def write_calls(directory,records):
 directory.mkdir(exist_ok=True);stamp(records)
 for index,row in enumerate(records):
  file=directory/f'x{index}.pt';file.write_bytes(b'bytes')
  row.update(file=file.name,file_sha256=MODULE._sha(file.read_bytes()))
 path=directory/'op_1_receipt.json'
 path.write_text(json.dumps({'schema':MODULE.SCHEMA,'boundary':1,'query_tokens':5,'target_input_sha':'ids','records':records}))
 return path

def call(positions,hashes):
 return {'path':'model.layers.op_list.3.self_attn.rotary','layer_idx':3,'operator':{'method':'forward'},
         'phase':'output','absolute_positions':positions,'row_sha256':hashes,
         'shape':[len(positions),4],'dtype':'torch.bfloat16'}

def test_repeated_qk_calls_are_distinct_and_self_comparison_passes(tmp_path):
 a,b=tmp_path/'a',tmp_path/'b'
 write_calls(a,[call([1],['query']),call([1],['key'])])
 write_calls(b,[call([1],['query']),call([1],['changed-key'])])
 assert MODULE.compare(a,a)['equal'] is True
 first=MODULE.compare(a,b)['first_layer_operator_difference']
 assert first['call_ordinal']==2 and first['absolute_tokenrow']==1

def test_repeated_calls_align_across_different_chunk_partitions(tmp_path):
 a,b=tmp_path/'a',tmp_path/'b'
 write_calls(a,[call([1,2,3,4],['q1','q2','q3','q4']),call([1,2,3,4],['k1','k2','k3','k4'])])
 write_calls(b,[call([1,2],['q1','q2']),call([1,2],['k1','k2']),
                call([3,4],['q3','q4']),call([3,4],['k3','k4'])])
 assert MODULE.compare(a,b)['equal'] is True

def test_duplicate_capture_sequence_and_missing_call_fail_closed(tmp_path):
 a,b=tmp_path/'a',tmp_path/'b'
 path=write_calls(a,[call([1],['q']),call([1],['k'])])
 write_calls(b,[call([1],['q'])])
 with pytest.raises(ValueError,match='coverage'):MODULE.compare(a,b)
 data=json.loads(path.read_text());data['records'][1]['event']=0
 path.write_text(json.dumps(data))
 with pytest.raises(ValueError,match='duplicate or reordered'):MODULE.compare(a,a)
