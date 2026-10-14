"""Read-only final runtime ownership, readiness and stopped-Ollama check."""
import importlib.util
from pathlib import Path

root = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ops", root.parent / "r067c_retry2_production_control_20261009/ssh_ops.py")
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)
client = ops.connect()
try:
    ops.run(client, r'''
import datetime,importlib.util,json,pathlib,subprocess,urllib.request
root=pathlib.Path('/data2/FreeToken/development/upstream_oom_pr_retry2_20261014')
auth=json.loads((root/'WINDOW_AUTHORIZATION.json').read_text())
active=json.loads(pathlib.Path('/data2/FreeToken/run/production.active.json').read_text())
assert active['approval_id']=='UPSTREAM-OOM-PR-RESTORE-E3-20261014-03'
spec=importlib.util.spec_from_file_location('controller',root/'gpu_window_oom.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
helper=m.load_module(pathlib.Path(auth['frozen_ops']['helper_path']),'helper');assert m.active_owner_is_live(helper,active)
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
argv=active['argv'];host=argv[argv.index('--host')+1];port=argv[argv.index('--port')+1]
with opener.open('http://'+host+':'+port+'/health',timeout=10) as response:health=json.load(response)
assert health['status']=='ok' and health['maintenance']=='serving'
ollama=subprocess.check_output(['docker','inspect','-f','{{.State.Running}}','ollama'],text=True).strip()
assert ollama=='false'
receipt={'at':datetime.datetime.now().astimezone().isoformat(),'production_approval':active['approval_id'],'production_commit':active['commit'],'owner_live':True,'health':health,'ollama_running':False,'generation_calls':0,'control_actions':0}
with (root/'FINAL_RUNTIME_CHECK.json').open('x') as handle:json.dump(receipt,handle,indent=2)
print(json.dumps(receipt,indent=2))
''')
    sftp = client.open_sftp()
    sftp.get("/data2/FreeToken/development/upstream_oom_pr_retry2_20261014/FINAL_RUNTIME_CHECK.json", str(root / "FINAL_RUNTIME_CHECK.json"))
    sftp.close()
finally:
    client.close()
