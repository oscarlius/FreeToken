"""R040a parking raw-state capture wrapper; defaults remain off."""
from __future__ import annotations
import hashlib, json, os
from pathlib import Path
import d16_exact_service_startup as _base
ROLES=('conv','recurrent','ple_conv','ple_ngram_ctx')
_base_roundtrip=_base.parking_roundtrip
STAGES=('before','host','cleared','restored')

def _sha(path):
 h=hashlib.sha256(path.read_bytes()).hexdigest(); return h

def parking_roundtrip(scheduler, request_id):
    """Use the existing real D2H/H2D hook, then seal its four physical states."""
    value=_base_roundtrip(scheduler,request_id)
    root=Path(os.environ['FT_D16_SERVICE_CAPTURE_DIR'])/'parking'
    if value.get('request_id')!=request_id or set(value.get('before',{}))!=set(ROLES):
        raise RuntimeError('R040a parking roundtrip lacks four-role capture metadata')
    files={}
    for stage in STAGES:
        path=root/(stage+'.pt')
        if path.is_symlink() or not path.is_file() or set(value.get(stage,{}))!=set(ROLES):
            raise RuntimeError('R040a parking physical four-role capture is incomplete: '+stage)
        files[stage]={'path':path.name,'sha256':_sha(path),'states':value[stage]}
    index={'schema':'ft_r040a_native_parking_raw_capture/v1','request_id':request_id,
           'execution_id':value.get('execution_id'),'pid':value.get('pid'),'requests':value.get('requests'),
           'stages':files,'state_transport_bitwise':value.get('state_transport_bitwise') is True,
           'continuation_accepted':False,'model_admitted':False}
    with (root/'raw_capture_index.json').open('x',encoding='utf-8') as out: json.dump(index,out,sort_keys=True)
    return value

def install():
    if os.environ.get('FT_D16_PARK_RESTORE')=='1': _base.parking_roundtrip=parking_roundtrip
    _base.install()
