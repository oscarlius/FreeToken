"""Read existing overnight observation, process identities and health records."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'development/r067c_retry2_production_control_20261009'))
import ssh_ops

CODE = r'''
from pathlib import Path
import json
from datetime import datetime, timezone
p=Path('/data2/FreeToken/runs/observation/OBSERVE-481-20261009-OVERNIGHT-01')
lines=(p/'samples.jsonl').read_text().splitlines()
active=json.loads(Path('/data2/FreeToken/run/production.active.json').read_text())
ids={}
for role in ('supervisor','service'):
    item=active[role]
    fields=Path('/proc/%s/stat'%item['pid']).read_text().rsplit(')',1)[1].split()
    ids[role]={'pid':item['pid'],'expected_start_ticks':item['start_ticks'],'actual_start_ticks':int(fields[19]),'state':fields[0]}
print(json.dumps({'captured_at':datetime.now(timezone.utc).isoformat(), 'terminal_exists':(p/'terminal.json').exists(),
 'samples':len(lines),'last':json.loads(lines[-1]) if lines else None,'active_approval':active['approval_id'],
 'commit':active['commit'],'process_identities':ids},ensure_ascii=False))
'''


def main():
    client = ssh_ops.connect()
    try:
        output = ssh_ops.run(client, CODE)
    finally:
        client.close()
    data = json.loads(output)
    data['local_recorded_at'] = datetime.now(timezone(timedelta(hours=8))).isoformat()
    data['action'] = 'read_existing_files_and_proc_only_no_http'
    (HERE / 'OBSERVATION_SNAPSHOT.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
