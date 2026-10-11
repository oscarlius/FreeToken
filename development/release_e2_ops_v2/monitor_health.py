"""Minimal external watchdog: health once per minute and supervisor-exit alerts."""
import argparse
import json
from pathlib import Path
import time
import urllib.request

from release_config import HOST


def append(path, payload):
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + '\n')


def write_alert(run_dir, event, details):
    append(Path(run_dir) / 'alerts.jsonl', {'at': time.time(), 'event': event, 'details': details})


def health():
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open('http://' + HOST + ':8095/health', timeout=10) as response:
        payload = json.loads(response.read())
        good = response.status == 200 and payload.get('status') == 'ok' and payload.get('maintenance') == 'serving'
        return {'healthy': good, 'http_status': response.status, 'payload': payload}


STARTUP_TIMEOUT = 1800  # same cold-start bound as the deploy handbook


def monitor(run_dir, supervisor, identity, check=health, sleep=time.sleep, clock=time.monotonic):
    failures = 0
    started = next_check = clock()
    serving_seen = startup_alerted = False
    while True:
        current = identity(supervisor['pid'])
        if (current is None or current.get('state') == 'Z' or
                any(current.get(k) != supervisor.get(k) for k in ('pid', 'start_ticks', 'pgid', 'session'))):
            # release_control.stop() writes stop_<approval>.json before SIGTERM, so its
            # presence marks an approved stop. stopped.json is not usable here: the
            # supervisor's finally writes it on crashes too.
            if not any(Path(run_dir).glob('stop_*.json')):
                write_alert(run_dir, 'supervisor_exit', {'expected': supervisor, 'observed': current})
            return
        now = clock()
        if now >= next_check:
            try:
                result = check()
            except Exception as exc:
                result = {'healthy': False, 'error': repr(exc)}
            serving_seen = serving_seen or result['healthy']
            # Cold start (expert banks, PLE) legitimately reports loading for minutes:
            # count failures only after the first serving, and alert once on timeout.
            if serving_seen:
                failures = 0 if result['healthy'] else failures + 1
            append(run_dir / 'health_monitor.jsonl', {'at': time.time(), 'consecutive_failures': failures,
                                                      'serving_seen': serving_seen, **result})
            if failures == 3:
                write_alert(run_dir, 'three_consecutive_health_failures', result)
            if not serving_seen and not startup_alerted and now - started >= STARTUP_TIMEOUT:
                write_alert(run_dir, 'startup_not_serving', result)
                startup_alerted = True
            next_check = now + 60
        sleep(min(1, max(0, next_check - clock())))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--supervisor', required=True)
    args = parser.parse_args()
    from release_control import helpers
    monitor(args.run_dir, json.loads(args.supervisor), helpers().process_identity)


if __name__ == '__main__':
    main()
