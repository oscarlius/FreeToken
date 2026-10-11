import hashlib, importlib.util, json, os
from pathlib import Path
import pytest, sys
from types import SimpleNamespace
ROOT=Path(__file__).parents[1];sys.path.insert(0,str(ROOT)); spec=importlib.util.spec_from_file_location('v3',ROOT/'d16_exact_service_startup_v4.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def test_parking_wrapper_seals_actual_four_stage_file_index(tmp_path,monkeypatch):
 root=tmp_path/'capture'/'parking';root.mkdir(parents=True)
 meta={r:{'sha256':'a'*64,'shape':[1],'dtype':'torch.float32'} for r in m.ROLES}
 def fake(scheduler,request_id):
  for stage in m.STAGES:(root/(stage+'.pt')).write_bytes(stage.encode())
  return {'request_id':request_id,'execution_id':'x','pid':7,'requests':[{'uid':0,'linear_slot_idx':1,'host_slot':2}],'before':meta,'host':meta,'cleared':meta,'restored':meta,'state_transport_bitwise':True}
 monkeypatch.setattr(m,'_base_roundtrip',fake);monkeypatch.setenv('FT_D16_SERVICE_CAPTURE_DIR',str(tmp_path/'capture'))
 pool=SimpleNamespace(_slot_specs=[SimpleNamespace(name='ple_conv',fill_value=3.5),SimpleNamespace(name='ple_ngram_ctx',fill_value=-1)])
 m.parking_roundtrip(SimpleNamespace(engine=SimpleNamespace(linear_state_pool=pool)),'pause')
 idx=json.loads((root/'raw_capture_index.json').read_text());assert set(idx['stages'])==set(m.STAGES) and idx['requests'][0]['uid']==0
 assert idx['schema']=='ft_r040a_native_parking_raw_capture/v2'
 assert idx['clear_fill_values']==dict(conv=0,recurrent=0,ple_conv=3.5,ple_ngram_ctx=-1)
def test_missing_raw_stage_fails_closed(tmp_path,monkeypatch):
 root=tmp_path/'capture'/'parking';root.mkdir(parents=True)
 meta={r:{} for r in m.ROLES}
 monkeypatch.setattr(m,'_base_roundtrip',lambda *_:{'request_id':'x','before':meta,'host':meta,'cleared':meta,'restored':meta})
 monkeypatch.setenv('FT_D16_SERVICE_CAPTURE_DIR',str(tmp_path/'capture'))
 with pytest.raises(RuntimeError,match='incomplete'):m.parking_roundtrip(None,'x')
