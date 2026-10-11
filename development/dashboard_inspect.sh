set -euo pipefail
ss -ltnp 'sport = :8099 or sport = :8088'
for port in 8099 8088; do
  printf 'DASHBOARD_HTTP %s\n' "$port"
  curl --max-time 5 -sS -I "http://127.0.0.1:$port/" || true
done
if [ -d /data2/_shared/model_hub_dashboard ]; then
  printf 'DASHBOARD_FILES\n'
  find /data2/_shared/model_hub_dashboard -maxdepth 2 -type f \( -name '*.py' -o -name '*.html' -o -name 'AGENTS.md' -o -name '*DASHBOARD*.md' -o -name '*.service' \) -printf '%P\n' | head -60
fi
