"""Real continuation driver, with CPU substitutes only for service I/O."""
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

HERE = Path(__file__).resolve().parent
FILES = {'cold32k_1': 'cold32k_1.json', 'cold32k_2': 'cold32k_2.json',
         'seed_45k': 'seed_45k_replay.json', 'seed_real': 'seed_real_replay.json',
         'two_decode_diff512': 'two_decode.json'}

def load():
    spec = importlib.util.spec_from_file_location('r049_v12_continuation', HERE/'r049_t21_ordinary_prepare_v14.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

def record(uid, count=128):
    return {'uid': uid, 'ordinary_uid': uid, 'input_ids_sha256': f'{uid:064x}',
            'prompt_tokens': 32000, 'completion_tokens': count, 'finish_reason': 'length',
            'token_ids_sha256': f'{uid+100:064x}', 'model_output_sha256': f'{uid+200:064x}',
            'response': {'content_text': f'output-{uid}', 'reasoning_text': '', 'tool_calls': []},
            'ttft_s': 1.0, 'decode_tps': 10.0}

def retained_fixture(monkeypatch, tmp_path):
    m = load()
    root = tmp_path/'rounds'/m.R049A_FAILED_RID/'L1'
    root.mkdir(parents=True)
    docs = {
        'cold32k_1': {'schema': 'ft_t21_cold_ordinary/v1', 'cold_id': 'E2-R049a-cold1', 'record': record(0)},
        'cold32k_2': {'schema': 'ft_t21_cold_ordinary/v1', 'cold_id': 'E2-R049a-cold2', 'record': record(1)},
        'seed_45k': {'schema': 'ft_r049_ordinary_heldout_replay/v3', 'rounds': [{'record': record(i)} for i in range(2,14)]},
        'seed_real': {'schema': 'ft_r049_ordinary_heldout_replay/v3', 'rounds': [{'record': record(i)} for i in range(14,22)]},
        'two_decode_diff512': {'schema': 'ft_r049_ordinary_two_decode/v9',
            'pause_enabled': False, 'ft_dev_ack': False, 'simultaneous_barrier': True,
            'overlap_basis': 'network_first_nonempty_and_terminal_only', 'records': [record(22,512),record(23,512)]}}
    # Both sealed baselines have the independently reviewed 6,334-token, six-field-identical payload.
    rows = [row for doc in docs.values() for row in m._workload_rows(doc)]
    for index,row in enumerate(rows): row['completion_tokens'] = 228 if index == 2 else 242
    docs['two_decode_diff512']['records'][0]['completion_tokens'] = 512
    docs['two_decode_diff512']['records'][1]['completion_tokens'] = 512
    artifacts = {}
    for name, filename in FILES.items():
        path = root/filename
        m.write_new(path, docs[name])
        path.chmod(0o444)
        artifacts[filename] = {'path': str(path), 'sha256': m.sha(path)}
    p1root = tmp_path/'rounds'/m.R049B_FAILED_RID/'P1'
    p1root.mkdir(parents=True)
    p1docs = copy.deepcopy(docs)
    inventory = {}
    for name, filename in FILES.items():
        path = p1root/filename
        m.write_new(path, p1docs[name]); path.chmod(0o444)
        inventory[f'P1/{filename}'] = m.sha(path)
    p1round = p1root.parent/'round.json'; m.write_new(p1round, {'raw_inventory_before_closure': inventory}); p1round.chmod(0o444)
    review = tmp_path/'retained_review.json'
    m.write_new(review, {'artifacts': artifacts})
    review.chmod(0o444)
    monkeypatch.setattr(m, 'ROUNDS', tmp_path/'rounds')
    monkeypatch.setattr(m, 'RETAINED_L1_REVIEW', review)
    # Separate Linux tests exercise the real metadata admission. This driver
    # still executes all retained raw SHA/mode checks and result computation.
    monkeypatch.setattr(m, 'require_retained_l1_review', lambda: {'sha256': m.sha(review), 'requests': 24})
    monkeypatch.setattr(m, 'require_retained_p1_review', lambda: {'sha256': '1'*64, 'round': str(p1round), 'requests': 24, 'completion_tokens': 6334})
    return m, root, docs, artifacts

def mock_service_boundary(monkeypatch, m, docs):
    started, stopped, references, baselines = [], [], [], []
    monkeypatch.setattr(m, 'load_d07', lambda: SimpleNamespace())
    def build(run, **kwargs):
        path = run/'seed12k_only.strp'
        path.write_text('CPU profile fixture')
        return path, ['build-profile-fixture']
    monkeypatch.setattr(m, 'build_profile', build)
    monkeypatch.setattr(m, 'dynamic_private_port', lambda: 12345)
    def start(d, directory, *args):
        started.append(directory.name)
        return SimpleNamespace(name=directory.name)
    monkeypatch.setattr(m, 'start_service', start)
    monkeypatch.setattr(m, 'stop_service', lambda d, process: stopped.append(process.name))
    monkeypatch.setattr(m, 'compare_actual_configuration', lambda directory, reference: references.append((directory.name, reference)))
    def workloads(directory, port, spec, baseline=None, **kwargs):
        baselines.append((spec['name'], baseline))
        outputs, texts, bindings = {}, {}, {}
        for name, filename in FILES.items():
            doc = copy.deepcopy(docs[name])
            rows = m._workload_rows(doc)
            for row in rows:
                row['decode_tps'] = 10.0 if spec['policy']=='lru' else 12.0
            target = directory/filename
            m.write_new(target, doc)
            binding = rows[0] if name.startswith('cold') else rows
            m._checked_output(directory,name,target,binding,baseline,texts,bindings)
            outputs[name] = target
        return {'d0_enabled': spec['d0'], 'texts': texts, 'request_input_bindings': bindings,
                'timing': m._timing_metrics(outputs), 'generated_tokens': m._output_tokens(outputs)}
    monkeypatch.setattr(m, 'run_workloads', workloads)
    def d0_rows(directory):
        missing = 5 if directory.name=='L_D0' else 3
        return {'sha256': '0'*64, 'worker_birth': {'pid':1234}, 'adapt': [], 'decode': [
            {'rids':list(range(2,14)), 'step':1, 'active':10, 'missing':missing, 'hits':10-missing, 'h2d_bytes':100*missing},
            {'rids':list(range(14,22)), 'step':2, 'active':10, 'missing':missing, 'hits':10-missing, 'h2d_bytes':100*missing}]}
    monkeypatch.setattr(m, '_d0_rows', d0_rows)
    return started, stopped, references, baselines

def test_actual_driver_compares_retained_l1_p1_and_exact_seven_new_services(monkeypatch,tmp_path):
    m, root, docs, artifacts = retained_fixture(monkeypatch,tmp_path)
    started, stopped, refs, baselines = mock_service_boundary(monkeypatch,m,docs)
    result = m.run_measurements(batch=999)
    assert started == stopped == ['PA1','L2','P2','PA2','L_D0','P_D0','PA_D0']
    assert set(result['production']) == {'L1','P1','PA1','L2','P2','PA2'}
    assert set(result['diagnostic_only']) == {'L_D0','P_D0','PA_D0'}
    retained = result['production']['L1']
    assert retained['generated_tokens'] == 6334
    assert all(value is result['production']['L1'] for name,value in baselines if name in ('PA1','L2','P2','PA2'))
    assert all(value is None for name,value in baselines if name.endswith('_D0'))
    assert dict(refs)['L2'] == root
    assert dict(refs)['PA1'] == m.ROUNDS/m.R049B_FAILED_RID/'P1'
    assert result['heldout_benefit']['heldout']['P']['seed_real']['baseline_decode_tps'] == 10.0
    assert all(m.sha(root/name)==metadata['sha256'] for name,metadata in artifacts.items())
    assert not (m.ROUNDS/m.RID/'L1').exists()
    assert json.loads((m.ROUNDS/m.RID/'result.json').read_text())['production']['L1']['outputs']['cold32k_1']==str(root/'cold32k_1.json')

@pytest.mark.parametrize('damage',['missing','wrong_sha'])
def test_bad_retained_raw_is_rejected_before_service_start(monkeypatch,tmp_path,damage):
    m, root, docs, _ = retained_fixture(monkeypatch,tmp_path)
    started, _, _, _ = mock_service_boundary(monkeypatch,m,docs)
    target = root/'cold32k_1.json'
    target.chmod(0o644)
    if damage=='missing':
        target.unlink()
    else:
        target.write_text('{}')
        target.chmod(0o444)
    with pytest.raises(RuntimeError,match='retained raw binding differs'):
        m.run_measurements(batch=999)
    assert started == []

def test_actual_workloads_preserve_retained_cold_input_prefix(monkeypatch,tmp_path):
    m, root, docs, _ = retained_fixture(monkeypatch,tmp_path)
    baseline = m.retained_l1_baseline()
    directory = tmp_path/'new_P1'
    directory.mkdir()
    cold_ids = []
    monkeypatch.setattr(m, 'load_d07',lambda:SimpleNamespace())
    monkeypatch.setattr(m, '_load_tokenizer',lambda path:object())
    monkeypatch.setattr(m, '_load_original',lambda:object())
    def cold(d,tok,folder,base,cold_id,original):
        cold_ids.append(cold_id)
        document = docs[folder.name]
        assert cold_id==document['cold_id']
        target = folder.parent/(folder.name+'.json')
        m.write_new(target,document)
        return target,document['record']
    def replay(port,trace,target,spec,profile):
        role = 'seed_45k' if target.name.startswith('seed_45k') else 'seed_real'
        m.write_new(target,docs[role])
    def two(folder,*args):
        target = folder/'two_decode.json'
        m.write_new(target,docs['two_decode_diff512'])
        return target,docs['two_decode_diff512']['records']
    monkeypatch.setattr(m, '_cold_request',cold)
    monkeypatch.setattr(m, '_timed_agent_replay',replay)
    monkeypatch.setattr(m, '_agent_bindings',lambda tok,trace,target:m._workload_rows(json.loads(target.read_text())))
    monkeypatch.setattr(m, '_run_two_decode_bound',two)
    value = m.run_workloads(directory,12345,{'policy':'profile','d0':False},baseline)
    assert cold_ids==['E2-R049a-cold1','E2-R049a-cold2']
    assert value['texts']==baseline['texts']

