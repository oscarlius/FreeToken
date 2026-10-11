import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest
import copy
import json
import hashlib

ROOT = Path(__file__).parents[1]
CASES = {
    'D15': ('t16_r050_d15_candidate.py', 'E2-R050-gate-D15', '988c9e183c8dca4415fd9b5d02318b26664da619'),
    'D08': ('t16_r051_d08_candidate.py', 'E2-R051-gate-D08', '8bf0ad396f5d3104d9b4385fc6a3962c2c81dfd8'),
}

@pytest.mark.parametrize('card', CASES)
def test_private_clients_bind_original_probe_despite_shared_probe_drift(card, tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('helpers_' + card, ROOT / CASES[card][0])
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    # A later shared probe cannot enter either the preflight or private client.
    (tmp_path / 'probe_ft_cold32k.py').write_text('later D18 probe')
    monkeypatch.setitem(module.base, 'ROOT', tmp_path)
    helpers = ROOT / 't16_frozen_helpers_v1'
    assert module.base['SCR'] == helpers
    assert {name: hashlib.md5((helpers / name).read_bytes()).hexdigest()
            for name in module.base['TOOL_MD5']} == module.base['TOOL_MD5']
    runner = module.base['Runner'].__new__(module.base['Runner']); runner.port = 49123
    code = runner.private_probe_bootstrap('cold_eq.py')
    assert repr(str(helpers / 'probe_ft_cold32k.py')) in code
    assert repr(str(helpers / 'cold_eq.py')) in code
    assert repr(str(tmp_path / 'probe_ft_cold32k.py')) not in code
    assert '127.0.0.1:49123' in code

@pytest.mark.parametrize('card', CASES)
def test_bindings(card):
    name, rid, commit = CASES[card]
    spec=importlib.util.spec_from_file_location('adapter_'+card, ROOT/name)
    module=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(module)
    case=module.CASES[card]
    assert case['parent_wt']=='e2base1-p1'
    assert case['parent_commit']=='effb9969706922ddad9e59b96377e46469ebe97f'
    assert case['new_commit']==commit
    assert module.validate_identity(SimpleNamespace(case=card,rid=rid,batch=72,candidate_commit=commit))==case

@pytest.mark.parametrize('card', CASES)
def test_rejects_wrong_identity(card):
    name,rid,commit=CASES[card]
    spec=importlib.util.spec_from_file_location('bad_'+card, ROOT/name)
    module=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(module)
    with pytest.raises(ValueError):
        module.validate_identity(SimpleNamespace(case=card,rid='E2-R999-gate-'+card,batch=72,candidate_commit=commit))
    with pytest.raises(ValueError):
        module.validate_identity(SimpleNamespace(case=card,rid=rid,batch=72,candidate_commit='0'*40))


@pytest.mark.parametrize('drift', [None, 'path', 'sha', 'missing', 'extra', 'symlink', 'size', 'origin'])
def test_d08_import_manifest_accepts_expected_differences_and_rejects_drift(tmp_path, drift):
    spec = importlib.util.spec_from_file_location('manifest_d08', ROOT / CASES['D08'][0])
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    parent, new = tmp_path / 'parent', tmp_path / 'new'
    records = {}
    for role, wt in [('parent', parent), ('new', new)]:
        records[role] = {}
        for name, sha in module.EXTENSION_SHA256[role].items():
            path = wt / 'python/freetoken/kernel' / (name + '.cpython-310-x86_64-linux-gnu.so')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'fixture')
            records[role][name] = {'path': str(path), 'sha256': sha, 'size': module.EXTENSION_SIZE[role][name]}
    assert records['parent']['_cpu_moe']['sha256'] != records['new']['_cpu_moe']['sha256']
    module.validate_extensions(records, parent, new)
    bad = copy.deepcopy(records)
    if drift is None:
        return
    if drift == 'path': bad['new']['_cpu_moe']['path'] = records['parent']['_cpu_moe']['path']
    elif drift == 'sha': bad['new']['_cpu_moe']['sha256'] = '0' * 64
    elif drift == 'missing': del bad['new']['_pinned_tensor']
    elif drift == 'extra': bad['new']['unexpected'] = {}
    elif drift == 'size': bad['new']['_cpu_moe']['size'] += 1
    elif drift == 'origin':
        path = Path(bad['parent']['_cpu_moe']['path']); path.unlink()
        try: path.symlink_to(new / 'python/freetoken/kernel' / path.name)
        except OSError:
            if __import__('sys').platform == 'win32': pytest.skip('requires Linux symlink validation')
            raise
    elif drift == 'symlink':
        path = Path(bad['new']['_cpu_moe']['path']); path.unlink()
        try: path.symlink_to(Path(records['parent']['_cpu_moe']['path']))
        except OSError: pytest.skip('symlinks unavailable on this test host')
    with pytest.raises(ValueError, match='compiled extension'):
        module.validate_extensions(bad, parent, new)


def candidate_provenance_fixture(module, tmp_path, monkeypatch):
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    source = tmp_path / 'wt/e2d08/python/freetoken/kernel/csrc/cpu_moe/cpu_moe_ext.cpp'
    source.parent.mkdir(parents=True); source.write_bytes(b'native CPU source fixture')
    path = tmp_path / 'candidate_native.json'
    value = {'schema': 'ft_d08_native_cpu_provenance/v5', 'candidate_commit': module.CASES['D08']['new_commit'],
             'parent_commit': module.CASES['D08']['parent_commit'], 'so_sha256': module.EXTENSION_SHA256['new']['_cpu_moe'],
             'so_size': module.EXTENSION_SIZE['new']['_cpu_moe'], 'pinned_sha256': module.EXTENSION_SHA256['new']['_pinned_tensor'],
             'pytest': '11 passed', 'skip': 0, 'csrc_sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
    path.write_bytes(json.dumps(value).encode()); path.chmod(0o444)
    monkeypatch.setattr(module, 'CANDIDATE_NATIVE_PROVENANCE', path)
    monkeypatch.setattr(module, 'CANDIDATE_NATIVE_PROVENANCE_SHA256', hashlib.sha256(path.read_bytes()).hexdigest())
    return path, source, value


@pytest.mark.parametrize('drift', [None, 'missing', 'tampered', 'writable', 'symlink', 'commit'])
def test_d08_native_provenance_is_enforced_before_launch(tmp_path, monkeypatch, drift):
    spec = importlib.util.spec_from_file_location('provenance_d08', ROOT / CASES['D08'][0])
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    candidate, _, _ = candidate_provenance_fixture(module, tmp_path, monkeypatch)
    path = tmp_path / 'provenance.json'
    value = {'schema': 'ft_r051_parent_native_provenance/v1',
             'business_python_parent': {'commit': module.CASES['D08']['parent_commit']},
             'native_artifact_origin': {'commit': module.PARENT_NATIVE_COMMIT}}
    if drift == 'commit': value['native_artifact_origin']['commit'] = '0' * 40
    payload = json.dumps(value).encode(); path.write_bytes(payload)
    monkeypatch.setattr(module, 'PARENT_NATIVE_PROVENANCE', path)
    monkeypatch.setattr(module, 'PARENT_NATIVE_PROVENANCE_SHA256', hashlib.sha256(payload).hexdigest())
    if drift == 'missing': path.unlink()
    elif drift == 'tampered': path.write_bytes(payload + b' ')
    elif drift == 'symlink':
        target = tmp_path / 'other.json'; target.write_bytes(payload); path.unlink()
        try: path.symlink_to(target)
        except OSError: pytest.skip('symlinks unavailable on this test host')
    if path.exists() and drift != 'writable': path.chmod(0o444)
    try:
        if drift is None: assert module.require_native_provenance() == path
        else:
            with pytest.raises(ValueError, match='native provenance'):
                module.require_native_provenance()
    finally:
        if path.exists(): path.chmod(0o644)
        candidate.chmod(0o644)


@pytest.mark.parametrize('drift', ['candidate_commit', 'parent_commit', 'so_sha256', 'so_size', 'pinned_sha256', 'pytest', 'skip', 'source'])
def test_new_d08_native_cpu_binding_rejects_drift(tmp_path, monkeypatch, drift):
    spec = importlib.util.spec_from_file_location('new_native_d08', ROOT / CASES['D08'][0])
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    candidate, source, value = candidate_provenance_fixture(module, tmp_path, monkeypatch)
    parent = tmp_path / 'parent_native.json'
    parent.write_bytes(json.dumps({'schema': 'ft_r051_parent_native_provenance/v1',
        'business_python_parent': {'commit': module.CASES['D08']['parent_commit']},
        'native_artifact_origin': {'commit': module.PARENT_NATIVE_COMMIT}}).encode())
    parent.chmod(0o444)
    monkeypatch.setattr(module, 'PARENT_NATIVE_PROVENANCE', parent)
    monkeypatch.setattr(module, 'PARENT_NATIVE_PROVENANCE_SHA256', hashlib.sha256(parent.read_bytes()).hexdigest())
    if drift == 'source': source.write_bytes(b'changed C++ source')
    else:
        value[drift] = 1 if isinstance(value[drift], int) else 'wrong'
        candidate.chmod(0o644); candidate.write_bytes(json.dumps(value).encode()); candidate.chmod(0o444)
        monkeypatch.setattr(module, 'CANDIDATE_NATIVE_PROVENANCE_SHA256', hashlib.sha256(candidate.read_bytes()).hexdigest())
    try:
        with pytest.raises(ValueError, match='candidate native provenance'):
            module.require_native_provenance()
    finally:
        candidate.chmod(0o644); parent.chmod(0o644)
