set -euo pipefail
CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python - <<'PY'
import json,pathlib,torch
root=pathlib.Path('/data2/_shared/runs/ft_rounds/E1-R003-stateeq')
def load(arm):
    d=root/arm
    row=next(r for r in map(json.loads,(d/'index.jsonl').read_text().splitlines()) if r['kind']=='donate' and r['length']==12416)
    return torch.load(d/row['files']['conv_states'],map_location='cpu')
a,b=load('dump_A'),load('dump_B')
for i in [0,*range(31,36)]:
    aa,bb=a[i].float(),b[i].float()
    diff=torch.linalg.vector_norm(aa-bb)
    ra=100*diff/torch.linalg.vector_norm(aa)
    rb=100*diff/torch.linalg.vector_norm(bb)
    bf=100*torch.linalg.vector_norm((a[i]-b[i]).float())/torch.linalg.vector_norm(aa)
    print(i,'ref_A',round(ra.item(),4),'ref_B',round(rb.item(),4),'bf16_sub_A',round(bf.item(),4))
PY
