"""Copy completed evidence only; never copies environments, weights or build trees."""
import hashlib
import importlib.util
import json
from pathlib import Path
import stat

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('ops',HERE.parent/'r067c_retry2_production_control_20261009/ssh_ops.py')
ops=importlib.util.module_from_spec(spec);spec.loader.exec_module(ops)
client=ops.connect()
try:
    remote='/data2/FreeToken/development/upstream_layer_major_pr_20261014/'
    local=HERE/'gpu_evidence'
    sftp=client.open_sftp()
    recovery_result=json.loads(sftp.open(remote+'GPU_WINDOW_RECOVERY.json').read())
    if not recovery_result['restored']:raise RuntimeError('Recovery has not passed')
    local.mkdir()
    terminal=json.loads(sftp.open(remote+'GPU_WINDOW_TERMINAL.json').read())
    def copy_tree(source,target):
        target.mkdir()
        for item in sftp.listdir_attr(source):
            src=source+'/'+item.filename;dst=target/item.filename
            if stat.S_ISDIR(item.st_mode):copy_tree(src,dst)
            elif stat.S_ISREG(item.st_mode):sftp.get(src,str(dst))
            else:raise RuntimeError('Refuse nonregular evidence path: '+src)
    copy_tree(remote+'gpu_results',local/'gpu_results')
    for name in ('GPU_WINDOW_TERMINAL.json','GPU_WINDOW_RECOVERY.json','restore_resume_supervisor.log','window_events.jsonl','window_supervisor.log',
                 'stop_e3.log','restore_start.log','restore_smoke.log','WINDOW_RUN_CONSUMED.json'):
        try:sftp.get(remote+name,str(local/name))
        except FileNotFoundError:pass
    recovery=json.loads((HERE/'restore_e3/DEPLOYMENT_APPROVAL.json').read_text())
    try:copy_tree(recovery['run_dir'],local/'restored_production')
    except FileNotFoundError:pass
    sftp.close()
    manifest={p.relative_to(local).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
              for p in local.rglob('*') if p.is_file()}
    (HERE/'GPU_EVIDENCE_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'terminal':terminal,'copied_files':len(manifest)},indent=2))
finally:client.close()
