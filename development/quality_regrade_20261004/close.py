"""Synchronize the verified standard, append E0 provenance, and seal this analysis."""
import hashlib,importlib.util,json,os
from pathlib import Path
import subprocess,sys,urllib.request
import fcntl
from publication import Journal, digest, ensure_bytes, publish

HERE=Path(__file__).resolve().parent
ROUNDS=Path('/data2/_shared/runs/ft_rounds')
ROOT=Path('/data2/FreeToken')
RID='E2-R009-regrade'
EVALUATOR_SHA='39f10fa8ddab2c1b076862eb827d903be945243bb2e2422ec448e8560646e330'
PREVIOUS_SHA='250e197f1c09716ae399d491537c396e3ba47706b7d289b6b95220b5a30f4a71'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def encode(value):return (json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
def put(path,value):
    ensure_bytes(path,encode(value))
def copy(source,target):
    ensure_bytes(target,source.read_bytes())

def execute():
    directory=ROUNDS/RID
    if directory.is_symlink():raise ValueError('analysis symlink refused')
    report=json.loads((HERE/'measure_receipt.json').read_bytes())
    stage=Path(report['stage']);cpu=stage/'cpu_validation.json'
    if sha(cpu)!=report['cpu_receipt_sha256']:raise ValueError('CPU receipt differs')
    proof=json.loads(cpu.read_bytes())
    if proof['returncode']!=0 or proof['gpu_started'] is not False:raise ValueError('CPU-only proof required')
    if sha(stage/'tests.log')!=proof['test_log_sha256']:raise ValueError('test log differs')
    for name,digest in proof['source_files'].items():
        if (stage/name).is_symlink() or (stage/name).stat().st_mode&0o222 or sha(stage/name)!=digest:
            raise ValueError('frozen grader source differs')
    summary=json.loads((directory/'quality_summary.json').read_bytes())
    if summary!=report['result']:raise ValueError('actual measured summary differs')
    for rid,value in summary['sets'].items():
        if sha(Path(value['input_path']))!=value['input_sha256'] or sha(directory/value['output_file'])!=value['output_sha256']:
            raise ValueError('answer/input bytes changed')
        if value['passed']!=47 or value['total']!=60 or summary['comparison'][rid]['same_graded_verdicts']!=60:
            raise ValueError('reviewed grade consistency no longer holds')
    copy(stage/'evaluator_previous_250e197f.py',directory/'source/evaluator_previous_250e197f.py')
    (directory/'source/cpu_proof').mkdir(exist_ok=True)
    for source in stage.iterdir():
        if source.is_file():copy(source,directory/'source/cpu_proof'/source.name)
    (directory/'source/closure').mkdir(exist_ok=True)
    for source in HERE.iterdir():
        if source.is_file():copy(source,directory/'source/closure'/source.name)
    canonical=Path('/data2/_shared/evaluator.py')
    if sha(stage/'evaluator.py')!=EVALUATOR_SHA:raise ValueError('selected standard changed')
    benchmark=Path('/data2/_shared/benchmark_client.py')
    prior_benchmark=HERE/'benchmark_client_previous.py'
    copy(prior_benchmark,directory/'source/benchmark_client_previous.py')
    new_benchmark=HERE/'benchmark_client.py'
    bridge=json.loads((HERE/'bridge_cpu.json').read_bytes())
    if bridge['returncode']!=0 or sha(new_benchmark)!=bridge['benchmark_client_sha256'] or sha(HERE/'bridge_tests.log')!=bridge['test_log_sha256']:
        raise ValueError('exact Linux benchmark bridge regression proof missing')
    store=Path('/data2/_shared/model_hub_dashboard/data/rounds.json')
    before_path=directory/'E0_record_before.json'
    before=json.loads(before_path.read_bytes()) if before_path.exists() else json.loads(store.read_bytes())['rounds']['E0-R000']
    put(directory/'E0_record_before.json',before)
    if before['results']['quality60']['pass_rate']!=0.7833:raise ValueError('original E0 scalar differs')
    existing=before['results']['quality60'].get('source_corrections',[])
    if any(row.get('id')=='quality-source-20261004' for row in existing):raise ValueError('correction already exists')
    entry={'id':'quality-source-20261004','analysis_round':RID,
           'original_value_retained':0.7833,'original_value_source':'Local regrade_paper_headroom.py regraded the original E0 answers with evaluator39f10fa8; 47/60, not a new generation.',
           'evaluator_sha256':EVALUATOR_SHA,'questions_sha256':summary['questions_sha256'],
           'recorded_server_original':{'passed':38,'total':60,'pass_rate':38/60,'available_evaluator_sha256':PREVIOUS_SHA,
              'grading_implementation_note':'Historical benchmark_client.py contains its own grade_response; available evaluator hash alone does not prove that function was used.'},
           'standard_regrade':{'passed':47,'total':60,'pass_rate':47/60},
           'evidence':{'path':str(directory/'quality_summary.json'),'sha256':sha(directory/'quality_summary.json')},
           'by':'Codex under CODEX_HANDOFF_20261004c and explicit user request'}
    payload={'round_id':'E0-R000','results':{'quality60':{'source_corrections':existing+[entry],
             'evaluator_sha256':EVALUATOR_SHA}}}
    put(directory/'E0_correction_payload.json',payload)
    module_path=HERE/'round_json_append.py'
    spec=importlib.util.spec_from_file_location('quality_append_validator',module_path)
    validator=importlib.util.module_from_spec(spec);sys.modules[spec.name]=validator;spec.loader.exec_module(validator)
    for name in ('round_json_append.py','round_close.py','round_close.sh'):copy(HERE/name,directory/name)
    metadata={'schema':'ft_round/v2','round_id':RID,'epoch':2,'card':'T08','title':'One-standard offline regrade of E0/R004/R009',
              'parent':'E2-R009','base':{'code_version':'historical answer sets; no new model execution'},
              'serve':'none','experimental':{'analysis_only':True,'gpu_started':False},'evaluator_sha256':EVALUATOR_SHA,
              'questions_sha256':summary['questions_sha256'],'results':summary,
              'proposed_verdict':'measured','verdict':'pending_review','verdict_history':[],'retractions':[],
              'acceptance_limits':['Offline grading only; preserves historical outputs and their runtime defects.',
                                   'Not a new generation, E2-base.1 acceptance, or post-D14 quality test.']}
    if not (directory/'round.json').exists():put(directory/'round.json',metadata)
    else:
        actual=json.loads((directory/'round.json').read_bytes())
        if any(actual.get(key)!=value for key,value in metadata.items()):raise ValueError('prepared round metadata differs')
    ensure_bytes(directory/'batch.sh',('#!/usr/bin/env bash\nset -euo pipefail\nCUDA_VISIBLE_DEVICES="" PYTHONDONTWRITEBYTECODE=1 '+sys.executable+' '+str(stage/'regrade.py')+'\n').encode())
    transaction=ROOT/'runs'/('quality_publish_'+RID)
    transaction.mkdir(exist_ok=True)
    identity={'round_id':RID,'closure_stage':str(HERE),'measurement_sha256':sha(HERE/'measure_receipt.json'),
              'evaluator_sha256':EVALUATOR_SHA,'benchmark_sha256':sha(new_benchmark),'payload_sha256':sha(directory/'E0_correction_payload.json')}
    journal=Journal(transaction/'journal.json',identity)
    if not (directory/'MANIFEST.sha256').exists():
        close_spec=importlib.util.spec_from_file_location('quality_close_validator',HERE/'round_close.py')
        closer=importlib.util.module_from_spec(close_spec);close_spec.loader.exec_module(closer)
        closer.prepare(directory)  # Validate every immutable prerequisite before external mutation.
        journal.note('prepared',lock='/data2/_shared/quality_standard_publish.lock',policy='flock plus renameat2 RENAME_NOREPLACE')
    publish(canonical,stage/'evaluator.py',PREVIOUS_SHA,transaction/'evaluator.previous.py',journal,0o444)
    publish(benchmark,new_benchmark,sha(prior_benchmark),transaction/'benchmark.previous.py',journal,0o644)
    put(directory/'standard_sync.json',{'path':str(canonical),'evaluator_sha256':EVALUATOR_SHA,
        'previous_sha256':PREVIOUS_SHA,'previous_archived':'source/evaluator_previous_250e197f.py',
        'journal':str(transaction/'journal.json'),'lock':'/data2/_shared/quality_standard_publish.lock','policy':'renameat2 RENAME_NOREPLACE'})
    put(directory/'benchmark_sync.json',{'path':str(benchmark),'benchmark_client_sha256':sha(benchmark),
                                        'previous_sha256':sha(prior_benchmark)})
    after=json.loads(store.read_bytes())['rounds']['E0-R000']
    expected=existing+[entry]
    if after['results']['quality60'].get('source_corrections')!=expected:
        if after!=before:raise ValueError('E0 changed since preparation; preserve it and do not POST')
        journal.note('panel_post_intent',payload_sha256=identity['payload_sha256'])
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        request=urllib.request.Request('http://127.0.0.1:8098/api/rounds/record',data=encode(payload),
                                       method='POST',headers={'Content-Type':'application/json'})
        try:
            with opener.open(request,timeout=30) as response:response.read()
        except Exception as error:
            journal.note('panel_response_ambiguous',error_type=type(error).__name__)
            raise  # Next invocation reads the actual record before deciding whether to POST.
        after=json.loads(store.read_bytes())['rounds']['E0-R000']
    validator.validate_change(before,after)
    if after['results']['quality60']['source_corrections']!=expected or after['results']['quality60']['pass_rate']!=0.7833 or after['results']['quality60']['evaluator_sha256']!=EVALUATOR_SHA:
        raise ValueError('append/readback did not preserve original record')
    put(directory/'E0_record_after.json',after)
    put(directory/'E0_panel_post_receipt.json',{'status':'verified_by_persisted_record_readback',
                                             'payload_sha256':identity['payload_sha256'],'record_sha256':sha(directory/'E0_record_after.json')})
    journal.note('panel_readback',record_sha256=sha(directory/'E0_record_after.json'))
    if not (directory/'MANIFEST.sha256').exists():
        subprocess.run(['bash',str(directory/'round_close.sh'),RID,'--round-root',str(ROUNDS)],
                       env={**os.environ,'FT_ROUND_PYTHON':sys.executable},check=True)
    subprocess.run([sys.executable,str(directory/'round_json_append.py'),str(directory),'check'],check=True)
    subprocess.run(['sha256sum','-c','MANIFEST.sha256'],cwd=directory,stdout=subprocess.DEVNULL,check=True)
    for value in summary['sets'].values():
        if sha(Path(value['input_path']))!=value['input_sha256']:raise ValueError('original input changed')
    if any(p.stat().st_mode&0o222 for p in (directory,*directory.rglob('*'))):raise ValueError('analysis not read-only')
    journal.note('sealed',round_sha256=sha(directory/'round.json'),manifest_sha256=sha(directory/'MANIFEST.sha256'))
    print(json.dumps({'round_id':RID,'evaluator_sha256':sha(canonical),'benchmark_client_sha256':sha(benchmark),'E0_original_value':after['results']['quality60']['pass_rate'],
                      'correction_id':entry['id'],'round_sha256':sha(directory/'round.json'),
                      'manifest_sha256':sha(directory/'MANIFEST.sha256'),'formal_verdict':'pending_review'}))

if __name__=='__main__':
    with Path('/data2/_shared/quality_standard_publish.lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        execute()
