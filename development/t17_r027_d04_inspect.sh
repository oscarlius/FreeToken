set -euo pipefail
r=/data2/_shared/runs/ft_rounds/E2-R027-diagnostic-T17
find "$r" -maxdepth 2 -type f -printf '%P\n' | sort
printf '%s\n' '--- status ---'
cat "$r/status_batch55.json"
printf '%s\n' '--- terminal check ---'
for pid in 588986 589436 603017; do if test -r "/proc/$pid/stat"; then awk '{print $1,$3,$22}' "/proc/$pid/stat"; else echo "$pid absent"; fi; done
printf '%s\n' '--- close files ---'
for n in round.json round_history MANIFEST.sha256 review_batch55.json source_tools batch.sh; do test -e "$r/$n" && echo "present $n" || echo "absent $n"; done