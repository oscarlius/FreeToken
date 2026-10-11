import copy
import importlib.util
from pathlib import Path
import pytest
import regrade

def corpus():
    prompts={str(i):{'id':str(i),'category':'chinese_extraction','expected_entities':['abc']} for i in range(60)}
    rows=[{'question_id':key,'category':'chinese_extraction','response':'abc','thinking':'hidden wrong answer',
           'finish_reason':'stop','passed':False,'detail':'old'} for key in prompts]
    return rows,prompts

def test_only_answer_is_graded_and_input_is_retained():
    rows,prompts=corpus();before=copy.deepcopy(rows);seen=[]
    def grader(question,answer,finish_reason):seen.append((answer,finish_reason));return 'PASS','ok'
    graded,summary=regrade.grade_set(rows,prompts,grader)
    assert rows==before and seen==[('abc','stop')]*60
    assert summary['passed']==60 and all(r['historical_passed'] is False for r in graded)

@pytest.mark.parametrize('mutation',[lambda rows:rows.pop(),lambda rows:rows.__setitem__(1,rows[0]),
                                   lambda rows:rows[0].pop('finish_reason'),lambda rows:rows[0].update(category='code_autotest')])
def test_reject_incomplete_or_unbound_inputs(mutation):
    rows,prompts=corpus();mutation(rows)
    with pytest.raises(ValueError):regrade.validate(rows,prompts)

def test_grader_error_is_not_a_model_failure():
    rows,prompts=corpus()
    with pytest.raises(ValueError,match='grader/runtime error'):
        regrade.grade_set(rows,prompts,lambda *a,**k:('EVALUATOR_ERROR','bad fixture'))

def evaluator():
    source=Path(__file__).with_name('evaluator.py')
    if not source.is_file():source=Path(__file__).resolve().parents[3]/'_shared/evaluator.py'
    assert regrade.sha(source.read_bytes())==regrade.EVALUATOR_SHA
    spec=importlib.util.spec_from_file_location('standard_test',source)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def test_standard_executes_test_cases_and_rejects_wrong_code():
    module=evaluator();q={'category':'code_autotest','function_name':'double',
                         'test_cases':[{'input':[3],'expected':6}]}
    assert module.grade_question(q,'def double(x):\n    return x*2')[0]=='PASS'
    assert module.grade_question(q,'def double(x):\n    return x')[0]=='ANSWER_FAIL'

def test_standard_detects_thinking_truncation_and_empty_expected():
    module=evaluator()
    assert module.grade_question({'category':'code_autotest'},'',finish_reason='length')[0]=='TRUNCATED'
    assert module.grade_question({'category':'chinese_extraction'},'arbitrary')[0]=='EVALUATOR_ERROR'
