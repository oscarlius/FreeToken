import hashlib, json, struct
from pathlib import Path
here = Path(__file__).resolve().parent
for tail, second in ((1, 1), (30, 2), (63, 3), (64, 4)):
    rows = [
        {'start': 0, 'end': 8193, 'mode': 'layer_major', 'subchunks': [4096,4096,1]},
        {'start': 8192, 'end': 8192 + tail, 'mode': 'ordinary', 'subchunks': [tail]},
    ]
    (here / f't{tail}.json').write_text(json.dumps(rows, sort_keys=True), encoding='utf-8')
manifest=[]
for tail, second in ((1, 1), (30, 2), (63, 3), (64, 4)):
    p=here/f't{tail}.json'; ids=[100,second]
    manifest.append({'id':f't{tail}','path':f'/data2/FreeToken/development/r067_d20_short_tail_v1/cpu_probe_input/{p.name}', 'sha256':hashlib.sha256(p.read_bytes()).hexdigest(), 'input_ids_sha256':hashlib.sha256(struct.pack('<2i',*ids)).hexdigest()})
(here/'manifest.json').write_text(json.dumps(manifest, sort_keys=True), encoding='utf-8')
