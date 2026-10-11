import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import pytest


SOURCE = Path(__file__).parents[1] / 't17_r027_d04_close.py'
SPEC = importlib.util.spec_from_file_location('t17_r027_d04_close', SOURCE)
CLOSE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLOSE)
DEVELOPMENT = SOURCE.parent
REPORT_NAME = 't17_prefix_numeric_E2-R027-diagnostic-T17_reader_v3.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(tmp_path, monkeypatch):
    closure = tmp_path / 'closure'; closure.mkdir(parents=True)
    monkeypatch.setattr(CLOSE, 'HERE', closure)
    for name in ('t17_prefix_numeric_read.py', 't17_r027_independent_cpu_review.py'):
        shutil.copy2(DEVELOPMENT / name, closure / name)
    module = importlib.util.spec_from_file_location('reader_fixture', closure / 't17_prefix_numeric_read.py')
    reader = importlib.util.module_from_spec(module); module.loader.exec_module(reader)
    raw = tmp_path / 'round'; raw.mkdir()
    report = json.loads((DEVELOPMENT / REPORT_NAME).read_text())
    for name, item in report['raw_tensors'].items():
        path = raw / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'x')
        item['sha256'] = sha(path)
    report['reader_source_sha256'] = sha(closure / 't17_prefix_numeric_read.py')
    report['companion_source_sha256'] = sha(closure / 't17_r027_independent_cpu_review.py')
    (closure / REPORT_NAME).write_text(json.dumps(report))
    return raw, report, reader


def test_v2_reader_requires_exact_42_tensor_inventory(tmp_path, monkeypatch):
    raw, report, reader = fixture(tmp_path, monkeypatch)
    observed, binding = CLOSE.load_review(raw, CLOSE.raw_files(raw))
    assert set(observed['raw_tensors']) == set(reader.EXPECTED_TENSORS)
    assert len(observed['raw_tensors']) == 42
    assert binding['reader_output_sha256'] == sha(CLOSE.HERE / REPORT_NAME)

    report['raw_tensors']['unexpected.pt'] = next(iter(report['raw_tensors'].values()))
    (CLOSE.HERE / REPORT_NAME).write_text(json.dumps(report))
    with pytest.raises(ValueError, match='raw tensor inventory'):
        CLOSE.load_review(raw, CLOSE.raw_files(raw))


def test_v2_reader_rejects_unlisted_and_tampered_raw_bytes(tmp_path, monkeypatch):
    raw, report, _ = fixture(tmp_path, monkeypatch)
    missing = next(iter(report['raw_tensors']))
    del report['raw_tensors'][missing]
    (CLOSE.HERE / REPORT_NAME).write_text(json.dumps(report))
    with pytest.raises(ValueError, match='raw tensor inventory'):
        CLOSE.load_review(raw, CLOSE.raw_files(raw))

    raw, report, _ = fixture(tmp_path / 'fresh', monkeypatch)
    target = next(iter(report['raw_tensors']))
    (raw / target).write_bytes(b'tampered')
    with pytest.raises(ValueError, match='raw tensor bytes differ'):
        CLOSE.load_review(raw, CLOSE.raw_files(raw))
