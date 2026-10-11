from __future__ import annotations
import hashlib, importlib.util, json, struct
from pathlib import Path
import pytest

DEV=Path(__file__).parents[1]
def load():
 s=importlib.util.spec_from_file_location('retry_prepare',DEV/'d03_phase2_prepare.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
P=load()
def old_tests():
 s=importlib.util.spec_from_file_location('old_phase2_tests',DEV/'tests'/'test_d03_phase2_prepare.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def dig(x): return hashlib.sha256(struct.pack(f'<{len(x)}i',*x)).hexdigest()
def write(p,x): p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x)+'\n')
def controlled(tmp_path):
 d=tmp_path/'E2-R015';d.mkdir(); prefix=list(range(21976)); suffix=list(range(300,332)); full=prefix+suffix
 source={'schema':'ft_dev_tokens/v1','uid':1,'pid':9008000,'prompt_ids':prefix,'generated_ids':suffix,'prompt_length':len(prefix),'finish_reason':'length','prompt_ids_sha256_int32le':dig(prefix),'generated_ids_sha256_int32le':dig(suffix),'input_ids_sha256_int32le':dig(full)}
 write(d/'terminal_tokens.json',source);write(d/'prompt_ids.json',prefix);write(d/'output_ids_first_k.json',suffix)
 cap={'uid':1,'capture_pid':9008000,'dump_seq':1,'k':32,'input_sha256':dig(full),'input_length':len(full),'positions':list(range(len(prefix),len(full))),'mode':'branch-bank','warm_usage':None,'cached_len':12672,'restore_proof':{'kind':'host','uid':1,'source_slot':1,'destination_slot':2,'length':12672},'priming':{'warm_usage':None,'branch_input_length':12768,'common_prefix_length':12672,'branch_usage':{'kind':'branch'}} ,'branch_usage':{'kind':'branch'}}
 logits=d/'restore/logits';write(logits/'controlled_capture.json',{k:v for k,v in cap.items() if k!='capture_pid'});write(logits/'index.jsonl',{'kind':'logits','uid':1,'seq':1,'extra':{'cached_len':12672,'restore_proof':cap['restore_proof']}})
 branch=prefix[:12672]+[999]*96;branch[12672]=998
 write(logits/'branch_ids.json',{'branch_ids':branch,'common_prefix_length':12672,'branch_token_count':96,'prefix_length':len(prefix),'branch_sha256':dig(branch),'full_input_sha256':dig(full),'full_input_length':len(full),'full_prompt_next_token':prefix[12672],'branch_first_token':998})
 token={**source,'uid':0,'prompt_ids':branch,'generated_ids':[1],'prompt_length':len(branch),'prompt_ids_sha256_int32le':dig(branch),'generated_ids_sha256_int32le':dig([1]),'input_ids_sha256_int32le':dig(branch+[1])};write(logits/'tokens_uid0_pid9008000.json',token)
 return d,cap
def test_controlled_restore_history_accepts_actual_shape(tmp_path):
 d,c=controlled(tmp_path);assert P.validate_controlled_history(d,'restore',c)
@pytest.mark.parametrize('fault',['shortproof','wrongbranch','missingmanifest','indexproof','controlledjson'])
def test_controlled_restore_history_rejects_tampering(tmp_path,fault):
 d,c=controlled(tmp_path);log=d/'restore/logits'
 if fault=='shortproof':c['restore_proof']['length']=1
 elif fault=='wrongbranch': x=json.loads((log/'branch_ids.json').read_text());x['branch_ids'][12672]=list(range(21976))[12672];write(log/'branch_ids.json',x)
 elif fault=='missingmanifest':(log/'branch_ids.json').unlink()
 elif fault=='indexproof':x=json.loads((log/'index.jsonl').read_text());x['extra']['cached_len']=0;write(log/'index.jsonl',x)
 else:write(log/'controlled_capture.json',{'bad':1})
 with pytest.raises(ValueError):P.validate_controlled_history(d,'restore',c)


def rewrite_rid(value, old='E2-R012', new='E2-R016'):
 if isinstance(value,str):return value.replace(old,new)
 if isinstance(value,list):return [rewrite_rid(x,old,new) for x in value]
 if isinstance(value,dict):return {k:rewrite_rid(v,old,new) for k,v in value.items()}
 return value


def r016_fixture(tmp_path):
 old=old_tests();directory,batch=old.t10_phase1_fixture(tmp_path)
 target=directory.parent/'E2-R016';directory.rename(target)
 for path in target.rglob('*.json'):
  value=json.loads(path.read_text());write(path,rewrite_rid(value))
 old.manifest(target)
 return target,batch


def test_r016_full_72_terminal_prepare(tmp_path):
 d,b=r016_fixture(tmp_path);result=P.prepare(d,b,d/f'review_batch{b}.json')
 metadata=json.loads((d/'initial_metadata.json').read_text())
 assert result['rid']=='E2-R016' and metadata['results']['numeric']['terminal_records']==72


def test_r016_wrong_phase_manifest_rid_rejects_without_metadata(tmp_path):
 d,b=r016_fixture(tmp_path);path=d/'phase1_manifest.json';value=json.loads(path.read_text());value['rid']='E2-R012';write(path,value)
 old_tests().manifest(d)
 with pytest.raises(ValueError):P.prepare(d,b,d/f'review_batch{b}.json')
 assert not (d/'initial_metadata.json').exists()


def manifest(directory):
    entries = []
    for path in sorted(p for p in directory.rglob('*')
                       if p.is_file() and p.name != 'RUN_MANIFEST.sha256'):
        entries.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(directory).as_posix()}\n")
    (directory / 'RUN_MANIFEST.sha256').write_text(''.join(entries), encoding='utf-8')


def _token(uid, pid, prompt, generated):
    return {
        'schema': 'ft_dev_tokens/v1', 'uid': uid, 'pid': pid,
        'prompt_ids': prompt, 'generated_ids': generated,
        'prompt_length': len(prompt), 'finish_reason': 'length',
        'prompt_ids_sha256_int32le': dig(prompt),
        'generated_ids_sha256_int32le': dig(generated),
        'input_ids_sha256_int32le': dig(prompt + generated),
    }


def r015_fixture(tmp_path, monkeypatch):
    """Actual R015 producer shape, including all four controlled captures."""
    directory = tmp_path / 'E2-R015'
    directory.mkdir()
    batch = 71
    prefix = list(range(21976))
    generated = list(range(300, 332))
    full = prefix + generated
    full_sha = dig(full)
    source = _token(1, 9_008_000, prefix, generated)
    write(directory / 'terminal_tokens.json', source)
    trace_rows = []
    for index in range(12):
        messages = [{'role': 'user', 'content': f'controlled prompt {index}'}]
        messages_sha = hashlib.sha256(json.dumps(messages, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
        trace_rows.append({'messages': messages, 'record': {'messages_sha': messages_sha}})
    write(directory / 'trace.json', {'rounds': trace_rows})
    binding = {
        'trace_sha256': hashlib.sha256((directory / 'trace.json').read_bytes()).hexdigest(),
        'raw_ids_sha256': source['prompt_ids_sha256_int32le'],
        'input_length': len(prefix), 'messages_sha': trace_rows[0]['record']['messages_sha'],
        'request_sha256': 'a' * 64,
    }
    write(directory / 'raw_binding_manifest.json', binding)
    frozen = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
              for name in ('terminal_tokens.json', 'raw_binding_manifest.json', 'trace.json')}
    monkeypatch.setattr(P, 'T04_CONTROLLED_SOURCE_HASHES', frozen)
    write(directory / 'prompt_ids.json', prefix)
    write(directory / 'output_ids_first_k.json', generated)
    wrapper = b'#!/bin/sh\ntrue\n'
    (directory / 'batch.sh').write_bytes(wrapper)
    wrapper_sha = hashlib.sha256(wrapper).hexdigest()
    write(directory / 'admission.json', {
        'rid': 'E2-R015', 'card': 'T04', 'batch': batch,
        'commit': P.PARENT, 'code_version': 'E2-base@23f2e2c',
        'candidate_commit': P.CANDIDATE, 'batch_wrapper_sha256': wrapper_sha,
        'input': {'k': 32, 'prompt_length': len(prefix), 'full_input_sha256': full_sha,
                  'token_file_sha256': frozen['terminal_tokens.json'],
                  'binding_manifest_sha256': frozen['raw_binding_manifest.json'],
                  'trace_sha256': frozen['trace.json'], 'terminal_uid': source['uid'],
                  'terminal_pid': source['pid']},
        'binding': binding,
    })
    write(directory / f'status_batch{batch}.json', {
        'rid': 'E2-R015', 'batch': batch, 'gate': 'T04',
        'state': 'complete_measurements_pending_review', 'batch_pid': 9_009_999,
        'batch_wrapper_sha256': wrapper_sha,
    })
    write(directory / f'review_batch{batch}.json', {'rid': 'E2-R015', 'batch': batch, 'verdict': 'PASS'})

    captures = {}
    names = ('candidate_boundary', 'restore', 'recompute', 'legal')
    modes = {'candidate_boundary': 'diagnostic', 'restore': 'branch-bank',
             'recompute': 'fresh', 'legal': 'fresh'}
    for number, arm_name in enumerate(names):
        pid = 9_008_100 + number
        arm = directory / arm_name
        arm.mkdir()
        for filename in ('SERVE_CMD.txt', 'serve.log', 'serve_args.txt'):
            (arm / filename).write_text(filename + '\n', encoding='utf-8')
        (arm / 'ENV.txt').write_text(P.CANDIDATE + '\n', encoding='utf-8')
        write(arm / 'owned_process.json', {'pid': pid, 'pgid': pid + 10_000})
        proof = None
        branch_usage = None
        priming = {'warm_usage': None}
        cached_len = 0
        if arm_name == 'restore':
            proof = {'kind': 'host', 'uid': 1, 'source_slot': 1, 'destination_slot': 2, 'length': 12672}
            branch_usage = {'kind': 'branch'}
            priming = {'warm_usage': None, 'branch_input_length': 12768,
                       'common_prefix_length': 12672, 'branch_usage': branch_usage}
            cached_len = 12672
        capture = {
            'uid': 1, 'capture_pid': pid, 'dump_seq': 1, 'k': 32,
            'input_sha256': full_sha, 'input_length': len(full),
            'positions': list(range(len(prefix), len(full))), 'mode': modes[arm_name],
            'warm_usage': None, 'cached_len': cached_len, 'restore_proof': proof,
            'priming': priming, 'branch_usage': branch_usage,
        }
        captures[arm_name] = capture
        write(arm / 'capture.json', capture)
        (arm / 'logits_capture.log').write_text(json.dumps({k: v for k, v in capture.items() if k != 'capture_pid'}) + '\n', encoding='utf-8')
        logits = arm / 'logits'
        logits.mkdir()
        extra = {'input_prefix_sha256': full_sha, 'k': 32, 'input_length': len(full),
                 'positions': capture['positions'], 'cached_len': cached_len,
                 'restore_proof': proof}
        write(logits / 'index.jsonl', {'kind': 'logits', 'uid': 1, 'seq': 1, 'length': len(full), 'extra': extra})
        write(logits / f'tokens_uid1_pid{pid}.json', _token(1, pid, full, [7]))
        write(logits / 'controlled_capture.json', {k: v for k, v in capture.items() if k != 'capture_pid'})
        if arm_name == 'restore':
            branch = prefix[:12672] + [998] + [999] * 95
            write(logits / 'branch_ids.json', {
                'branch_ids': branch, 'common_prefix_length': 12672, 'branch_token_count': 96,
                'prefix_length': len(prefix), 'branch_sha256': dig(branch),
                'full_input_sha256': full_sha, 'full_input_length': len(full),
                'full_prompt_next_token': prefix[12672], 'branch_first_token': branch[12672],
            })
            write(logits / f'tokens_uid0_pid{pid}.json', _token(0, pid, branch, [8]))

    comparison = {'bitwise': True, 'kl': 0.0, 'top1': 1, 'k': 32,
                  'input_prefix_sha256': full_sha, 'input_length': len(full),
                  'positions': list(range(len(prefix), len(full)))}
    (directory / 'logits_compare.json').write_text(json.dumps(comparison) + '\n', encoding='utf-8')
    boundary = directory / 'candidate_boundary' / 'logits' / 'tokens_uid1_pid9008100.json'
    write(directory / 'round_metadata.json', {
        'rid': 'E2-R015', 'status': 'complete_measurements_pending_review',
        'arms': {**captures,
                 'candidate_boundary_regenerated_x': {'matches_supplied': True},
                 'candidate_boundary_terminal': {'path': str(boundary),
                     'sha256': hashlib.sha256(boundary.read_bytes()).hexdigest(), 'uid': 1, 'pid': 9_008_100}},
        'comparison': comparison,
    })
    manifest(directory)
    return directory, batch


def _mutate_r015_capture(directory, arm, mutate):
    metadata = json.loads((directory / 'round_metadata.json').read_text())
    capture = metadata['arms'][arm]
    mutate(capture)
    write(directory / arm / 'capture.json', capture)
    write(directory / arm / 'logits' / 'controlled_capture.json', {k: v for k, v in capture.items() if k != 'capture_pid'})
    (directory / arm / 'logits_capture.log').write_text(json.dumps({k: v for k, v in capture.items() if k != 'capture_pid'}) + '\n')
    index = json.loads((directory / arm / 'logits' / 'index.jsonl').read_text())
    index['extra']['cached_len'] = capture['cached_len']
    index['extra']['restore_proof'] = capture['restore_proof']
    write(directory / arm / 'logits' / 'index.jsonl', index)
    write(directory / 'round_metadata.json', metadata)


def test_r015_full_controlled_measurement_prepares(tmp_path, monkeypatch):
    directory, batch = r015_fixture(tmp_path, monkeypatch)
    result = P.prepare(directory, batch, directory / f'review_batch{batch}.json')
    metadata = json.loads((directory / 'initial_metadata.json').read_text())
    assert result['rid'] == 'E2-R015'
    assert metadata['card'] == 'T04'
    assert metadata['verdict'] == 'pending_review'
    assert metadata['results']['numeric']['comparison.kl'] == 0.0


@pytest.mark.parametrize('fault', ('cache_pollution', 'short_proof', 'branch_raw_input',
                                    'missing_branch_manifest', 'index_proof', 'controlled_json'))
def test_r015_controlled_failures_reject_before_initial_metadata(tmp_path, fault, monkeypatch):
    directory, batch = r015_fixture(tmp_path, monkeypatch)
    restore = directory / 'restore' / 'logits'
    if fault == 'cache_pollution':
        _mutate_r015_capture(directory, 'recompute', lambda c: c.update(cached_len=1))
    elif fault == 'short_proof':
        _mutate_r015_capture(directory, 'restore', lambda c: c['restore_proof'].update(length=1))
    elif fault == 'branch_raw_input':
        branch = json.loads((restore / 'branch_ids.json').read_text())
        branch['branch_ids'][12672] = 12672
        write(restore / 'branch_ids.json', branch)
    elif fault == 'missing_branch_manifest':
        (restore / 'branch_ids.json').unlink()
    elif fault == 'index_proof':
        index = json.loads((restore / 'index.jsonl').read_text())
        index['extra']['cached_len'] = 0
        write(restore / 'index.jsonl', index)
    else:
        write(restore / 'controlled_capture.json', {'forged': True})
    manifest(directory)
    with pytest.raises(ValueError):
        P.prepare(directory, batch, directory / f'review_batch{batch}.json')
    assert not (directory / 'initial_metadata.json').exists()





@pytest.mark.parametrize('field', ('token_file_sha256', 'binding_manifest_sha256', 'trace_sha256',
                                    'terminal_uid', 'terminal_pid'))
def test_r015_admission_source_identity_tamper_rejects(tmp_path, monkeypatch, field):
    directory, batch = r015_fixture(tmp_path, monkeypatch)
    admission = json.loads((directory / 'admission.json').read_text())
    admission['input'][field] = ('0' * 64 if field.endswith('sha256') else admission['input'][field] + 1)
    write(directory / 'admission.json', admission)
    manifest(directory)
    with pytest.raises(ValueError, match='controlled T04 admission'):
        P.prepare(directory, batch, directory / f'review_batch{batch}.json')
    assert not (directory / 'initial_metadata.json').exists()


def test_r015_coherent_replacement_rejects_pinned_frozen_source(tmp_path, monkeypatch):
    directory, batch = r015_fixture(tmp_path, monkeypatch)
    prefix = list(range(1, 21977))
    generated = list(range(400, 432))
    full = prefix + generated
    full_sha = dig(full)
    source = _token(2, 9_008_001, prefix, generated)
    write(directory / 'terminal_tokens.json', source)
    write(directory / 'prompt_ids.json', prefix)
    write(directory / 'output_ids_first_k.json', generated)
    admission = json.loads((directory / 'admission.json').read_text())
    admission['input'].update({
        'full_input_sha256': full_sha, 'prompt_length': len(prefix), 'terminal_uid': source['uid'],
        'terminal_pid': source['pid'], 'token_file_sha256': hashlib.sha256((directory / 'terminal_tokens.json').read_bytes()).hexdigest(),
    })
    binding = admission['binding']
    binding.update({'raw_ids_sha256': source['prompt_ids_sha256_int32le'], 'input_length': len(prefix)})
    write(directory / 'raw_binding_manifest.json', binding)
    admission['input']['binding_manifest_sha256'] = hashlib.sha256((directory / 'raw_binding_manifest.json').read_bytes()).hexdigest()
    write(directory / 'admission.json', admission)
    metadata = json.loads((directory / 'round_metadata.json').read_text())
    for arm_name in ('candidate_boundary', 'restore', 'recompute', 'legal'):
        capture = metadata['arms'][arm_name]
        capture.update({'uid': 2, 'input_sha256': full_sha, 'input_length': len(full),
                        'positions': list(range(len(prefix), len(full)))})
        if capture['restore_proof']:
            capture['restore_proof']['uid'] = 2
        arm = directory / arm_name
        write(arm / 'capture.json', capture)
        write(arm / 'logits' / 'controlled_capture.json', {k: v for k, v in capture.items() if k != 'capture_pid'})
        (arm / 'logits_capture.log').write_text(json.dumps({k: v for k, v in capture.items() if k != 'capture_pid'}) + '\n')
        index = json.loads((arm / 'logits' / 'index.jsonl').read_text())
        index.update({'uid': 2, 'length': len(full)})
        index['extra'].update({'input_prefix_sha256': full_sha, 'input_length': len(full),
                               'positions': capture['positions']})
        write(arm / 'logits' / 'index.jsonl', index)
        old_token = arm / 'logits' / f"tokens_uid1_pid{capture['capture_pid']}.json"
        old_token.unlink()
        write(arm / 'logits' / f"tokens_uid2_pid{capture['capture_pid']}.json", _token(2, capture['capture_pid'], full, [7]))
    metadata['comparison'].update({'input_prefix_sha256': full_sha, 'input_length': len(full),
                                   'positions': list(range(len(prefix), len(full)))})
    write(directory / 'round_metadata.json', metadata)
    (directory / 'logits_compare.json').write_text(json.dumps(metadata['comparison']) + '\n')
    manifest(directory)
    with pytest.raises(ValueError, match='frozen source artifact changed'):
        P.prepare(directory, batch, directory / f'review_batch{batch}.json')
    assert not (directory / 'initial_metadata.json').exists()


@pytest.mark.parametrize('name', ('terminal_tokens.json', 'raw_binding_manifest.json', 'trace.json'))
def test_r015_missing_frozen_source_manifest_entry_rejects(tmp_path, monkeypatch, name):
    directory, batch = r015_fixture(tmp_path, monkeypatch)
    manifest_path = directory / 'RUN_MANIFEST.sha256'
    relative = name
    lines = [line for line in manifest_path.read_text().splitlines() if not line.endswith('  ' + relative)]
    manifest_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    with pytest.raises(ValueError, match='RUN_MANIFEST does not cover consumed artifact'):
        P.prepare(directory, batch, directory / f'review_batch{batch}.json')
    assert not (directory / 'initial_metadata.json').exists()
