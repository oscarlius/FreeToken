"""Stage, verify and publish the authorized immutable defect-status erratum."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import runpy
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]
TOOL = 'development/ftd_release_erratum_20261004.py'
EXPECTED_TOOL = '3a76885138c24d28f0db6ffe1bb8e90361c7101946bc9f5bf3087aab1776e638'
RECEIPT = ROOT / 'development/ftd_erratum_stage_receipt.json'
RELEASE = 'FTD-20261004-1-erratum-1'
BASE = '/data2/_shared/runs/ft_releases/FTD-20261004-1/manifest.json'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def remote(program, payload):
    result = subprocess.run([
        'ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '9',
        '/data2/FreeToken/venv/bin/python', '-c', shlex.quote(program),
    ], input=json.dumps(payload).encode(), capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace')[-6000:])
    return json.loads(result.stdout)


STAGE = r'''
import base64,hashlib,json,os,pathlib,runpy,subprocess,sys
data=json.load(sys.stdin);stage=pathlib.Path(data['stage']);stage.mkdir(parents=True,exist_ok=False)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
try:
 for name,value in data['files'].items():
  relative=pathlib.PurePosixPath(name)
  if relative.is_absolute() or '..' in relative.parts:raise ValueError('unsafe stage path')
  path=stage/name;path.parent.mkdir(parents=True,exist_ok=True)
  with path.open('xb') as stream:stream.write(base64.b64decode(value))
  if sha(path)!=data['hashes'][name]:raise ValueError('stage source differs')
 env={**os.environ,'CUDA_VISIBLE_DEVICES':'','PYTHONDONTWRITEBYTECODE':'1'}
 tests=subprocess.run([sys.executable,str(stage/'development/test_ftd_release_erratum_20261004.py')],env=env,capture_output=True,timeout=60)
 (stage/'linux_tests.log').write_bytes(tests.stdout+tests.stderr)
 if tests.returncode or 'Ran 6 tests' not in tests.stderr.decode():raise ValueError('exact Linux regression did not pass')
 namespace=runpy.run_path(str(stage/data['tool']))
 proposal=namespace['build_erratum'](pathlib.Path(data['base']),stage)
 namespace['atomic_create'](stage/'proposal.json',namespace['canonical_bytes'](proposal),'proposal')
 receipt={'schema':'ft_erratum_stage/v1','stage':str(stage),'files':data['hashes'],
  'base_sha256':sha(pathlib.Path(data['base'])),'proposal_sha256':sha(stage/'proposal.json'),
  'test_log_sha256':sha(stage/'linux_tests.log'),'linux_tests':tests.stderr.decode().strip(),
  'hypothesis_overrides':len(proposal['release_only_claim_overrides']),'gpu_started':False}
 with (stage/'cpu_receipt.json').open('x') as stream:json.dump(receipt,stream,sort_keys=True,indent=2);stream.write('\n')
 print(json.dumps(receipt))
finally:
 for path in reversed([stage,*sorted(stage.rglob('*'))]):
  if path.is_symlink():raise ValueError('stage has alias')
  path.chmod(path.stat().st_mode & ~0o222)
'''


PUBLISH = r'''
import base64,hashlib,json,pathlib,runpy,sys
data=json.load(sys.stdin);stage=pathlib.Path(data['stage']);sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
stored=json.loads((stage/'cpu_receipt.json').read_text())
if stored!=data:raise ValueError('frozen stage receipt differs')
for name,wanted in data['files'].items():
 path=stage/name
 if path.is_symlink() or path.stat().st_mode&0o222 or sha(path)!=wanted:raise ValueError('frozen source differs')
for name,key in (('proposal.json','proposal_sha256'),('linux_tests.log','test_log_sha256')):
 if sha(stage/name)!=data[key]:raise ValueError('review or Linux evidence differs')
namespace=runpy.run_path(str(stage/'development/ftd_release_erratum_20261004.py'))
base=pathlib.Path('/data2/_shared/runs/ft_releases/FTD-20261004-1/manifest.json')
document=namespace['build_erratum'](base,stage)
if namespace['canonical_bytes'](document)!=(stage/'proposal.json').read_bytes():raise ValueError('reviewed proposal changed')
release_id=namespace['ERRATUM_ID'];server=base.parent.parent/release_id
copy=stage.parent/(release_id+'.server-copy.json')
if server.exists():
 namespace['require_regular_file'](server/'erratum.json','existing erratum')
 namespace['require_read_only'](server,'existing erratum directory')
 namespace['require_read_only'](server/'erratum.json','existing erratum')
 if (server/'erratum.json').read_bytes()!=namespace['canonical_bytes'](document):raise ValueError('existing immutable erratum differs')
else:
 namespace['create_erratum'](base,stage,server,copy)
manifest=server/'erratum.json';payload=manifest.read_bytes()
namespace['require_read_only'](manifest,'published erratum');namespace['require_read_only'](server,'published directory')
if sha(base)!=data['base_sha256']:raise ValueError('original release changed')
print(json.dumps({'server_erratum':str(manifest),'sha256':sha(manifest),'base_sha256':sha(base),
 'hypothesis_overrides':len(document['release_only_claim_overrides']),'manifest_base64':base64.b64encode(payload).decode()}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    if digest((ROOT / TOOL).read_bytes()) != EXPECTED_TOOL:
        raise ValueError('independently reviewed erratum source changed')
    if not args.publish:
        namespace = runpy.run_path(str(ROOT / TOOL))
        names = [TOOL, 'development/test_ftd_release_erratum_20261004.py', *namespace['SOURCE_REFERENCES']]
        files = {name: (ROOT / name).read_bytes() for name in names}
        identity = digest(b''.join(name.encode() + value for name, value in sorted(files.items())))
        stage = '/data2/FreeToken/runs/dev_P0/erratum_' + identity[:12]
        payload = {'stage': stage, 'tool': TOOL, 'base': BASE,
                   'files': {name: base64.b64encode(value).decode() for name, value in files.items()},
                   'hashes': {name: digest(value) for name, value in files.items()}}
        report = remote(STAGE, payload)
        with RECEIPT.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, indent=2, ensure_ascii=False)
            stream.write('\n')
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    receipt = json.loads(RECEIPT.read_text(encoding='utf-8'))
    result = remote(PUBLISH, receipt)
    payload = base64.b64decode(result.pop('manifest_base64'))
    if digest(payload) != result['sha256']:
        raise ValueError('downloaded erratum differs')
    output = ROOT / 'plan/data_releases' / (RELEASE + '.json')
    if output.exists():
        if output.is_symlink() or output.read_bytes() != payload:
            raise ValueError('local immutable erratum differs')
    else:
        with output.open('xb') as stream:
            stream.write(payload)
    os.chmod(output, 0o444)
    result.update(local_erratum=str(output), byte_identical=True)
    with (ROOT / 'development/ftd_erratum_publish_receipt.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
