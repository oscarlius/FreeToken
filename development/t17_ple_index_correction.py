"""Append the real HF-to-decoder PLE indexing correction to sealed R026."""
import argparse
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
PROGRAM = r'''
import copy,hashlib,json,os,pathlib,stat,subprocess,sys,urllib.request
directory=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R026-diagnostic-T17')
writer=pathlib.Path('/data2/FreeToken/scripts/round_json_append.py')
config=pathlib.Path('/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay/config.json')
parser=pathlib.Path('/data2/FreeToken/wt/e2d14/python/freetoken/models/qwen4_exp/config.py')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
if sha(writer)!='67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff':raise ValueError('canonical append source changed')
if sha(config)!='deef67a61f3311faf051b23dc4192f442c7fee4f9cd2f38cbcbe4da55c763a80' or sha(parser)!='72905266db8c384ea3cd267a1b739c58a32b8b069f37039b778665cc2be14607':raise ValueError('actual model/parser source changed')
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['PYTHONDONTWRITEBYTECODE']='1'
sys.path.insert(0,'/data2/FreeToken/wt/e2d14/python')
from types import SimpleNamespace
import torch
from freetoken.models.qwen4_exp.config import parse_config
doc=json.loads(config.read_bytes());hf=SimpleNamespace(**doc);hf.text_config=SimpleNamespace(**doc['text_config'])
if isinstance(getattr(hf,'vision_config',None),dict):hf.vision_config=SimpleNamespace(**hf.vision_config)
parsed=parse_config(hf)
if parsed.qwen4_args.ple_layer_ids!=(1,) or torch.cuda.is_initialized():raise ValueError('actual CPU config mapping differs')
subprocess.run(['sha256sum','-c','MANIFEST.sha256'],cwd=directory,check=True,stdout=subprocess.DEVNULL)
subprocess.run([sys.executable,str(writer),str(directory),'check'],check=True,stdout=subprocess.DEVNULL)
before_sha=sha(directory/'round.json');manifest_sha=sha(directory/'MANIFEST.sha256');before=json.loads((directory/'round.json').read_bytes())
if before['verdict']!='failed_harness' or before['results']['measurements_completed'] is not False:raise ValueError('exact unmeasured failure required')
raw=before['diagnostics']['original_raw_files']
if len(raw)!=23 or any(sha(directory/name)!=digest for name,digest in raw.items()):raise ValueError('original failure raw changed')
existing=before['diagnostics'].get('layer_indexing_correction')
entry={'id':'r026-ple-indexing-20261005','original_field_retained':True,
 'original_field':'diagnostics.actual_ple_decoder_indices','original_declared_decoder_indices':[2],
 'HF_ple_layer_ids':[2],'parsed_zero_based_decoder_indices':[1],
 'model_config_sha256':sha(config),'actual_config_parser_path':str(parser),'actual_config_parser_sha256':sha(parser),
 'candidate_commit':'e4f32022a5aa4d8734d87d9f6eb15e98c1edde42','CPU_parser_executed':True,'cuda_initialized':False,
 'reason':'HF PLE ids are one-indexed; the actual candidate parse_config subtracts one. The previous failure review treated HF id2 as decoder index2.',
 'effect':'Initialization failure classification, no-measurement status, original23raw bytes and failed_harness verdict remain unchanged.'}
patch={'diagnostics':{'layer_indexing_correction':entry}}
origin_path=directory/'round_history/round.v002.json'
origin=json.loads(origin_path.read_bytes())
intended=copy.deepcopy(origin);intended['diagnostics']['layer_indexing_correction']=entry
result={'rid':directory.name,'before_round_sha256':before_sha,'manifest_sha256':manifest_sha,'patch':patch,'original_raw_count':23}
if data['apply']:
 if existing is None:
  if result!=data['expected']:raise ValueError('reviewed correction changed')
 else:
  if existing!=entry or data['expected']['patch']!=patch or data['expected']['manifest_sha256']!=manifest_sha:raise ValueError('different existing correction; do not resume')
  old_version=directory/'round_history/round.v002.json'
  if sha(old_version)!=data['expected']['before_round_sha256']:raise ValueError('approved original version changed')
  versions=sorted(p.name for p in (directory/'round_history').glob('round.v*.json'))
  if before!=intended or versions!=['round.v001.json','round.v002.json','round.v003.json'] or (directory/'round.json').read_bytes()!=(directory/'round_history/round.v003.json').read_bytes():raise ValueError('current round exceeds the exact approved append')
 stage=pathlib.Path('/data2/FreeToken/runs/dev_D14/r026_ple_index_correction')
 files={'review.json':(json.dumps(result,indent=2)+'\n').encode(),'append.json':(json.dumps(patch,indent=2)+'\n').encode(),
  'config_parser.py':parser.read_bytes(),'model_config.json':config.read_bytes(),'correction_driver.py':data['driver'].encode()}
 if not stage.exists():
  stage.mkdir()
  for name,body in files.items():
   with (stage/name).open('xb') as f:f.write(body)
   (stage/name).chmod(0o444)
  stage.chmod(0o555)
 else:
  if stage.is_symlink() or stage.stat().st_uid!=os.geteuid():raise ValueError('foreign correction stage')
  if stage.stat().st_mode&0o777!=0o555 or set(p.name for p in stage.iterdir())!=set(files):raise ValueError('correction stage scope or permissions changed')
  for name in files:
   p=stage/name;mode=p.lstat()
   if p.is_symlink() or not stat.S_ISREG(mode.st_mode) or mode.st_uid!=os.geteuid() or mode.st_mode&0o777!=0o444:raise ValueError('frozen correction input changed: '+name)
  if json.loads((stage/'review.json').read_bytes())!=data['expected'] or json.loads((stage/'append.json').read_bytes())!=patch:raise ValueError('frozen approved correction stage differs')
  if sha(stage/'config_parser.py')!=sha(parser) or sha(stage/'model_config.json')!=sha(config):raise ValueError('frozen target source differs')
  if sha(stage/'correction_driver.py')!=hashlib.sha256(data['driver'].encode()).hexdigest():raise ValueError('frozen correction driver changed')
 if existing is None:
  subprocess.run([sys.executable,str(writer),str(directory),'add','--json',str(stage/'append.json')],check=True,stdout=subprocess.DEVNULL)
 after=json.loads((directory/'round.json').read_bytes())
 if after!=intended:raise ValueError('append is not exactly the approved single diagnostic field')
 if after['diagnostics']['layer_indexing_correction']!=entry or after['verdict']!='failed_harness' or after['diagnostics']['original_raw_files']!=raw or sha(directory/'MANIFEST.sha256')!=manifest_sha:raise ValueError('append changed original contract')
 if any(sha(directory/name)!=digest for name,digest in raw.items()):raise ValueError('original raw changed')
 subprocess.run([sys.executable,str(writer),str(directory),'check'],check=True,stdout=subprocess.DEVNULL)
 subprocess.run(['sha256sum','-c','MANIFEST.sha256'],cwd=directory,check=True,stdout=subprocess.DEVNULL)
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 store=pathlib.Path('/data2/_shared/model_hub_dashboard/data/rounds.json')
 old_panel=json.loads(store.read_bytes())['rounds'].get(directory.name)
 if old_panel is None:raise ValueError('original R026 panel registration required')
 previous_panel_entry=old_panel.get('diagnostics',{}).get('layer_indexing_correction')
 if previous_panel_entry is not None and previous_panel_entry!=entry:raise ValueError('different panel correction')
 payload={'round_id':directory.name,**patch}
 request=urllib.request.Request('http://127.0.0.1:8098/api/rounds/record',data=json.dumps(payload).encode(),method='POST',headers={'Content-Type':'application/json'})
 if previous_panel_entry is None:
  with opener.open(request,timeout=30) as response:posted={'http_status':response.status,'response':json.loads(response.read())}
 else:posted={'http_status':None,'existing_panel_verified':True}
 with opener.open('http://127.0.0.1:8098/api/rounds',timeout=30) as response:visible=json.loads(response.read())['rounds'][directory.name]
 stored=json.loads(store.read_bytes())['rounds'][directory.name]
 if any(stored.get(k)!=v or visible.get(k)!=v for k,v in after.items()):raise ValueError('corrected panel readback differs')
 stage.chmod(0o555)
 if any(p.stat().st_mode&0o222 for p in (directory,*directory.rglob('*'))):raise ValueError('round writable after append')
 result={'rid':directory.name,'after_round_sha256':sha(directory/'round.json'),'manifest_sha256':manifest_sha,
  'correction_id':entry['id'],'original_raw_files_verified':23,'verdict_retained':'failed_harness',
  'correction_evidence':str(stage/'review.json'),'panel_readback_verified':True,'panel_post_status':posted['http_status']}
print(json.dumps(result))
'''

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    options = parser.parse_args()
    data = {'apply': options.apply}
    if options.apply:
        data['expected'] = json.loads((HERE / 't17_ple_index_correction_review.json').read_bytes())
        data['driver'] = Path(__file__).read_text(encoding='utf-8')
    wire = 'data=' + repr(data) + '\n' + PROGRAM
    process = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '9',
                              '/data2/FreeToken/venv/bin/python', '-'], input=wire.encode(), capture_output=True)
    if process.returncode:
        print(process.stderr.decode())
        raise SystemExit(process.returncode)
    result = json.loads(process.stdout)
    target = HERE / ('t17_ple_index_correction_receipt.json' if options.apply else 't17_ple_index_correction_review.json')
    if options.apply and target.exists():
        previous = json.loads(target.read_bytes())
        if any(previous.get(key) != result[key] for key in ('rid', 'after_round_sha256', 'manifest_sha256', 'correction_id', 'original_raw_files_verified', 'verdict_retained', 'panel_readback_verified')):
            raise ValueError('previous correction receipt differs')
    else:
        with target.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2)
            stream.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='patch'}, indent=2))
