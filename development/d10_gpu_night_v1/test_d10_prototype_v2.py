from pathlib import Path
def test_health_and_branch_contract_are_explicit():
    s=Path(__file__).with_name('d10_prototype_owned_parent_v2.py').read_text()
    assert "'/health'" in s and 'prototype health timeout' in s
    assert '--enable-d10-staggered-decode' in s and 'native reuse bytes absent' in s
    assert 'stop_owned_process' in s and 'rebound=reserve_pair' in s
