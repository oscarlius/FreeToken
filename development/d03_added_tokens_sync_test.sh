set -euo pipefail
wt=/data2/FreeToken/wt/e1r003st
test "$(git -C "$wt" rev-parse HEAD)" = fda62d9e763bab66b54e8ed3ac398ae78bbf0080
test -z "$(git -C "$wt" status --porcelain --untracked-files=no)"
git -C "$wt" fetch /data2/FreeToken/runs/plan_batches/d03-added-tokens.bundle exp/e1r003-statetools
test "$(git -C "$wt" rev-parse FETCH_HEAD)" = 326749079e163785b8f2ec92c90be18d74969e6d
git -C "$wt" merge --ff-only FETCH_HEAD
test -z "$(git -C "$wt" status --porcelain --untracked-files=no)"
cd "$wt"
log=/data2/FreeToken/runs/dev_D03/targeted_cpu_added_tokens.log
test ! -e "$log"
CUDA_VISIBLE_DEVICES='' PYTHONPATH=python /data2/FreeToken/venv/bin/python -m pytest -q tests/kvcache/test_state_dump_at.py tests/server/test_dev_logits.py tests/scripts/test_logits_probe.py scripts/tests/test_state_envelope.py tests/tokenizer/test_tokenize.py > "$log" 2>&1 || { tail -n 50 "$log"; exit 1; }
tail -n 6 "$log"
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,pathlib,subprocess
p=pathlib.Path('/data2/FreeToken/runs/dev_D03/targeted_cpu_added_tokens.log')
print('TARGETED_LOG_SHA256',hashlib.sha256(p.read_bytes()).hexdigest())
print('CANDIDATE_COMMIT',subprocess.check_output(['git','-C','/data2/FreeToken/wt/e1r003st','rev-parse','HEAD'],text=True).strip())
PY
