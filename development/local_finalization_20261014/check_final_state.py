"""Record final local identity, archive integrity and unchanged runtime."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
from datetime import datetime

from finalize_workspace import ARCHIVE,HERE,ROOT,digest,git,write_json,worktrees

records={}
for label,repo in [('research',ROOT),('product',ROOT/'product'),('upstream',ROOT/'upstream-flashml'),('paper',ROOT/'paper-en')]:
    result=subprocess.run(['git','-C',str(repo),'fsck','--connectivity-only'],capture_output=True,text=True)
    (HERE/(label+'_fsck.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
    assert result.returncode==0,(label,result.stderr)
    records[label]={'head':git(repo,'rev-parse','HEAD'),'tree':git(repo,'rev-parse','HEAD^{tree}'),
                    'branches':git(repo,'for-each-ref','--format=%(refname:short)','refs/heads/').splitlines(),
                    'worktrees':worktrees(repo),'status':git(repo,'status','--porcelain'),'connectivity_fsck':0}
    if label!='research':
        assert not records[label]['status']
before=json.loads((HERE/'PRODUCT_BEFORE.json').read_text(encoding='utf-8'))
assert records['product']['head']==before['head'] and records['product']['tree']==before['tree']
assert records['upstream']['head']=='a7c24b27612769ff25929c39c7cf65ded34aeccc'
assert records['paper']['head']=='ce1105772d16323641547a080b8056d2a82f81d2'
manifest={str(path.relative_to(ARCHIVE)):digest(path) for path in sorted(ARCHIVE.rglob('*')) if path.is_file()}
write_json(HERE/'ARCHIVE_MANIFEST.json',manifest)
spec=importlib.util.spec_from_file_location('transport',HERE.parent/'r067c_retry2_production_control_20261009/ssh_ops.py')
transport=importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)
expected=json.dumps(before['active'],ensure_ascii=True)
code=r'''
import datetime,json,pathlib,subprocess,urllib.request
active=json.loads(pathlib.Path('/data2/FreeToken/run/production.active.json').read_text())
assert active==json.loads(EXPECTED_ACTIVE)
argv=active['argv']; host=argv[argv.index('--host')+1]; port=argv[argv.index('--port')+1]
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open('http://'+host+':'+port+'/health',timeout=10) as response: health=json.load(response)
assert health['maintenance']=='serving' and health['instance_id']==EXPECTED_INSTANCE
ollama=subprocess.check_output(['docker','inspect','-f','{{.State.Running}}','ollama'],text=True).strip()
assert ollama=='false'
print(json.dumps({'at':datetime.datetime.now().astimezone().isoformat(),'active_identity_unchanged':True,'health':health,'ollama_running':False,'generation_calls':0,'service_actions':0}))
'''.replace('EXPECTED_ACTIVE',repr(expected)).replace('EXPECTED_INSTANCE',repr(before['health']['instance_id']))
client=transport.connect()
try:
    _,out,err=client.exec_command('/data2/FreeToken/venv/bin/python -c '+shlex.quote(code))
    output,error=out.read().decode(),err.read().decode()
    assert out.channel.recv_exit_status()==0,error
    runtime=json.loads(output)
finally:
    client.close()
receipt={'at':datetime.now().astimezone().isoformat(),'repositories':records,'runtime':runtime,
         'archive_files':len(manifest),'archive_manifest_sha256':digest(HERE/'ARCHIVE_MANIFEST.json')}
write_json(HERE/'FINAL_CHECK.json',receipt)
print(json.dumps({'repositories':{key:{'head':value['head'],'branches':value['branches'],'worktrees':len(value['worktrees']),'clean':not value['status']} for key,value in records.items()},'archive_files':len(manifest),'runtime':runtime},ensure_ascii=False))
