from pathlib import Path


SOURCE = (Path(__file__).parents[1] / 't17_hc_runner.py').read_text(encoding='utf-8')


def test_three_service_requests_keep_the_original_exact_id_arguments():
    assert "self.request(arm, 'donor', case['donor'], 0, 2)" in SOURCE
    assert "self.request(arm, 'short', case['short'], 8192, 128)" in SOURCE
    assert "self.request(arm, 'query', case['short'], 0, 128)" in SOURCE
    assert "device=8193, extend=3585" in SOURCE
    assert "device=8257, extend=3649" in SOURCE


def test_final_validator_requires_real_observation_files_and_state_comparison():
    assert "HC terminal observation is incomplete" in SOURCE
    assert "HC tensor shape/dtype/stride differs" in SOURCE
    assert "signed_zero_rows_or_values" in SOURCE
    assert "artifacts.validate_case" in SOURCE
    assert "kind='donate', length=8256" in SOURCE
