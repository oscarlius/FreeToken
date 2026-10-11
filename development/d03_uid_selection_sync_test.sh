set -euo pipefail
wt=/data2/FreeToken/wt/e1r003st
test "$(git -C "$wt" rev-parse HEAD)" = 2e5cdab707ff8dde8723f138c45a6ba73a3a43f6
test -z "$(git -C "$wt" status --porcelain --untracked-files=no)"
git -C "$wt" fetch /data2/FreeToken/runs/plan_batches/d03-uid-selection.bundle exp/e1r003-statetools
test "$(git -C "$wt" rev-parse FETCH_HEAD)" = c30ae0d7003c3bbbf56867ce74da797332fa7ed5
git -C "$wt" merge --ff-only FETCH_HEAD
test -z "$(git -C "$wt" status --porcelain --untracked-files=no)"
cd "$wt"
log=/data2/FreeToken/runs/dev_D03/targeted_cpu_uid_selection.log
test ! -e "$log"
CUDA_VISIBLE_DEVICES='' PYTHONPATH=python /data2/FreeToken/venv/bin/python -m pytest -q tests/kvcache/test_state_dump_at.py tests/server/test_dev_logits.py tests/scripts/test_logits_probe.py scripts/tests/test_state_envelope.py tests/tokenizer/test_tokenize.py tests/scheduler/test_dev_tokens.py > "$log" 2>&1 || { tail -n 60 "$log"; exit 1; }
tail -n 6 "$log"
sha256sum "$log"
git rev-parse HEAD
md5sum scripts/state_envelope.py
