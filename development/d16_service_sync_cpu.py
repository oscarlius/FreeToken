"""Synchronize reviewed D16 service tools and validate both dedicated CPU trees."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
TREES = {
    'e2d16-readers': ('e914d5026d73b60717599da49d1667bb7ab134fe', 'bde6283c68c0ad153dcd727a14f631244819b535'),
    'e2base1': ('185fa36091ce66a94f6a0f3323513df4b1ecf73f', '2396728f5f210b98bfde0b8ba3556e9cbc2b234f'),
}
TESTS = [f'tests/scripts/test_equiv_{name}.py' for name in (
    'suite', 'continuation', 'path_readers', 'retained_d03', 'sampler_capture',
    'retained_state', 'service_capture')]

PROGRAM = r'''
import base64,hashlib,json,os,pathlib,subprocess,sys
x=json.loads(sys.stdin.read()); out=pathlib.Path(x['stage']); out.mkdir(exist_ok=False)
def sha(raw): return hashlib.sha256(raw).hexdigest()
def git(tree,*args): return subprocess.check_output(['git','-C',str(tree),*args],text=True).strip()
def write(path,raw):
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('xb') as f: f.write(raw)
write(out/'stage_source.py',base64.b64decode(x['source']))
repo=pathlib.Path('/data2/FreeToken/src/FreeToken')
for name,spec in x['trees'].items():
 tree=pathlib.Path('/data2/FreeToken/wt')/name
 assert git(tree,'rev-parse','HEAD')==spec['parent'] and not git(tree,'status','--porcelain'),name
reports={}
try:
 for name,spec in x['trees'].items():
  tree=pathlib.Path('/data2/FreeToken/wt')/name
  bundle=out/(name+'.bundle'); raw=base64.b64decode(spec['bundle']); assert sha(raw)==spec['bundle_sha256']; write(bundle,raw)
  subprocess.run(['git','-C',str(repo),'bundle','verify',str(bundle)],check=True,capture_output=True)
  subprocess.run(['git','-C',str(repo),'fetch',str(bundle),'HEAD'],check=True,capture_output=True)
  subprocess.run(['git','-C',str(tree),'merge','--ff-only',spec['commit']],check=True,capture_output=True)
  assert git(tree,'rev-parse','HEAD')==spec['commit'] and not git(tree,'status','--porcelain')
  sources={}
  for file,digest in spec['source_sha256'].items():
   p=tree/file; assert p.is_file() and not p.is_symlink()
   raw=p.read_bytes(); blob=subprocess.check_output(['git','-C',str(tree),'show','HEAD:'+file])
   assert sha(raw)==sha(blob)==digest,file
   write(out/'sources'/name/file,raw); sources[file]=digest
  env={k:v for k,v in os.environ.items() if k!='PYTHONPATH' and not k.startswith('FT_')}
  env.update(CUDA_VISIBLE_DEVICES='',PYTHONPATH=str(tree/'scripts')+':'+str(tree/'python'),PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='2',FT_D16_D03_TOOL='/data2/FreeToken/runs/dev_D16/path_readers_cpu_7b382efbb437/d03_tools/logits_probe.py')
  probe=[sys.executable,'-c',"import json,pathlib,torch,freetoken; p=pathlib.Path(freetoken.__file__).resolve(); assert p.is_relative_to(pathlib.Path('"+str(tree/'python')+"')); assert not torch.cuda.is_initialized(); print(json.dumps({'origin':str(p),'cuda_initialized':False}))"]
  binding=subprocess.run(probe,cwd=tree,env=env,capture_output=True); write(out/(name+'_binding.log'),binding.stdout+binding.stderr); assert binding.returncode==0
  argv=[sys.executable,'-m','pytest','-q','-p','no:cacheprovider',*x['tests']]
  r=subprocess.run(argv,cwd=tree,env=env,capture_output=True,timeout=240)
  raw=r.stdout+r.stderr; write(out/(name+'_tests.log'),raw)
  reports[name]={'commit':spec['commit'],'source_sha256':sources,'argv':argv,'returncode':r.returncode,'log_sha256':sha(raw),'binding_argv':probe,'binding_log_sha256':sha(binding.stdout+binding.stderr),'clean':not git(tree,'status','--porcelain')}
  print(json.dumps({'tree':name,'returncode':r.returncode,'tail':raw.decode(errors='replace')[-1200:]}),flush=True)
  assert r.returncode==0 and '86 passed' in raw.decode() and reports[name]['clean']
 verdict='PASS'
except BaseException as e:
 verdict='FAIL'; reports['error']=repr(e)
finally:
 report={'schema':'ft_d16_service_sync_cpu/v1','verdict':verdict,'gpu_started':False,'requests_sent':False,'trees':reports,'files':{p.relative_to(out).as_posix():sha(p.read_bytes()) for p in out.rglob('*') if p.is_file()}}
 raw=json.dumps(report,sort_keys=True).encode(); write(out/'sync_report.json',raw)
 for p in sorted(out.rglob('*'),reverse=True):
  assert not p.is_symlink(); p.chmod(0o444 if p.is_file() else 0o555)
 out.chmod(0o555)
 print(json.dumps({'stage':str(out),'report_sha256':sha(raw),'verdict':verdict}),flush=True)
sys.exit(0 if verdict=='PASS' else 1)
'''

def main():
    source = Path(__file__).read_bytes()
    specs = {}
    for name, (parent, commit) in TREES.items():
        tree = HERE / name
        def git(*args):
            return subprocess.check_output(['git', '-C', str(tree), *args], text=True).strip()
        assert git('rev-parse', 'HEAD') == commit and not git('status', '--porcelain')
        bundle = HERE / f'{name}_service_{commit[:7]}.bundle'
        if bundle.exists():
            assert git('bundle', 'list-heads', str(bundle)) == commit+' HEAD'
        else:
            subprocess.run(['git', '-C', str(tree), 'bundle', 'create', str(bundle), 'HEAD', '^'+parent], check=True)
        raw = bundle.read_bytes()
        names = git('ls-files', 'scripts/equiv_suite').splitlines() + TESTS + ['tests/conftest.py', 'README.md']
        hashes = {n: hashlib.sha256(subprocess.check_output(['git', '-C', str(tree), 'show', 'HEAD:'+n])).hexdigest() for n in names}
        specs[name] = {'parent': parent, 'commit': commit, 'source_sha256': hashes, 'bundle': base64.b64encode(raw).decode(), 'bundle_sha256': hashlib.sha256(raw).hexdigest()}
    payload = {'trees': specs, 'tests': TESTS, 'source': base64.b64encode(source).decode(), 'stage': '/data2/FreeToken/runs/dev_D16/service_bde6283_sync_'+hashlib.sha256(source).hexdigest()[:12]}
    code = 'import io,sys\nsys.stdin=io.StringIO('+repr(json.dumps(payload))+')\n'+PROGRAM
    result = subprocess.run(['ssh', '9', '/data2/FreeToken/venv/bin/python', '-'], input=code, text=True, capture_output=True)
    receipt = HERE / ('d16_service_bde6283_sync_'+hashlib.sha256(source).hexdigest()[:12]+'.json')
    with receipt.open('x', encoding='utf-8') as f:
        json.dump({'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}, f)
    print(result.stdout)
    print(result.stderr)
    raise SystemExit(result.returncode)

if __name__ == '__main__':
    main()
