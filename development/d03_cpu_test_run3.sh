set -euo pipefail
wt=/data2/FreeToken/wt/e1r003st
base=23f2e2caa3395837c9474735ffc83321f3b9b5a1
if [ ! -e "$wt" ]; then
    git -C /data2/FreeToken/wt/e2base worktree add --detach "$wt" "$base"
fi
test "$(git -C "$wt" rev-parse HEAD)" = "$base"
mkdir -p /data2/FreeToken/runs/dev_D03
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,pathlib,tarfile
wt=pathlib.Path('/data2/FreeToken/wt/e1r003st')
source=pathlib.Path('/data2/FreeToken/runs/plan_batches')
expected=json.loads((source/'d03-cpu-source.sha256.json').read_text())
with tarfile.open(source/'d03-cpu-source.tar.gz') as archive:
    assert set(archive.getnames())==set(expected)
    for member in archive.getmembers():
        assert member.isfile() and wt in (wt/member.name).resolve().parents
    archive.extractall(wt,filter='data')
for name,sha in expected.items():
    assert hashlib.sha256((wt/name).read_bytes()).hexdigest()==sha,name
base=pathlib.Path('/data2/FreeToken/wt/e2base/python/freetoken')
for sourcefile in base.rglob('*.so'):
    dst=wt/'python/freetoken'/sourcefile.relative_to(base)
    if not dst.exists():
        dst.parent.mkdir(parents=True,exist_ok=True)
        dst.symlink_to(sourcefile.resolve())
print('D03 candidate delta SHA256 verified; unchanged compiled extensions linked')
PY
cd "$wt"
run=${D03_CPU_RUN:-3}
log=/data2/FreeToken/runs/dev_D03/targeted_cpu_run${run}.log
test ! -e "$log"
CUDA_VISIBLE_DEVICES='' PYTHONPATH=python /data2/FreeToken/venv/bin/python -m pytest -q tests/kvcache/test_state_dump_at.py tests/server/test_dev_logits.py tests/scripts/test_logits_probe.py scripts/tests/test_state_envelope.py > "$log" 2>&1 || { tail -n 70 "$log"; exit 1; }
tail -n 8 "$log"
