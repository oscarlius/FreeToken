"""Archive rebuilt entities and copy the two gate-tested extensions. No GPU work."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path('/data2/FreeToken')
GATE = ROOT / 'wt/e2oom-protocol-restart'
ARCHIVE = ROOT / 'runs/dev_release/binary_alignment_20261009_gate_v1'
EXPECTED = {
    '_cpu_moe.cpython-310-x86_64-linux-gnu.so': '10a2bd8311b9569bd03a6569db59da707699a44e67d7b677c35c3547d77855b4',
    '_pinned_tensor.cpython-310-x86_64-linux-gnu.so': '07701be28030c4ebf63c210804b6eba2556cc0f4d2f1e5ed80b9d423ebfe7e68',
}
REBUILT = {
    '_cpu_moe.cpython-310-x86_64-linux-gnu.so': '0ecb98bbe2e7c765d5edd87cb301e3fd9ee81529d6340c682e545f51666afa4f',
    '_pinned_tensor.cpython-310-x86_64-linux-gnu.so': 'c0a3eb191162979f2bdcdd4b3d27468f1b192c34260f7de0dbf67ab957c864c5',
    '_row_store.cpython-310-x86_64-linux-gnu.so': 'a210059ea92599fddc1a1dec2ac9d160890515e54880798955763d8fba93b1d5',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert not ARCHIVE.exists()
    trees = {'release': (ROOT / 'wt/release-e2', '481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9'),
             'r067_cold': (ROOT / 'wt/d20_short_tail_v1', 'd50be0f8f84ab1105f788be8f1354773ad539b63')}
    kernel = Path('python/freetoken/kernel')
    assert not (GATE / kernel / '_row_store.cpython-310-x86_64-linux-gnu.so').exists()
    for name, digest in EXPECTED.items():
        source = GATE / kernel / name
        assert source.is_file() and not source.is_symlink() and sha(source) == digest
    for mode, (tree, commit) in trees.items():
        assert subprocess.check_output(['git', '-C', str(tree), 'rev-parse', 'HEAD'], text=True).strip() == commit
        assert not subprocess.check_output(['git', '-C', str(tree), 'status', '--porcelain', '--untracked-files=all'], text=True)
        for name, digest in REBUILT.items():
            target = tree / kernel / name
            assert target.is_file() and not target.is_symlink() and sha(target) == digest
    ARCHIVE.mkdir(parents=True)
    result = {'schema': 'ft_gate_binary_alignment/v1', 'gate_worktree': str(GATE),
              'GPU_started': False, 'service_started': False, 'worktrees': {}}
    for mode, (tree, commit) in trees.items():
        before = ARCHIVE / 'before_recompiled' / mode
        before.mkdir(parents=True)
        for name, digest in REBUILT.items():
            shutil.copyfile(tree / kernel / name, before / name)
            assert sha(before / name) == digest
            (before / name).chmod(0o444)
        copied = []
        for name, digest in EXPECTED.items():
            source, target = GATE / kernel / name, tree / kernel / name
            shutil.copyfile(source, target)
            assert target.read_bytes() == source.read_bytes() and sha(target) == digest
            copied.append({'path': (kernel / name).as_posix(), 'sha256': digest,
                           'source': str(source), 'byte_for_byte_equal': True, 'symlink': False})
        removed = tree / kernel / '_row_store.cpython-310-x86_64-linux-gnu.so'
        assert removed.resolve().parent == (tree / kernel).resolve()
        removed.unlink()
        assert not removed.exists()
        assert not subprocess.check_output(['git', '-C', str(tree), 'status', '--porcelain', '--untracked-files=all'], text=True)
        result['worktrees'][mode] = {'path': str(tree), 'commit': commit, 'extensions': copied,
                                    'row_store_absent': True, 'rebuilt_archive': str(before)}
    blob = json.dumps(result, indent=2) + '\n'
    (ARCHIVE / 'alignment_receipt.json').write_text(blob)
    (ARCHIVE / 'alignment_receipt.json').chmod(0o444)
    print(blob)


if __name__ == '__main__':
    main()
