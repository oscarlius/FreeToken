#!/usr/bin/env bash
# Loopback-only verification.  No model URL, GPU service, or datasets are used.
set -euo pipefail

toolchain_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
receipt="$toolchain_dir/receipt-$(date -u +%Y%m%dT%H%M%SZ).txt"
exec > >(tee "$receipt") 2>&1

echo "utc=$(date -u +%FT%TZ)"
echo "toolchain_dir=$toolchain_dir"
sha256sum "$toolchain_dir/requirements-aiperf.txt" "$toolchain_dir/requirements-eval.txt" "$toolchain_dir/bootstrap_remote.sh" "$toolchain_dir/verify_remote.sh" "$toolchain_dir/test_openai_fixture.py" "$toolchain_dir/test_aiperf_fixture.py"
"$toolchain_dir/venv-aiperf/bin/python" -m pip check
"$toolchain_dir/venv-eval/bin/python" -m pip check
"$toolchain_dir/venv-aiperf/bin/aiperf" --version
"$toolchain_dir/venv-aiperf/bin/aiperf" validate --help >/dev/null
"$toolchain_dir/venv-eval/bin/lm_eval" --help >/dev/null
"$toolchain_dir/venv-aiperf/bin/python" -c "import aiperf; import importlib.metadata as m; print('aiperf=' + m.version('aiperf'))"
"$toolchain_dir/venv-eval/bin/python" -c "import lm_eval, openai; import importlib.metadata as m; print('openai=' + m.version('openai')); print('pytest=' + m.version('pytest')); print('lm-eval=' + m.version('lm-eval'))"
"$toolchain_dir/venv-eval/bin/python" -m pytest -q "$toolchain_dir/test_openai_fixture.py" "$toolchain_dir/test_aiperf_fixture.py"
