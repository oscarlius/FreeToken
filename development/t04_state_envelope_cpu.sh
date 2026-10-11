set -euo pipefail
CUDA_VISIBLE_DEVICES='' OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 /data2/FreeToken/venv/bin/python - <<'PY'
import csv,hashlib,json,pathlib,subprocess,sys
root=pathlib.Path('/data2/FreeToken')
rounds=pathlib.Path('/data2/_shared/runs/ft_rounds')
wt=root/'wt/e1r003st'
commit='c30ae0d7003c3bbbf56867ce74da797332fa7ed5'
tool=wt/'scripts/state_envelope.py'
assert subprocess.check_output(['git','-C',str(wt),'rev-parse','HEAD'],text=True).strip()==commit
assert not subprocess.check_output(['git','-C',str(wt),'status','--porcelain','--untracked-files=no'],text=True).strip()
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
 return h.hexdigest()
phase1=rounds/'E2-R002'
assert sha(phase1/'MANIFEST.sha256')=='116114bb330db38c4f1163a972fe5d4c7a8da9b943719950e79b3a39e5bb3ad6'
assert sha(phase1/'round.json')=='53b1849cc68584d488ae7f7388e91c169c20575d9bb0f2b64a52d80692c38427'
out=root/'runs/dev_D03/t04_envelope_c30ae0d'
assert not out.exists()
dirs={'A':rounds/'E1-R003-stateeq/dump_A','B':rounds/'E1-R003-stateeq/dump_B',
      'R4096':phase1/'R4096/dump','R8192':phase1/'R8192/dump'}
rows={key:[json.loads(line) for line in (p/'index.jsonl').read_text().splitlines() if line] for key,p in dirs.items()}
lengths={key:{row['length'] for row in values if row['kind']=='donate'} for key,values in rows.items()}
selected=sorted(lengths['A'])
assert selected==[12416,12736,13056,13248,14080,18944,20096,21248,21312,21568,21952]
assert all(set(selected)<=values for values in lengths.values())
files={str(p/'index.jsonl'):sha(p/'index.jsonl') for p in dirs.values()}
roles={'conv_states','recurrent_states','slot:ple_conv','slot:ple_ngram_ctx'}
for key,values in rows.items():
 for row in values:
  if row['kind']!='donate' or row['length'] not in selected: continue
  assert roles <= set(row['files'])
  for role in roles:
   path=dirs[key]/row['files'][role]
   files[str(path)]=sha(path)
out.mkdir()
def write(name,value):
 with (out/name).open('x',encoding='utf-8') as f: json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n')
write('input_provenance.json',{'candidate_commit':commit,'tool_sha256':sha(tool),'phase1_manifest_sha256':sha(phase1/'MANIFEST.sha256'),
 'selected_lengths':selected,'all_input_lengths':{k:sorted(v) for k,v in lengths.items()},'input_files_sha256':files,
 'selection_reason':'all historical A donate lengths; B-only 13376 has no A pair and is separately reported',
 'legal_pair':'R4096 -> R8192 only; RLM integer-context anomaly is excluded from admission',
 'legacy_binding_gap':'historical dump rows do not retain raw prompt hashes/global layer IDs; recorded index alignment is used'})
argv=[sys.executable,str(tool),'--ref',str(dirs['B']),'--test',str(dirs['A']),
 '--legal',f"{dirs['R4096']}:{dirs['R8192']}",'--lengths',','.join(map(str,selected)),
 '--out',str(out/'restore_vs_legal_envelope.csv'),'--tier','device']
write('command.json',argv)
with (out/'comparison.log').open('x',encoding='utf-8') as log:
 subprocess.run(argv,cwd=wt,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=1800)
summary=json.loads((out/'comparison.log').read_text().splitlines()[-1])
assert summary['lengths']==selected and summary['points']==len(selected)*74 and summary['legal_pairs']==1
for path,digest in files.items(): assert sha(pathlib.Path(path))==digest,path
write('summary.json',summary)
print('T04_LAYER_ENVELOPE_MEASURED',json.dumps(summary))
print('T04_LAYER_ENVELOPE_CSV_SHA256',sha(out/'restore_vs_legal_envelope.csv'))
print('T04_LAYER_ENVELOPE_PROVENANCE_SHA256',sha(out/'input_provenance.json'))
print('T04_LAYER_ENVELOPE_GAP B-only length13376 has no historicalA comparison; no tolerance or release decision')
PY
