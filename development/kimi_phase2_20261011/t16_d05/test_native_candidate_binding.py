"""CPU-only assertions for the bd57-to-c17 native-extension authorization."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent


def load(name: str):
    spec = importlib.util.spec_from_file_location('d09_' + name, HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_bd57_candidate_and_authorized_c17_native_links_are_exact_cpu_only():
    owned, runner = load('owned_launch'), load('runner')
    candidate = owned.require_candidate('D05')
    parent = runner.ROOT / 'wt/release-e2'
    layout = runner.require_native_extension_layout(parent, candidate)
    assert candidate == runner.ROOT / 'wt/d05-decode-align-481-20261011'
    assert all(entry['path'].is_symlink() for entry in layout['new'].values())
    assert all(not entry['path'].is_symlink() for entry in layout['parent'].values())
    assert all(entry['resolved_path'].is_file() and not entry['resolved_path'].is_symlink()
               for entry in layout['new'].values())


def test_imported_extension_records_match_the_exact_authorized_layout_cpu_only():
    runner = load('runner')
    options = SimpleNamespace(case='D05', rid=runner.ASSIGNED_RID, batch=1,
                              candidate_commit=runner.CASES['D05']['new_commit'],
                              run=False, gate=None, file_dry_run=True)
    candidate_runner = runner.CandidateRunner(options)
    parent, candidate = runner.ROOT / 'wt/release-e2', runner.ROOT / 'wt/d05-decode-align-481-20261011'
    extensions = {'parent': candidate_runner.compiled_extensions(parent),
                  'new': candidate_runner.compiled_extensions(candidate)}
    runner.validate_extensions(extensions, parent, candidate)
    assert all(record['path'].startswith(str(candidate))
               and record['resolved_path'].startswith(str(runner.NATIVE_LINK_SOURCE_WORKTREE))
               for record in extensions['new'].values())
