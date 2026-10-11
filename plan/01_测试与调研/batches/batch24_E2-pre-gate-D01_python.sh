#!/bin/bash
set -euo pipefail
exec /data2/FreeToken/venv/bin/python -u /data2/FreeToken/runs/plan_batches/t16_runner.py --gate D01 --rid E2-pre-gate-D01 --batch 24 --run
