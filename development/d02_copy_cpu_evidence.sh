set -euo pipefail
cp -n /data2/FreeToken/runs/dev_D02/cpu_regression.log /data2/FreeToken/runs/dev_D02/cpu_regression_23f2e2c.log
git -C /data2/FreeToken/wt/e1ms rev-parse HEAD
git -C /data2/FreeToken/wt/e1ms rev-parse 'HEAD^{tree}'
