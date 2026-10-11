set -euo pipefail
target=/data2/FreeToken/runs/dev_D03/t10_retry_r017_8a7f9e3
test ! -e "$target"
mkdir "$target"
mkdir "$target/development" "$target/development/tests"
