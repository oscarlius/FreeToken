set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,pathlib,socket,subprocess
root=pathlib.Path('/data2/_shared/runs/ft_rounds')
assert not pathlib.Path('/data2/_shared/gpu.lock').exists()
with socket.socket() as s: assert s.connect_ex(('127.0.0.1',8095))!=0
for rid,batch in [('E2-pre-gate-D01',24),('E2-pre-gate-D02',25)]:
    d=root/rid
    assert json.loads((d/f'gate_batch{batch}.json').read_text())['proposed_verdict']=='kept'
    assert json.loads((d/f'review_batch{batch}.json').read_text())['verdict']=='PASS'
    for line in (d/'MANIFEST.sha256').read_text().splitlines():
        sha,name=line.split('  ',1)
        assert hashlib.sha256((d/name).read_bytes()).hexdigest()==sha,name
wt='/data2/FreeToken/wt/e2base'
def git(*args): return subprocess.check_output(['git','-C',wt,*args],text=True).strip()
assert git('branch','--show-current')=='e2/base'
assert git('rev-parse','--short=7','HEAD')=='3db7b50'
assert not git('status','--porcelain','--untracked-files=no')
assert git('rev-parse','--short=7','E2-pre^{commit}')=='3db7b50'
subprocess.run(['git','-C',wt,'merge-base','--is-ancestor','HEAD','23f2e2c'],check=True)
subprocess.run(['git','-C',wt,'merge','--ff-only','23f2e2c'],check=True)
assert git('rev-parse','HEAD^{tree}')=='abf260e436a793ef28827962193de4c94067d004'
assert not git('status','--porcelain','--untracked-files=no')
print('D00 CANDIDATE INTEGRATED '+git('rev-parse','HEAD')+'; E2-pre preserved; E2-base not tagged')
PY
