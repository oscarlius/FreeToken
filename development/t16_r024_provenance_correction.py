"""Prepare or append a bounded raw-file classification correction; preserve all R024 bytes."""
import argparse
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
PROGRAM = r'''
import hashlib,json,os,pathlib,subprocess,sys
directory=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R024-gate-D07')
writer=pathlib.Path('/data2/FreeToken/scripts/round_json_append.py')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
if directory.is_symlink() or any(p.is_symlink() for p in directory.rglob('*')):raise ValueError('regular sealed paths required')
if any(p.stat().st_uid!=os.geteuid() for p in (directory,*directory.rglob('*'))):raise ValueError('foreign evidence owner')
if sha(writer)!='67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff':raise ValueError('verified D04 writer required')
subprocess.run(['sha256sum','-c','MANIFEST.sha256'],cwd=directory,check=True,stdout=subprocess.DEVNULL)
subprocess.run([sys.executable,str(writer),str(directory),'check'],check=True,stdout=subprocess.DEVNULL)
before_sha=sha(directory/'round.json');manifest_sha=sha(directory/'MANIFEST.sha256')
doc=json.loads((directory/'round.json').read_bytes());original=doc['diagnostics']['original_raw_files']
extra='source_tools/t16_r024_d04_close.py'
if doc['verdict']!='kept' or len(original)!=74 or extra not in original:raise ValueError('exact published R024 classification required')
for name,digest in original.items():
 path=directory/name
 if directory.resolve() not in path.resolve().parents or sha(path)!=digest:raise ValueError('original declared file changed')
measurement={name:digest for name,digest in original.items() if name!=extra}
aggregate=hashlib.sha256(''.join(name+' '+measurement[name]+'\n' for name in sorted(measurement)).encode()).hexdigest()
if len(measurement)!=73 or aggregate!='0752924bb7a98f760d60ecac46403d66dd82d4116510d20ead393db7e001d358':
 raise ValueError('independently captured pre-closure raw baseline differs')
if doc['diagnostics'].get('raw_file_classification_correction') is not None:raise ValueError('classification correction already exists')
entry={'id':'r024-raw-classification-20261004','original_field_retained':True,'declared_original_raw_count':74,
 'actual_preclosure_measurement_raw_count':73,'preclosure_raw_set_sha256':aggregate,
 'excluded_closure_files':{extra:original[extra]},
 'reason':'The preserved original_raw_files map includes the closure tool written before its snapshot. The independently captured measurement baseline has 73 files; the added closure source is byte-valid but not original measurement raw.',
 'effect':'Classification only; no runtime raw byte, measurement value, manifest or kept verdict changed.',
 'by':'Codex mainline independent verification under authorized handoff'}
patch={'diagnostics':{'raw_file_classification_correction':entry}}
result={'rid':directory.name,'before_round_sha256':before_sha,'manifest_sha256':manifest_sha,
 'original_declared_raw_count':74,'verified_measurement_raw_count':73,'preclosure_raw_set_sha256':aggregate,'patch':patch}
if data['apply']:
 expected=data['expected']
 if result!=expected:raise ValueError('reviewed exact correction or target changed')
 stage=pathlib.Path('/data2/FreeToken/runs/dev_D07/r024_provenance_0752924')
 stage.mkdir()
 proof=stage/'review.json';proof.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');proof.chmod(0o444)
 proposal=stage/'append.json';proposal.write_text(json.dumps(patch,ensure_ascii=False,indent=2)+'\n');proposal.chmod(0o444)
 subprocess.run([sys.executable,str(writer),str(directory),'add','--json',str(proposal)],check=True,stdout=subprocess.DEVNULL)
 after=json.loads((directory/'round.json').read_bytes())
 if (after['diagnostics']['original_raw_files']!=original or after['diagnostics']['raw_file_classification_correction']!=entry
     or after['verdict']!='kept' or sha(directory/'MANIFEST.sha256')!=manifest_sha):raise ValueError('append changed original contract')
 for name,digest in original.items():
  if sha(directory/name)!=digest:raise ValueError('declared immutable original changed')
 subprocess.run([sys.executable,str(writer),str(directory),'check'],check=True,stdout=subprocess.DEVNULL)
 subprocess.run(['sha256sum','-c','MANIFEST.sha256'],cwd=directory,check=True,stdout=subprocess.DEVNULL)
 if any(p.stat().st_mode&0o222 for p in (directory,*directory.rglob('*'))):raise ValueError('round writable after append')
 stage.chmod(0o555)
 result={'rid':directory.name,'after_round_sha256':sha(directory/'round.json'),'manifest_sha256':manifest_sha,
  'original_declared_raw_files_verified':74,'verified_measurement_raw_count':73,'preclosure_raw_set_sha256':aggregate,
  'correction_id':entry['id'],'verdict_retained':'kept','correction_evidence':str(proof)}
print(json.dumps(result,ensure_ascii=False))
'''

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    options = parser.parse_args()
    review_path = HERE / 't16_r024_provenance_review.json'
    data = {'apply': options.apply}
    if options.apply:
        data['expected'] = json.loads(review_path.read_text(encoding='utf-8'))
    wire = 'data=' + repr(data) + '\n' + PROGRAM
    process = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '9',
                              '/data2/FreeToken/venv/bin/python', '-'], input=wire.encode('utf-8'), capture_output=True)
    if process.returncode:
        print(process.stderr.decode())
        raise SystemExit(process.returncode)
    result = json.loads(process.stdout)
    target = HERE / 't16_r024_provenance_correction_receipt.json' if options.apply else review_path
    with target.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
