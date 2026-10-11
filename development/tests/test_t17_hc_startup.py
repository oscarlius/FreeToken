from pathlib import Path


SOURCE = (Path(__file__).parents[1] / 't17_hc_startup.py').read_text(encoding='utf-8')


def test_spawn_contract_and_parser_binding_are_explicit():
    assert 'from t17_projection_startup import PARSER_SHA, target_structure' in SOURCE
    assert "'ft_t17_hc_spawn/v1'" in SOURCE
    assert "proof['hc_engine_init'] != 'init_hc'" in SOURCE
    assert "proof['reply_wrapper'] != 'reply_hc'" in SOURCE
    assert "proof['cuda_initialized']" in SOURCE


def test_only_the_hc_environment_enables_installation():
    assert "os.environ.get('FT_T17_HC')" in SOURCE
    assert "os.environ.get('FT_LM_CHUNK') != '4096'" in SOURCE
    assert "parsed_ple_layer_ids=tuple(structure['parsed_ple_decoder_indices'])" in SOURCE
