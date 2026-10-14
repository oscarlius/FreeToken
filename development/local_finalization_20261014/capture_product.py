"""Export the deployed E3 commit; only /health is queried, no generation."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("transport", HERE.parent / "r067c_retry2_production_control_20261009/ssh_ops.py")
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)
code = r'''
import datetime, hashlib, json, pathlib, subprocess, urllib.request
root = pathlib.Path('/data2/FreeToken')
active = json.loads((root/'run/production.active.json').read_text())
assert active['commit'] == '9db0ee776c25afa8d2719ab700b2de7ccc606142'
wt = pathlib.Path(active['worktree'])
assert str(wt) == '/data2/FreeToken/wt/release-e3'
def git(*args): return subprocess.check_output(['git','-C',str(wt),*args],text=True).strip()
assert git('rev-parse','HEAD') == active['commit']
assert not git('status','--porcelain','--untracked-files=no')
argv = active['argv']
host, port = argv[argv.index('--host')+1], argv[argv.index('--port')+1]
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open('http://'+host+':'+port+'/health',timeout=10) as response:
    health = json.load(response)
assert health['maintenance'] == 'serving'
ollama = subprocess.check_output(['docker','inspect','-f','{{.State.Running}}','ollama'],text=True).strip()
assert ollama == 'false'
target = root/'development/local_finalization_20261014'
target.mkdir(exist_ok=True)
bundle = target/'deployed_e3.bundle'
if not bundle.exists():
    subprocess.run(['git','-C',str(wt),'bundle','create',str(bundle),'release/e3'],check=True,capture_output=True)
subprocess.run(['git','-C',str(wt),'bundle','verify',str(bundle)],check=True,capture_output=True)
receipt = {'at':datetime.datetime.now().astimezone().isoformat(),'active':active,'health':health,
 'ollama_running':False,'head':git('rev-parse','HEAD'),'tree':git('rev-parse','HEAD^{tree}'),
 'parent':git('rev-parse','HEAD^'),'bundle':str(bundle),'bundle_bytes':bundle.stat().st_size,
 'bundle_sha256':hashlib.sha256(bundle.read_bytes()).hexdigest(),
 'generation_calls':0,'service_actions':0}
print(json.dumps(receipt))
'''
client = transport.connect()
try:
    _, out, err = client.exec_command('/data2/FreeToken/venv/bin/python -c ' + shlex.quote(code))
    result, errors = out.read().decode(), err.read().decode()
    assert out.channel.recv_exit_status() == 0, errors
    receipt = json.loads(result)
    archive = HERE.parents[1] / 'archive/local_finalization_20261014/deployed_product'
    archive.mkdir(parents=True, exist_ok=True)
    local = archive / 'deployed_e3.bundle'
    sftp = client.open_sftp()
    sftp.get(receipt['bundle'], str(local))
    sftp.close()
    assert hashlib.file_digest(local.open('rb'), 'sha256').hexdigest() == receipt['bundle_sha256']
    (HERE/'PRODUCT_BEFORE.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({key:receipt[key] for key in ['at','head','tree','bundle_bytes','health','ollama_running','generation_calls','service_actions']}, ensure_ascii=False))
finally:
    client.close()
