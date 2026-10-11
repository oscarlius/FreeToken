"""Read-only V9 consumers for formal rounds, retry cleanup, and native reuse."""
from __future__ import annotations
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path('/data2/FreeToken'); ROUNDS=Path('/data2/_shared/runs/ft_rounds'); HERE=Path(__file__).resolve().parent
T16='E2-D10-T16-night-20261010'; D09='E2-D09-T16-night-20261010-retry1'; CAND='22ff3a389eae3724cdca9a45f2e19577082a2032'; BASE='481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def seal(p):
 p=Path(p)
 if p.is_symlink() or not p.is_file() or p.stat().st_mode&0o222:raise RuntimeError('unsealed '+str(p))
 return p
def formal(rid):
 d=ROUNDS/rid;r=seal(d/'round.json');m=seal(d/'MANIFEST.sha256');rows=[]
 for line in m.read_text().splitlines():
  h,n=line.split(maxsplit=1);n=n.lstrip('* ');n=n[2:] if n.startswith('./') else n
  if n in ('round.json','MANIFEST.sha256') or n.startswith('round_history/'):raise RuntimeError('governance listed in manifest')
  f=seal(d/n)
  if len(h)!=64 or sha(f)!=h:raise RuntimeError('manifest entry differs')
  rows.append(n)
 data=sorted(str(x.relative_to(d)) for x in d.rglob('*') if x.is_file() and x.name not in ('round.json','MANIFEST.sha256') and 'round_history' not in x.parts)
 if sorted(rows)!=data or len(rows)!=len(set(rows)):raise RuntimeError('manifest data coverage differs')
 hist=seal(d/'round_history'/'SHA256SUMS')
 for line in hist.read_text().splitlines():
  h,n=line.split(maxsplit=1);f=seal(hist.parent/n.lstrip('* '));
  if sha(f)!=h:raise RuntimeError('history differs')
 checker=ROOT/'scripts/round_json_append.py'
 if checker.is_file() and subprocess.run([str(ROOT/'venv/bin/python'),str(checker),str(d),'check'],capture_output=True).returncode:raise RuntimeError('round app check fails')
 return json.loads(r.read_text()),{'round_sha256':sha(r),'manifest_sha256':sha(m),'history_sha256':sha(hist)}
def round_semantics(rid):
 x,h=formal(rid)
 if rid==T16:
  if x.get('schema')!='ft_round/v2' or x.get('round_id')!=rid or x.get('verdict')!='kept' or x.get('candidate_commit')!=CAND or x.get('parent_commit')!=BASE or x.get('card')!='D10-T16':raise RuntimeError('T16 semantics differ')
  text=json.dumps(x); 
  if 'd10_staggered_decode' not in text or 'False' not in text:raise RuntimeError('T16 default-off facts absent')
 else:
  if x.get('round_id')!=rid or x.get('candidate_commit')!='c17b69a46cd512fbf3d127d3879bce92caae457b' or x.get('parent_commit')!=BASE or x.get('card')!='D09-T16' or x.get('verdict') not in ('kept','not_met','failed_harness'):raise RuntimeError('D09 semantics differ')
 return h
def cleanup(path,launch):
 p=seal(path);x=json.loads(p.read_text());l=seal(launch);status=seal(x['status'])
 if not (x.get('cleanup_ok') is True and x.get('child_absent') is True and x.get('launch_sha256')==sha(l) and x.get('status_sha256')==sha(status) and isinstance(x.get('owners'),list) and x['owners']):raise RuntimeError('cleanup watcher schema differs')
 ld=json.loads(l.read_text());sd=json.loads(status.read_text());child=ld.get('child')
 if ld.get('rid')!=D09 or ld.get('batch')!=144 or not isinstance(child,dict) or sd.get('rid')!=D09 or sd.get('verdict') not in ('kept','not_met','failed_harness'):raise RuntimeError('cleanup launch/status semantics differ')
 return sha(p)
def native():
 n=seal(HERE/'d10_native_provenance_v2.json');x=json.loads(n.read_text());r=seal(Path(x['reuse_receipt']));q=json.loads(r.read_text())
 if x.get('candidate_commit')!=CAND or x.get('parent_commit')!=BASE or q.get('candidate_commit')!=CAND or q.get('base_commit')!=BASE or q.get('native_source_diff_empty') is not True or q.get('compiled') is not False:raise RuntimeError('native reuse semantics differ')
 for f in q.get('files',[]):
  a,b=seal(f['source']),seal(f['destination'])
  if sha(a)!=f.get('sha256') or sha(b)!=f.get('sha256') or a.stat().st_size!=f.get('size') or b.stat().st_size!=f.get('size'):raise RuntimeError('native extension bytes differ')
 return {'provenance_sha256':sha(n),'reuse_sha256':sha(r)}
