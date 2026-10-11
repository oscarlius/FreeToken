"""Low-cost environmental receipts for one birth-bound, already running round."""
import argparse
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import subprocess
import time


def alive(pid, ticks):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        return fields[0] != 'Z' and int(fields[19]) == ticks
    except (FileNotFoundError, ProcessLookupError):
        return False


def snapshot():
    rows = subprocess.check_output(['ps', '-eLo', 'pid,lwp,stat,comm', '--no-headers'], text=True).splitlines()
    running = [row for row in rows if row.split()[2].startswith('R')]
    return {'at': datetime.now(timezone(timedelta(hours=8))).isoformat(),
            'uptime': subprocess.check_output(['uptime'], text=True).strip(),
            'running_thread_count': len(running), 'running_thread_rows': running,
            'environment_change_at': '2026-10-10T20:35:15+08:00',
            'cross_change_batch_comparisons': '环境不同'}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--pid', type=int, required=True)
    p.add_argument('--start-ticks', type=int, required=True)
    p.add_argument('--rid', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    # Neither this watcher nor its PID is a GPU or service lifecycle authority.
    with a.output.open('x') as out:
        while True:
            live = alive(a.pid, a.start_ticks)
            out.write(json.dumps({**snapshot(), 'rid': a.rid, 'round_process_alive': live}, ensure_ascii=False) + '\n')
            out.flush()
            if not live:
                return
            time.sleep(15)


if __name__ == '__main__':
    main()
