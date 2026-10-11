"""Read the exact stopped R023 measurement; never launch or alter a round."""
import json
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
PROGRAM = r'''
import hashlib,importlib.util,json,os,pathlib,sys
os.environ['CUDA_VISIBLE_DEVICES']=''
receipt=json.load(sys.stdin)
directory=pathlib.Path('/data2/_shared/runs/ft_rounds')/receipt['rid']
server=pathlib.Path('/data2/FreeToken/runs/dev_D14')/('launch_'+receipt['rid']+'.json')
if json.loads(server.read_text())!=receipt:raise ValueError('exact server/controller receipt differs')
execution=pathlib.Path(receipt['frozen_runner']).parent
for name,digest in receipt['source_files'].items():
 path=execution/name
 if path.is_symlink() or path.stat().st_mode&0o222 or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
  raise ValueError('frozen source differs: '+name)
artifact=directory/'t17_d14_artifacts.py'
if hashlib.sha256(artifact.read_bytes()).hexdigest()!=receipt['source_files']['t17_d14_artifacts.py']:
 raise ValueError('archived actual validator differs')
spec=importlib.util.spec_from_file_location('ft_r023_raw_reader',artifact)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
inputs=json.loads((directory/'real_inputs.json').read_text())
case=inputs['cases'][0];name=case['name'];warm=directory/(name+'_warm');cold=directory/(name+'_short_cold')
raw=module.validate_case({'name':name,'length':case['length'],'trace_index':case['trace_index'],'context':case['expected_ngram']},
 cold,warm,tail=65,cold_request='query',hit_request='short',state_root=warm/'dump')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def digest_text(text):return hashlib.sha256(text.encode()).hexdigest()
def one_dump(arm,uid,length):
 rows=module.jsonl(arm/'dump/index.jsonl')
 return module.one([row for row in rows if row['kind']=='donate' and row['uid']==uid and row['length']==length],'query computation state')
hot_record=one_dump(warm,raw['hit_uid'],8256)
cold_uid=str(json.loads((cold/'query.json').read_text())['response']['uid'])
cold_record=one_dump(cold,cold_uid,8256)
import torch
roles={}
for role in module.ROLES:
 a,a_receipt=module.state_file(warm/'dump',hot_record,role,module.load_tensor)
 b,b_receipt=module.state_file(cold/'dump',cold_record,role,module.load_tensor)
 compatible=a.shape==b.shape and a.dtype==b.dtype
 difference=a!=b if compatible else None
 byte_a=a.contiguous().view(torch.uint8).flatten();byte_b=b.contiguous().view(torch.uint8).flatten()
 byte_indices=(byte_a!=byte_b).nonzero().flatten() if compatible else None
 roles[role]={'shape_warm':list(a.shape),'shape_cold':list(b.shape),'dtype_warm':str(a.dtype),'dtype_cold':str(b.dtype),
  'bitwise_equal':module.bit_equal(a,b),'different_values':int(difference.sum()) if difference is not None else None,
  'different_bytes':int(byte_indices.numel()) if byte_indices is not None else None,
  'first_byte_offset':int(byte_indices[0]) if byte_indices is not None and byte_indices.numel() else None,
  'max_abs':float((a.float()-b.float()).abs().max()) if compatible and a.numel() else None,
  'warm':a_receipt,'cold':b_receipt}
tokens=list(zip(raw['cold_token_ids'],raw['hit_token_ids']))
forks=[i for i,(a,b) in enumerate(tokens) if a!=b]
saved=json.loads((directory/(name+'_short_comparison.json')).read_text())
for role,value in roles.items():
 old=saved['recompute_roles'][role]
 if old['equal']!=value['bitwise_equal'] or old['max_abs']!=value['max_abs']:
  raise ValueError('saved computed-role comparison does not independently recompute: '+role)
children=[r for r in module.jsonl(warm/'observations.jsonl') if r.get('uid')=='3' and r['kind']=='layer-children']
print(json.dumps({'rid':receipt['rid'],'batch':receipt['batch'],'status':json.loads((directory/'status_batch51.json').read_text()),
 'candidate':receipt['candidate_commit'],'boundary':case['length'],'actual_cached_tokens':raw['actual_cached_tokens'],
 'donor_ngram':raw['state_roles']['slot:ple_ngram_ctx']['observed_donor'],
 'resume_ngram':raw['state_roles']['slot:ple_ngram_ctx']['observed_resume'],
 'restore_roles':{k:v['bitwise_equal'] for k,v in raw['state_roles'].items()},
 'tokens_equal':raw['tokens_bitwise_equal'],'text_equal':raw['full_text_equal'],
 'sampled_tokens':{'cold':len(raw['cold_token_ids']),'hit':len(raw['hit_token_ids'])},
 'first_token_fork':forks[0] if forks else None,'token_forks':forks,
 'token_id_sha256':{'cold':raw['cold_token_ids_sha256'],'hit':raw['hit_token_ids_sha256']},
 'text_sha256':{'cold':digest_text(raw['cold_raw_text']),'hit':digest_text(raw['hit_raw_text'])},
 'computed_roles_at_8256':roles,'long_children':children,'cuda_initialized':torch.cuda.is_initialized(),
 'comparison_sha256':sha(directory/(name+'_short_comparison.json'))},ensure_ascii=False))
'''
def main():
    receipt = json.loads((HERE / 't17_d14_E2-R023-gate-T17_launch_receipt.json').read_text(encoding='utf-8'))
    process = subprocess.run(['ssh', '-o', 'BatchMode=yes', '9', '/data2/FreeToken/venv/bin/python',
                              '-c', shlex.quote(PROGRAM)], input=json.dumps(receipt).encode(), capture_output=True)
    if process.returncode:
        print(process.stderr.decode())
        raise SystemExit(process.returncode)
    print(json.dumps(json.loads(process.stdout), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
