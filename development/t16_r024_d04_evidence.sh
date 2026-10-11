set -euo pipefail
round=/data2/_shared/runs/ft_rounds/E2-R024-gate-D07
sha256sum "$round"/{runner_batch52.py,base_runner_batch52.py,candidate_binding.json,gate_batch52.json,batch52.sh,status_batch52.json,tools_batch52.json}
python3 - <<'PY'
import json, pathlib
root=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R024-gate-D07')
for name in ('candidate_binding.json','gate_batch52.json','tools_batch52.json','status_batch52.json'):
    print(name, json.dumps(json.loads((root/name).read_text()),sort_keys=True))
for arm in ('PARENT_b52','NEW_b52','PARENT_P_b52','NEW_P_b52'):
    det=json.loads((root/arm/'det.json').read_text())
    seq=(root/arm/'prefill_seq.txt').read_text().splitlines()
    print(arm, json.dumps({'det_keys':sorted(det),'det':det,'prefill_lines':len(seq),'prefill_tail':seq[-2:]},sort_keys=True))
PY
