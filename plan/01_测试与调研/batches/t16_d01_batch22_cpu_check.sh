#!/bin/bash
set -euo pipefail
PY=python
strict_h2d() {
  $PY - "$1" "$2" <<'PY'
import json,sys
a=[json.loads(x) for x in open(sys.argv[1])]; b=[json.loads(x) for x in open(sys.argv[2])]
if not a or not b or len(a)!=len(b): raise SystemExit('H2D EMPTY_OR_LENGTH')
for i,(x,y) in enumerate(zip(a,b)):
    if (x['h2d_bytes'],x['d2d_bytes']) != (y['h2d_bytes'],y['d2d_bytes']): raise SystemExit('H2D DIFF %d'%i)
PY
}
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
printf '{"h2d_bytes":1,"d2d_bytes":2}\n' > "$tmp/a"
printf '{"h2d_bytes":2,"d2d_bytes":2}\n' > "$tmp/b"
if strict_h2d "$tmp/a" "$tmp/b"; then
  echo 'CPU-STRICT-FAIL: mismatched H2D accepted'
  exit 1
fi
printf '{"h2d_bytes":1,"d2d_bytes":2}\n' > "$tmp/b"
strict_h2d "$tmp/a" "$tmp/b"
echo CPU-STRICT-OK
