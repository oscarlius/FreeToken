"""Pure fail-closed D15 projection from the authoritative release recipe."""
from __future__ import annotations
import hashlib,json
from dataclasses import dataclass
ARMS={'W98K':(98304,2700,32101,32201),'W128K':(131072,2401,32102,32202)}
FORBIDDEN_ENV=('FT_DEV_D0','FT_DEV_D0_PATH','FT_DEV_ROUTE_TRACE','FT_DEV_PAUSE_ENDPOINT','FT_DEV_ADAPTATION')
@dataclass(frozen=True)
class Arm: name:str; window:int; expected_slots:int; port:int; master_port:int
def arm(name):
    try:return Arm(name,*ARMS[name])
    except KeyError as e:raise RuntimeError('unknown D15 arm') from e
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def _replace(argv,flag,value):
    if argv.count(flag)!=1:raise RuntimeError(f'release argv requires exactly one {flag}')
    i=argv.index(flag)
    if i+1>=len(argv):raise RuntimeError(f'release argv truncates {flag}')
    argv[i+1]=value
def release_projection(release_config,arm_name,observer_entry):
    """Pass {} so ambient FT_DEV flags cannot enter the D15 environment."""
    s=arm(arm_name); argv=list(release_config.serve_argv('release')); env=dict(release_config.environment('release',{}))
    if any(k in env for k in FORBIDDEN_ENV):raise RuntimeError('release environment contains forbidden development state')
    for f,v in (('--host','127.0.0.1'),('--port',str(s.port)),('--kv-reserve-tokens',str(s.window)),('--max-seq-len-override',str(s.window))):_replace(argv,f,v)
    if '--max-running-requests' not in argv or argv[argv.index('--max-running-requests')+1]!='2':raise RuntimeError('release concurrency differs')
    ft=next((i for i,x in enumerate(argv) if x=='ft' or x.endswith('/ft')),None)
    if ft is None or not env.get('VIRTUAL_ENV'):raise RuntimeError('release ft/VIRTUAL_ENV absent')
    argv[ft:ft+1]=[env['VIRTUAL_ENV']+'/bin/python',observer_entry,'--observer-dir','__RUN_DIR__/observer','--']
    env.update(PATH=env['VIRTUAL_ENV']+'/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',MASTER_PORT=str(s.master_port),R046C_T06_OBSERVER_ENTRY=observer_entry,R046C_T06_OBSERVER_DIR='__RUN_DIR__/observer')
    for k in FORBIDDEN_ENV:env.pop(k,None)
    return argv,env
def projected_record(release_config,arm_name,observer_entry):
    argv,env=release_projection(release_config,arm_name,observer_entry);s=arm(arm_name)
    return {'arm':s.name,'window':s.window,'expected_auto_slots':s.expected_slots,'port':s.port,'master_port':s.master_port,'argv':argv,'argv_sha256':digest(argv),'environment':env,'environment_sha256':digest(env),'source_mode':'release_empty_parent'}
