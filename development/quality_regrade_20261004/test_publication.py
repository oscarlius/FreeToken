import hashlib
import sys
from pathlib import Path

import pytest
import publication

pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='Linux renameat2 publication contract')


def setup(tmp_path):
    old, new, backup = (tmp_path / name for name in ('canonical.py', 'new.py', 'previous.py'))
    old.write_bytes(b'old');new.write_bytes(b'new')
    journal = publication.Journal(tmp_path / 'journal.json', {'sources': 'test'})
    return old, new, backup, journal


def publish(parts):
    old, new, backup, journal = parts
    publication.publish(old, new, hashlib.sha256(b'old').hexdigest(), backup, journal, 0o444)


def test_publish_and_retry_readback(tmp_path):
    parts = setup(tmp_path);publish(parts);publish(parts)
    assert parts[0].read_bytes() == b'new'
    assert parts[2].read_bytes() == b'old'


def test_resume_after_old_source_move(tmp_path):
    parts = setup(tmp_path);publication.no_replace(parts[0], parts[2]);publish(parts)
    assert parts[0].read_bytes() == b'new'


def test_unexpected_current_source_is_preserved(tmp_path):
    parts = setup(tmp_path);parts[0].write_bytes(b'other writer')
    with pytest.raises(ValueError):publish(parts)
    assert parts[0].read_bytes() == b'other writer'
    assert not parts[2].exists()


def test_concurrent_new_file_is_never_replaced(tmp_path, monkeypatch):
    parts = setup(tmp_path);real = publication.no_replace
    def race(source, target):
        if str(source).endswith('.prepared'):
            parts[0].write_bytes(b'concurrent')
        real(source, target)
    monkeypatch.setattr(publication, 'no_replace', race)
    with pytest.raises(FileExistsError):publish(parts)
    assert parts[0].read_bytes() == b'concurrent'
    assert parts[2].read_bytes() == b'old'


def test_writer_racing_before_move_is_restored(tmp_path, monkeypatch):
    parts = setup(tmp_path);real = publication.no_replace
    def race(source, target):
        if source == parts[0]:parts[0].write_bytes(b'concurrent')
        real(source, target)
    monkeypatch.setattr(publication, 'no_replace', race)
    with pytest.raises(ValueError):publish(parts)
    assert parts[0].read_bytes() == b'concurrent'


def test_identity_mismatch_refuses_journal_reuse(tmp_path):
    setup(tmp_path)
    with pytest.raises(ValueError):
        publication.Journal(tmp_path / 'journal.json', {'sources': 'different'})


def test_prepared_artifact_retry_requires_exact_bytes(tmp_path):
    path = tmp_path / 'artifact'
    publication.ensure_bytes(path, b'exact');publication.ensure_bytes(path, b'exact')
    with pytest.raises(ValueError):publication.ensure_bytes(path, b'changed')
    assert path.read_bytes() == b'exact'


def test_no_replace_preserves_existing_destination(tmp_path):
    parts = setup(tmp_path)
    with pytest.raises(FileExistsError):publication.no_replace(parts[1], parts[0])
    assert parts[0].read_bytes() == b'old'
    assert parts[1].read_bytes() == b'new'
