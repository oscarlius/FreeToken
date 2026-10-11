set -euo pipefail
test ! -e /data2/_shared/gpu.lock
test ! -e /data2/_shared/runs/ft_rounds/E2-R009-p64k
test "$(sha256sum /data2/_shared/runs/ft_rounds/E2-R009/MANIFEST.sha256 | cut -d ' ' -f 1)" = d0b8ef2a7597c438fb0cda68fd89d30d287280b6f9c965d7ef95007cf68c4fca
/data2/FreeToken/venv/bin/python /data2/FreeToken/scripts/round_json_append.py /data2/_shared/runs/ft_rounds/E2-R009 check
/data2/FreeToken/venv/bin/python /data2/FreeToken/runs/plan_batches/e2_launch.py --card T08-P2
