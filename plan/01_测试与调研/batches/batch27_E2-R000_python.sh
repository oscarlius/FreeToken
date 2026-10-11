#!/bin/bash
set -euo pipefail
exec /data2/FreeToken/venv/bin/python -u /data2/FreeToken/runs/plan_batches/t00_runner.py --batch 27 --run
