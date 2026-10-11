#!/bin/bash
python3 - <<'PY'
import json
from pathlib import Path
p=Path("/home/dell/.cache/freetoken/benchbw/GPU-052dcdb7-8f82-efdb-c9c0-8bef86e41efa.json")
print(p.read_text()[:3000])
PY
echo '====CWD===='
ls -l /proc/594162/cwd
echo '====STDOUT===='
readlink /proc/594162/fd/1; readlink /proc/594162/fd/2
echo '====SCRIPTS===='
ls /data2/FreeToken/scripts 2>/dev/null
ls /home/dell/*.sh 2>/dev/null | head
