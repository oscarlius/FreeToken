import hashlib
from pathlib import Path
import subprocess

import pytest

from worktree_checks import SCHEMA, WorktreeValidationError, validate_worktree


def git(worktree, *args):
    subprocess.run(['git', *args], cwd=worktree, check=True, stdout=subprocess.PIPE)


@pytest.fixture
def worktree(tmp_path):
    git(tmp_path, 'init', '-q')
    git(tmp_path, 'config', 'user.email', 'test@example.invalid')
    git(tmp_path, 'config', 'user.name', 'test')
    (tmp_path / 'tracked.txt').write_text('tracked\n')
    git(tmp_path, 'add', 'tracked.txt')
    git(tmp_path, 'commit', '-qm', 'fixture')
    return tmp_path


def manifest(worktree, extensions=()):
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=worktree, text=True).strip()
    return {'schema': SCHEMA, 'worktrees': {
        'release': {'path': str(worktree), 'commit': commit, 'extensions': list(extensions)},
        'rollback': {'path': str(worktree), 'commit': commit, 'extensions': []}}}, commit


def check(worktree, extensions=()):
    data, commit = manifest(worktree, extensions)
    return validate_worktree(worktree, commit, data, 'release')


def test_allows_nested_caches_and_hashed_extension(worktree):
    extension = worktree / 'python/freetoken/kernel/test.so'
    extension.parent.mkdir(parents=True)
    extension.write_bytes(b'extension')
    cache = worktree / 'python/freetoken/__pycache__/x.pyc'
    cache.parent.mkdir(parents=True)
    cache.write_bytes(b'cache')
    egg = worktree / 'build/pkg.egg-info/PKG-INFO'
    egg.parent.mkdir(parents=True)
    egg.write_text('pkg')
    receipt = check(worktree, [{'path': 'python/freetoken/kernel/test.so',
        'sha256': hashlib.sha256(b'extension').hexdigest()}])
    assert receipt['ok'] and receipt['extensions'][0]['path'].endswith('test.so')
    assert sorted(receipt['allowed_cache_paths']) == sorted([
        'build/pkg.egg-info/PKG-INFO', 'python/freetoken/__pycache__/x.pyc'])


@pytest.mark.parametrize('mutator,extensions,match', [
    (lambda root: (root / 'new.txt').write_text('no'), (), 'unapproved'),
    (lambda root: (root / 'tracked.txt').write_text('changed'), (), 'tracked'),
    (lambda root: (root / 'test.so').write_bytes(b'bad'), [{'path': 'test.so', 'sha256': '0' * 64}], 'hash'),
])
def test_rejects_unapproved_tracked_and_wrong_hash(worktree, mutator, extensions, match):
    mutator(worktree)
    with pytest.raises(WorktreeValidationError, match=match):
        check(worktree, extensions)


def test_rejects_path_escape_duplicate_and_header_commit(worktree):
    data, commit = manifest(worktree, [{'path': '../x.so', 'sha256': '0' * 64}])
    with pytest.raises(WorktreeValidationError, match='traversal'):
        validate_worktree(worktree, commit, data, 'release')
    data, commit = manifest(worktree, [])
    data['worktrees']['release']['commit'] = '0' * 40
    with pytest.raises(WorktreeValidationError, match='path/commit'):
        validate_worktree(worktree, commit, data, 'release')
    extension = {'path': 'same.so', 'sha256': '0' * 64}
    data, commit = manifest(worktree, [extension, dict(extension)])
    with pytest.raises(WorktreeValidationError, match='duplicate'):
        validate_worktree(worktree, commit, data, 'release')


def test_requires_common_release_and_rollback_manifest_entries(worktree):
    data, commit = manifest(worktree)
    del data['worktrees']['rollback']
    with pytest.raises(WorktreeValidationError, match='worktrees'):
        validate_worktree(worktree, commit, data, 'release')


def test_rejects_symlinked_cache_without_symlink_privilege(worktree, monkeypatch):
    cache = worktree / '__pycache__/x.pyc'
    cache.parent.mkdir()
    cache.write_bytes(b'cache')
    original = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda path: path == cache or original(path))
    with pytest.raises(WorktreeValidationError, match='symlink'):
        check(worktree)


def test_rejects_unlisted_extension_inside_cache(worktree):
    extension = worktree / '__pycache__/hidden.so'
    extension.parent.mkdir()
    extension.write_bytes(b'extension')
    with pytest.raises(WorktreeValidationError, match='compiled extension'):
        check(worktree)
