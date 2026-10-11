set -eu
pid=880187
ps -o pid,pgid,args -p "$pid"
kill -- -"$pid"
sleep 30
kill -9 -- -"$pid" 2>/dev/null || true
ps -o pid,pgid,args -p "$pid" || true
