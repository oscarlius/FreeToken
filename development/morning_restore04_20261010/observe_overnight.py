"""Task-owned RESTORE481 adaptation of the reviewed read-only watchdog observer."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import time

def write_new(path, value):
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False); handle.write('\n')
def alive(item):
    try:
        fields = Path(f"/proc/{item['pid']}/stat").read_text().rsplit(')', 1)[1].split()
        return fields[0] != 'Z' and int(fields[19]) == item['start_ticks']
    except (FileNotFoundError, ProcessLookupError): return False
def records(path):
    if not path.exists(): return []
    rows = []
    for line in path.read_text().splitlines():
        try: rows.append(json.loads(line))
        except json.JSONDecodeError: pass
    return rows
def sample(run, owner):
    active = Path('/data2/FreeToken/run/production.active.json'); same = active.exists() and json.loads(active.read_text()) == owner
    history, alerts = records(run / 'health_monitor.jsonl'), records(run / 'alerts.jsonl'); latest = history[-1] if history else None
    payload, now = (latest or {}).get('payload', {}), time.time()
    return {'at': now, 'active_owner_matches': same, 'supervisor_alive': alive(owner['supervisor']), 'service_alive': alive(owner['service']), 'monitor_alive': alive(owner['monitor']), 'watchdog_rows': len(history), 'watchdog_latest': latest, 'watchdog_fresh': latest is not None and now - latest['at'] <= 180, 'alerts_count': len(alerts), 'alerts': alerts, 'backend_epoch': payload.get('backend_epoch'), 'restart_attempts': payload.get('restart_attempts')}
def eligible(row):
    return (row['active_owner_matches'] and row['supervisor_alive'] and row['service_alive'] and row['monitor_alive'] and row['watchdog_fresh'] and row['alerts_count'] == 0 and (row['watchdog_latest'] or {}).get('healthy') is True and row['backend_epoch'] == 0 and row['restart_attempts'] == 0)
def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--run-dir', type=Path, required=True); parser.add_argument('--out-dir', type=Path, required=True); parser.add_argument('--until', required=True); args = parser.parse_args()
    until = datetime.fromisoformat(args.until).timestamp()
    if until <= time.time(): raise RuntimeError('observation deadline must remain in the future')
    owner = json.loads((args.run_dir / 'owner.json').read_text())
    if owner.get('commit') != '481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9': raise RuntimeError('observer owner commit is not RESTORE481')
    if owner.get('approval_id') != 'RESTORE481-MORNING-20261010-04': raise RuntimeError('observer owner approval differs')
    if json.loads((args.run_dir / 'smoke_execution_result.json').read_text()).get('exit_code') != 0: raise RuntimeError('observer requires a passing RESTORE481 smoke')
    args.out_dir.mkdir(parents=True, exist_ok=False)
    write_new(args.out_dir / 'start.json', {'at': time.time(), 'until': args.until, 'until_epoch': until, 'owner': owner, 'observer_pid': os.getpid(), 'source_run': str(args.run_dir), 'generation_requests': 0, 'service_mutations': 0})
    samples, issues, previous_state, started = 0, [], None, time.time()
    while True:
        row = sample(args.run_dir, owner); samples += 1; good = eligible(row); state = (good, row['alerts_count'], row['backend_epoch'], row['restart_attempts'])
        if not good and state != previous_state: issues.append({'sample': samples, 'state': state, 'at': row['at']}); print(json.dumps({'event': 'observation_requires_review', 'row': row}), flush=True)
        with (args.out_dir / 'samples.jsonl').open('a', encoding='utf-8') as handle: handle.write(json.dumps(row, ensure_ascii=False) + '\n'); handle.flush()
        previous_state = state
        if time.time() >= until:
            result = {'at': time.time(), 'started_at': started, 'until': args.until, 'samples': samples, 'issues': issues, 'final': row, 'classification': 'clean_observation' if not issues and good else 'requires_review', 'eligible_to_request_push_approval': not issues and good, 'push_approved': False, 'push_executed': False}
            write_new(args.out_dir / 'terminal.json', result); print(json.dumps({'event': 'observation_completed', **result}), flush=True); return 0
        time.sleep(min(60, max(1, until - time.time())))
if __name__ == '__main__': raise SystemExit(main())
