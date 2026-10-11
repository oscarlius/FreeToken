"""Read-only byte binding to the original R066b shared-prefix inputs."""
import hashlib, importlib.util, json
from pathlib import Path
HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'r066b_canary_v2'
INPUT_SHA = 'fd2463b22532ecf3a35cf1d3cddb01cde984bfb60acb979527540a10261d8d02'
VERIFIER_SHA = 'cf198e341a0dde14f887aa4e7f7e54324f2e352a66dcec012ea70f714c9215ce'
ADAPTER_SHA = 'd62974a6ae455587a7ebd5bdd23814a40acb6a64f350cff613685843402e64fe'
PREVIOUS = Path('/data2/_shared/runs/ft_rounds/E2-R066b-canary-v2/calls/pair1')
RAW_SHA = {
    'primary_p1_sun': '5bb86dba9581857fee9c5e01d1e2176d94c1137dcff44b586064322834c4313c',
    'primary_p1_ice': '89438b5b279495a6b6c943d36a74fdb0e4cbc93c48fb8f55be1284ff2e2f7af1',
}
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def verify_inputs():
    if sha(HERE/'inputs.json') != INPUT_SHA or sha(OLD/'inputs.json') != INPUT_SHA or sha(OLD/'prepare_inputs.py') != VERIFIER_SHA or sha(OLD/'sdk_adapter.py') != ADAPTER_SHA:
        raise ValueError('original R066b input or transport binding differs')
    spec=importlib.util.spec_from_file_location('r066c_bound_input_verifier', OLD/'prepare_inputs.py')
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    verified=module.verify_inputs()
    data=json.loads((HERE/'inputs.json').read_text())['items']
    bound={}
    for key, digest in RAW_SHA.items():
        p=PREVIOUS/(key+'.json')
        if p.is_symlink() or p.stat().st_mode & 0o222 or sha(p)!=digest:
            raise ValueError('sealed original SDK artifact differs')
        raw=json.loads(p.read_text())
        if raw['request']['prompt']!=data[key]['prompt']:
            raise ValueError('original wire prompt bytes differ')
        bound[key]={'path':str(p),'sha256':digest,'prompt_sha256':data[key]['prompt_sha256'],'prompt_tokens':data[key]['prompt_tokens']}
    return {**verified,'selected_keys':list(RAW_SHA),'original_calls':bound,'no_regeneration':True}
if __name__=='__main__': print(json.dumps(verify_inputs(),sort_keys=True))
