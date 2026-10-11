from pathlib import Path
import importlib.util
PATH=Path(__file__).parents[1]/'r041_fixture_seal.py';s=importlib.util.spec_from_file_location('x',PATH);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def test_rejects_non_all28(tmp_path):
 import pytest
 with pytest.raises(ValueError): m.seal(tmp_path,{'verdict':'x'},close_source=tmp_path/'x',writer=tmp_path/'x',gate_source=tmp_path/'x')
