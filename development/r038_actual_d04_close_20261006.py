"""One-shot canonical D04 orchestration for the measured R038 14+14 round."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path('/data2/FreeToken')
ROUND = Path('/data2/_shared/runs/ft_rounds/E2-R038')
REVIEW = ROOT / 'runs/dev_D16/r038_incremental_raw_review_20261006_1201'
CANDIDATE = 'a9dca443cd07e1f60d1533e0a678935a09d21636'
TOOLS = {'round_json_append.py': '67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff', 'round_close.py': 'fd3d40c25b045920cc6a247c0e3e09e11bf831c4d24ddfaa67dfb562dec60fb5', 'round_close.sh': '6df87a2f2edfcbc985a2d593edb16349bf923e1f301939cdda1590d52d1f55f9'}

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def load(path):
    return json.loads(Path(path).read_text())

def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as f:
        f.write(data)

def encoded(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2) + '\n').encode()

def require(ok, message):
    if not ok:
        raise ValueError(message)

def main():
    summary_path = Path(sys.argv[1])
    summary = load(summary_path)
    require(sha(summary_path) == '2e00291e3a70dfa63916fd323e97b14ae13f0a46c3d43fdd785a6501d3ec7716', 'independent summary changed')
    require(summary['schema'] == 'ft_t17_r036_r038_combined_28_review/v1' and summary['verdict'] == 'PASS_ALL_28_PENDING_CANONICAL_D04' and summary['candidate_commit'] == CANDIDATE, 'independent verdict')
    coverage = summary['canonical_coverage']
    require(coverage['exact'] is True and coverage['actual_positions'] == list(range(1,29)), 'combined positions')
    rows = summary['r036_retained_cases'] + summary['r038_recomputed_cases']
    require(len(summary['r036_retained_cases']) == len(summary['r038_recomputed_cases']) == 14, 'combined counts')
    for row in rows:
        for key in ['case', 'schedule', 'report']:
            if key+'_path' in row:
                require(sha(Path(row[key+'_path'])) == row[key+'_sha256'], 'summary binding: '+key)
        case = load(row['case_path'])
        require(case['evidence']['requested_input_ids_sha256'] == row['input_ids_sha256'], 'case input ids changed')
    require(not any((ROUND/n).exists() for n in ['round.json', 'round_history', 'MANIFEST.sha256']), 'already closed')
    require(not any(p.is_symlink() for p in [ROUND, *ROUND.rglob('*')]), 'symlink evidence')
    receipt_path = ROOT / 'runs/dev_D16/launch_E2-R038.json'
    require(sha(receipt_path) == '4281d151514a85762485ca3c412e0c84e24ee8aa2b24dddfb824eec9d1d648e1', 'launch receipt changed')
    receipt = load(receipt_path)
    status = load(ROUND/'status_batch67.json')
    result = load(ROUND/'result.json')
    require(receipt['candidate_commit'] == CANDIDATE and receipt['batch_execution_id'] == '1569424:133994698', 'launch candidate/identity')
    require(status['state'] == 'complete_measurements_pending_independent_review' and status['batch_pid'] == 1569424, 'not terminal')
    require(result['verdict'] == 'measurements_pass_pending_independent_review', 'measurements failed')
    require(not Path('/proc/1569424').exists() and not Path('/data2/_shared/gpu.lock').exists(), 'controller/lock active')
    memory = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'], text=True)
    require(memory.strip() and all(int(x) < 1000 for x in memory.splitlines()), 'GPU not idle')
    permit_path = ROOT/'runs/dev_D16/r036_retained_cases_review_r_overlap/review.json'
    require(sha(permit_path) == '9bb40368c6fb0406d3bbdfe29c9f2dbd36da8aad11710fab90c6203fef0508f4', 'reuse permit changed')
    permit = load(permit_path)
    require(permit['reuse_permitted'] is True and permit['target_candidate'] == CANDIDATE, 'reuse denied')
    expected = lambda prefixes: {f'prefix-{p}-tail-{t}' for p in prefixes for t in [65,4095,4096,4097,8191,8192,8193]}
    require(set(coverage['actual_case_names']) == expected([8192,12416,12736,18944]), 'combined canonical names')
    require({c['case'] for c in permit['computed_cases']} == expected([8192,12416]), 'retained coverage')
    reports = sorted(REVIEW.glob('prefix-*.json'))
    require({p.stem for p in reports} == expected([12736,18944]), 'new coverage')
    for p in reports:
        report = load(p); case = load(ROUND/'cases'/p.name); gate = report['case']['gate']
        require(report['verdict'] == 'PASS' and report['case_sha256'] == sha(ROUND/'cases'/p.name), 'case report changed')
        require(report['guard_installed'] is True and report['cuda_visible_devices'] == '', 'reader guard')
        require(report['raw_input_sha256'] == sha(ROUND/'real_inputs.json'), 'input binding')
        require(report['case']['schedule_sha256'] == sha(Path(case['schedule'])), 'schedule binding')
        require(all(gate['state_handoff']['roles'].values()), 'state mismatch')
        for comparison in ['repeat','warm_comparison']:
            c = gate['same_structure_reference'][comparison]
            require(c['tokens_equal'] is True and c['text_equal'] is True and c['first_token_fork'] is None, 'generation mismatch')
    for c in permit['computed_cases']:
        old = Path(permit['source_round'])/'cases'/(c['case']+'.json')
        require(sha(old) == c['case_doc_sha256'], 'retained case changed')
        require(sha(Path(load(old)['schedule'])) == c['schedule_sha256'], 'retained schedule changed')
    closure_path = ROOT/'runs/dev_D14/r037_gate_closure_r_overlap/closure_receipt.json'
    require(sha(closure_path) == '15d74a8c131f5cfdcf6b549d0d6a9d2f24a28ac46efa86fec57bc96a456bf8c9', 'R037 closure changed')
    for name, digest in receipt['source_files'].items():
        require(sha(ROUND/'source_tools'/name) == digest, 'archived source changed: '+name)
    for name, digest in TOOLS.items():
        require(sha(ROOT/'scripts'/name) == digest, 'D04 source changed')
    log_path = Path(receipt['batch_log']); log = log_path.read_text()
    stops = re.findall(r'STOP PASS owned_pid=(\d+) gpu=\d+', log)
    arms = {p.name: {'files': {n: sha(p/n) for n in ['SERVE_CMD.txt','ENV.txt','serve.log','serve_args.txt','compiled_extensions.json']}} for p in ROUND.iterdir() if p.is_dir() and (p/'SERVE_CMD.txt').exists()}
    require(len(arms) == len(stops) == 44 and all(not (Path('/proc')/pid).exists() for pid in stops), 'service termination')
    original = {str(p.relative_to(ROUND)): sha(p) for p in sorted(ROUND.rglob('*')) if p.is_file()}
    print(json.dumps({'phase':'prevalidated','original_files':len(original)}), flush=True)
    archive = {'combined_review.json': summary_path, 'retained_review.json': permit_path, 'r037_closure_receipt.json': closure_path, 'launch_receipt.json': receipt_path}
    archive.update({'independent_review/'+p.name: p for p in reports})
    for name,p in archive.items():
        write(ROUND/name, p.read_bytes())
    identity = {'pid':1569424,'start_ticks':133994698,'pgid':receipt['batch_pgid'],'launch_receipt_sha256':sha(receipt_path)}
    write(ROUND/'launch_identity.json', encoded(identity))
    write(ROUND/'close_source/r038_actual_d04_close_20261006.py', Path(__file__).read_bytes())
    for name in TOOLS:
        write(ROUND/name, (ROOT/'scripts'/name).read_bytes())
    metadata = {'schema':'ft_round/v2','round_id':'E2-R038','epoch':2,'card':'T17','parent':'E2-R037-gate-D14','base':{'commit':receipt['parent_commit']},'experimental':{'candidate_commit':CANDIDATE},'serve':{'arms':arms},'design':{'batch':67,'retained_count':14,'measured_count':14,'combined_count':28},'results':summary,'proposed_verdict':'kept','verdict':'pending_review','verdict_history':[],'retractions':[],'independent_review_sha256':sha(summary_path),'batch_logs':[{'path':str(log_path),'sha256':sha(log_path)}],'acceptance_limits':['T17 continuation mechanism only; ordinary cold differences recorded, not T04 envelope acceptance.','Operator comparison covers Python method boundaries, not CUDA kernel proof.'],'diagnostics':{'original_raw_files':original,'launch_identity':identity,'retained_review_sha256':sha(permit_path),'r037_closure_sha256':sha(closure_path)}}
    write(ROUND/'round.json', encoded(metadata))
    subprocess.run([sys.executable,str(ROUND/'round_close.py'),'E2-R038','--round-root',str(ROUND.parent)],check=True)
    subprocess.run([sys.executable,str(ROUND/'round_json_append.py'),str(ROUND),'verdict','--new','kept','--reason','PLAN section 8.7: R036 retained 14 independently recomputed cases with reuse_permitted=true for a9dca443; R038 remaining 14 independently recomputed PASS; exact 28-case matrix, R037 kept prerequisite.','--evidence','combined_review.json','retained_review.json','r037_closure_receipt.json','launch_identity.json',*[str('independent_review/'+p.name) for p in reports],'--by','root authorized D04 closure'],check=True)
    subprocess.run([sys.executable,str(ROUND/'round_json_append.py'),str(ROUND),'check'],check=True)
    for name,digest in original.items():
        require(sha(ROUND/name)==digest,'raw evidence changed: '+name)
    for line in (ROUND/'MANIFEST.sha256').read_text().splitlines():
        digest, name = line.split('  ./',1)
        require(sha(ROUND/name)==digest,'manifest mismatch: '+name)
    require(all(not p.stat().st_mode & 0o222 for p in [ROUND,*ROUND.rglob('*')]),'closure writable')
    print(json.dumps({'rid':'E2-R038','verdict':'kept','round_sha256':sha(ROUND/'round.json'),'manifest_sha256':sha(ROUND/'MANIFEST.sha256'),'combined_review_sha256':sha(summary_path),'original_raw_files_verified':len(original)}),flush=True)

if __name__ == '__main__':
    main()
