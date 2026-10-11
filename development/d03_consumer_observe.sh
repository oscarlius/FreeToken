set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import datetime, hashlib, json, pathlib, sys
writer_path = pathlib.Path('/data2/FreeToken/scripts/round_json_append.py')
writer_sha256 = '67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff'
if (not writer_path.is_file()
        or hashlib.sha256(writer_path.read_bytes()).hexdigest() != writer_sha256):
    raise ValueError('reviewed public round writer differs')
sys.path.insert(0, str(writer_path.parent))
from round_json_append import guarded_round, validate_history

root = pathlib.Path('/data2/_shared/runs/ft_rounds')
dev = pathlib.Path('/data2/FreeToken/runs/dev_D03')
def small(path):
    if path.is_symlink() or path.stat().st_size > 1024 * 1024:
        raise ValueError('not a bounded regular JSON artifact: ' + str(path))
    return json.loads(path.read_text())

def checked_latest_round(round_dir):
    _, round_json, history = guarded_round(round_dir)
    _, document, snapshots = validate_history(round_json, history)
    return document, snapshots
record = small(dev / 'launch_E2-R014.json')
directory = root / record['rid']
process = pathlib.Path('/proc') / str(record['batch_pid'])
alive, identity = False, False
if process.exists():
    try:
        alive = process.joinpath('stat').read_text().partition(') ')[2][0] != 'Z'
        argv = process.joinpath('cmdline').read_bytes().split(b'\0')
        identity = (b'/data2/FreeToken/runs/dev_D03/phase2_tools_c30ae0d_ready/t04_logits_phase2.py' in argv
                    and b'E2-R014' in argv and b'39' in argv
                    and b'c30ae0d7003c3bbbf56867ce74da797332fa7ed5' in argv)
    except FileNotFoundError:
        alive = False
status = small(directory / 'status_batch39.json')
t16 = root / 'E2-R002-gate-D03'
proof = small(t16 / 'round.json')
manifest_sha = hashlib.sha256((t16 / 'MANIFEST.sha256').read_bytes()).hexdigest()
if manifest_sha != '2bc41220885af37386e0f365ef2fba3be97c39e96ec585b4a4cf9ed7dbd8526f':
    raise ValueError('sealed T16 manifest changed')
result = {'observed_at': datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z'),
          'rid': record['rid'], 'batch': record['batch'], 'batch_pid': record['batch_pid'],
          'pid_alive': alive, 'identity_verified': identity, 'status': status,
          'lock_present': pathlib.Path('/data2/_shared/gpu.lock').exists(),
          'captured_arms': [name for name in ('candidate_boundary', 'restore', 'recompute', 'legal')
                            if (directory / name / 'capture.json').is_file()],
          't16_closed_at': proof.get('closed_at'), 't16_formal_verdict': proof.get('verdict'),
          't16_manifest_sha256': manifest_sha}
status11 = small(root / 'E2-R011/status_batch40.json')
if (status11.get('rid'), status11.get('batch'), status11.get('batch_pid')) != ('E2-R011', 40, 2569357):
    raise ValueError('T11 status identity changed')
process11 = pathlib.Path('/proc/2569357')
alive11, identity11 = False, False
if process11.exists():
    try:
        alive11 = process11.joinpath('stat').read_text().partition(') ')[2][0] != 'Z'
        argv11 = process11.joinpath('cmdline').read_bytes().split(b'\0')
        identity11 = (b'/data2/FreeToken/runs/plan_batches/state_test_runner.py' in argv11
                      and all(value in argv11 for value in (b'T11', b'E2-R011', b'40', b'--run')))
    except FileNotFoundError:
        alive11 = False
result['t11'] = {'status': status11, 'pid_alive': alive11, 'identity_verified': identity11}
closed11 = root / 'E2-R011'
expected11 = 'e3fa7c8ec4c168cea4f29afcae1a2fc50f0a3b97958c03f778df0b1394d468ee'
if hashlib.sha256((closed11 / 'MANIFEST.sha256').read_bytes()).hexdigest() != expected11:
    raise ValueError('sealed T11 manifest changed')
round11 = small(closed11 / 'round.json')
if (round11.get('round_id') != 'E2-R011' or round11.get('independent_review_sha256')
        != '4fb65d0dc3dab596af231f596511a3940e10ea8ca3be4a12ff4764662d1f91af'):
    raise ValueError('sealed T11 review identity changed')
result['t11']['sealed_proof'] = {'closed_at': round11['closed_at'], 'formal_verdict': round11['verdict'],
                               'manifest_sha256': expected11, 'scientific_classification': 'unresolved'}
status10 = small(root / 'E2-R012/status_batch41.json')
if (status10.get('rid'), status10.get('batch'), status10.get('batch_pid'), status10.get('state')) != ('E2-R012', 41, 2628647, 'error'):
    raise ValueError('failed T10 startup identity changed')
process10 = pathlib.Path('/proc/2628647/stat')
result['t10_failed'] = {'status': status10, 'pid_alive': process10.exists() and process10.read_text().partition(') ')[2][0] != 'Z'}
receipt16 = small(dev / 'launch_E2-R016.json')
runner16 = '/data2/FreeToken/runs/dev_D03/t10_retry_r016_ready/development/t10_raw_phase1_retry.py'
if (receipt16.get('rid'), receipt16.get('batch'), receipt16.get('batch_pid'), receipt16.get('runner'), receipt16.get('cuda_visible_devices')) != ('E2-R016', 42, 2672941, runner16, '0'):
    raise ValueError('T10 retry receipt identity changed')
status16 = small(root / 'E2-R016/status_batch42.json')
if (status16.get('rid'), status16.get('batch'), status16.get('batch_pid')) != ('E2-R016', 42, 2672941):
    raise ValueError('T10 retry status identity changed')
process16 = pathlib.Path('/proc/2672941')
alive16, identity16 = False, False
if process16.exists():
    try:
        alive16 = process16.joinpath('stat').read_text().partition(') ')[2][0] != 'Z'
        argv16 = process16.joinpath('cmdline').read_bytes().split(b'\0')
        identity16 = runner16.encode() in argv16 and all(value in argv16 for value in (b'E2-R016', b'42', b'--run'))
    except FileNotFoundError:
        alive16 = False
count16 = 0
loading16 = False
for arm in ('B1', 'B2', 'B3'):
    arm_path = root / 'E2-R016' / arm
    if arm_path.is_dir():
        loading16 = not (arm_path / 'health.json').is_file()
    files = list((root / 'E2-R016' / arm / 'logits').glob('tokens_uid*_pid*.json'))
    if len(files) > 24 or any(p.is_symlink() or not p.is_file() for p in files):
        raise ValueError('T10 terminal progress artifacts exceed the assigned bounded stream')
    count16 += len(files)
result['t10_retry'] = {'status': status16, 'pid_alive': alive16, 'identity_verified': identity16,
                       'terminal_records': count16, 'terminal_records_total': 72, 'loading': loading16}
receipt15 = small(dev / 'launch_E2-R015.json')
runner15 = '/data2/FreeToken/runs/dev_D03/t04_retry_r015_71d4846/development/t04_logits_retry.py'
if (receipt15.get('rid'), receipt15.get('batch'), receipt15.get('batch_pid'), receipt15.get('runner_sha256')) != ('E2-R015', 43, 2749339, '1f8dcac3f75bcd98b38b496068e727d13435cdf60117f0d99c27b95370445458'):
    raise ValueError('T04 controlled retry receipt identity changed')
status15 = small(root / 'E2-R015/status_batch43.json')
if (status15.get('rid'), status15.get('batch'), status15.get('batch_pid')) != ('E2-R015', 43, 2749339):
    raise ValueError('T04 controlled retry status identity changed')
process15 = pathlib.Path('/proc/2749339')
alive15, identity15 = False, False
if process15.exists():
    try:
        alive15 = process15.joinpath('stat').read_text().partition(') ')[2][0] != 'Z'
        argv15 = process15.joinpath('cmdline').read_bytes().split(b'\0')
        identity15 = runner15.encode() in argv15 and all(value in argv15 for value in (b'E2-R015', b'43', b'--run'))
    except FileNotFoundError:
        alive15 = False
captures15, loading15 = [], False
for arm in ('candidate_boundary', 'restore', 'recompute', 'legal'):
    path = root / 'E2-R015' / arm
    if path.is_dir():
        loading15 = not (path / 'health.json').is_file()
    if (path / 'capture.json').is_file():
        captures15.append(arm)
result['t04_retry'] = {'status': status15, 'pid_alive': alive15, 'identity_verified': identity15,
                      'captured_arms': captures15, 'capture_total': 4, 'loading': loading15}
receipt17 = small(dev / 'launch_E2-R017.json')
runner17 = '/data2/FreeToken/runs/dev_D03/t10_retry_r017_8a7f9e3/development/t10_raw_phase1_r017.py'
if (receipt17.get('rid'), receipt17.get('batch'), receipt17.get('batch_pid'), receipt17.get('runner'), receipt17.get('cuda_visible_devices')) != ('E2-R017', 44, 2786369, runner17, '0'):
    raise ValueError('T10 bridge retry receipt identity changed')
status17 = small(root / 'E2-R017/status_batch44.json')
if (status17.get('rid'), status17.get('batch'), status17.get('batch_pid')) != ('E2-R017', 44, 2786369):
    raise ValueError('T10 bridge retry status identity changed')
process17 = pathlib.Path('/proc/2786369')
alive17, identity17 = False, False
if process17.exists():
    try:
        alive17 = process17.joinpath('stat').read_text().partition(') ')[2][0] != 'Z'
        argv17 = process17.joinpath('cmdline').read_bytes().split(b'\0')
        identity17 = runner17.encode() in argv17 and all(value in argv17 for value in (b'E2-R017', b'44', b'--run'))
    except FileNotFoundError:
        alive17 = False
count17, loading17 = 0, False
for arm in ('B1', 'B2', 'B3'):
    path = root / 'E2-R017' / arm
    if path.is_dir():
        loading17 = not (path / 'health.json').is_file()
    files = list((path / 'logits').glob('tokens_uid*_pid*.json'))
    if len(files) > 24 or any(p.is_symlink() or not p.is_file() for p in files):
        raise ValueError('R017 terminal stream exceeds assigned progress bound')
    count17 += len(files)
result['t10_bridge_retry'] = {'status': status17, 'pid_alive': alive17, 'identity_verified': identity17,
                            'terminal_records': count17, 'terminal_records_total': 72, 'loading': loading17}
closed17 = root / 'E2-R017'
if (closed17 / 'MANIFEST.sha256').is_file():
    expected17 = '68595988896b31b4f08e545b291396cb9cafb45162b965e0edc48bc296316c38'
    if hashlib.sha256((closed17 / 'MANIFEST.sha256').read_bytes()).hexdigest() != expected17:
        raise ValueError('sealed R017 manifest changed')
    original17_path = closed17 / 'round_history/round.v001.json'
    original17 = small(original17_path)
    if (hashlib.sha256(original17_path.read_bytes()).hexdigest() != '88cbfee4e0cd4f0a12570d5231e5f3516a31ac851c59dd10037c6da25f9900c7'
            or original17.get('round_id') != 'E2-R017'
            or original17.get('independent_review_sha256') != '0a2eebdd9dc6872cfce8450823e8ceb596fc046ecf3f316847dcd1fa91ab0e99'):
        raise ValueError('sealed R017 v001 identity changed')
    round17, _ = checked_latest_round(closed17)
    result['t10_bridge_retry']['sealed_proof'] = {
        'closed_at': round17['closed_at'], 'formal_verdict': round17['verdict'],
        'manifest_sha256': expected17, 'forkpoints': 11,
        'cross_cold_equal': 36, 'cross_warm_equal': 36, 'cold_warm_equal': 3, 'pair_total': 36}

receipt13 = small(dev / 'launch_E2-R013.json')
runner13 = '/data2/FreeToken/runs/dev_D03/t10_stage2_r013_from_r017_d231fe0_87bf525/development/t10_r013_from_r017.py'
if (receipt13.get('rid'), receipt13.get('batch'), receipt13.get('batch_pid'), receipt13.get('runner'),
        receipt13.get('runner_sha256'), receipt13.get('cuda_visible_devices')) != (
        'E2-R013', 45, 2977969, runner13, 'd231fe011f57babb5c9d8d82bb3e175d95b5ee287e355004219eee9ccf92f49f', '0'):
    raise ValueError('T10 stage2 launch receipt identity changed')
directory13 = root / 'E2-R013'
status13 = small(directory13 / 'status_batch45.json')
if (status13.get('rid'), status13.get('batch'), status13.get('batch_pid')) != ('E2-R013', 45, 2977969):
    raise ValueError('T10 stage2 status identity changed')
admission13 = small(directory13 / 'admission.json')
if (admission13.get('forkpoints'), admission13.get('parent_rid'), admission13.get('candidate_commit'),
        admission13.get('phase1_round_proof_sha256')) != (
        11, 'E2-R017', 'c30ae0d7003c3bbbf56867ce74da797332fa7ed5',
        '88cbfee4e0cd4f0a12570d5231e5f3516a31ac851c59dd10037c6da25f9900c7'):
    raise ValueError('T10 stage2 admission changed')
process13 = pathlib.Path('/proc/2977969')
alive13, identity13 = False, False
if process13.exists():
    try:
        alive13 = process13.joinpath('stat').read_text().partition(') ')[2][0] != 'Z'
        argv13 = process13.joinpath('cmdline').read_bytes().split(b'\0')
        # RID is compiled into this runner; no --rid argument is passed.
        identity13 = runner13.encode() in argv13 and all(value in argv13 for value in (
            b'--run', b'45', b'c30ae0d7003c3bbbf56867ce74da797332fa7ed5',
            b'/data2/_shared/runs/ft_rounds/E2-R017/phase1_manifest.json',
            b'/data2/_shared/runs/ft_rounds/E2-R017/round.json'))
    except FileNotFoundError:
        alive13 = False
captures13, comparisons13, active13, progress_errors13 = [], [], [], []
for n in range(11):
    for side in ('a', 'b'):
        arm = directory13 / f'fork{n:02d}_{side}'
        if arm.is_symlink():
            raise ValueError('T10 stage2 progress arm is symlink')
        if not arm.is_dir():
            continue
        capture = arm / 'capture.json'
        if capture.is_file():
            try:
                data = small(capture)
                if data.get('k') != 1 or type(data.get('uid')) is not int or type(data.get('capture_pid')) is not int:
                    raise ValueError('T10 stage2 capture does not bind K1/UID/PID')
                captures13.append(arm.name)
            except json.JSONDecodeError:
                progress_errors13.append(arm.name + ': capture is being written; excluded from count')
        owner_path = arm / 'owned_process.json'
        if owner_path.is_file():
            owner = small(owner_path)
            proc = pathlib.Path('/proc') / str(owner['pid'])
            if proc.exists():
                try:
                    stat = proc.joinpath('stat').read_text().partition(') ')[2].split()
                    argv = proc.joinpath('cmdline').read_bytes().split(b'\0')
                    if stat[0] != 'Z' and int(stat[2]) == owner['pgid']:
                        exact = (b'/data2/FreeToken/venv/bin/ft' in argv and b'serve' in argv
                                 and b'/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay' in argv
                                 and b'--port' in argv and argv[argv.index(b'--port') + 1] == b'8095'
                                 and b'--mamba-host-slots' in argv and argv[argv.index(b'--mamba-host-slots') + 1] == b'0'
                                 and b'--prefill-layer-major' not in argv)
                        active13.append({'arm': arm.name, 'pid': owner['pid'],
                                         'pgid': owner['pgid'], 'identity_verified': exact,
                                         'health_ready': (arm / 'health.json').is_file()})
                except FileNotFoundError:
                    pass
    compare = directory13 / f'fork{n:02d}_compare.log'
    if compare.is_file():
        if compare.is_symlink() or compare.stat().st_size > 1024 * 1024:
            raise ValueError('T10 stage2 comparison log exceeds bounded summary')
        lines = [line for line in compare.read_text().splitlines() if line.strip()]
        try:
            doc = json.loads(lines[-1]) if lines else None
        except json.JSONDecodeError:
            doc = None
        if isinstance(doc, dict) and all(f'fork{n:02d}_{side}' in captures13 for side in ('a', 'b')):
            comparisons13.append(n)
result['t10_stage2'] = {'status': status13, 'pid_alive': alive13, 'identity_verified': identity13,
    'capture_count': len(captures13), 'capture_total': 22,
    'comparison_count': len(comparisons13), 'comparison_total': 11,
    'active_arms': active13, 'progress_errors': progress_errors13,
    'loading': any(not item['health_ready'] for item in active13),
    'receipt_sha256': hashlib.sha256((dev / 'launch_E2-R013.json').read_bytes()).hexdigest()}
if status13['state'] == 'complete_measurements_pending_review':
    manifest13 = directory13 / 'RUN_MANIFEST.sha256'
    if manifest13.is_symlink() or manifest13.stat().st_size > 1024 * 1024:
        raise ValueError('R013 producer manifest must be a bounded regular file')
    result['t10_stage2']['run_manifest_sha256'] = hashlib.sha256(manifest13.read_bytes()).hexdigest()
if (directory13 / 'MANIFEST.sha256').is_file():
    expected13 = '804d84e9fe0692d2989ba5786cc987599181ff59ecfe687e68b153d49b39cab8'
    if hashlib.sha256((directory13 / 'MANIFEST.sha256').read_bytes()).hexdigest() != expected13:
        raise ValueError('sealed R013 manifest changed')
    original13_path = directory13 / 'round_history/round.v001.json'
    original13 = small(original13_path)
    if (hashlib.sha256(original13_path.read_bytes()).hexdigest()
            != '580a24ff8d4009c07fd203eec2660d896922574fae92eadd976ca01c27acbf1c'
            or original13.get('round_id') != 'E2-R013' or original13.get('parent') != 'E2-R017'
            or original13.get('independent_review_sha256')
            != 'de10719d612984d4e0790ac7aaab74a3fb76ad5e4b61446bd14e689d01be9f3d'):
        raise ValueError('sealed R013 v001 identity changed')
    round13, _ = checked_latest_round(directory13)
    result['t10_stage2']['sealed_proof'] = {
        'closed_at': round13['closed_at'], 'formal_verdict': round13['verdict'],
        'manifest_sha256': expected13, 'parent': round13['parent']}
receipt18_path = dev / 'launch_E2-R018-gate-D03.json'
if receipt18_path.is_file():
    if hashlib.sha256(receipt18_path.read_bytes()).hexdigest() != '49a2fa4327613d639413e57a0d66115f3c0033c7508f91db8c97b3ffa1dba88b':
        raise ValueError('R018 candidate launch receipt changed')
    receipt18 = small(receipt18_path)
    directory18 = root / receipt18['rid']
    status18 = small(directory18 / 'status_batch46.json')
    if (status18.get('rid'), status18.get('batch'), status18.get('batch_pid')) != ('E2-R018-gate-D03',46,3451139):
        raise ValueError('R018 candidate status identity changed')
    proc18 = pathlib.Path('/proc/3451139')
    alive18, identity18 = False, False
    if proc18.exists():
        try:
            stat18 = proc18.joinpath('stat').read_text().rpartition(') ')[2].split()
            argv18 = proc18.joinpath('cmdline').read_bytes().split(b'\0')
            alive18 = stat18[0] != 'Z'
            identity18 = (int(stat18[2]) == 3451139 and receipt18['runner'].encode() in argv18
                and all(value in argv18 for value in (b'--run',b'E2-R018-gate-D03',b'46',b'D03-continuation',
                    b'f5067bbe05da51d5f78185213435a8be095a684a')))
        except FileNotFoundError:
            alive18 = False
    arm_names18 = [prefix + name + '_b46' for prefix in ('','CHUNK_')
                   for name in ('PARENT','NEW','PARENT_P','NEW_P')]
    summaries18 = [name for name in arm_names18
        if (directory18/name/'business_prefill_events.json').is_file()
        and (directory18/name/'tax.json').is_file()]
    result['t16_candidate'] = {'receipt': receipt18, 'status': status18,
        'pid_alive': alive18, 'identity_verified': identity18,
        'measured_arms': summaries18, 'arm_total': 8,
        'receipt_sha256': hashlib.sha256(receipt18_path.read_bytes()).hexdigest()}
    proof18_path = directory18 / 'round.json'
    if proof18_path.is_file():
        proof18 = small(proof18_path)
        manifest18_sha = hashlib.sha256((directory18/'MANIFEST.sha256').read_bytes()).hexdigest()
        if manifest18_sha != 'e7b63c0ec3c4b2d53d42663581af9bcd86de21dd3cf9748fc450c3b19b80f142':
            raise ValueError('R018 sealed manifest changed')
        original18_v1 = directory18 / 'round_history/round.v001.json'
        original18_v2 = directory18 / 'round_history/round.v002.json'
        proof18_v2 = small(original18_v2)
        if (hashlib.sha256(original18_v1.read_bytes()).hexdigest()
                != '99517fb399c8adf758e2b50a63bedabf7b5c5fb322d8795c2e4fc0d33a940ca7'
                or hashlib.sha256(original18_v2.read_bytes()).hexdigest()
                != '36c249835233e9bdf2d09e7825fef7c377220f0f8006d99264f2b2b77e71b5f7'
                or proof18_v2['base'].get('code_version')!='E2-base@23f2e2c'):
            raise ValueError('R018 immutable metadata history differs')
        proof18, _ = checked_latest_round(directory18)
        result['t16_candidate']['sealed_proof'] = {'closed_at':proof18['closed_at'],
            'formal_verdict':proof18['verdict'],'manifest_sha256':manifest18_sha}
receipt19_path = dev / 'launch_E2-R019-gate-D06.json'
if receipt19_path.is_file():
    receipt19_sha = hashlib.sha256(receipt19_path.read_bytes()).hexdigest()
    if receipt19_sha != '051697d13a2dda6627f30a65ca2d0f45c1de315ff5740d8454330aaddf4fa9b0':
        raise ValueError('R019 candidate launch receipt changed')
    receipt19 = small(receipt19_path)
    directory19 = root / receipt19['rid']
    status19 = small(directory19 / 'status_batch47.json')
    if (status19.get('rid'), status19.get('batch'), status19.get('batch_pid')) != ('E2-R019-gate-D06',47,3600451):
        raise ValueError('R019 candidate status identity changed')
    proc19 = pathlib.Path('/proc/3600451')
    alive19, identity19 = False, False
    if proc19.exists():
        try:
            stat19 = proc19.joinpath('stat').read_text().rpartition(') ')[2].split()
            argv19 = proc19.joinpath('cmdline').read_bytes().split(b'\0')
            alive19 = stat19[0] != 'Z'
            identity19 = (int(stat19[2]) == 3600451 and receipt19['runner'].encode() in argv19
                and all(value in argv19 for value in (b'--run',b'E2-R019-gate-D06',b'47',b'D06',
                    b'03692633df48456fb0baa78de7b64e5628a12ab1')))
        except FileNotFoundError:
            alive19 = False
    arms19 = [name + '_b47' for name in ('PARENT','NEW','PARENT_P','NEW_P')]
    summaries19 = [name for name in arms19
        if (directory19/name/'business_prefill_events.json').is_file()
        and (directory19/name/'tax.json').is_file()]
    result['t16_d06_candidate'] = {'receipt':receipt19,'status':status19,
        'pid_alive':alive19,'identity_verified':identity19,
        'measured_arms':summaries19,'arm_total':4,'receipt_sha256':receipt19_sha}
receipt20_path = pathlib.Path('/data2/FreeToken/runs/dev_D06/launch_E2-R020-gate-D06.json')
if receipt20_path.is_file():
    receipt20_sha = hashlib.sha256(receipt20_path.read_bytes()).hexdigest()
    if receipt20_sha != '913d82b367dd8c0f736b7767f323c7e1075cbc2d327ad4b43a515ce8f1d221b8':
        raise ValueError('R020 launch receipt changed')
    receipt20=small(receipt20_path); directory20=root/receipt20['rid']
    status20=small(directory20/'status_batch48.json')
    if (status20.get('rid'),status20.get('batch'),status20.get('batch_pid'))!=('E2-R020-gate-D06',48,3817162):
        raise ValueError('R020 status identity changed')
    proc20=pathlib.Path('/proc/3817162');alive20,identity20=False,False
    if proc20.exists():
        try:
            fields20=proc20.joinpath('stat').read_text().rpartition(') ')[2].split()
            argv20=proc20.joinpath('cmdline').read_bytes().split(b'\0')
            alive20=fields20[0]!='Z'
            identity20=(int(fields20[2])==3817162 and receipt20['runner'].encode() in argv20
                and all(value in argv20 for value in (b'--run',b'E2-R020-gate-D06',b'48',b'D06',
                    b'03692633df48456fb0baa78de7b64e5628a12ab1')))
        except FileNotFoundError:
            alive20=False
    arms20=[name+'_b48' for name in ('PARENT','NEW','PARENT_P','NEW_P')]
    result['t16_d06_retry']={'receipt':receipt20,'status':status20,'pid_alive':alive20,
        'identity_verified':identity20,'receipt_sha256':receipt20_sha,'arm_total':4,
        'measured_arms':[name for name in arms20 if (directory20/name/'business_prefill_events.json').is_file()
            and (directory20/name/'tax.json').is_file()]}
    sealed20_path=directory20/'round.json'
    if sealed20_path.is_file():
        original20_path = directory20 / 'round_history/round.v001.json'
        original20 = small(original20_path)
        manifest20=hashlib.sha256((directory20/'MANIFEST.sha256').read_bytes()).hexdigest()
        if (hashlib.sha256(original20_path.read_bytes()).hexdigest()!='a80eb0c3c66f4bfc248691f29b5b60324bff14c090f5d8cb703b3744d884e666'
            or manifest20!='66eb455b51f927746014a3b31ef8c61f4c3347b25a6ba589a31804f015a33e01'
            or original20['base']['commit']!=receipt20['parent_commit']
            or original20['experimental']['candidate_commit']!=receipt20['candidate_commit']):
            raise ValueError('R020 immutable closure identity differs')
        sealed20, _ = checked_latest_round(directory20)
        result['t16_d06_retry']['sealed_proof']={'closed_at':sealed20['closed_at'],
            'formal_verdict':sealed20['verdict'],'manifest_sha256':manifest20,
            'round_sha256':hashlib.sha256(sealed20_path.read_bytes()).hexdigest()}
f506_receipt = dev / 'gpu_selfcheck_launch_f5067bb.json'
if f506_receipt.is_file():
    digest = hashlib.sha256(f506_receipt.read_bytes()).hexdigest()
    if digest != '1013a44948be27b904f68504a9aa0f2fee7cec0246f14e7bc65b952c43bcf8ef':
        raise ValueError('f506 development selfcheck receipt changed')
    receipt = small(f506_receipt)
    pid = receipt['pid']; proc = pathlib.Path('/proc')/str(pid)
    alive, identity = False, False
    if proc.exists():
        try:
            fields = proc.joinpath('stat').read_text().rpartition(') ')[2].split()
            argv = [part.decode() for part in proc.joinpath('cmdline').read_bytes().split(b'\0') if part]
            alive = fields[0] != 'Z'
            identity = (int(fields[2]) == pid and int(fields[3]) == pid
                and argv == receipt['argv'] and proc.stat().st_uid == __import__('os').geteuid())
        except FileNotFoundError:
            alive = False
    output = pathlib.Path(receipt['output'])
    names = ['parent_off','candidate_off','candidate_on_state_logits','candidate_boundary','candidate_logits_a','candidate_logits_b']
    existing = [name for name in names if (output/name).is_dir()]
    active = existing[-1] if existing else None
    error_path, summary_path = output/'selfcheck_error.json', output/'selfcheck.json'
    error = small(error_path) if error_path.is_file() else None
    summary = small(summary_path) if summary_path.is_file() else None
    phase = ('failed' if error else 'complete_measurements_pending_review' if summary else
        'probing' if active and (output/active/'health.json').is_file() else 'loading')
    result['d03_f506_selfcheck'] = {'receipt':receipt,'receipt_sha256':digest,
        'pid_alive':alive,'identity_verified':identity,'phase':phase,'active_arm':active,
        'cold_summary_arms':[name for name in names[:3] if (output/name/'cold.json').is_file()],
        'error':error,'summary':summary}
d06_receipt_path=pathlib.Path('/data2/FreeToken/runs/dev_D06/gpu_selfcheck_launch_195aa332.json')
if d06_receipt_path.is_file():
    digest06=hashlib.sha256(d06_receipt_path.read_bytes()).hexdigest()
    if digest06!='e0ceca3447cbf365e2cb4453fd8beec86d634033866b763e9ff5a12de4f70793':
        raise ValueError('D06 development selfcheck launch receipt changed')
    receipt06=small(d06_receipt_path)
    if (receipt06['runner_sha256']!='195aa332d220cf43955a50c25d68276e39ac66a67002e9be0d25497b8df38a10'
        or receipt06['candidate_commit']!='03692633df48456fb0baa78de7b64e5628a12ab1'):
        raise ValueError('D06 development source identity differs')
    proc06=pathlib.Path('/proc')/str(receipt06['pid']);alive06,identity06=False,False
    if proc06.exists():
        try:
            fields06=proc06.joinpath('stat').read_text().rpartition(') ')[2].split()
            argv06=[part.decode() for part in proc06.joinpath('cmdline').read_bytes().split(b'\0') if part]
            alive06=fields06[0]!='Z'
            identity06=(int(fields06[2])==receipt06['pid'] and int(fields06[3])==receipt06['pid']
                and argv06==receipt06['argv'] and proc06.stat().st_uid==__import__('os').geteuid())
        except FileNotFoundError:alive06=False
    output06=pathlib.Path(receipt06['output'])
    error06=small(output06/'error.json') if (output06/'error.json').is_file() else None
    summary06=small(output06/'result.json') if (output06/'result.json').is_file() else None
    if summary06 and (summary06.get('mode')!='development_selfcheck_not_T05_or_T16'
        or summary06.get('candidate_commit')!=receipt06['candidate_commit']):
        raise ValueError('D06 result identity differs')
    phase06=('failed' if error06 else 'complete_measurements_pending_review' if summary06 else
        'G4; G3 raw file present' if (output06/'candidate/g3.json').is_file() else 'service startup or G3; no probe result yet')
    result['d06_selfcheck']={'receipt':receipt06,'receipt_sha256':digest06,
        'pid_alive':alive06,'identity_verified':identity06,'phase':phase06,'error':error06,'summary':summary06}
print(json.dumps(result, ensure_ascii=False, allow_nan=False))
PY
