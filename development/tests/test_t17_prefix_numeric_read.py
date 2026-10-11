"""Exact evidence inventory and source binding regressions; no model inference."""
import importlib.util
from pathlib import Path
import pytest

source = Path(__file__).parents[1]/'t17_prefix_numeric_read.py'
spec = importlib.util.spec_from_file_location('r027_reader_test',source)
reader = importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)

def test_every_raw_tensor_is_required():
    assert len(reader.EXPECTED_TENSORS) == 42
    reader.require_inventory(reader.EXPECTED_TENSORS)
    with pytest.raises(ValueError,match='42-tensor'):
        reader.require_inventory(set(reader.EXPECTED_TENSORS)-{next(iter(reader.EXPECTED_TENSORS))})
    with pytest.raises(ValueError,match='42-tensor'):
        reader.require_inventory(set(reader.EXPECTED_TENSORS)|{'foreign.pt'})

def test_retained_cpu_source_is_bound():
    assert 'tensor_comparisons' in reader.companion_program()
    old = reader.COMPANION_SHA
    try:
        reader.COMPANION_SHA = '0'*64
        with pytest.raises(ValueError,match='source changed'):
            reader.companion_program()
    finally:
        reader.COMPANION_SHA = old

def test_synthetic_terminal_flags_are_not_actual_launch_proof():
    with pytest.raises(ValueError,match='exact R027'):
        reader.read_actual({'terminal':{'controller_terminal':True}})

def test_supplied_program_cannot_impersonate_retained_source():
    with pytest.raises(ValueError,match='PROGRAM changed'):
        reader.read_actual({},program='raise AssertionError("must never execute")')
