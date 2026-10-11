set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,pathlib,socket,subprocess
root=pathlib.Path('/data2/FreeToken')
out=root/'runs/dev_D02/gpu_selfcheck_23f2e2c'
def cmd(*args):return subprocess.check_output(args,text=True).strip()
assert not pathlib.Path('/data2/_shared/gpu.lock').exists()
with socket.socket() as sock: assert sock.connect_ex(('127.0.0.1',8095))!=0
memory=cmd('nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits')
assert all(int(x)<1000 for x in memory.splitlines())
wt=root/'wt/e1ms'
assert cmd('git','-C',str(wt),'rev-parse','--short=7','HEAD')=='23f2e2c'
assert not cmd('git','-C',str(wt),'status','--porcelain','--untracked-files=no')
assert cmd('git','-C',str(root/'wt/e2base'),'rev-parse','--short=7','HEAD')=='3db7b50'
assert cmd('git','-C',str(root/'wt/e1r008'),'rev-parse','--short=7','HEAD')=='f91054b'
manifest=out/'MANIFEST.sha256'
manifest_lines=manifest.read_text().splitlines()
for line in manifest_lines:
    digest,name=line.split('  ',1)
    assert hashlib.sha256((out/name).read_bytes()).hexdigest()==digest,name
result=json.loads((out/'gpu_selfcheck.json').read_text())
summary={k:result[k] for k in ['commit','sequence','off_median_tok_s','on_median_tok_s','median_drop_pct','paired_drop_range_pct']}
summary['arms']=[{'arm':r['arm'],'decode_tok_s':r['decode_tok_s'],'first_real_s':r['first_shot']['first_real_s'],
                 'tokens':[c['usage']['completion_tokens'] for c in r['clients']],
                 'content_sha256':[c['content_sha256'] for c in r['clients']],
                 'telemetry':r.get('telemetry')} for r in result['arms']]
tl=json.loads((out/'timeline/timeline_summary.json').read_text())
timeline_rows=[json.loads(s) for s in (out/'timeline/d0_decode_timeline.jsonl').read_text().splitlines()]
assert len(timeline_rows)==8 and len(tl['layers'])==48
assert all(len(r['layers'])==48 for r in timeline_rows)
summary['timeline']={'steps':len(timeline_rows),'layer_samples':8*48,'layers':len(tl['layers']),
 'overall':tl['overall'],'sample_layers':{k:tl['layers'][k] for k in ['0','24','47']},
 'last_gpu_step_ms':timeline_rows[-1]['step_ms']}
summary['close']={'lock_absent':True,'port_8095_free':True,'memory_used_mib':memory,
 'tree':cmd('git','-C',str(wt),'rev-parse','HEAD^{tree}'),
 'manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),'manifest_files':len(manifest_lines),
 'analyzer_md5':hashlib.md5((root/'scripts/d0_timeline_summary.py').read_bytes()).hexdigest(),
 'candidate_bundle_sha256':hashlib.sha256((root/'runs/dev_D02/e2-d01-d02-candidate.bundle').read_bytes()).hexdigest()}
delivery=root/'runs/dev_D02/delivery_23f2e2c'
delivery.mkdir(exist_ok=False)
(delivery/'verification.json').write_text(json.dumps(summary,indent=2,allow_nan=False))
print(json.dumps(summary,ensure_ascii=False))
PY
