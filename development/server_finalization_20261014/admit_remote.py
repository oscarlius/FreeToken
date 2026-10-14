"""Append source binding to the prepared backup plan; no cleanup execution."""
import hashlib
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('transport',HERE.parent/'r067c_retry2_production_control_20261009/ssh_ops.py')
transport=importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)
private=HERE/'private'
prepared=json.loads((private/'PREPARED_SCRIPT_SHA.json').read_text())['sha256']
source=(HERE/'remote_cleanup.py').read_bytes()
client=transport.connect()
try:
    sftp=client.open_sftp()
    remote='/data2/FreeToken/development/server_finalization_20261014/remote_cleanup.py'
    archive='/data2/FreeToken/archive/server_finalization_20261014'
    with sftp.open(remote,'rb') as f: old=f.read()
    assert hashlib.sha256(old).hexdigest()==prepared
    with sftp.open(archive+'/PLAN.json','rb') as f: plan=f.read()
    assert plan==(private/'PLAN.json').read_bytes()
    admission={'prepared_script_sha256':prepared,'execution_script_sha256':hashlib.sha256(source).hexdigest(),'plan_sha256':hashlib.sha256(plan).hexdigest(),'only_source_change':'bind plan and execution source; disable execute-time reupload','production_actions':0}
    with sftp.open(remote,'wb') as f:f.write(source)
    with sftp.open(archive+'/ADMISSION.json','wx') as f:f.write(json.dumps(admission,indent=2)+'\n')
    sftp.chmod(archive+'/ADMISSION.json',0o600)
    (private/'ADMISSION.json').write_text(json.dumps(admission,indent=2)+'\n',encoding='utf-8')
    sftp.close()
    print(json.dumps({'source_and_plan_bound':True,'plan_unchanged':True,'cleanup_executed':False}))
finally:
    client.close()
