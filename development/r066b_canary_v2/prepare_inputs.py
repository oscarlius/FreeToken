"""CPU-only neutral prompts bound to the actual target tokenizer."""
from __future__ import annotations
import hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
TOKENIZER=Path('/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay/tokenizer.json')
def sha(value): return hashlib.sha256(value).hexdigest()
def main():
    from tokenizers import Tokenizer
    tok=Tokenizer.from_file(str(TOKENIZER)); encode=lambda s:tok.encode(s,add_special_tokens=False).ids
    def body(sentence):
        n=1
        while len(encode(sentence*n))<8256: n+=1
        return sentence*n
    patterns={'primary_p1':'A neutral laboratory notebook records numbered observations in plain language. ',
        'primary_p2_sun':'Orchard survey entries describe apples, soil, rainfall, and temperature. ',
        'primary_p2_ice':'Harbor survey entries describe tides, buoys, ships, and cloud cover. ',
        'alternative_p1':'Archive ledger pages list dates, measurements, and ordinary notes. ',
        'alternative_p2_sun':'Cedar field records describe leaves, insects, and daylight. ',
        'alternative_p2_ice':'River field records describe stones, currents, and bridges. '}
    bodies={k:body(v) for k,v in patterns.items()}; marks={'sun':'SUNSTONE-7319','ice':'GLACIER-4826'}; rows={}
    for template in ('primary','alternative'):
        for phase in ('p1','p2'):
            for who in ('sun','ice'):
                key=f'{template}_{phase}_{who}'; b=bodies[f'{template}_{phase}'+('' if phase=='p1' else '_'+who)]
                prompt=b+f'\nCODE: {marks[who]}\nCODE: {marks[who]}\nCODE:'; ids=encode(prompt)
                other=marks['ice' if who=='sun' else 'sun']
                if not 8192<=len(encode(b))<=8500 or other in prompt: raise ValueError('body length or marker isolation differs')
                rows[key]={'prompt':prompt,'prompt_sha256':sha(prompt.encode()),'prompt_tokens':len(ids),'body_tokens':len(encode(b)),'first64':ids[:64],'own_marker':marks[who],'other_marker':other}
    common={}
    for template in ('primary','alternative'):
        a,b=(encode(rows[f'{template}_p1_{who}']['prompt']) for who in ('sun','ice'))
        length=next((i for i,(x,y) in enumerate(zip(a,b)) if x!=y),min(len(a),len(b)))
        if length<8192: raise ValueError('shared token prefix too short')
        common[template]=length
    firsts=[v['first64'] for k,v in rows.items() if '_p2_' in k]
    if len({tuple(v) for v in firsts})!=4 or any(v==rows[f'{t}_p1_sun']['first64'] for v in firsts for t in ('primary','alternative')): raise ValueError('independent prefixes collide')
    result={'schema':'ft_r066b_inputs/v2','template':'neutral_raw_completion_three_code_lines','tokenizer_path':str(TOKENIZER),'tokenizer_sha256':sha(TOKENIZER.read_bytes()),'shared_prefix_tokens':common,'items':rows}
    (HERE/'inputs.json').write_text(json.dumps(result,ensure_ascii=False,sort_keys=True)+'\n')
    print(json.dumps({'tokenizer_sha256':result['tokenizer_sha256'],'shared_prefix_tokens':common,'prompt_tokens':{k:v['prompt_tokens'] for k,v in rows.items()}}))
def verify_inputs():
    from tokenizers import Tokenizer
    data=json.loads((HERE/'inputs.json').read_text()); tok=Tokenizer.from_file(str(TOKENIZER))
    if data['tokenizer_path']!=str(TOKENIZER) or sha(TOKENIZER.read_bytes())!=data['tokenizer_sha256']: raise ValueError('tokenizer differs')
    ids={}
    for key,row in data['items'].items():
        prompt=row['prompt']; ids[key]=tok.encode(prompt,add_special_tokens=False).ids
        body=prompt.rsplit('\nCODE:',3)[0]
        if sha(prompt.encode())!=row['prompt_sha256'] or len(ids[key])!=row['prompt_tokens'] or ids[key][:64]!=row['first64'] or len(tok.encode(body,add_special_tokens=False).ids)!=row['body_tokens'] or row['body_tokens']<8192 or row['other_marker'] in prompt or not prompt.endswith(f"CODE: {row['own_marker']}\nCODE: {row['own_marker']}\nCODE:"): raise ValueError('input binding differs')
    for template in ('primary','alternative'):
        a,b=(ids[f'{template}_p1_{who}'] for who in ('sun','ice'))
        common=next((i for i,(x,y) in enumerate(zip(a,b)) if x!=y),min(len(a),len(b)))
        if common<8192 or common!=data['shared_prefix_tokens'][template]: raise ValueError('shared prefix differs')
    firsts=[v[:64] for k,v in ids.items() if '_p2_' in k]
    if len({tuple(v) for v in firsts})!=4 or any(v==ids[f'{t}_p1_sun'][:64] for v in firsts for t in ('primary','alternative')): raise ValueError('independent prefixes differ')
    return {'verified':True,'inputs_sha256':sha((HERE/'inputs.json').read_bytes()),'tokenizer_sha256':data['tokenizer_sha256'],'shared_prefix_tokens':data['shared_prefix_tokens'],'items':len(ids)}
if __name__=='__main__':
    if sys.argv[1:]==['--verify']: print(json.dumps(verify_inputs(),sort_keys=True))
    elif not sys.argv[1:]: main()
    else: raise ValueError('unknown arguments')
