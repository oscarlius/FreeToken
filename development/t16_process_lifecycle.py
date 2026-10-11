"""Pinned owner/reservation lifecycle extracted from reviewed T16 launcher 7e1c05a."""
import hashlib,json,os,re,signal,sys,time
from pathlib import Path
from types import ModuleType

SOURCE_SHA256='7e1c05a79b856b6a99c3f8d9422afd7013b9ef0215c78e17427d205f78384dcf'
SOURCE_PATH='/data2/FreeToken/runs/dev_D14/t16_7e8f8f9569eb/t16_candidate_launch_full_tail.py'

def read_pinned(path,digest):
    source=Path(path).read_bytes()
    if Path(path).is_symlink() or hashlib.sha256(source).hexdigest()!=digest: raise ValueError('frozen launch dependency changed: '+str(path))
    return source
def verified_module(path,digest,name):
    source=read_pinned(path,digest); module=ModuleType(name); module.__file__=str(path);sys.modules[name]=module;exec(compile(source,str(path),'exec'),module.__dict__);return module
def write_exclusive(path,value):
    with Path(path).open('x',encoding='utf-8') as stream: stream.write(json.dumps(value,indent=2)+'\n');stream.flush();os.fsync(stream.fileno())
def publish_receipt(path,identity,value):
    path=Path(path); temporary=path.with_name(path.name+f'.{os.getpid()}.tmp')
    try:
        write_exclusive(temporary,value);current=path.stat()
        if path.is_symlink() or (current.st_dev,current.st_ino)!=identity: raise ValueError('exclusive launch receipt identity changed')
        os.replace(temporary,path)
    finally: temporary.unlink(missing_ok=True)
def process_identity(pid):
    stat=Path('/proc')/str(pid)/'stat'
    if not stat.is_file(): return None
    fields=stat.read_text().rpartition(') ')[2].split()
    if len(fields)<20: raise ValueError('invalid proc stat')
    return {'pid':pid,'state':fields[0],'pgid':int(fields[2]),'session':int(fields[3]),'start_ticks':int(fields[19]),'cmdline':(Path('/proc')/str(pid)/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')}
def owned_group_alive(pgid):
    try: os.killpg(pgid,0)
    except ProcessLookupError:return False
    alive=False
    for entry in Path('/proc').iterdir():
        if not entry.name.isdecimal():continue
        try: fields=(entry/'stat').read_text().rpartition(') ')[2].split()
        except FileNotFoundError:continue
        if int(fields[2])!=pgid:continue
        if int(fields[3])!=pgid:raise RuntimeError('process group no longer belongs to the reserved session')
        alive|=fields[0]!='Z'
    return alive
def stop_owned_process(process,term_timeout=120,kill_timeout=30):
    for signum,timeout in ((signal.SIGTERM,term_timeout),(signal.SIGKILL,kill_timeout)):
        process.poll()
        if not owned_group_alive(process.pid):return
        if process.poll() is None:
            try: group=os.getpgid(process.pid)
            except ProcessLookupError:
                if not owned_group_alive(process.pid):return
            else:
                if group!=process.pid:raise RuntimeError('owned batch no longer has its expected process group')
        try:os.killpg(process.pid,signum)
        except ProcessLookupError:
            if not owned_group_alive(process.pid):return
            raise RuntimeError('owned group identity changed during cleanup')
        deadline=time.monotonic()+timeout
        while True:
            process.poll()
            if not owned_group_alive(process.pid):return
            if deadline-time.monotonic()<=0:break
            time.sleep(.1)
    raise RuntimeError('owned process group remains after KILL deadline')
def reserve_process(helper,batch,rid,argv,receipt_path,reserved):
    write_exclusive(receipt_path,reserved);current=Path(receipt_path).stat();identity=(current.st_dev,current.st_ino)
    try:process,wrapper,log=helper.reserve_and_launch(batch,rid,argv)
    except BaseException as exc:
        publish_receipt(receipt_path,identity,{**reserved,'state':'launch_failed','error':repr(exc)});raise
    receipt={**reserved,'state':'launched','batch_pid':process.pid,'batch_pgid':process.pid,'process_identity':process_identity(process.pid),'wrapper':str(wrapper),'wrapper_sha256':hashlib.sha256(Path(wrapper).read_bytes()).hexdigest(),'batch_log':str(log)}
    try:publish_receipt(receipt_path,identity,receipt)
    except BaseException as error:
        cleanup=None
        try:stop_owned_process(process)
        except BaseException as exc:cleanup=repr(exc)
        recovery={**receipt,'state':'cleanup_failure' if cleanup else 'receipt_publish_failed_stopped','receipt_error':repr(error),'cleanup_error':cleanup}
        write_exclusive(Path(receipt_path).with_name(Path(receipt_path).name+f'.cleanup_{process.pid}.json'),recovery)
        raise RuntimeError('launch receipt failed and owned process cleanup failed: '+cleanup if cleanup else 'launch receipt publish failed after owned process stop') from error
    return receipt
def next_round(root):
    numbers=[]
    for path in Path(root).iterdir():
        match=re.fullmatch(r'E2-R([0-9]{3})(?:-[A-Za-z0-9-]+)?',path.name)
        if match:
            if path.is_symlink() or not path.is_dir():raise ValueError('round ledger has an invalid matching entry')
            numbers.append(int(match.group(1)))
    if not numbers or max(numbers)>=999:raise ValueError('usable E2 round ledger required')
    return max(numbers)+1
