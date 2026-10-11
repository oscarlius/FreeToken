set -euo pipefail
wt=/data2/FreeToken/wt/e1r003st
test "$(git -C "$wt" rev-parse HEAD)" = 23f2e2caa3395837c9474735ffc83321f3b9b5a1
git -C "$wt" fetch /data2/FreeToken/runs/plan_batches/d03.bundle exp/e1r003-statetools
test "$(git -C "$wt" rev-parse FETCH_HEAD)" = fda62d9e763bab66b54e8ed3ac398ae78bbf0080
git -C "$wt" stash push --include-untracked -m 'preserve D03 CPU-tested source snapshot before immutable checkout'
git -C "$wt" switch -c exp/e1r003-statetools FETCH_HEAD
test -z "$(git -C "$wt" status --porcelain --untracked-files=no)"
/data2/FreeToken/venv/bin/python - <<'PY'
import pathlib,tarfile,subprocess,hashlib
wt=pathlib.Path('/data2/FreeToken/wt/e1r003st')
with tarfile.open('/data2/FreeToken/runs/plan_batches/d03-cpu-source.tar.gz') as archive:
    for member in archive.getmembers():
        before=archive.extractfile(member).read().replace(b'\r\n',b'\n')
        after=(wt/member.name).read_bytes().replace(b'\r\n',b'\n')
        assert before==after,member.name
print('D03 committed source matches all 22 CPU-tested files after newline normalization')
for key in ['HEAD','HEAD^{tree}','HEAD^']:
    print(key,subprocess.check_output(['git','rev-parse',key],cwd=wt,text=True).strip())
for name in ['scripts/state_envelope.py','scripts/logits_probe.py']:
    print(name,'md5',hashlib.md5((wt/name).read_bytes()).hexdigest())
print('D03 clean immutable worktree ready; no candidate GPU run performed')
PY
