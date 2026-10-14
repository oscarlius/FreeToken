"""Read-only FT server inventory; preserve credentials and production identity."""
import importlib.util
import json
from pathlib import Path
import shlex

HERE=Path(__file__).resolve().parent
PRIVATE=HERE/'private'
PRIVATE.mkdir(exist_ok=True)
spec=importlib.util.spec_from_file_location('transport',HERE.parent/'r067c_retry2_production_control_20261009/ssh_ops.py')
transport=importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)
code=r'''
import datetime,hashlib,json,os,pathlib,subprocess,urllib.request
root=pathlib.Path('/data2/FreeToken')
active=json.loads((root/'run/production.active.json').read_text())
assert active['commit']=='9db0ee776c25afa8d2719ab700b2de7ccc606142'
assert active['worktree']=='/data2/FreeToken/wt/release-e3'
argv=active['argv']; host=argv[argv.index('--host')+1]; port=argv[argv.index('--port')+1]
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open('http://'+host+':'+port+'/health',timeout=10) as response: health=json.load(response)
assert health['maintenance']=='serving'
def git(path,*args):
    r=subprocess.run(['git','-C',str(path),*args],capture_output=True,text=True)
    assert r.returncode==0,(str(path),args,r.stderr)
    return r.stdout.strip()
roots=[]
for candidate in [root,root/'src/FreeToken',root/'wt/release-e3',root/'upstream-flashml',root/'src/upstream-flashml',root/'development/local_finalization_20261014/integration_a7c24b2']:
    if (candidate/'.git').exists(): roots.append(candidate)
for parent in [root/'wt',root/'development',root/'src']:
    if parent.is_dir():
        roots += [p for p in parent.iterdir() if p.is_dir() and (p/'.git').exists()]
repos={}
for repo in roots:
    common=pathlib.Path(git(repo,'rev-parse','--git-common-dir'))
    if not common.is_absolute(): common=(repo/common).resolve()
    if str(common) in repos: continue
    trees=[]
    for block in git(repo,'worktree','list','--porcelain').split('\n\n'):
        wt=dict(line.split(' ',1) if ' ' in line else (line,True) for line in block.splitlines() if line)
        if not wt: continue
        p=pathlib.Path(wt['worktree'])
        if not p.exists():
            trees.append({**wt,'missing':True});continue
        extra=git(p,'ls-files','--others','--exclude-standard','-z').split('\0')
        ignored=git(p,'ls-files','--others','--ignored','--exclude-standard','-z').split('\0')
        files=[]
        for name in [n for n in extra+ignored if n and not any(part in {'__pycache__','.pytest_cache','.ruff_cache','.mypy_cache'} for part in pathlib.Path(n).parts)]:
            target=p/name
            if target.is_file() and not target.is_symlink(): files.append({'path':name,'bytes':target.stat().st_size})
        trees.append({**wt,'status':git(p,'status','--porcelain'),'extra_count':len(files),'extra_bytes':sum(f['bytes'] for f in files),'largest_extra':sorted(files,key=lambda x:x['bytes'],reverse=True)[:12]})
    repos[str(common)]={'repo':str(repo),'common':str(common),'branches':git(repo,'for-each-ref','--format=%(refname) %(objectname)','refs/heads/').splitlines(),'worktrees':trees,'shallow':git(repo,'rev-parse','--is-shallow-repository')}
processes=[]
for proc in pathlib.Path('/proc').iterdir():
    if not proc.name.isdigit(): continue
    try:
        command=(proc/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
        cwd=os.readlink(proc/'cwd')
        if '/data2/FreeToken/' not in command and not cwd.startswith(str(root)): continue
        env=(proc/'environ').read_bytes().split(b'\0')
        pythonpath=next((part.decode(errors='replace').split('=',1)[1] for part in env if part.startswith(b'PYTHONPATH=')),'')
        paths=set()
        for value in [command,cwd,pythonpath]:
            for repo in repos.values():
                for wt in repo['worktrees']:
                    if wt['worktree'] in value: paths.add(wt['worktree'])
        stat=(proc/'stat').read_text().rsplit(')',1)[1].split()
        processes.append({'pid':int(proc.name),'starttime':stat[19],'cwd':cwd,'command_sha256':hashlib.sha256(command.encode()).hexdigest(),'worktree_references':sorted(paths)})
    except (OSError,PermissionError): pass
ops=[]
for parent in [root/'runs/dev_release',root/'development/ophak_release_e3_20261012/release_e3']:
    if not parent.exists(): continue
    for filename in parent.rglob('binary_manifest.json'):
        try:
            content=json.loads(filename.read_text())
            if 'release_e3' in str(filename): ops.append({'path':str(filename),'content':content})
        except (OSError,ValueError): pass
pth=[]
for parent in (root/'venv/lib').glob('python*/site-packages'):
    for pattern in ['*.pth','*.egg-link']:
        for file in parent.glob(pattern):
            value=file.read_text(errors='replace')
            if '/data2/FreeToken' in value: pth.append({'path':str(file),'value':value})
result={'at':datetime.datetime.now().astimezone().isoformat(),'active':active,'health':health,'repositories':list(repos.values()),'processes':processes,'e3_binary_manifests':ops,'venv_path_files':pth,
'ollama_running':subprocess.check_output(['docker','inspect','-f','{{.State.Running}}','ollama'],text=True).strip()=='true'}
print(json.dumps(result))
'''
client=transport.connect()
try:
    _,out,err=client.exec_command('nice -n 19 ionice -c 3 /data2/FreeToken/venv/bin/python -c '+shlex.quote(code))
    result,error=out.read().decode(),err.read().decode()
    assert out.channel.recv_exit_status()==0,error
    data=json.loads(result)
    (PRIVATE/'SERVER_INVENTORY.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'at':data['at'],'production_commit':data['active']['commit'],'instance':data['health']['instance_id'],'serving':data['health']['maintenance'],'repositories':[{'repo':r['repo'],'branches':len(r['branches']),'worktrees':len(r['worktrees']),'dirty':sum(bool(w.get('status')) for w in r['worktrees'])} for r in data['repositories']],'e3_manifests':len(data['e3_binary_manifests']),'active_processes':len(data['processes']),'ollama_running':data['ollama_running']},ensure_ascii=False))
finally:
    client.close()
