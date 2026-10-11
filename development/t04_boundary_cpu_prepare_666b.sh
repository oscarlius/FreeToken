set -euo pipefail
target=/data2/FreeToken/runs/dev_D03/t04_boundary_cpu_666bdb5
test ! -e "$target"
mkdir -p "$target/development/tests"
ln -s /data2/FreeToken/runs/dev_D03/continuation_cpu_71f93be/repo "$target/development/e2d03-continuation"
