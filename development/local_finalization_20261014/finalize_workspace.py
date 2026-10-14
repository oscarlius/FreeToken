"""Bounded local finalization evidence; no service, GPU, push, or broad prune."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
from datetime import datetime

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ARCHIVE = ROOT / "archive" / "local_finalization_20261014"
EPHEMERAL = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}


def git(repo: Path, *args: str, binary: bool = False):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if result.returncode:
        raise RuntimeError(f"git {args}: {result.stderr.decode('utf-8', 'replace')}")
    return result.stdout if binary else result.stdout.decode("utf-8", "replace").strip()


def within(path: Path, root: Path = ROOT):
    resolved = path.resolve()
    if resolved == root.resolve() or not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"Out of scope or root target: {resolved}")
    return resolved


def digest(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def worktrees(repo: Path):
    items = []
    for block in git(repo, "worktree", "list", "--porcelain").split("\n\n"):
        item = dict(line.split(" ", 1) if " " in line else (line, True)
                    for line in block.splitlines() if line)
        if item:
            items.append(item)
    return items


def other_files(repo: Path):
    names = git(repo, "ls-files", "--others", "-z", binary=True).decode("utf-8").split("\0")
    return sorted(name for name in names if name and not EPHEMERAL.intersection(Path(name).parts))


def inventory():
    candidates = [ROOT, ROOT / "upstream-flashml", ROOT / "paper-en"]
    candidates += [p for p in (ROOT / "development").iterdir()
                   if p.is_dir() and (p / ".git").exists()]
    repositories = {}
    for repo in candidates:
        common = git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir")
        if common in repositories:
            continue
        refs = git(repo, "for-each-ref", "--format=%(refname) %(objectname)").splitlines()
        records = []
        for wt in worktrees(repo):
            path = Path(wt["worktree"])
            if path.resolve() != ROOT.resolve():
                within(path)
            extra = other_files(path)
            sizes = [(name, (path / name).stat().st_size) for name in extra if (path / name).is_file()]
            records.append({**wt, "status": git(path, "status", "--porcelain"),
                            "extra_file_count": len(extra), "extra_bytes": sum(size for _, size in sizes),
                            "largest_extra": sorted(sizes, key=lambda x: x[1], reverse=True)[:5]})
        repositories[common] = {"repo": str(repo), "refs": refs, "worktrees": records}
    receipt = {"at": datetime.now().astimezone().isoformat(), "repositories": list(repositories.values())}
    write_json(HERE / "INVENTORY_BEFORE.json", receipt)
    for repo in receipt["repositories"]:
        print(json.dumps({"repo": repo["repo"], "refs": len(repo["refs"]),
                          "worktrees": len(repo["worktrees"]),
                          "extra_bytes": sum(wt["extra_bytes"] for wt in repo["worktrees"]),
                          "dirty_worktrees": sum(bool(wt["status"]) for wt in repo["worktrees"])}, ensure_ascii=False))


def backup_repo(repo: Path, label: str):
    target = ARCHIVE / label
    target.mkdir(parents=True, exist_ok=False)
    refs_before = git(repo, "for-each-ref", "--format=%(refname) %(objectname)").splitlines()
    trees = worktrees(repo)
    # Name detached heads too: a bundle containing branches alone can omit them.
    for index, wt in enumerate(trees):
        tag = f"archive/finalization-20261014/worktree-{index:02d}"
        git(repo, "tag", tag, wt["HEAD"])
    for row in refs_before:
        ref, sha = row.split(" ", 1)
        if ref.startswith("refs/heads/"):
            git(repo, "tag", "archive/finalization-20261014/" + ref.removeprefix("refs/heads/"), sha)
    bundle = target / "all_refs.bundle"
    git(repo, "bundle", "create", str(bundle), "--all")
    verification = git(repo, "bundle", "verify", str(bundle))
    covered = {line.split(" ", 1)[0] for line in git(repo, "bundle", "list-heads", str(bundle)).splitlines()}
    assert all(wt["HEAD"] in covered for wt in trees)
    receipts = []
    for wt in trees:
        path = within(Path(wt["worktree"]))
        sub = target / path.name
        sub.mkdir()
        status_before = git(path, "status", "--porcelain")
        changes = git(path, "diff", "--name-only", "HEAD", "-z", binary=True).decode("utf-8").split("\0")
        names = sorted(set(other_files(path)) | {p for p in changes if p})
        entries = []
        archive = sub / "working_files.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            for name in names:
                full = path / name
                if not full.exists() and not full.is_symlink():
                    entries.append({"path": name, "deleted": True})
                    continue
                if not full.is_symlink():
                    within(full, path)
                if full.is_dir():
                    raise RuntimeError(f"Nested directory needs explicit handling: {full}")
                record = {"path": name, "sha256": digest(full)} if not full.is_symlink() else {"path": name, "symlink": os.readlink(full)}
                tar.add(full, arcname=name, recursive=False)
                entries.append(record)
        with tarfile.open(archive, "r:gz") as tar:
            for entry in entries:
                if entry.get("deleted"):
                    continue
                member = tar.getmember(entry["path"])
                if "symlink" in entry:
                    assert member.linkname == entry["symlink"]
                else:
                    with tar.extractfile(member) as stream:
                        assert hashlib.file_digest(stream, "sha256").hexdigest() == entry["sha256"]
        assert git(path, "status", "--porcelain") == status_before
        for filename, args in [("head.patch", ("diff", "--binary", "HEAD")),
                               ("index.patch", ("diff", "--cached", "--binary")),
                               ("worktree.patch", ("diff", "--binary"))]:
            (sub / filename).write_bytes(git(path, *args, binary=True))
        record = {**wt, "status": status_before, "entries": entries,
                  "archive": str(archive), "sha256": digest(archive)}
        write_json(sub / "receipt.json", record)
        receipts.append(record)
    receipt = {"at": datetime.now().astimezone().isoformat(), "repo": str(repo),
               "refs_before": refs_before, "bundle": str(bundle), "bundle_sha256": digest(bundle),
               "bundle_verified": True, "verification": verification, "worktrees": receipts}
    write_json(target / "BACKUP_RECEIPT.json", receipt)
    print(json.dumps({"label": label, "bundle_bytes": bundle.stat().st_size,
                      "worktrees": len(trees), "working_archives_verified": True}))


def verify_backups():
    for path in ARCHIVE.glob("*/BACKUP_RECEIPT.json"):
        receipt = json.loads(path.read_text(encoding="utf-8"))
        assert digest(Path(receipt["bundle"])) == receipt["bundle_sha256"]
        for wt in receipt["worktrees"]:
            assert digest(Path(wt["archive"])) == wt["sha256"]
            source = Path(wt["worktree"])
            assert git(source, "rev-parse", "HEAD") == wt["HEAD"]
            assert git(source, "status", "--porcelain") == wt["status"]
            for entry in wt["entries"]:
                if "sha256" in entry:
                    assert digest(source / entry["path"]) == entry["sha256"]
        print(json.dumps({"backup": str(path.parent), "unchanged": True}))


def capture_shallow():
    for label, repo in [("historical_engine", ROOT / "development/e2d01"),
                        ("upstream_engine", ROOT / "upstream-flashml"),
                        ("r067_retry_engine", ROOT / "development/r067d_retry2_localwt"),
                        ("research", ROOT), ("paper", ROOT / "paper-en")]:
        common = Path(git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir"))
        shallow = (common / "shallow").read_bytes() if (common / "shallow").exists() else b""
        target = ARCHIVE / label
        (target / "shallow.txt").write_bytes(shallow)
        write_json(target / "SHALLOW_METADATA.json", {
            "repo": str(repo), "shallow": bool(shallow),
            "boundary_count": len(shallow.splitlines()),
            "sha256": hashlib.sha256(shallow).hexdigest(),
            "restore": "git init; copy shallow.txt to .git/shallow if nonempty; git bundle unbundle all_refs.bundle; restore refs with git update-ref; checkout the recorded branch"})
        print(json.dumps({"label": label, "shallow_boundaries": len(shallow.splitlines())}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["inventory", "backup", "verify", "shallow"])
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--label")
    args = parser.parse_args()
    if args.action == "inventory":
        inventory()
    elif args.action == "backup":
        backup_repo(within(args.repo), args.label)
    elif args.action == "shallow":
        capture_shallow()
    else:
        verify_backups()
