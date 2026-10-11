"""Offline target-tokenizer preparation; no model launch."""
import argparse, hashlib, json
from pathlib import Path
from tokenizers import Tokenizer
def prepare(binding_path, tokenizer_path, output):
    binding=json.loads(binding_path.read_text(encoding='utf-8')); tok=Tokenizer.from_file(str(tokenizer_path)); items={}
    for row in binding['inputs']:
        key='long' if row['label']=='slot_1_long_query' else 'short'; prompt=row['decoded_prompt']; ids=tok.encode(prompt,add_special_tokens=False).ids
        if ids!=row['original_input_ids'] or len(ids)!=({'long':8257,'short':512}[key]): raise ValueError('original mapping differs')
        items[key]={'prompt':prompt,'prompt_tokens':len(ids),'max_tokens':128}
    for key,marker in (('alpha','R065_ALPHA_SUNSTONE_7319'),('beta','R065_BETA_MOONSTONE_2846')):
        prompt=items['long']['prompt']+'\n\nIgnore the preceding coding question for the response. This request has exactly one private marker: '+marker+'.\nOutput only this exact ASCII marker. Repeat your own marker as needed. Do not output other content or invent another marker.\nResponse: '
        ids=tok.encode(prompt,add_special_tokens=False).ids
        if len(ids)<8192: raise ValueError('discriminator too short')
        items[key]={'prompt':prompt,'prompt_tokens':len(ids),'max_tokens':64,'marker':marker,'input_ids':ids}
    doc={'schema':'ft_r065_inputs/v1','binding_sha256':hashlib.sha256(binding_path.read_bytes()).hexdigest(),'tokenizer_sha256':hashlib.sha256(tokenizer_path.read_bytes()).hexdigest(),'offline_target_tokenizer_verified':True,'items':items}
    with output.open('x',encoding='utf-8') as f: json.dump(doc,f,ensure_ascii=False,sort_keys=True,indent=2); f.write('\n')
    print(json.dumps({'counts':{k:v['prompt_tokens'] for k,v in items.items()},'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}))
if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--binding',type=Path,required=True); p.add_argument('--tokenizer',type=Path,required=True); p.add_argument('--output',type=Path,required=True); a=p.parse_args(); prepare(a.binding,a.tokenizer,a.output)
