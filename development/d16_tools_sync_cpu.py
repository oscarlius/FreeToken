"""Transfer the committed D16 tool tree and retain a Linux CPU-only proof."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
TREE = HERE / 'e2d16-tools'
COMMIT = 'e9ee6aac1786485bb447579f224b0927d8b15cab'
PARENT = 'e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7'
TREE_SHA = '2e80536f319fcde0bf05427af7a7333c3178dc4c'
TESTS = ('tests/scripts/test_equiv_suite.py', 'tests/scripts/test_equiv_continuation.py')
CHANGED = ('scripts/equiv_suite/README.md', 'scripts/equiv_suite/continuation.py',
           'scripts/equiv_suite/gate.py', 'scripts/equiv_suite/raw.py', *TESTS)

PROGRAM = r'''import base64,hashlib,json,os,pathlib,re,subprocess,sys
x=json.load(sys.stdin);stage=pathlib.Path(x['stage'])
stage.mkdir(parents=True,exist_ok=False)
parent=pathlib.Path('/data2/FreeToken/wt/e2d14-schedule');tree=parent.with_name('e2d16-tools')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def command(args):return subprocess.check_output(args,text=True).strip()
def write(p,raw):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb') as stream:stream.write(raw)
report={'schema':'ft_d16_tools_cpu/v1','gpu_started':False,'requests_sent':False,'engine_candidate_unchanged':False,'commit':x['commit'],'tree':x['tree'],'parent':x['parent'],'stage':str(stage),'worktree':str(tree),'passed':0}
try:
 if tree.exists() or tree.is_symlink():raise FileExistsError('dedicated D16 worktree already exists')
 if command(['git','-C',str(parent),'rev-parse','HEAD'])!=x['parent'] or command(['git','-C',str(parent),'status','--porcelain','--untracked-files=no']):raise ValueError('D14 candidate source differs')
 for name,raw in x['controller_files'].items():write(stage/name,base64.b64decode(raw))
 raw=base64.b64decode(x['bundle'])
 if hashlib.sha256(raw).hexdigest()!=x['bundle_sha256']:raise ValueError('bundle transport differs')
 bundle=stage/'candidate.bundle';write(bundle,raw)
 subprocess.run(['git','-C',str(parent),'bundle','verify',str(bundle)],check=True,capture_output=True)
 subprocess.run(['git','-C',str(parent),'fetch',str(bundle),'HEAD'],check=True,capture_output=True)
 if command(['git','-C',str(parent),'rev-parse',x['commit']+'^{tree}'])!=x['tree'] or command(['git','-C',str(parent),'rev-parse',x['commit']+'^'])!=x['parent']:raise ValueError('D16 fetched tree or sole parent differs')
 if set(command(['git','-C',str(parent),'diff','--name-only',x['parent'],x['commit']]).splitlines())!=set(x['changed']):raise ValueError('D16 changes cross tool-only boundary')
 subprocess.run(['git','-C',str(parent),'worktree','add','--detach',str(tree),x['commit']],check=True,capture_output=True)
 env={k:v for k,v in os.environ.items() if not k.startswith(('FT_DEV_','FT_T17_','FT_D3_'))}
 env.update(CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(tree/'scripts'))
 argv=[sys.executable,'-m','pytest','-q','-p','no:cacheprovider','--confcutdir=tests/scripts',*x['tests']]
 run=subprocess.run(argv,cwd=tree,env=env,capture_output=True,timeout=180)
 write(stage/'regression.log',run.stdout+run.stderr)
 report['step']={'argv':argv,'returncode':run.returncode,'log_sha256':sha(stage/'regression.log')}
 output=(run.stdout+run.stderr).decode()
 if run.returncode or re.findall(r'(\d+) passed',output)!=['31'] or re.search(r'\d+ (failed|skipped|error)',output):raise ValueError('complete 31-test Linux CPU regression required')
 report['passed']=31
 for name,digest in x['source_files'].items():
  source=tree/name
  blob=subprocess.check_output(['git','-C',str(tree),'show',x['commit']+':'+name])
  if source.is_symlink() or sha(source)!=digest or hashlib.sha256(blob).hexdigest()!=digest:raise ValueError('live/Git/transport D16 source differs: '+name)
  write(stage/'source'/name,source.read_bytes())
 if command(['git','-C',str(tree),'rev-parse','HEAD'])!=x['commit'] or command(['git','-C',str(tree),'rev-parse','HEAD^{tree}'])!=x['tree'] or command(['git','-C',str(tree),'status','--porcelain']):raise ValueError('D16 source changed during CPU test')
 if command(['git','-C',str(parent),'rev-parse','HEAD'])!=x['parent'] or command(['git','-C',str(parent),'status','--porcelain','--untracked-files=no']):raise ValueError('D14 candidate changed during tool sync')
 report.update(verdict='PASS',engine_candidate_unchanged=True,source_files=x['source_files'])
except BaseException as error:report.update(verdict='FAIL',error=repr(error))
finally:
 report['files']={p.relative_to(stage).as_posix():sha(p) for p in stage.rglob('*') if p.is_file()}
 write(stage/'cpu_validation.json',(json.dumps(report,indent=2)+'\n').encode())
 for p in sorted(stage.rglob('*'),reverse=True):
  if p.is_symlink():raise ValueError('unexpected stage symlink')
  p.chmod(0o444 if p.is_file() else 0o555)
 stage.chmod(0o555)
print(json.dumps({'stage':str(stage),'report_sha256':sha(stage/'cpu_validation.json'),'report':report}))
'''


def main():
    def git(*args):
        return subprocess.check_output(['git', '-C', str(TREE), *args], text=True).strip()
    if git('status', '--porcelain') or git('rev-parse', 'HEAD') != COMMIT or git('rev-parse', 'HEAD^{tree}') != TREE_SHA:
        raise ValueError('exact clean committed D16 local tree required')
    if git('rev-parse', 'HEAD^') != PARENT or set(git('diff', '--name-only', PARENT, COMMIT).splitlines()) != set(CHANGED):
        raise ValueError('D16 parent or tool-only scope differs')
    names = git('ls-files', 'scripts/equiv_suite').splitlines() + list(TESTS)
    sources = {}
    for name in names:
        raw = (TREE / name).read_bytes()
        blob = subprocess.check_output(['git', '-C', str(TREE), 'show', COMMIT+':'+name])
        if git('hash-object', '--path='+name, name) != git('rev-parse', COMMIT+':'+name):
            raise ValueError('local committed D16 source differs: '+name)
        # Windows checkout filters may use CRLF; Linux is bound to Git blob bytes.
        sources[name] = hashlib.sha256(blob).hexdigest()
    bundle = HERE / ('d16_tools_' + COMMIT[:12] + '.bundle')
    if bundle.exists():
        raise FileExistsError(bundle)
    subprocess.run(['git', '-C', str(TREE), 'bundle', 'create', str(bundle), 'HEAD', '^'+PARENT], check=True)
    raw = bundle.read_bytes()
    controller = {'d16_tools_sync_cpu.py': Path(__file__).read_bytes(), 'stage_program.py': PROGRAM.encode()}
    identity = hashlib.sha256(raw+b''.join(controller[k] for k in sorted(controller))).hexdigest()
    payload = {'stage':'/data2/FreeToken/runs/dev_D16/tools_cpu_'+identity[:12],
               'commit':COMMIT,'tree':TREE_SHA,'parent':PARENT,'changed':CHANGED,'tests':TESTS,
               'bundle_sha256':hashlib.sha256(raw).hexdigest(),'bundle':base64.b64encode(raw).decode(),
               'source_files':sources,'controller_files':{k:base64.b64encode(v).decode() for k,v in controller.items()}}
    wire = 'import io,sys\nsys.stdin=io.StringIO('+repr(json.dumps(payload))+')\n'+PROGRAM
    run = subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','9',
                          '/data2/FreeToken/venv/bin/python','-'],input=wire.encode(),capture_output=True)
    receipt = HERE / ('d16_tools_cpu_'+identity[:12]+'.json')
    output = {'controller_sha256':hashlib.sha256(controller['d16_tools_sync_cpu.py']).hexdigest(),
              'program_sha256':hashlib.sha256(PROGRAM.encode()).hexdigest(),'source_files':sources,
              'returncode':run.returncode,'stdout':run.stdout.decode(),'stderr':run.stderr.decode()}
    if not run.returncode:
        output.update(json.loads(run.stdout))
    with receipt.open('x',encoding='utf-8') as stream:
        json.dump(output,stream,indent=2);stream.write('\n')
    if run.returncode or output['report']['verdict'] != 'PASS':
        raise ValueError('failed D16 sync retained: '+str(receipt))
    print(json.dumps({'receipt':str(receipt),'stage':output['stage'],'passed':output['report']['passed'],
                      'report_sha256':output['report_sha256']}))


if __name__ == '__main__':
    main()
