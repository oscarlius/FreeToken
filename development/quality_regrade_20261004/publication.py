"""Recover exact source publications without replacing an unexpected writer's file."""
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ensure_bytes(path, data):
    if path.is_symlink():
        raise ValueError(f'symlink refused: {path}')
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f'prepared artifact changed: {path}')
        return
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def no_replace(source, target):
    libc = ctypes.CDLL(None, use_errno=True)
    fn = libc.renameat2
    fn.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    fn.restype = ctypes.c_int
    if fn(-100, os.fsencode(source), -100, os.fsencode(target), 1):
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(target))
    descriptor = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class Journal:
    def __init__(self, path, identity):
        self.path = path
        if path.exists():
            self.value = json.loads(path.read_bytes())
            if self.value['identity'] != identity:
                raise ValueError('publication journal belongs to different sources')
        else:
            self.value = {'identity': identity, 'events': []}
            self.save()

    def save(self):
        temporary = self.path.with_suffix('.tmp')
        data = (json.dumps(self.value, sort_keys=True, indent=2) + '\n').encode()
        # The caller holds the exact publication lock; a leftover temp is only
        # reusable when its bytes identify the same next journal snapshot.
        ensure_bytes(temporary, data)
        temporary.replace(self.path)
        descriptor = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def note(self, name, **evidence):
        self.value['events'].append({'name': name, **evidence})
        self.save()


def publish(canonical, source, previous_sha, backup, journal, mode):
    """Caller holds flock; NOREPLACE also preserves non-cooperating writers."""
    wanted = digest(source)
    if canonical.is_symlink() or backup.is_symlink():
        raise ValueError('publication symlink refused')
    if canonical.exists() and digest(canonical) == wanted:
        if not backup.exists() or digest(backup) != previous_sha:
            raise ValueError('new source has no identity-bound prior backup')
        journal.note('source_readback', path=str(canonical), sha256=wanted)
        return
    temporary = canonical.with_name(canonical.name + '.E2-R009-regrade.prepared')
    ensure_bytes(temporary, source.read_bytes())
    temporary.chmod(mode)
    if backup.exists():
        if digest(backup) != previous_sha or canonical.exists():
            raise ValueError('unexpected publication state; preserve all files')
    else:
        if not canonical.exists() or canonical.stat().st_uid != os.geteuid() or digest(canonical) != previous_sha:
            raise ValueError('existing canonical differs; preserve it')
        old = canonical.stat()
        journal.note('source_move_intent', path=str(canonical), previous_sha256=previous_sha,
                     device=old.st_dev, inode=old.st_ino, backup=str(backup))
        no_replace(canonical, backup)
        moved = backup.stat()
        if (moved.st_dev, moved.st_ino) != (old.st_dev, old.st_ino) or digest(backup) != previous_sha:
            try:
                no_replace(backup, canonical)
            except OSError as error:
                if error.errno != errno.EEXIST:
                    raise
            raise ValueError('writer raced with source move; its bytes are retained')
    # A concurrent file appearing here makes this fail without replacing it.
    no_replace(temporary, canonical)
    if digest(canonical) != wanted:
        raise ValueError('published source readback differs')
    journal.note('source_readback', path=str(canonical), sha256=wanted)
