"""Replay actual child/Effects/receipt code with GPU, HTTP, spawn seams inert."""
import argparse,json,tempfile,types,sys
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).parent
sys.path.insert(0,str(HERE))
import d10_clean_owned_parent as owned

def run():
    proof=owned.candidate_proof()  # Actual clean candidate and native links.
    scenarios=[]
    for scenario in ['valid_measurement','client_failure','startup_exit','cleanup_failure']:
        with tempfile.TemporaryDirectory(prefix='cpu_d10_filedry_',dir=HERE) as temp:
            root=Path(temp);output=root/'output';admission=root/'admission.json';receipt=root/'receipt.json'
            real=owned.Effects();g=real.gate;mine=g.process_birth();seen=[]
            service={'api_port':31955,'argv':['ft','serve',owned.FLAG],'cwd':str(owned.WT),'endpoint':'http://127.0.0.1:31955'}
            doc={'prototype_output':str(output),'service':service,'candidate_proof':proof,'source_sha256':owned.hashes()}
            admission.write_text(json.dumps(doc));batch=0
            receipt.write_text(json.dumps({'schema':'ft_d07_owned_launch/v2','state':'launched','rid':owned.RID,'batch':batch,'candidate_commit':owned.CANDIDATE,'argv_sha256':g.argv_sha256(owned.child_argv(admission,batch,receipt,output)),'child':mine,'batch_pid':mine['pid'],'scope':{'worktree':str(owned.WT),'output_root':str(output)}}))
            owned.verify_receipt(g,receipt,batch,admission,output) # Real PID/birth/argv checks.
            lock=root/'cpu_lock_unused';pid=mine['pid']
            class Process:
                pid=mine['pid']
                def poll(self):return 1 if scenario=='startup_exit' else None
            def start(*args):seen.append('spawn_seam');return Process()
            def dispatch(endpoint,out,timeout):
                seen.append('two_http_seams')
                (out/'clients').mkdir()
                for i in range(2):owned.put(out/'clients'/f'client{i}.json',{'submitted_monotonic_ns':1,'cpu_fixture':True})
                if scenario=='client_failure':raise RuntimeError('injected consumer failure')
                owned.put(out/'d10_branch_event.json',{'schema':'ft_d10_branch_event/v4','method':'Engine._forward_d10_staggered_decode','entered':True,'actual_batch_reqs':2,'actual_can_use_d10_staggered':True,'candidate_commit':owned.CANDIDATE,'engine_birth':{'pid':pid+1,'start_ticks':mine['start_ticks']},'engine_pgid':pid})
                return {'verdict':'valid_negative','cpu_fixture_not_gpu_measurement':True}
            def stop(*args):
                seen.append('owned_stop_seam')
                if scenario=='cleanup_failure':raise RuntimeError('injected owned cleanup failure')
            real.start=start;real.dispatch=dispatch;real.health=lambda *a,**k:{'status':'ok'};real.stop=stop;real.alive=lambda _:False
            def ident(p):return {'pid':p,'start_ticks':mine['start_ticks'],'pgid':pid}
            with patch.object(owned,'require_admission',return_value=doc),patch.object(owned,'reserve_pair',side_effect=lambda p:seen.append('port_bind_seam') or []),patch.object(g,'LOCK',lock),patch.object(g,'take_d07_gpu_lock',side_effect=lambda *a:seen.append('lock_seam') or {'cpu_fixture':True}),patch.object(g,'require_gpu_idle',side_effect=lambda:seen.append('idle_seam')),patch.object(g,'process_identity',side_effect=ident),patch.object(g,'release_d07_gpu_lock',side_effect=lambda _:seen.append('release_lock_seam')):
                try:owned.child(admission,batch,receipt,real)
                except RuntimeError:pass
            terminal=json.loads((output/'terminal.json').read_text())
            expected='not_met' if scenario=='valid_measurement' else 'failed_harness'
            assert terminal['verdict']==expected,(scenario,terminal)
            assert terminal['calls_reserved']<=2 and terminal['actual_generation_calls']<=2
            assert terminal['actual_generation_calls']==(0 if scenario=='startup_exit' else 2)
            assert ('release_lock_seam' in seen)==(scenario!='cleanup_failure')
            assert terminal['lock_retained']==(scenario=='cleanup_failure')
            scenarios.append({'scenario':scenario,'expected_verdict':expected,'actual_verdict':terminal['verdict'],'call_submission_receipt_count':terminal['actual_generation_calls'],'seam_order':seen,'CPU_fixture_only':True})
    return {'schema':'ft_d10_actual_child_cpu_filedry/v1','candidate_proof':proof,'actual_Effects_constructor':True,'actual_child_function':True,'actual_pid_birth_and_argv_receipt_checks':True,'actual_cleanup_path_replay':True,'source_sha256':owned.hashes(),'scenarios':scenarios,'gpu_started':False,'service_started':False,'http_started':False,'formal_batch_allocated':False,'seams':['admission authority CPU fixture','service spawn','HTTP consumers','GPU idle/lock','owned stop','port binding'],'does_not_prove':'GPU timing, server generation, product gate, real GPU cleanup'}
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);a=parser.parse_args();result=run();owned.put(a.output,result);print(json.dumps(result,sort_keys=True))
