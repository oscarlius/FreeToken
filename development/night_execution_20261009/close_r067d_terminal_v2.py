"""D04 closure during authorized night downtime, after independent terminal review."""
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import socket
import subprocess

HERE=Path(__file__).resolve().parent
PACKET=Path('/data2/FreeToken/development/r067d_short_tail_v1')
RID='E2-R067d-d20-short-tail-v1'
RAW=Path('/data2/FreeToken/runs/dev_R067')/RID
ROUND=Path('/data2/_shared/runs/ft_rounds')/RID
PY='/data2/FreeToken/venv/bin/python'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()

def absent(item):
    try:
        fields=Path(f"/proc/{item['pid']}/stat").read_text().rsplit(')',1)[1].split()
        return fields[0]=='Z' or int(fields[19])!=item['start_ticks']
    except FileNotFoundError:
        return True

def main():
    terminal=json.loads((RAW/'terminal.json').read_text())
    review=json.loads((HERE/'R067D_INDEPENDENT_TERMINAL_REVIEW.json').read_text())
    assert terminal['rid']==RID and terminal['batch']==138
    assert terminal['verdict']==review.get('raw_verdict',review['verdict'])
    assert terminal['verdict'] in ('PASS','not_met','failed_harness','probe_invalid')
    assert review['verdict'] in ('PASS','not_met','failed_harness','probe_invalid')
    assert not terminal['cleanup_errors'] and terminal['GPU_lock_released']
    assert terminal['actual_services']<=10 and terminal['actual_generation_calls']<=14
    assert absent(json.loads((RAW/'launch_binding.json').read_text())['child'])
    config=json.loads((PACKET/'R067D_CONFIG_CPU_ONLY.json').read_text())
    for arm in config['services']:
        for key in ('api','tcpstore'):
            with socket.socket() as s:s.bind(('0.0.0.0',arm['port_pair'][key]))
    for path in (RAW/'services').glob('*/owner.json'):
        owner=json.loads(path.read_text());assert absent(owner['pid_identity']) and absent(owner['GPU_owner'])
        pgid=owner['pid_identity']['pgid']
        for p in Path('/proc').iterdir():
            if p.name.isdigit():
                try:
                    fields=(p/'stat').read_text().rsplit(')',1)[1].split()
                    assert fields[0]=='Z' or int(fields[2])!=pgid
                except (FileNotFoundError,ProcessLookupError):pass
    authority=json.loads((HERE/'USER_AUTHORIZATION.json').read_text())
    assert not Path('/data2/FreeToken/run/production.active.json').exists()
    assert not Path('/data2/_shared/gpu.lock').exists()
    active=json.loads((HERE/'PRE_STOP_OWNER.json').read_text())['owner']
    assert active['commit']=='481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9'
    assert review['terminal_sha256']==sha(RAW/'terminal.json')
    for name,item in json.loads((HERE/'R067D_ALL_REMOTE_RAW_FILES_MANIFEST.json').read_text())['files'].items():
        assert sha(RAW/name)==item['sha256'],name
    assert not ROUND.exists();ROUND.mkdir()
    for p in RAW.iterdir():
        if p.is_file():shutil.copy2(p,ROUND/p.name)
    arms={}
    for arm in (RAW/'services').iterdir():
        assert arm.is_dir() and not arm.is_symlink()
        dest=ROUND/arm.name;shutil.copytree(arm,dest)
        if not (arm/'owner.json').exists():continue
        argv=json.loads((arm/'argv.json').read_text());env=json.loads((arm/'environment.json').read_text())
        (dest/'SERVE_CMD.txt').write_text(shlex.join(argv)+'\n')
        (dest/'ENV.txt').write_text(json.dumps(env,indent=2)+'\n')
        lines=[line for line in (arm/'serve.log').read_text().splitlines() if line.startswith('ServerArgs(')]
        assert len(lines)==1,'started arm missing ServerArgs: '+arm.name
        (dest/'serve_args.txt').write_text(lines[0]+'\n')
        arms[arm.name]={'raw_source':str(arm),'actual_argv_sha256':hashlib.sha256(json.dumps(argv,separators=(',',':')).encode()).hexdigest()}
    launch=RAW.parent/'launch_E2-R067d-d20-short-tail-v1_batch138.json'
    receipt=json.loads(launch.read_text())
    for source,name in ((launch,'launch_receipt.json'),(Path(receipt['wrapper']),'batch.sh'),(Path(receipt['batch_log']),'batch138.log')):
        shutil.copy2(source,ROUND/name)
    binding=ROUND/'startup_binding';binding.mkdir()
    for p in PACKET.iterdir():
        if p.is_file():shutil.copy2(p,binding/p.name)
    shutil.copytree(PACKET/'tooling',binding/'tooling',ignore=shutil.ignore_patterns('__pycache__'))
    for name in (RID+'_SEALED_CONTROLLER.py',RID+'_SEALED_CONTROLLER_RECEIPT.json'):
        shutil.copy2(HERE/name,binding/name)
    shutil.copy2(HERE/'R067D_INDEPENDENT_TERMINAL_REVIEW.json',ROUND/'independent_review.json')
    cleanup={'old_test_processes_absent':True,'old_test_groups_absent':True,'all_test_ports_bindable':True,'terminal_cleanup_errors':[],'pre_stop_production_owner':active,'production_intentionally_down_under_user_authority':authority,'restore481_required_after_queue':True}
    (ROUND/'cleanup_readback.json').write_text(json.dumps(cleanup,indent=2)+'\n')
    document={'schema':'ft_round/v2','round_id':RID,'card':'R067','batch':138,'retry_of':None,'retry_index':0,'verdict':'pending_review','proposed_verdict':review['verdict'],'raw_terminal_verdict':terminal['verdict'],'verdict_history':[],'retractions':[],'serve':{'arms':arms} if arms else 'none','base':{'commit':active['commit']},'experimental':{'candidate_commit':'d50be0f8f84ab1105f788be8f1354773ad539b63'},'batch_logs':[{'path':receipt['batch_log'],'sha256':sha(receipt['batch_log'])}],'raw_run':str(RAW),'result_binding':{name:{'path':name,'sha256':sha(ROUND/name)} for name in ('terminal.json','cleanup_readback.json')},'independent_review':{'path':'independent_review.json','sha256':sha(ROUND/'independent_review.json')},'actual_services':terminal['actual_services'],'actual_generation_calls':terminal['actual_generation_calls'],'cells_comparable':len(terminal['cells']),'product_acceptance':False,'retry_policy':{'maximum_tooling_retries':2,'used':0,'automatic_retries_remaining':2}}
    (ROUND/'round.json').write_text(json.dumps(document,indent=2)+'\n')
    closer=Path('/data2/FreeToken/runs/dev_D16/r041_accept_final_20261005_2012/d04_server_round_close_db7b2787.py')
    assert sha(closer)=='db7b278713f52b089a0079022cf73a46285ae1baef3fd7353da8194385f0585b'
    close=subprocess.run([PY,str(closer),RID,'--round-root',str(ROUND.parent)],capture_output=True,text=True)
    assert close.returncode==0,close.stderr
    app='/data2/FreeToken/scripts/round_json_append.py'
    append=subprocess.run([PY,app,str(ROUND),'verdict','--new',terminal['verdict'],'--reason',review['summary'],'--evidence',str(ROUND/'terminal.json'),str(ROUND/'independent_review.json'),str(ROUND/'cleanup_readback.json'),'--by','root'],capture_output=True,text=True)
    assert append.returncode==0,append.stderr
    if review['verdict']!=terminal['verdict']:
        semantic=subprocess.run([PY,app,str(ROUND),'verdict','--new',review['verdict'],'--reason',review['summary'],'--evidence',str(ROUND/'terminal.json'),str(ROUND/'independent_review.json'),'--by','root'],capture_output=True,text=True)
        assert semantic.returncode==0,semantic.stderr
    check=subprocess.run([PY,app,str(ROUND),'check'],capture_output=True,text=True)
    assert check.returncode==0,check.stderr
    for line in (ROUND/'MANIFEST.sha256').read_text().splitlines():
        digest,name=line.split('  ',1);assert sha(ROUND/name)==digest,name
    assert all(not p.stat().st_mode&0o222 for p in [ROUND,*ROUND.rglob('*')])
    print(json.dumps({'formal_round':str(ROUND),'manifest_sha256':sha(ROUND/'MANIFEST.sha256'),'D04':json.loads(close.stdout),'history_check':json.loads(check.stdout),'all_hashes_match':True,'all_read_only':True,'raw_verdict':terminal['verdict'],'verdict':review['verdict']}))

if __name__=='__main__':main()
