set -euo pipefail
mkdir -p /data2/FreeToken/runs/dev_D03/t10_stage2_r013_from_r017_37e10f2
test ! -e /data2/FreeToken/runs/dev_D03/t10_stage2_r013_from_r017_37e10f2/development
mkdir -p /data2/FreeToken/runs/dev_D03/t10_stage2_r013_from_r017_37e10f2/development/tests
cp /data2/FreeToken/runs/dev_D03/phase2_close_r017_a52e39e/development/d03_phase2_prepare_r017.py /data2/FreeToken/runs/dev_D03/t10_stage2_r013_from_r017_37e10f2/development/d03_phase2_prepare_r017.py
