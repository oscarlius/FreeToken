import copy
import importlib.util
from pathlib import Path

import pytest

source = Path(__file__).parents[1]/'t17_continuation_inputs.py'
spec = importlib.util.spec_from_file_location('continuation_inputs',source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def prefixes():
    return {'candidate_commit':module.CANDIDATE,'trace_sha256':'a'*64,
            'cases':[{'length':length,'donor':[10]*length+[11],'expected_ngram':[10,10],
                      'trace_index':i,'messages_sha':'b'*64,'original_ids_sha256':'c'*64}
                     for i,length in enumerate(module.BOUNDARIES)]}


def test_full_matrix_exact_ids_context_and_hashes():
    result = module.expand(prefixes(),[12]*8192)
    assert len(result['cases']) == 28
    assert result['cases'][0]['name']=='prefix-8192-tail-65'
    for row in result['cases']:
        assert len(row['query'])==row['length']+row['tail']
        assert row['query'][:row['length']+1]==row['donor']
        assert module.token_sha(row['query'])==row['input_ids_sha256']
        assert row['query'][row['length']-2:row['length']]==row['expected_ngram']


@pytest.mark.parametrize('change',['candidate','boundary','context','suffix'])
def test_reject_unbound_frontend_data(change):
    data=copy.deepcopy(prefixes());suffix=[12]*8192
    if change=='candidate':data['candidate_commit']='wrong'
    if change=='boundary':data['cases'][-1]['length']=19008
    if change=='context':data['cases'][0]['expected_ngram']=[11,12]
    if change=='suffix':suffix=suffix[:-1]
    with pytest.raises(ValueError):module.expand(data,suffix)
