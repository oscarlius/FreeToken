"""R040f D16 collection compatibility layer over the sealed v4 probe closure."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
import d16_native_process_collection_v4 as _v2
from d16_native_process_collection_v4 import *  # retained ordinary paths
functools=_v2.functools; workloads=_v2.workloads; retained=_v2.retained

RETAINED_SCHEMA='ft_r040d_retained_batch0/v1'
SLOTS4_REMAINING={'batch_repeat1':9,'parking':4,'cache':4,'interleave':6}

def retained_batch0(path, *, candidate_commit, review_sha256, pin_sha256):
 p=Path(path)
 if p.is_symlink() or not p.is_file() or p.stat().st_mode & 0o222: raise ValueError('R040f retained batch0 metadata must be sealed regular file')
 d=json.loads(p.read_text())
 if d.get('schema')!=RETAINED_SCHEMA or d.get('candidate_commit')!=candidate_commit or d.get('review_sha256')!=review_sha256 or d.get('pin_sha256')!=pin_sha256 or d.get('terminal')!='retained_batch0': raise ValueError('R040f retained batch0 binding differs')
 bound=dict(d); declared=bound.pop('metadata_sha256',None)
 if declared!=hashlib.sha256(json.dumps(bound,sort_keys=True,separators=(',',':')).encode()).hexdigest(): raise ValueError('R040f retained batch0 metadata SHA differs')
 return {'path':str(p),'sha256':d['metadata_sha256'],'round':d.get('round'),'review_sha256':review_sha256,'pin_sha256':pin_sha256,'retained_only':True}

def slots4_repeat1_plan(*, slots, interleave, candidate_commit, retained_path=None, review_sha256=None, pin_sha256=None):
 if slots!=4 or interleave: return None
 if not (isinstance(candidate_commit,str) and len(candidate_commit)==40 and all(isinstance(x,str) and len(x)==64 for x in (review_sha256,pin_sha256))): raise ValueError('R040f slots4 retained binding requires SHA values')
 if retained_path is None: raise ValueError('R040f slots4 repeat1 requires retained batch0 metadata')
 kept=retained_batch0(retained_path,candidate_commit=candidate_commit,review_sha256=review_sha256,pin_sha256=pin_sha256)
 return {'schema':'ft_r040e_slots4_remaining/v1','slots':4,'interleave':False,'retained_batch0':kept,'launch':{'batch_repetitions':[1],'parking_repetitions':2,'cache_repetitions':2,'interleave_repetitions':3},'remaining_items':SLOTS4_REMAINING,'total_remaining':23,'old_raw_read':False,'needs_terminal_combination':True,'partial':True}

def annotate_slots4_result(result, plan):
 if plan is None:return result
 out=dict(result);out['retained_batch0']=plan['retained_batch0'];out['remaining_scope']=plan['remaining_items'];out['partial']=True;out['needs_terminal_combination']=True;out['terminal_combination']='independent reviewer combines retained batch0 and this repeat1 evidence';return out


def arm_schedule(owner, *, slots, interleave=False):
    if slots == 4 and not interleave:
        info = getattr(owner, '_r040e_retained_batch0', None)
        if not isinstance(info, dict):
            raise ValueError('R040f slots4 requires owner._r040e_retained_batch0')
        plan = slots4_repeat1_plan(
            slots=4, interleave=False, candidate_commit=info.get('candidate_commit'),
            retained_path=info.get('binding_file'), review_sha256=info.get('review_sha256'),
            pin_sha256=info.get('pin_sha256'))
        return ([('batch', 1, None)] +
                [('single', repeat, slot) for repeat in (0, 1) for slot in range(slots)]), plan
    return ([('batch', repeat, None) for repeat in (0, 1)] +
            [('single', repeat, slot) for repeat in (0, 1) for slot in range(slots)]), None


# v2 collection body retained verbatim except the bounded schedule above.
def _collect_arms(owner, inputs, *, slots, wrapper, base_url, root, request_factory, interleave=False):
    batch, alone, runs = [[],[]], [[],[]], []
    interleave_shape = None
    
    schedule, plan = arm_schedule(owner, slots=slots, interleave=interleave)
    retained_mode = plan is not None
    for kind, repetition, slot in schedule:
        name = f'dev_D16_{slots}_{kind}_{repetition}_{slot}'
        execution = f'{owner.options.rid}:{name}'
        chosen = inputs if slot is None else [inputs[slot]]
        def operation(arm):
            frontend = birth(owner.proc.pid)
            write(arm/'owned_frontend.json',frontend)
            client = (request_factory(arm) if request_factory is not None
                      else functools.partial(retained.exact_id_request,base_url))
            result = (_v2._interleave_queries(arm, chosen, client=client, repetition=repetition)
                      if interleave and slot is None else workloads.collect(client, chosen,
                        slots=len(chosen),root=arm/'collection',observations_path=arm/'observations.jsonl',
                        mode='batch' if slot is None else 'alone', repetitions=1,
                        repetition_start=repetition,slot_offset=0 if slot is None else slot))
            identities = [json.loads(path.read_text())['process_identity']
                          for path in (arm/'capture/admissions').glob('*.json')]
            if len(identities) != len(chosen) or any(identity != identities[0] for identity in identities):
                raise ValueError('native admissions do not bind one live scheduler process')
            worker = identities[0]
            actual = birth(worker['pid'])
            if actual['start_ticks'] != worker['start_ticks'] or actual['pgid'] != frontend['pgid']:
                raise ValueError('native scheduler is outside the owned process birth/group')
            if worker['execution_id'] != execution+':tp0' or birth(owner.proc.pid) != frontend:
                raise ValueError('native worker execution or frontend birth differs')
            write(arm/'owned_native_worker.json', {'identity':worker,'live_birth':actual,'frontend':frontend})
            return result,worker
        with configured(owner,wrapper,execution_id=execution,request_count=len(chosen)):
            result, identity = owner.service(name,operation,health_only=True,max_running_requests=4)
        arm = owner.directory/name
        try:
            delivery = read_sealed_service_delivery(arm)
        except Exception as error:
            raise RuntimeError(f'R040f delivery arm={name} path={arm / "capture/service_delivery.json"}: {error}') from error
        if delivery.get('terminal') != 'complete' or delivery.get('process_identity') != identity:
            raise ValueError('owned service stop did not produce complete native delivery')
        if interleave and slot is None:
            mixed = [event for event in delivery.get('scheduler_batches', [])
                     if event.get('phase') == 'prefill'
                     and {req['uid'] for req in event.get('requests', [])} == {0, 1}
                     and {req['uid']: req['extend_len'] == 1 for req in event.get('request_geometry', [])} == {0: True, 1: False}]
            if not mixed:
                raise ValueError('D16 interleave has no native long-prefill/active-decode batch')
            write(arm/'interleave_scheduler_events.json', mixed)
            shape = [{key: event[key] for key in ('phase', 'physical_size', 'padded_size',
                                                   'input_shape', 'request_geometry')} for event in mixed]
            if interleave_shape is not None and shape != interleave_shape:
                raise ValueError('D16 repeat interleave native batch geometry differs')
            interleave_shape = shape
        group = result['batch' if slot is None else 'alone'][0]
        target = batch if slot is None else alone
        for row in group:
            row = dict(row)
            for field in ('request','response_path'):
                row[field] = str((arm/'collection'/row[field]).relative_to(owner.directory))
            target[repetition].append(row)
        runs.append({'kind':kind,'repeat':repetition,'slot':slot,'process_identity':identity,
                     'service_capture':str((arm/'capture/service_delivery.json').relative_to(owner.directory)),
                     'sampler_root':str((arm/'capture/sampler').relative_to(owner.directory))})
    collection = root/'collection.json'
    write(collection,{'schema':'ft_d16_exact_id_collection/v1','admitted':False,'physical_batch_verified':False,
                      'slots':slots,'batch':batch,'alone':alone, 'interleave':interleave, 'partial':retained_mode, 'needs_terminal_combination':retained_mode, 'retained_batch0':getattr(owner, '_r040e_retained_batch0', None) if retained_mode else None})
    # Publish a map after every owned process has stopped and sealed capture.
    # Its SHA must be externally frozen/reviewed before the reader consumes it.
    mapping = root/'evidence.json'
    files = {}
    for path in owner.directory.rglob('*'):
        if path.is_symlink(): raise ValueError('owned native collection contains a symlink')
        if path.is_file() and path != mapping:
            files[path.relative_to(owner.directory).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    write(mapping,{'schema':'ft_d16_native_workload_map/v1','collection':str(collection.relative_to(owner.directory)),
                   'runs':runs,'files':files})
    return {'root':str(root),'evidence_map':str(mapping),'evidence_map_sha256':hashlib.sha256(mapping.read_bytes()).hexdigest(),
            'model_admitted':False,'requires_independent_raw_review':True, 'partial':retained_mode, 'needs_terminal_combination':retained_mode, 'arms':runs}

def collect_native_processes(owner, inputs, **kwargs):
    """Retain v2 source checks/context; install the one bounded arm scheduler."""
    arm_schedule(owner, slots=kwargs.get('slots'), interleave=kwargs.get('interleave', False))
    original = _v2._collect_arms
    _v2._collect_arms = _collect_arms
    try:
        return _v2.collect_native_processes(owner, inputs, **kwargs)
    finally:
        _v2._collect_arms = original


def collect_parking_processes(*args, **kwargs):
    return _v2.collect_parking_processes(*args, **kwargs)


def collect_cache_processes(*args, **kwargs):
    return _v2.collect_cache_processes(*args, **kwargs)
