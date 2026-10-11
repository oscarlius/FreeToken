"""Resume the approved D10 default-off gate after actual fourth Strata cleanup."""
import datetime,hashlib,importlib.util,json,os,socket,subprocess,time
from pathlib import Path
NIGHT=Path(__file__).resolve().parent
ROOT=Path('/data2/FreeToken')
S3=Path('/data2/Strata/r002-prep/s3_parallel2_v2_20261010/raw-runs/retry1-S3')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def regular(p):
    assert p.is_file() and not p.is_symlink() and not p.stat().st_mode&0o222,str(p)
def put(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2);f.write(chr(10));f.flush();os.fsync(f.fileno())
    p.chmod(p.stat().st_mode&~0o222)
def absent(b):
    try: f=Path(f"/proc/{b['pid']}/stat").read_text().rsplit(')',1)[1].split()
    except FileNotFoundError:return True
    return f[0]=='Z' or int(f[19])!=b['start_ticks']
def main():
    receipt=NIGHT/'STRATA_S3_ROOT_DRIVER_RECEIPT.json';regular(receipt);d=json.loads(receipt.read_text());assert (d['pid'],d['start_ticks'])==(572970,166623287)
    while not absent(d):time.sleep(20)
    op=S3/'pid_birth.json';regular(op);b=json.loads(op.read_text());assert (b['pid'],b['start_ticks'])==(573194,166623516) and absent(b)
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:f=(p/'stat').read_text().rsplit(')',1)[1].split();assert f[0]=='Z' or int(f[2])!=b['pgid']
        except (FileNotFoundError,ProcessLookupError):pass
    terminal=S3/'terminal.json';regular(terminal);t=json.loads(terminal.read_text());assert t['arm']=='S3'
    recovery=NIGHT/'STRATA_S3_CLEANUP_RECOVERY_V1.json';regular(recovery)
    assert sha(recovery)=='83f7cc8de00d285aa7073cd16adcd45ac3be2f9ce1dd5b12b8216022b6cafea0'
    rr=json.loads(recovery.read_text());assert rr['cleanup_ok'] and rr['root_recovery_no_extra_services_or_generation'] and rr['lock_absent_after'] and rr['gpu_compute_absent']
    assert rr['terminal']=={'path':str(terminal),'sha256':sha(terminal)} and rr['service_absent']==b and rr['driver_absent']=={'pid':d['pid'],'start_ticks':d['start_ticks']}
    for name in ['/data2/_shared/gpu.lock','/data2/FreeToken/run/production.active.json','/data2/FreeToken/run/production.cleanup_failed.json']:
        p=Path(name);assert not p.exists() and not p.is_symlink()
    assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip()
    tcp=[]
    for n in ['/proc/net/tcp','/proc/net/tcp6']:
        for line in Path(n).read_text().splitlines()[1:]:
            f=line.split()
            if int(f[1].rsplit(':',1)[1],16)==8085:tcp.append(f[3])
    assert '0A' not in tcp
    with socket.socket() as s:s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('0.0.0.0',8085))
    with socket.socket(socket.AF_INET6,socket.SOCK_STREAM) as s:
        s.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_V6ONLY,1);s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('::',8085))
    cleanup=NIGHT/'STRATA_S3_OWNED_CLEANUP_READBACK_V2.json'
    put(cleanup,{'at':datetime.datetime.now().astimezone().isoformat(),'cleanup_ok':True,'arm':'S3','driver_absent':d,'service_absent':b,'owned_group_absent':True,'terminal':{'path':str(terminal),'sha256':sha(terminal)},'gpu_compute_absent':True,'gpu_lock_absent':True,'port8085_listen_absent':True,'port8085_tcp_states':tcp,'reuseaddr_bind':True,'ipv6_reuseaddr_bind':True,'recovery_sha256':sha(recovery)})
    now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    cutoff=now.replace(hour=7,minute=30,second=0,microsecond=0);assert (cutoff-now).total_seconds()>=75*60,'insufficient time for complete T16 before restore deadline'
    leaf=ROOT/'development/d10_gpu_night_v1/d10_owned_launch_v7.py';regular(leaf);assert not leaf.stat().st_mode&0o222 and sha(leaf)=='b27197becdf00346b115c1401b6f0f77c87d58ca01e288389fbc0833dc101e95'
    review=ROOT/'runs/dev_T16/reviews/E2-D10-T16-night-20261010_startup_review_v3.json';regular(review);assert not review.stat().st_mode&0o222 and sha(review)=='3fb657c91005d13e59900425aace6712908eae8e5e9625ee0e4a1dbc470d9cff'
    spec=importlib.util.spec_from_file_location('d10_leaf',leaf);a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a);a.require_leaf_review('D10');a.require_candidate('D10')
    scope=review.parent/'E2-D10-T16-night-20261010_user_scope_approval_v3.json'
    put(scope,{'schema':'ft_t16_user_scope_approval/v1','rid':'E2-D10-T16-night-20261010','candidate_commit':a.SPECS['D10'][1],'parent_commit':a.PARENT_COMMIT,'queue_predecessors':[],'arms':8,'planned_generation_calls':100,'approved':True,'at':now.isoformat(),'authority':'NIGHT_SUPPLEMENT_20261010_0035','actual_queue_predecessor_cleanup':{'path':str(cleanup),'sha256':sha(cleanup)},'full_frozen_protocol_unchanged':True,'no_push':True})
    a.require_user_scope_approval('D10')
    argv=[str(ROOT/'venv/bin/python'),'-B','-u',str(leaf),'--run','--card','D10']
    with (NIGHT/'D10_T16_ROOT_DRIVER_V2.log').open('xb') as f:p=subprocess.Popen(argv,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
    fields=Path(f'/proc/{p.pid}/stat').read_text().rsplit(')',1)[1].split();v={'at':datetime.datetime.now().astimezone().isoformat(),'pid':p.pid,'start_ticks':int(fields[19]),'argv':argv,'leaf_sha256':sha(leaf),'scope_sha256':sha(scope),'predecessor_cleanup_sha256':sha(cleanup),'event':'D10_DEFAULT_OFF_FULL_T16_STARTED_AFTER_S3_CLEANUP'}
    put(NIGHT/'D10_T16_ROOT_DRIVER_RECEIPT_V2.json',v)
    with (NIGHT/'COORDINATION_LOG.jsonl').open('a') as f:f.write(json.dumps(v)+chr(10));f.flush();os.fsync(f.fileno())
    print(json.dumps(v),flush=True)
if __name__=='__main__':main()
