set -euo pipefail
round=/data2/_shared/runs/ft_rounds/E2-R024-gate-D07
test -d "$round"
find "$round" -maxdepth 2 -type f -printf '%P\n' | sort
printf '%s\n' '--- control ---'
for name in status_batch52.json review_batch52.json round.json MANIFEST.sha256 initial_metadata.json; do
  if test -e "$round/$name"; then sha256sum "$round/$name"; else printf 'absent %s\n' "$name"; fi
done
printf '%s\n' '--- terminal ownership ---'
python3 - <<'PY'
import json, pathlib
round=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R024-gate-D07')
status=json.loads((round/'status_batch52.json').read_text())
print(json.dumps({key:status.get(key) for key in ('rid','batch','state','candidate_case','batch_pid','batch_start_ticks')},sort_keys=True))
for path in sorted(round.glob('*/serve_args.txt')):
    print(path.parent.name, path.read_text(errors='replace').strip().splitlines()[-1])
PY
stat -c '%a %u %n' "$round"
