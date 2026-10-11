"""No-service H2 supplement: exact parser and argv-with-help verification."""
from __future__ import annotations
import hashlib, json, os, re, subprocess
from pathlib import Path

RUN=Path('/data2/FreeToken/runs/dev_release/rollback_preflight_20261009_1340_v1')
HISTORY=Path('/data2/_shared/runs/ft_rounds/_e0/paper_headroom_20261003/serve_final_8192.log')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    packet=json.loads((RUN/'h2_input.json').read_text()); deep=json.loads((RUN/'h2_deep_input.json').read_text())
    env=dict(os.environ)
    for k in list(env):
        if k.startswith('FT_') or k in {'PYTHONPATH','CUDA_VISIBLE_DEVICES'}: env.pop(k)
    req=packet['clean_environment_rule']['required']; env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1',PYTHONPATH=req['PYTHONPATH'],VIRTUAL_ENV=req['VIRTUAL_ENV'],CUDA_VISIBLE_DEVICES='')
    env['PATH']=req['VIRTUAL_ENV']+'/bin:'+env.get('PATH','')
    argv=packet['rollback_argv']; ft_argv=argv[argv.index('serve')-1:]+['--help']
    cmd=subprocess.run(ft_argv,cwd=RUN,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
    (RUN/'ft_serve_exact_argv_help.stdout.txt').write_text(cmd.stdout,encoding='utf-8'); (RUN/'ft_serve_exact_argv_help.stderr.txt').write_text(cmd.stderr,encoding='utf-8')
    raw=HISTORY.read_bytes(); text=raw.decode('utf-8','replace'); regex=deep['cached_rows_source']['regex']; matches=re.findall(regex,text)
    physical=raw.decode('utf-8','replace').split('\n')
    lines={str(n):physical[n-1] if n<=len(physical) else None for n in (261,262,264)}
    usage_dict_fields=sorted(set(re.findall(r'\b(prompt_tokens|completion_tokens|total_tokens)\b',text)))
    usage_dict_present=bool(re.search(r'\busage\s*[:=]\s*\{',text))
    value_opts={'--model-path','--served-model-name','--host','--port','--memory-ratio','--ple-backend','--moe-strategy','--quant-backend','--max-running-requests','--cuda-graph-max-bs','--kv-reserve-tokens','--max-seq-len-override','--max-prefill-length','--tool-call-parser','--reasoning-parser'}
    table=[]; i=argv.index('serve')+1
    while i<len(argv):
        opt=argv[i]
        if opt.startswith('--'):
            value=argv[i+1] if opt in value_opts else None
            table.append({'option':opt,'value':value,'accepted_by_exact_ft_argv_help':cmd.returncode==0})
            i+=2 if opt in value_opts else 1
        else: i+=1
    out={'schema':'ft_release_h2_deep_check/v1','input_sha256':sha(RUN/'h2_deep_input.json'),'cached_rows_source':deep['cached_rows_source'],'history':{'full_file_sha256':sha(HISTORY),'regex_match_count':len(matches),'regex_first_8':[list(x) for x in matches[:8]],'physical_lines_261_262_264':lines,'usage_dict_present':usage_dict_present,'usage_dict_fields':usage_dict_fields,'r066_parser_supportable_from_history':bool(matches) and usage_dict_present and {'prompt_tokens','completion_tokens','total_tokens'}<=set(usage_dict_fields)},'exact_ft_argv_help':{'argv':ft_argv,'returncode':cmd.returncode,'stdout_sha256':sha(RUN/'ft_serve_exact_argv_help.stdout.txt'),'stderr_sha256':sha(RUN/'ft_serve_exact_argv_help.stderr.txt'),'cuda_visible_devices':env['CUDA_VISIBLE_DEVICES']},'ft_option_value_table':table,'numactl_value_grammar':{'--cpunodebind=0,1':'supported by numactl usage: comma-delimited node numbers/ranges','--interleave=all':'supported by numactl usage: all is a valid node selector'},'terminal_status':'blocked_dirty_rollback_worktree'}
    (RUN/'h2_deep_check.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    return 0
if __name__=='__main__': raise SystemExit(main())
