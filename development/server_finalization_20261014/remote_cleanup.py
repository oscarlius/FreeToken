"""A consumed, bounded FT server worktree cleanup; production is read-only."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request

ROOT=Path('/data2/FreeToken')
HERE=ROOT/'development/server_finalization_20261014'
ARCHIVE=ROOT/'archive/server_finalization_20261014'
EPHEMERAL={'__pycache__','.pytest_cache','.ruff_cache','.mypy_cache'}


def git(repo,*args):
    r=subprocess.run(['git','-C',str(repo),*args],capture_output=True)
    if r.returncode:
        raise RuntimeError('Git operation failed: '+r.stderr.decode(errors='replace'))
    return r.stdout


def textgit(repo,*args):
    return git(repo,*args).decode('utf-8').strip()


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''): h.update(block)
    return h.hexdigest()


def save(path,value):
    Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')


def scoped(path):
    path=Path(path)
    resolved=path.resolve()
    assert resolved!=ROOT and ROOT in resolved.parents,(str(path),'out of scope')
    assert path.absolute()==resolved,('symlinked target',str(path))
    return resolved


def runtime():
    active=json.loads((ROOT/'run/production.active.json').read_text())
    assert active['commit']=='9db0ee776c25afa8d2719ab700b2de7ccc606142'
    assert active['worktree']==str(ROOT/'wt/release-e3')
    args=active['argv']; host=args[args.index('--host')+1];port=args[args.index('--port')+1]
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open('http://'+host+':'+port+'/health',timeout=10) as response: health=json.load(response)
    assert health['maintenance']=='serving'
    assert subprocess.check_output(['docker','inspect','-f','{{.State.Running}}','ollama'],text=True).strip()=='false'
    return {'active':active,'instance':health['instance_id'],'epoch':health['backend_epoch'],'restarts':health['restart_attempts']}


def process_refs(paths):
    found=set()
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit(): continue
        try:
            values=[(proc/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace'),os.readlink(proc/'cwd')]
            env=(proc/'environ').read_bytes().split(b'\0')
            values += [v.decode(errors='replace') for v in env if v.startswith(b'PYTHONPATH=')]
            maps=(proc/'maps').read_text(errors='replace')
            values.append(maps)
            for path in paths:
                if any(path in v for v in values): found.add(path)
        except (OSError,PermissionError): pass
    return found


def protected_files(paths,inventory):
    records={}
    for source in paths:
        p=Path(source)
        if not (p/'.git').exists(): continue
        records[str(p)]={'head':textgit(p,'rev-parse','HEAD'),'tree':textgit(p,'rev-parse','HEAD^{tree}'),'files':{}}
        names=[n for n in git(p,'ls-files','-z').decode().split('\0') if n]
        names += [str(v.relative_to(p)) for v in (p/'python/freetoken/kernel').glob('*.so')]
        for name in sorted(set(names)):
            file=p/name
            if file.is_symlink(): value='symlink:'+os.readlink(file)
            elif file.is_file(): value=sha(file)
            else: continue
            records[str(p)]['files'][name]=value
    manifests={v['path']:sha(v['path']) for v in inventory['e3_binary_manifests']}
    return {'worktrees':records,'frozen_manifests':manifests}


def original_evidence():
    dirs=[Path('/data2/_shared/runs/ft_rounds'),Path('/data2/_shared/runs/ft_releases')]
    records={}
    for root in dirs:
        manifests={}
        if root.exists():
            for file in root.glob('*/SHA256SUMS'):
                manifests[str(file)]=sha(file)
            for file in root.glob('*/manifest.json'):
                manifests[str(file)]=sha(file)
        records[str(root)]={'exists':root.exists(),'manifests':manifests}
    return records


def prepare():
    os.umask(0o077)
    ARCHIVE.mkdir(parents=True,exist_ok=False)
    inventory=json.loads((HERE/'inventory.json').read_text())
    before=runtime()
    all_paths=[w['worktree'] for r in inventory['repositories'] for w in r['worktrees']]
    protected={str(ROOT/'src/FreeToken'),str(ROOT/'wt/release-e3'),str(ROOT/'wt/release-e2')}
    for manifest in inventory['e3_binary_manifests']:
        protected.update(v['path'] for v in manifest['content'].get('worktrees',{}).values())
    protected.update(process_refs(all_paths))
    for repo in inventory['repositories']:
        for wt in repo['worktrees']:
            p=Path(wt['worktree'])
            if not str(p).startswith(str(ROOT)+'/') or ROOT/'runs' in p.parents:
                protected.add(str(p))
    # Preserve dependencies reached through symlinks in a protected source tree.
    changed=True
    while changed:
        changed=False
        for source in list(protected):
            p=Path(source)
            if not p.exists() or not str(p).startswith(str(ROOT)+'/'): continue
            for base,dirs,files in os.walk(p,followlinks=False):
                dirs[:]=[d for d in dirs if d not in {'.git','__pycache__','models','venv','.venv'}]
                for name in dirs+files:
                    file=Path(base)/name
                    if file.is_symlink():
                        resolved=file.resolve()
                        for candidate in all_paths:
                            q=Path(candidate)
                            if (resolved==q or q in resolved.parents) and candidate not in protected:
                                protected.add(candidate); changed=True
    protection=protected_files(protected,inventory)
    evidence=original_evidence()
    repositories=[]
    for index,repo in enumerate(inventory['repositories']):
        primary=repo['worktrees'][0]['worktree']
        path=Path(primary)
        label='repo-%02d'%index
        dest=ARCHIVE/label;dest.mkdir()
        refs=textgit(path,'for-each-ref','--format=%(refname) %(objectname)').splitlines()
        for row in refs:
            ref,commit=row.split(' ',1)
            if ref.startswith('refs/heads/'):
                tag='archive/server-finalization-20261014/'+ref[len('refs/heads/'):]
                git(path,'tag',tag,commit)
        for number,wt in enumerate(repo['worktrees']):
            git(path,'tag','archive/server-finalization-20261014/head-%02d'%number,wt['HEAD'])
        bundle=dest/'all_refs.bundle'
        git(path,'bundle','create',str(bundle),'--all')
        git(path,'bundle','verify',str(bundle))
        common=Path(repo['common'])
        shallow=(common/'shallow').read_bytes() if (common/'shallow').exists() else b''
        (dest/'shallow.txt').write_bytes(shallow)
        items=[]
        for number,wt in enumerate(repo['worktrees']):
            if wt['worktree'] in protected: continue
            source=scoped(wt['worktree'])
            assert source.parent==ROOT/'wt' or source.parent==ROOT/'development/local_finalization_20261014'
            assert textgit(source,'rev-parse','HEAD')==wt['HEAD']
            status=textgit(source,'status','--porcelain')
            archive=dest/('worktree-%02d.tar.gz'%number)
            extras=git(source,'ls-files','--others','-z').decode().split('\0')
            modified=git(source,'diff','HEAD','--name-only','-z').decode().split('\0')
            names=sorted(set(n for n in extras+modified if n and not EPHEMERAL.intersection(Path(n).parts)))
            entries=[]
            with tarfile.open(archive,'w:gz',compresslevel=1) as tar:
                for name in names:
                    full=source/name
                    if not full.exists() and not full.is_symlink():
                        entries.append({'path':name,'deleted':True});continue
                    assert not full.is_dir(),('nested repository or unexpected directory',str(full))
                    entry={'path':name,'symlink':os.readlink(full)} if full.is_symlink() else {'path':name,'sha256':sha(full)}
                    tar.add(full,arcname=name,recursive=False)
                    entries.append(entry)
            with tarfile.open(archive,'r:gz') as tar:
                for entry in entries:
                    if entry.get('deleted'): continue
                    member=tar.getmember(entry['path'])
                    if 'symlink' in entry:
                        assert member.linkname==entry['symlink']
                    else:
                        h=hashlib.sha256()
                        stream=tar.extractfile(member)
                        for block in iter(lambda:stream.read(1048576),b''): h.update(block)
                        assert h.hexdigest()==entry['sha256']
            patch=dest/('worktree-%02d.patch'%number)
            patch.write_bytes(git(source,'diff','--binary','HEAD'))
            index_patch=dest/('worktree-%02d-index.patch'%number)
            index_patch.write_bytes(git(source,'diff','--cached','--binary'))
            assert textgit(source,'status','--porcelain')==status
            items.append({**wt,'status':status,'archive':str(archive),'archive_sha256':sha(archive),'patch':str(patch),'patch_sha256':sha(patch),'index_patch':str(index_patch),'index_patch_sha256':sha(index_patch),'entries':entries})
        kept_branches={w['branch'] for w in repo['worktrees'] if w['worktree'] in protected and w.get('branch')}
        repositories.append({'primary':primary,'label':label,'bundle':str(bundle),'bundle_sha256':sha(bundle),'shallow_sha256':sha(dest/'shallow.txt'),'original_refs':refs,'kept_branches':sorted(kept_branches),'remove':items})
        print(json.dumps({'prepared_repository':label,'worktrees_backed_up':len(items)}),flush=True)
    assert runtime()==before
    plan={'at':datetime.datetime.now().astimezone().isoformat(),'prepared_script_sha256':sha(Path(__file__)),'runtime':before,'protected_paths':sorted(protected),'protection':protection,'evidence':evidence,'repositories':repositories}
    save(ARCHIVE/'PLAN.json',plan)
    print(json.dumps({'prepared':True,'protected_worktrees':len(protected),'retiring_worktrees':sum(len(r['remove']) for r in repositories),'archive':str(ARCHIVE)}),flush=True)


def assert_protected(plan):
    assert runtime()==plan['runtime'],'Production identity/state changed'
    for source,record in plan['protection']['worktrees'].items():
        path=Path(source)
        assert textgit(path,'rev-parse','HEAD')==record['head']
        for name,expected in record['files'].items():
            file=path/name
            actual='symlink:'+os.readlink(file) if file.is_symlink() else sha(file)
            assert actual==expected,('Protected file changed',source,name)
    assert original_evidence()==plan['evidence']
    for file,expected in plan['protection']['frozen_manifests'].items(): assert sha(file)==expected


def execute():
    admission=json.loads((ARCHIVE/'ADMISSION.json').read_text())
    assert sha(ARCHIVE/'PLAN.json')==admission['plan_sha256']
    assert sha(Path(__file__))==admission['execution_script_sha256']
    plan=json.loads((ARCHIVE/'PLAN.json').read_text())
    assert not (ARCHIVE/'RESULT.json').exists()
    assert_protected(plan)
    removal=[w['worktree'] for repo in plan['repositories'] for w in repo['remove']]
    assert not process_refs(removal),'A candidate worktree is referenced by a live process'
    result={'removed_linked_worktrees':[],'archived_primary_repositories':[],'deleted_branches':[]}
    for repo in plan['repositories']:
        primary=Path(repo['primary'])
        assert sha(repo['bundle'])==repo['bundle_sha256']
        assert sha(ARCHIVE/repo['label']/'shallow.txt')==repo['shallow_sha256']
        for wt in repo['remove']:
            source=scoped(wt['worktree'])
            assert source not in [Path(p) for p in plan['protected_paths']]
            assert textgit(source,'rev-parse','HEAD')==wt['HEAD']
            assert textgit(source,'status','--porcelain')==wt['status']
            assert sha(wt['archive'])==wt['archive_sha256']
            assert sha(wt['patch'])==wt['patch_sha256']
            assert sha(wt['index_patch'])==wt['index_patch_sha256']
            for entry in wt['entries']:
                if 'sha256' in entry: assert sha(source/entry['path'])==entry['sha256']
                if 'symlink' in entry: assert os.readlink(source/entry['path'])==entry['symlink']
            if source==primary: continue
            assert source.parent==ROOT/'wt' or source.parent==ROOT/'development/local_finalization_20261014'
            git(primary,'worktree','remove','--force',str(source))
            assert not source.exists()
            result['removed_linked_worktrees'].append(str(source))
            save(ARCHIVE/'PROGRESS.json',result)
        if repo['primary'] not in plan['protected_paths']:
            git(primary,'switch','--detach','HEAD')
        for row in repo['original_refs']:
            ref,head=row.split(' ',1)
            if ref.startswith('refs/heads/') and ref not in repo['kept_branches']:
                assert textgit(primary,'rev-parse',ref)==head
                git(primary,'branch','-D',ref[len('refs/heads/'):])
                result['deleted_branches'].append({'repository':repo['label'],'branch':ref,'head':head})
                save(ARCHIVE/'PROGRESS.json',result)
        if repo['primary'] not in plan['protected_paths']:
            destination=scoped(ARCHIVE/repo['label']/'retained_repository')
            assert not destination.exists()
            assert len(textgit(primary,'worktree','list','--porcelain').split('\n\n'))==1
            shutil.move(str(scoped(primary)),str(destination))
            git(destination,'worktree','repair')
            git(destination,'fsck','--connectivity-only')
            result['archived_primary_repositories'].append({'original':str(primary),'archive':str(destination)})
            save(ARCHIVE/'PROGRESS.json',result)
        assert_protected(plan)
    result.update({'at':datetime.datetime.now().astimezone().isoformat(),'runtime_unchanged':True,'protected_files_unchanged':True,'evidence_manifests_unchanged':True,'ollama_running':False,'service_actions':0,'generation_calls':0})
    save(ARCHIVE/'RESULT.json',result)
    print(json.dumps({'complete':True,'removed_linked_worktrees':len(result['removed_linked_worktrees']),'archived_primary_repositories':len(result['archived_primary_repositories']),'deleted_branches':len(result['deleted_branches']),'runtime_unchanged':True}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['prepare','execute','verify'])
    args=parser.parse_args()
    if args.action=='prepare': prepare()
    elif args.action=='execute': execute()
    else:
        assert_protected(json.loads((ARCHIVE/'PLAN.json').read_text()))
        print(json.dumps({'protected_runtime_files_evidence_verified':True}))
