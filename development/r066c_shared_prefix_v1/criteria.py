"""Frozen 11:45 literal reply grammar and ordered per-prompt classification."""
from __future__ import annotations
import hashlib, json, unicodedata
from pathlib import Path
RID = 'E2-R066c-shared-prefix-discriminate'
ORIGINAL = Path('/data2/_shared/runs/ft_rounds/E2-R066b-canary-v2/calls')
ORIGINAL_SHA = {
    'pair1/primary_p1_sun.json': '5bb86dba9581857fee9c5e01d1e2176d94c1137dcff44b586064322834c4313c',
    'pair1/primary_p1_ice.json': '89438b5b279495a6b6c943d36a74fdb0e4cbc93c48fb8f55be1284ff2e2f7af1',
    'pair2/primary_p2_sun.json': 'ba5c4d46078ef5c5f1fd989e2d27f3c944b225debfcd7dab72bfdc8970e75356',
    'pair2/primary_p2_ice.json': '6e620fe635bdec7f79e2d3d4fef031f82a6100eef31d7e46d1edc43f40c5ad79',
}
def text_sha(text): return hashlib.sha256(text.encode('utf-8')).hexdigest()
def grammar(text, marker):
    parts = text.split('\n')
    expected = 'CODE: ' + marker
    first_ok = parts[0].lstrip(' ') == marker
    complete_ok = all(line == expected for line in parts[1:-1])
    tail_ok = text.endswith('\n') or expected.startswith(parts[-1])
    return {'clean': first_ok and complete_ok and tail_ok,
            'first_line_matches': first_ok, 'complete_lines_match': complete_ok,
            'unfinished_tail_is_prefix': tail_ok, 'first_three_raw_lines': parts[:3],
            'fulltext_sha256': text_sha(text)}
def product_failure(text, other):
    if other in text: return 'other_marker'
    if '\ufffd' in text: return 'U+FFFD'
    if any(unicodedata.category(c) == 'Cc' and c not in '\n\r\t' for c in text):
        return 'illegal_control_character'
    return None
def selfcheck(root=ORIGINAL):
    rows = []
    for rel, digest in ORIGINAL_SHA.items():
        path = Path(root)/rel
        if path.is_symlink() or path.stat().st_mode & 0o222 or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('sealed R066b selfcheck binding differs: ' + rel)
        raw = json.loads(path.read_text())
        marker = 'SUNSTONE-7319' if 'sun.json' in rel else 'GLACIER-4826'
        result = grammar(raw['projection']['text'], marker)
        expected = rel.startswith('pair2/')
        if result['clean'] != expected:
            raise ValueError('11:45 R066b selfcheck expectation differs: ' + rel)
        rows.append({'path': str(path), 'artifact_sha256': digest,
                     'expected_clean': expected, **result})
    return {'schema': 'ft_r066c_grammar_selfcheck/v1', 'rid': RID,
            'pass': True, 'expected_clean': [False, False, True, True], 'rows': rows}
def classify(rows):
    """Rows must have unique service/prompt identities for all five calls."""
    expected = {('X','SUNSTONE'),('X','GLACIER'),('Y','GLACIER'),('Z','SUNSTONE'),('Z','GLACIER')}
    keys = [(row['service'], row['prompt']) for row in rows]
    if len(keys) != 5 or set(keys) != expected:
        raise ValueError('classification requires exactly five bound replies')
    if any(row['product_failure'] for row in rows):
        return {'category': '0', 'classification': 'product_failure', 'proposed_verdict': 'not_met', 'stop': True, 'release_gate_may_close': False}
    clean = {key: row['clean'] for key,row in zip(keys,rows)}
    interference = []
    for prompt, standalone in [('SUNSTONE',[('X','SUNSTONE')]),
                                ('GLACIER',[('X','GLACIER'),('Y','GLACIER')])]:
        if not clean[('Z',prompt)] and all(clean[key] for key in standalone):
            interference.append(prompt)
    if interference:
        return {'category': 'a', 'classification': '共享前缀并发干扰', 'prompts': interference,
                'proposed_verdict': 'not_met', 'product_failure_observed': False,
                'stop': True, 'release_gate_may_close': False}
    if not clean[('X','GLACIER')] and clean[('Y','GLACIER')]:
        return {'category': 'b', 'classification': '尾段 ≤ 64 热路径差异',
                'proposed_verdict': 'not_met', 'product_failure_observed': False,
                'stop': True, 'release_gate_may_close': False}
    return {'category': 'c', 'classification': '与并发无关 / 未复现', 'proposed_verdict': 'kept',
            'product_failure_observed': False, 'stop': False, 'release_gate_may_close': True}
def observed_cache(run, service, warm, raw):
    result=json.loads((Path(run)/service/'calls/result.json').read_text())
    if result['status']!='observed': raise ValueError('arm did not complete its evidence checks')
    if service=='Z':
        coverage=result['pair_coverage']
        if not all(coverage[k] is True for k in ('api_windows_overlap','first_chunk_order','cache_scope_met')):
            raise ValueError('shared pair coverage not proven')
        rows=coverage['backend_rows']
        if rows:
            split=next((i for i,row in enumerate(rows) if row['cached_tokens']>0),None)
            if split is None: raise ValueError('shared pair missing actual hot row')
            selected=rows[split:] if warm else rows[:split]
            cached=sum(row['cached_tokens'] for row in selected)
            new=sum(row['new_tokens'] for row in selected)
        else:
            cached=raw['cached_tokens_observation']['value']
            if cached is None: raise ValueError('missing actual cache evidence')
            new=raw['projection']['usage']['prompt_tokens']-cached
        expected=(8256,30) if warm else (0,8284)
        if (cached,new)!=expected: raise ValueError('shared pair actual cache extent differs')
        return {'cached':cached,'new':new,'evidence':coverage}
    proof=result['cache_proof']['warm' if warm else 'cold'] if service=='X' else result['cache_proof']
    if proof['met'] is not True: raise ValueError('standalone cache coverage not proven')
    rows=proof['backend_rows']
    cached=sum(row['cached_tokens'] for row in rows) if rows else proof['api_cached_tokens']
    new=sum(row['new_tokens'] for row in rows) if rows else raw['projection']['usage']['prompt_tokens']-cached
    return {'cached':cached,'new':new,'evidence':proof}
def summarize(run, original=ORIGINAL):
    run = Path(run)
    inputs = json.loads((run/'preflight.json').read_text())['input_binding']['original_calls']
    rows = []
    for service, prompt, label, warm, key in [
        ('X','SUNSTONE','X_sun_cold',False,'primary_p1_sun'),
        ('X','GLACIER','X_ice_warm',True,'primary_p1_ice'),
        ('Y','GLACIER','Y_ice_cold',False,'primary_p1_ice'),
        ('Z','SUNSTONE','Z_sun',False,'primary_p1_sun'),
        ('Z','GLACIER','Z_ice',True,'primary_p1_ice')]:
        path = run/service/'calls'/(label+'.json')
        raw = json.loads(path.read_text())
        marker = 'SUNSTONE-7319' if prompt=='SUNSTONE' else 'GLACIER-4826'
        other = 'GLACIER-4826' if prompt=='SUNSTONE' else 'SUNSTONE-7319'
        text = raw['projection']['text']
        cache=observed_cache(run,service,warm,raw)
        if hashlib.sha256(raw['request']['prompt'].encode()).hexdigest() != inputs[key]['prompt_sha256']:
            raise ValueError('summary wire prompt differs')
        rows.append({'service':service,'prompt':prompt,'cold_hot':'热' if warm else '冷',
                     'cached_tokens_api':raw['cached_tokens_observation']['value'],
                     'cached_tokens_observed':cache['cached'],'new_tokens_observed':cache['new'],
                     'cache_evidence':cache['evidence'],
                     'raw_path':str(path),'raw_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                     'finish_reason':raw['projection']['finish_reason'],'usage':raw['projection']['usage'],
                     'product_failure':product_failure(text,other),**grammar(text,marker)})
    comparisons=[]
    for row in rows[-2:]:
        key='primary_p1_sun' if row['prompt']=='SUNSTONE' else 'primary_p1_ice'
        old=Path(original)/'pair1'/(key+'.json')
        if hashlib.sha256(old.read_bytes()).hexdigest()!=ORIGINAL_SHA['pair1/'+key+'.json']:
            raise ValueError('original comparison binding differs')
        old_sha=text_sha(json.loads(old.read_text())['projection']['text'])
        comparisons.append({'prompt':row['prompt'],'R066b_fulltext_sha256':old_sha,
                            'Z_fulltext_sha256':row['fulltext_sha256'],
                            'same_sha':old_sha==row['fulltext_sha256'],'acceptance_criterion':False})
    return {'schema':'ft_r066c_terminal_classification/v1','rid':RID,'rows':rows,
            'Z_vs_R066b':comparisons,**classify(rows)}
