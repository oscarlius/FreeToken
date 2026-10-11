from __future__ import annotations
import importlib.util
from pathlib import Path
import pytest
DEV=Path(__file__).parents[1]
def mod():
 s=importlib.util.spec_from_file_location("replay",DEV/"t16_r018_replay.py");m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def make(tmp,m):
 d=tmp/m.RID;d.mkdir();(d/"runner_batch46.py").write_bytes(b"r");(d/"base_runner_batch46.py").write_bytes(b"b");return d
def test_missing_or_wrong_archives_fail_before_replay(tmp_path):
 m=mod();d=make(tmp_path,m)
 with pytest.raises(ValueError,match="SHA"):m.restore_and_selftest(d)
 (d/"base_runner_batch46.py").unlink()
 with pytest.raises(ValueError,match="missing"):m.restore_and_selftest(d)
def test_audit_requires_explicit_parser_path(tmp_path):
 m=mod();d=make(tmp_path,m)
 with pytest.raises((FileNotFoundError,ValueError)):m.audit(d,tmp_path/"missing_parser.py")
