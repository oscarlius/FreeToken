"""Read-only admission checks for the release and rollback worktrees."""
import hashlib
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess


SCHEMA = 'ft_release_binary_manifest/v1'
_CACHE_NAMES = {'__pycache__', '.pytest_cache'}


class WorktreeValidationError(RuntimeError):
    """A failed admission check with the complete inspection receipt."""

    def __init__(self, message, receipt):
        super().__init__(message)
        self.receipt = receipt


def _command(worktree, *args):
    output = subprocess.check_output(['git', '-C', str(worktree), *args])
    return output.decode('utf-8', 'surrogateescape') if isinstance(output, bytes) else output


def _paths(worktree, *args):
    output = _command(worktree, *args)
    return [item for item in output.split('\0') if item]


def _fail(receipt, reason):
    receipt['ok'] = False
    receipt['violations'].append(reason)
    raise WorktreeValidationError(reason, receipt)


def _relative_path(value):
    if not isinstance(value, str) or not value:
        raise ValueError('extension path must be a nonempty string')
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ('', '.', '..') for part in path.parts):
        raise ValueError('extension path must be a relative path without traversal')
    return path


def _under_worktree(worktree, relative):
    candidate = worktree.joinpath(*relative.parts)
    try:
        candidate.resolve(strict=False).relative_to(worktree.resolve(strict=True))
    except ValueError as exc:
        raise ValueError('path escapes worktree: ' + relative.as_posix()) from exc
    return candidate


def _ordinary_path(worktree, relative):
    """Reject symlink components so allowlisted files cannot leave the worktree."""
    candidate = worktree
    for part in relative.parts:
        candidate /= part
        if candidate.is_symlink():
            raise ValueError('symlink is not permitted: ' + relative.as_posix())
        try:
            mode = candidate.lstat().st_mode
        except FileNotFoundError as exc:
            raise ValueError('listed path is absent: ' + relative.as_posix()) from exc
    return candidate


def _is_allowed_cache(relative):
    return any(part in _CACHE_NAMES or part.endswith('.egg-info') for part in relative.parts)


def _manifest_entry(manifest, mode, worktree, expected_commit):
    if not isinstance(manifest, dict) or manifest.get('schema') != SCHEMA:
        raise ValueError('binary manifest schema differs')
    entries = manifest.get('worktrees')
    if (not isinstance(entries, dict) or not {'release', 'rollback'} <= set(entries)
            or set(entries) - {'release', 'rollback', 'r067_cold'}):
        raise ValueError('binary manifest worktrees are invalid')
    for name, candidate in entries.items():
        if not isinstance(candidate, dict) or set(candidate) != {'path', 'commit', 'extensions'}:
            raise ValueError('binary manifest entry differs for ' + name)
        if (not isinstance(candidate['path'], str) or not isinstance(candidate['commit'], str)
                or not isinstance(candidate['extensions'], list)):
            raise ValueError('binary manifest entry types differ for ' + name)
    entry = entries.get(mode)
    if not isinstance(entry, dict):
        raise ValueError('binary manifest entry differs for ' + mode)
    if entry['path'] != str(worktree) or entry['commit'] != expected_commit:
        raise ValueError('binary manifest path/commit differs for ' + mode)
    return entry


def validate_worktree(worktree, expected_commit, manifest, mode):
    """Validate one worktree without changing its files or Git metadata.

    The returned receipt is suitable for inclusion in a deployment ownership record.
    """
    worktree = Path(worktree)
    receipt = {
        'schema': 'ft_release_worktree_receipt/v1', 'mode': mode,
        'worktree': str(worktree), 'expected_commit': expected_commit,
        'manifest_schema': manifest.get('schema') if isinstance(manifest, dict) else None,
        'actual_head': None, 'tracked_status': [], 'tracked_files': [], 'untracked': [], 'ignored': [],
        'allowed_cache_paths': [], 'extensions': [], 'violations': [], 'ok': False,
    }
    try:
        entry = _manifest_entry(manifest, mode, worktree, expected_commit)
        if worktree.is_symlink() or not worktree.is_dir():
            raise ValueError('worktree must be an ordinary directory')
        receipt['actual_head'] = _command(worktree, 'rev-parse', 'HEAD').strip()
        if receipt['actual_head'] != expected_commit:
            _fail(receipt, 'worktree HEAD differs from expected commit')
        tracked = _command(worktree, 'status', '--porcelain', '--untracked-files=no')
        receipt['tracked_status'] = [line for line in tracked.splitlines() if line]
        if receipt['tracked_status']:
            _fail(receipt, 'tracked worktree changes are not permitted')

        untracked = _paths(worktree, 'ls-files', '--others', '--exclude-standard', '-z')
        ignored = _paths(worktree, 'ls-files', '--others', '--ignored', '--exclude-standard', '-z')
        tracked_files = _paths(worktree, 'ls-files', '-z')
        receipt['untracked'], receipt['ignored'], receipt['tracked_files'] = untracked, ignored, tracked_files
        extension_by_path = {}
        for item in entry['extensions']:
            if not isinstance(item, dict) or set(item) != {'path', 'sha256'}:
                raise ValueError('extension entry must contain only path and sha256')
            relative = _relative_path(item['path'])
            if not relative.name.endswith('.so') or not isinstance(item['sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', item['sha256']):
                raise ValueError('extension entry is not a hashed .so file')
            if relative.as_posix() in extension_by_path:
                raise ValueError('duplicate extension path')
            extension_by_path[relative.as_posix()] = item['sha256']

        listed_files = sorted(set(untracked + ignored + [
            path for path in tracked_files if path.endswith('.so')]))
        for listed in listed_files:
            relative = _relative_path(listed)
            _under_worktree(worktree, relative)
            if relative.as_posix() in extension_by_path:
                candidate = _ordinary_path(worktree, relative)
                if not stat.S_ISREG(candidate.lstat().st_mode):
                    _fail(receipt, 'extension is not a regular file: ' + listed)
                digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
                receipt['extensions'].append({'path': listed, 'sha256': digest})
                if digest != extension_by_path[listed]:
                    _fail(receipt, 'extension hash differs: ' + listed)
            elif relative.name.endswith('.so'):
                _fail(receipt, 'unapproved compiled extension: ' + listed)
            elif _is_allowed_cache(relative):
                candidate = _ordinary_path(worktree, relative)
                if not stat.S_ISREG(candidate.lstat().st_mode):
                    _fail(receipt, 'cache entry is not a regular file: ' + listed)
                receipt['allowed_cache_paths'].append(listed)
            else:
                _fail(receipt, 'unapproved untracked or ignored file: ' + listed)

        # A manifest extension must exist even if Git did not report it as ignored.
        for listed, wanted_hash in extension_by_path.items():
            if any(row['path'] == listed for row in receipt['extensions']):
                continue
            relative = _relative_path(listed)
            candidate = _ordinary_path(worktree, relative)
            if not stat.S_ISREG(candidate.lstat().st_mode):
                _fail(receipt, 'extension is not a regular file: ' + listed)
            digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
            receipt['extensions'].append({'path': listed, 'sha256': digest})
            if digest != wanted_hash:
                _fail(receipt, 'extension hash differs: ' + listed)
        receipt['ok'] = True
        return receipt
    except WorktreeValidationError:
        raise
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        _fail(receipt, type(exc).__name__ + ': ' + str(exc))
