set -euo pipefail
target=/data2/FreeToken/runs/dev_D03/t10_retry_r016_ready
test ! -e "$target"
mkdir "$target"
mkdir "$target/development" "$target/development/tests"
