import hashlib
import itertools
import pytest
from criteria import grammar, classify, product_failure

M='SUNSTONE-7319'
@pytest.mark.parametrize('text,clean',[
    (' '+M+'\nCODE: '+M+'\nCODE',True),
    (M+'\nCODE: '+M+'\n',True),
    (M+'\n',True),
    (M+'\nCODE: SUNSTONE',True),
    ('  '+M+'\n',True),
    (M,False),
    ('\t'+M+'\n',False),
    (M+' \n',False),
    (M+'\r\n',False),
    (M+'\n\nCODE',False),
    (M+'\nCODE: '+M+' extra\nCODE',False),
    (M+'\nCODE: '+M+'X',False),
    (M+'\nCODE: '+M+'\nCODE: SUNSTONE-<think>\n\n</think>',False),
    ('',False),
])
def test_literal_grammar(text,clean):
    out=grammar(text,M)
    assert out['clean'] is clean
    assert out['first_three_raw_lines']==text.split('\n')[:3]
    assert out['fulltext_sha256']==hashlib.sha256(text.encode()).hexdigest()

def reply_rows(bits, failure=None):
    keys=[('X','SUNSTONE'),('X','GLACIER'),('Y','GLACIER'),('Z','SUNSTONE'),('Z','GLACIER')]
    return [{'service':s,'prompt':p,'clean':b,'product_failure':failure if i==0 else None}
            for i,((s,p),b) in enumerate(zip(keys,bits))]

@pytest.mark.parametrize('bits',list(itertools.product([False,True],repeat=5)))
def test_per_prompt_ordered_classification(bits):
    x_sun,x_ice,y_ice,z_sun,z_ice=bits
    expected='a' if (x_sun and not z_sun) or (x_ice and y_ice and not z_ice) else ('b' if not x_ice and y_ice else 'c')
    result=classify(reply_rows(bits))
    assert result['category']==expected
    assert result['stop'] is (expected!='c')
    assert result['release_gate_may_close'] is (expected=='c')

def test_product_failure_precedes_interference_and_hot_difference():
    assert classify(reply_rows([True,False,True,False,False],'other_marker'))['category']=='0'

@pytest.mark.parametrize('text,reason',[
    ('GLACIER-4826','other_marker'),('\ufffd','U+FFFD'),('\x00','illegal_control_character'),
    ('GLACION-4826',None),('\n\r\t',None),('SUNSTONE-<think>',None),
])
def test_product_condition_independent_of_grammar(text,reason):
    assert product_failure(text,'GLACIER-4826')==reason

def test_duplicate_or_missing_identity_rejected():
    rows=reply_rows([True]*5)
    with pytest.raises(ValueError): classify(rows[:-1])
    rows[-1]=rows[-2].copy()
    with pytest.raises(ValueError): classify(rows)
