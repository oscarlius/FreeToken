"""Archive retry1's zero-service harness failure after production recovery."""
import hashlib
import json
from pathlib import Path
import shutil
import socket
import subprocess

HERE = Path(__file__).resolve().parent
RID = 'E2-R067c-d20-short-tail-retry1'
RAW = Path('/data2/FreeToken/runs/dev_R067') / RID
ROUND = Path('/data2/_shared/runs/ft_rounds') / RID
PACKET = Path('/data2/FreeToken/development/r067c_retry1_short_tail_v1')
PY = '/data2/FreeToken/venv/bin/python'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    terminal = json.loads((RAW/'terminal.json').read_text())
    assert terminal['verdict']=='failed_harness' and terminal['batch']==136
    assert terminal['actual_services']==terminal['actual_generation_calls']==0
    assert not terminal['cleanup_errors'] and terminal['GPU_lock_released']
    birth=json.loads((RAW/'launch_binding.json').read_text())['child']
    path=Path(f"/proc/{birth['pid']}/stat")
    if path.exists():
        fields=path.read_text().rsplit(')',1)[1].split()
        assert fields[0]=='Z' or int(fields[19])!=birth['start_ticks']
    for port in (28390,28391):
        with socket.socket() as s:s.bind(('0.0.0.0',port))
    active=json.loads(Path('/data2/FreeToken/run/production.active.json').read_text())
    assert active['approval_id']=='RESTORE481-E2-R067c-20261009-02'
    assert json.loads((Path(active['run_dir'])/'smoke_execution_result.json').read_text())['exit_code']==0
    review=json.loads((PACKET/'RETRY1_INDEPENDENT_TERMINAL_REVIEW.json').read_text())
    assert review['verdict']=='failed_harness' and review['actual_services']==0
    for name,item in json.loads((PACKET/'RETRY1_ALL_REMOTE_RAW_FILES_MANIFEST.json').read_text())['files'].items():
        assert sha(RAW/name)==item['sha256'],name
    assert not ROUND.exists()
    shutil.copytree(RAW,ROUND)
    receipt_path=RAW.parent/'launch_E2-R067c-d20-short-tail-retry1_batch136.json'
    receipt=json.loads(receipt_path.read_text())
    for source,name in ((receipt_path,'launch_receipt.json'),(Path(receipt['wrapper']),'batch.sh'),(Path(receipt['batch_log']),'batch136.log')):
        shutil.copy2(source,ROUND/name)
    binding=ROUND/'startup_binding';binding.mkdir()
    for p in PACKET.iterdir():
        if p.is_file():shutil.copy2(p,binding/p.name)
    shutil.copytree(PACKET/'tooling',binding/'tooling',ignore=shutil.ignore_patterns('__pycache__'))
    for name in ('RETRY1_SEALED_CONTROLLER.py','RETRY1_SEALED_CONTROLLER_RECEIPT.json'):
        shutil.copy2(HERE/name,binding/name)
    shutil.copy2(PACKET/'RETRY1_INDEPENDENT_TERMINAL_REVIEW.json',ROUND/'independent_review.json')
    cleanup={'test_services_started':0,'old_child_absent':True,'test_ports_bindable':[28390,28391],'terminal_cleanup_errors':[], 'restored_production_owner':active,'production_not_stopped_for_closure':True}
    (ROUND/'cleanup_readback.json').write_text(json.dumps(cleanup,indent=2)+'\n')
    document={'schema':'ft_round/v2','round_id':RID,'card':'R067','batch':136,'retry_of':'E2-R067c-d20-short-tail','retry_index':1,'verdict':'pending_review','proposed_verdict':'failed_harness','verdict_history':[],'retractions':[], 'serve':{'arms':{}},'base':{'commit':active['commit']},'experimental':{'candidate_commit':'d50be0f8f84ab1105f788be8f1354773ad539b63'},'batch_logs':[{'path':receipt['batch_log'],'sha256':sha(receipt['batch_log'])}],'raw_run':str(RAW),'result_binding':{name:{'path':name,'sha256':sha(ROUND/name)} for name in ('terminal.json','cleanup_readback.json')},'independent_review':{'path':'independent_review.json','sha256':sha(ROUND/'independent_review.json')},'actual_services':0,'actual_generation_calls':0,'cells_comparable':0,'product_acceptance':False,'retry_policy':{'maximum_tooling_retries':2,'used':1}}
    (ROUND/'round.json').write_text(json.dumps(document,indent=2)+'\n')
    closer=Path('/data2/FreeToken/runs/dev_D16/r041_accept_final_20261005_2012/d04_server_round_close_db7b2787.py')
    assert sha(closer)=='db7b278713f52b089a0079022cf73a46285ae1baef3fd7353da8194385f0585b'
    close=subprocess.run([PY,str(closer),RID,'--round-root',str(ROUND.parent)],capture_output=True,text=True)
    assert close.returncode==0,close.stderr
    tool='/data2/FreeToken/scripts/round_json_append.py'
    append=subprocess.run([PY,tool,str(ROUND),'verdict','--new','failed_harness','--reason','Independent review confirms all ten argv digests remained stale after retry1 RID path replacement; first digest assertion failed before any service or generation. Production restored first.','--evidence',str(ROUND/'terminal.json'),str(ROUND/'independent_review.json'),str(ROUND/'cleanup_readback.json'),'--by','root'],capture_output=True,text=True)
    assert append.returncode==0,append.stderr
    check=subprocess.run([PY,tool,str(ROUND),'check'],capture_output=True,text=True)
    assert check.returncode==0,check.stderr
    for line in (ROUND/'MANIFEST.sha256').read_text().splitlines():
        digest,name=line.split('  ',1);assert sha(ROUND/name)==digest,name
    assert all(not p.stat().st_mode & 0o222 for p in [ROUND,*ROUND.rglob('*')])
    print(json.dumps({'formal_round':str(ROUND),'manifest_sha256':sha(ROUND/'MANIFEST.sha256'),'D04':json.loads(close.stdout),'history_check':json.loads(check.stdout),'all_hashes_match':True,'all_read_only':True,'verdict':'failed_harness'}))

if __name__=='__main__':main()
