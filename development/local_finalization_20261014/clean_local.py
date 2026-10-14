"""Execute only the reviewed, hash-bound local worktree cleanup."""
import argparse
import json
from pathlib import Path
import shutil

from finalize_workspace import ARCHIVE, HERE, ROOT, digest, git, within, write_json, worktrees


def validate(label, skip_primary=False):
    receipt=json.loads((ARCHIVE/label/'BACKUP_RECEIPT.json').read_text(encoding='utf-8'))
    assert digest(Path(receipt['bundle']))==receipt['bundle_sha256']
    shallow=json.loads((ARCHIVE/label/'SHALLOW_METADATA.json').read_text())
    assert digest(ARCHIVE/label/'shallow.txt')==shallow['sha256']
    source_repo=Path(receipt['repo'])
    common=Path(git(source_repo,'rev-parse','--path-format=absolute','--git-common-dir'))
    source_shallow=(common/'shallow').read_bytes() if (common/'shallow').exists() else b''
    assert source_shallow==(ARCHIVE/label/'shallow.txt').read_bytes()
    assert (git(source_repo,'rev-parse','--is-shallow-repository')=='true')==shallow['shallow']
    for index,wt in enumerate(receipt['worktrees']):
        assert digest(Path(wt['archive']))==wt['sha256']
        if skip_primary and index==0:
            continue
        source=within(Path(wt['worktree']))
        assert git(source,'rev-parse','HEAD')==wt['HEAD']
        assert git(source,'status','--porcelain')==wt['status']
        for entry in wt['entries']:
            if 'sha256' in entry:
                assert digest(source/entry['path'])==entry['sha256']
    return receipt


def execute():
    result={'removed_worktrees':[],'deleted_branches':[],'removed_gitlinks':[]}
    historical=validate('historical_engine')
    retry=validate('r067_retry_engine')
    upstream=validate('upstream_engine',skip_primary=True)
    allowed_gitlinks={Path(wt['worktree']).relative_to(ROOT).as_posix()
                      for receipt in [historical,retry,upstream] for wt in receipt['worktrees']}
    actual_gitlinks=[line.split('\t',1)[1] for line in git(ROOT,'ls-files','--stage').splitlines()
                     if line.startswith('160000 ')]
    assert set(actual_gitlinks)<=allowed_gitlinks
    final=json.loads((HERE/'CPU_FINAL_RECEIPT.json').read_text())
    assert final['exit_code']==0 and final['head']=='a7c24b27612769ff25929c39c7cf65ded34aeccc'
    engine=within(ROOT/'development/e2d01')
    for wt in historical['worktrees'][1:]:
        path=within(Path(wt['worktree']))
        assert path.parent==ROOT/'development'
        git(engine,'worktree','remove','--force',str(path))
        assert not path.exists()
        result['removed_worktrees'].append(str(path))
        write_json(HERE/'CLEANUP_PROGRESS.json',result)
    git(engine,'switch','release/e3')
    for row in historical['refs_before']:
        ref,sha=row.split(' ',1)
        if ref.startswith('refs/heads/'):
            branch=ref.removeprefix('refs/heads/')
            if branch not in {'release/e3','release/e2'}:
                assert git(engine,'rev-parse',ref)==sha
                git(engine,'branch','-D',branch)
                result['deleted_branches'].append({'repo':'product','branch':branch,'head':sha})
                write_json(HERE/'CLEANUP_PROGRESS.json',result)
    assert len(worktrees(engine))==1
    product=within(ROOT/'product')
    assert not product.exists()
    shutil.move(str(engine),str(product))
    git(product,'worktree','repair')
    assert git(product,'rev-parse','HEAD')=='9db0ee776c25afa8d2719ab700b2de7ccc606142'
    result['product']=str(product)
    write_json(HERE/'CLEANUP_PROGRESS.json',result)
    retry_repo=within(ROOT/'development/r067d_retry2_localwt')
    for wt in retry['worktrees'][1:]:
        path=within(Path(wt['worktree']))
        assert path.parent==ROOT/'development'
        git(retry_repo,'worktree','remove','--force',str(path))
        result['removed_worktrees'].append(str(path))
        write_json(HERE/'CLEANUP_PROGRESS.json',result)
    metadata=json.loads((ARCHIVE/'r067_retry_engine/GIT_METADATA_RECEIPT.json').read_text())
    assert metadata['tar_read_verified']
    assert metadata['contains_git_objects']
    assert digest(ARCHIVE/'r067_retry_engine/git_metadata.tar.gz')==metadata['sha256']
    assert len(worktrees(retry_repo))==1
    retained=within(ARCHIVE/'r067_retry_engine/retained_repository')
    assert not retained.exists()
    shutil.move(str(retry_repo),str(retained))
    assert not retry_repo.exists()
    result['removed_worktrees'].append(str(retry_repo))
    result['deleted_branches'] += [{'repo':'r067_retry_engine','branch':row.split()[0].removeprefix('refs/heads/'),'head':row.split()[1]}
                                  for row in retry['refs_before'] if row.startswith('refs/heads/')]
    write_json(HERE/'CLEANUP_PROGRESS.json',result)
    return finish(result,upstream,final,product,allowed_gitlinks)


def finish(result,upstream,final,product,allowed_gitlinks):
    source=within(ROOT/'upstream-flashml')
    head=git(source,'rev-parse','HEAD')
    assert head==final['head']
    git(source,'switch','main')
    git(source,'merge','--ff-only',head)
    for wt in upstream['worktrees'][1:]:
        path=within(Path(wt['worktree']))
        assert path.parent==ROOT/'development'
        git(source,'worktree','remove','--force',str(path))
        result['removed_worktrees'].append(str(path))
        write_json(HERE/'CLEANUP_PROGRESS.json',result)
    branches=git(source,'for-each-ref','--format=%(refname:short)','refs/heads/').splitlines()
    for branch in branches:
        if branch!='main':
            sha=git(source,'rev-parse',branch)
            git(source,'merge-base','--is-ancestor',sha,'HEAD')
            git(source,'branch','-D',branch)
            result['deleted_branches'].append({'repo':'upstream_engine','branch':branch,'head':sha})
            write_json(HERE/'CLEANUP_PROGRESS.json',result)
    for repo in [product,source]:
        exclude=Path(git(repo,'rev-parse','--path-format=absolute','--git-common-dir'))/'info/exclude'
        with exclude.open('a',encoding='utf-8') as out:
            out.write('\n# Local agent metadata; no runtime source change\n.omc/\n.omx/\n')
    paper=within(ROOT/'paper-en')
    manuscript=git(paper,'rev-parse','HEAD')
    paper_tree=git(paper,'rev-parse','HEAD^{tree}')
    assert not git(paper,'status','--porcelain')
    git(paper,'switch','master')
    git(paper,'merge','--ff-only',manuscript)
    for branch in git(paper,'for-each-ref','--format=%(refname:short)','refs/heads/').splitlines():
        if branch!='master':
            sha=git(paper,'rev-parse',branch)
            git(paper,'merge-base','--is-ancestor',sha,'HEAD')
            git(paper,'branch','-d',branch)
            result['deleted_branches'].append({'repo':'paper','branch':branch,'head':sha})
            write_json(HERE/'CLEANUP_PROGRESS.json',result)
    assert git(paper,'rev-parse','HEAD^{tree}')==paper_tree
    for line in git(ROOT,'ls-files','--stage').splitlines():
        if line.startswith('160000 '):
            name=line.split('\t',1)[1]
            if name in allowed_gitlinks:
                git(ROOT,'update-index','--force-remove','--',name)
                result['removed_gitlinks'].append(name)
    review=within(HERE/'review_restore')
    if review.exists():
        retained=within(ARCHIVE/'review_restore')
        assert not retained.exists()
        shutil.move(str(review),str(retained))
        result['archived_review_temp']=str(retained)
    write_json(HERE/'CLEANUP_RECEIPT.json',result)
    print(json.dumps({'worktrees_removed':len(result['removed_worktrees']),
                      'branches_deleted':len(result['deleted_branches']),
                      'gitlinks_removed':len(result['removed_gitlinks']),
                      'product_head':git(product,'rev-parse','HEAD'),
                      'upstream_head':git(source,'rev-parse','HEAD'),
                      'paper_head':git(paper,'rev-parse','HEAD')},ensure_ascii=False))


def resume_after_r067_archive():
    result=json.loads((HERE/'CLEANUP_PROGRESS.json').read_text(encoding='utf-8'))
    product=within(Path(result['product']))
    assert git(product,'rev-parse','HEAD')=='9db0ee776c25afa8d2719ab700b2de7ccc606142'
    assert all(not Path(path).exists() for path in result['removed_worktrees'])
    retry_repo=within(ROOT/'development/r067d_retry2_localwt')
    remnant=within(ARCHIVE/'r067_retry_engine/retained_git_remnant')
    assert not retry_repo.exists() and remnant.exists()
    retry=json.loads((ARCHIVE/'r067_retry_engine/BACKUP_RECEIPT.json').read_text(encoding='utf-8'))
    assert digest(Path(retry['bundle']))==retry['bundle_sha256']
    metadata=json.loads((ARCHIVE/'r067_retry_engine/GIT_METADATA_RECEIPT.json').read_text())
    assert digest(ARCHIVE/'r067_retry_engine/git_metadata.tar.gz')==metadata['sha256']
    result['removed_worktrees'].append(str(retry_repo))
    result['archived_repositories']=[{'original_path':str(retry_repo),'retained_path':str(remnant),
                                   'branch_count':sum(row.startswith('refs/heads/') for row in retry['refs_before'])}]
    upstream=validate('upstream_engine',skip_primary=True)
    historical=json.loads((ARCHIVE/'historical_engine/BACKUP_RECEIPT.json').read_text(encoding='utf-8'))
    allowed={Path(wt['worktree']).relative_to(ROOT).as_posix()
             for receipt in [historical,retry,upstream] for wt in receipt['worktrees']}
    actual=[line.split('\t',1)[1] for line in git(ROOT,'ls-files','--stage').splitlines() if line.startswith('160000 ')]
    assert set(actual)<=allowed
    final=json.loads((HERE/'CPU_FINAL_RECEIPT.json').read_text())
    assert final['exit_code']==0 and final['head']=='a7c24b27612769ff25929c39c7cf65ded34aeccc'
    write_json(HERE/'CLEANUP_PROGRESS.json',result)
    finish(result,upstream,final,product,allowed)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--resume-after-r067-archive',action='store_true')
    args=parser.parse_args()
    if args.resume_after_r067_archive:
        resume_after_r067_archive()
    elif args.execute:
        execute()
    else:
        print('Inert. Reviewed scope: historical 36 linked worktrees, r067 2 worktrees, upstream 2 contribution worktrees; E3 remains exact and deployed service unchanged.')
