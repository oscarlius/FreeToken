from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

DEV = Path(__file__).parents[1]


def load(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


P = load(DEV / 'd03_phase2_prepare_r017.py')


def old():
    return load(DEV / 'tests' / 'test_d03_phase2_prepare.py')


def write(path, value):
    path.write_text(json.dumps(value) + '\n', encoding='utf-8')


def manifest(directory):
    entries = []
    for path in sorted(p for p in directory.rglob('*') if p.is_file() and p.name != 'RUN_MANIFEST.sha256'):
        entries.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(directory).as_posix()}\n")
    (directory / 'RUN_MANIFEST.sha256').write_text(''.join(entries), encoding='utf-8')


def rewrite(value, source='E2-R012', destination='E2-R017'):
    if isinstance(value, str): return value.replace(source, destination)
    if isinstance(value, list): return [rewrite(item, source, destination) for item in value]
    if isinstance(value, dict): return {key: rewrite(item, source, destination) for key, item in value.items()}
    return value


def r017_fixture(tmp_path):
    """Convert the reviewed 72-token producer fixture into R017 raw replay evidence."""
    source, batch = old().t10_phase1_fixture(tmp_path)
    directory = source.with_name('E2-R017')
    source.rename(directory)
    for path in directory.rglob('*.json'):
        write(path, rewrite(json.loads(path.read_text())))
    phase = json.loads((directory / 'phase1_manifest.json').read_text())
    frontend = {row['messages_sha']: row for row in json.loads((directory / 'frontend_manifest.json').read_text())['rounds']}
    for arm_name, phases in phase['arms'].items():
        arm = directory / arm_name
        for phase_name, rows in phases.items():
            replay = []
            for index, (key, record) in enumerate(sorted(rows.items())):
                tool = index < 6
                http_reason, engine_reason = ('tool_calls', 'stop') if tool else ('length', 'length')
                token = arm / 'logits' / record['terminal_file']
                token_data = json.loads(token.read_text())
                token_data['finish_reason'] = engine_reason
                write(token, token_data)
                record.update({'terminal_sha256': hashlib.sha256(token.read_bytes()).hexdigest(),
                               'http_finish_reason': http_reason, 'engine_finish_reason': engine_reason})
                replay.append({'round': record['round'], 'messages_sha': key, 'error': None, 'dry_run': False,
                               'finish_reason': http_reason, 'tool_calls': ['read_file'] if tool else [],
                               'completion_tokens': len(token_data['generated_ids']),
                               'prompt_tokens': frontend[key]['prompt_length']})
            filename = 'reverse_cold.json' if phase_name == 'cold' else 'forward_warm.json'
            write(arm / filename, {'meta': {'params': {'max_tokens': 200}}, 'rounds': replay})
    write(directory / 'phase1_manifest.json', phase)
    manifest(directory)
    return directory, batch


def reject(directory, batch):
    with pytest.raises(ValueError):
        P.prepare(directory, batch, directory / f'review_batch{batch}.json')
    assert not (directory / 'initial_metadata.json').exists()


def test_r017_prepares_complete_72_record_http_bridge(tmp_path):
    directory, batch = r017_fixture(tmp_path)
    result = P.prepare(directory, batch, directory / f'review_batch{batch}.json')
    metadata = json.loads((directory / 'initial_metadata.json').read_text())
    assert result['rid'] == 'E2-R017'
    assert metadata['results']['numeric']['terminal_records'] == 72


@pytest.mark.parametrize('fault', ('error', 'forged_http', 'forged_engine', 'empty_tools', 'unknown_reason',
                                    'dry', 'count_over_cap', 'duplicate_key', 'omit_raw_manifest'))
def test_r017_raw_bridge_rejects_before_metadata(tmp_path, fault):
    directory, batch = r017_fixture(tmp_path)
    phase = json.loads((directory / 'phase1_manifest.json').read_text())
    arm, phase_name = 'B1', 'cold'
    raw_path = directory / arm / 'reverse_cold.json'
    raw = json.loads(raw_path.read_text())
    key = raw['rounds'][0]['messages_sha']
    record = phase['arms'][arm][phase_name][key]
    token_path = directory / arm / 'logits' / record['terminal_file']
    if fault == 'error': raw['rounds'][0]['error'] = 'HTTP 500'
    elif fault == 'forged_http': record['http_finish_reason'] = 'length'
    elif fault == 'forged_engine':
        record['engine_finish_reason'] = 'length'
        token = json.loads(token_path.read_text()); token['finish_reason'] = 'length'; write(token_path, token)
        record['terminal_sha256'] = hashlib.sha256(token_path.read_bytes()).hexdigest()
    elif fault == 'empty_tools': raw['rounds'][0]['tool_calls'] = []
    elif fault == 'unknown_reason': raw['rounds'][0]['finish_reason'] = 'other'
    elif fault == 'dry': raw['rounds'][0]['dry_run'] = True
    elif fault == 'count_over_cap': raw['rounds'][0]['completion_tokens'] = 201
    elif fault == 'duplicate_key': raw['rounds'][1]['messages_sha'] = key
    else:
        manifest_path = directory / 'RUN_MANIFEST.sha256'
        manifest_path.write_text('\n'.join(line for line in manifest_path.read_text().splitlines()
                                             if not line.endswith('B1/reverse_cold.json')) + '\n')
        reject(directory, batch); return
    write(raw_path, raw)
    write(directory / 'phase1_manifest.json', phase)
    manifest(directory)
    reject(directory, batch)


def seal_r017(directory):
    import sys
    scripts = DEV.parent / 'scripts'
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import round_close, round_json_append
    writer = scripts / 'round_json_append.py'
    (directory / 'round_json_append.py').write_bytes(writer.read_bytes())
    document = {
        'schema': 'ft_round/v2', 'round_id': 'E2-R017', 'epoch': 2, 'card': 'T10',
        'verdict': 'pending_review', 'proposed_verdict': None, 'verdict_history': [], 'retractions': [],
        'base': {'commit': P.PARENT, 'code_version': 'E2-base@23f2e2c'},
        'serve': {'arms': {name: {} for name in ('B1', 'B2', 'B3')}}, 'results': {'records': 72},
        'sub_conclusions': [{'id': 'SC1', 'text': 'R017 phase one', 'status': 'pending'}],
    }
    (directory / 'round.json').write_bytes(round_json_append.json_bytes(document))
    round_close.close(directory)


def test_r013_accepts_actual_sealed_r017_parent(tmp_path):
    parent, parent_batch = r017_fixture(tmp_path)
    seal_r017(parent)
    # Reuse the reviewed independent R013 producer shape, but bind its copied
    # proof and admission to the sealed R017 parent rather than a legacy parent.
    legacy_root = tmp_path / 'legacy'; legacy_root.mkdir()
    _, _ = old().t10_phase2_fixture(legacy_root)
    child = legacy_root / 'E2-R013'
    destination = tmp_path / 'E2-R013'
    child.rename(destination)
    for filename in ('phase1_manifest.json', 'round.json'):
        source = parent / filename
        target = destination / ('phase1_round_proof.json' if filename == 'round.json' else filename)
        target.write_bytes(source.read_bytes())
    admission = json.loads((destination / 'admission.json').read_text())
    admission.update({'parent_rid': 'E2-R017',
                      'phase1_manifest_sha256': hashlib.sha256((destination / 'phase1_manifest.json').read_bytes()).hexdigest(),
                      'phase1_round_proof_sha256': hashlib.sha256((destination / 'phase1_round_proof.json').read_bytes()).hexdigest()})
    write(destination / 'admission.json', admission)
    manifest(destination)
    result = P.prepare(destination, 62, destination / 'review_batch62.json')
    assert result['rid'] == 'E2-R013'


def test_r017_raw_replay_rejects_non_dict_row(tmp_path):
    directory, batch = r017_fixture(tmp_path)
    raw_path = directory / 'B1' / 'reverse_cold.json'
    raw = json.loads(raw_path.read_text()); raw['rounds'][0] = None; write(raw_path, raw)
    manifest(directory)
    reject(directory, batch)
