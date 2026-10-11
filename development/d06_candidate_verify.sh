set -euo pipefail
unset FT_DEV_PAUSE_ENDPOINT FT_DEV_D0 FT_DEV_D0_TIMELINE
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,importlib.util,json,pathlib,subprocess,sys,traceback
stage=pathlib.Path('/data2/FreeToken/runs/dev_D06/candidate_0369263')
source=pathlib.Path('/data2/FreeToken/wt/e2base')
donor=pathlib.Path('/data2/FreeToken/wt/e1r003st')
repo=pathlib.Path('/data2/FreeToken/wt/e2d06')
bundle=stage/'candidate.bundle'
manifest=json.loads((stage/'candidate_commit.json').read_text())
commit='03692633df48456fb0baa78de7b64e5628a12ab1'
assert hashlib.sha256(bundle.read_bytes()).hexdigest()=='384b350c8216c1150d879d02169b0c01417bd27ad4fbb705d65049ae1f0d86fe'
assert manifest['candidate_commit']==commit
assert subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()==manifest['parent']
assert not subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True).strip()
assert not repo.exists()
subprocess.run(['git','-C',str(source),'bundle','verify',str(bundle)],check=True)
subprocess.run(['git','-C',str(source),'fetch',str(bundle),'refs/heads/exp/e2d06'],check=True)
subprocess.run(['git','-C',str(source),'worktree','add','--detach',str(repo),commit],check=True)
extensions=[]
for extension in (donor/'python/freetoken').rglob('*.so'):
    dest=repo/'python/freetoken'/extension.relative_to(donor/'python/freetoken')
    assert not dest.exists()
    dest.parent.mkdir(parents=True,exist_ok=True);dest.symlink_to(extension.resolve())
    extensions.append(str(dest.relative_to(repo)))
for name,digest in manifest['git_blob_files'].items():
    assert hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest,(name,'candidate Git blob mismatch')
assert subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()==commit
assert not subprocess.check_output(['git','-C',str(repo),'status','--porcelain'],text=True).strip()
log=stage/'targeted.log';assert not log.exists()
cmd=['/data2/FreeToken/venv/bin/python','-m','pytest','-q','tests/scheduler/test_dev_pause.py','tests/server/test_dev_pause_api.py','tests/server/test_generation_accounting.py','tests/server/test_message_wire.py','scripts/tests/test_multisession_probe.py']
with log.open('xb') as output:
    result=subprocess.run(cmd,cwd=repo,stdout=output,stderr=subprocess.STDOUT)
proof={'state':'not_run'}
if result.returncode==0:
    try:
        sys.path[:0]=[str(repo/'python'),str(repo)]
        spec=importlib.util.spec_from_file_location('d06_probe',repo/'scripts/multisession_probe.py')
        probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
        from freetoken.tokenizer.tokenize import TokenizeManager
        from freetoken.message import TokenizeMsg
        from freetoken.core import SamplingParams
        tokenizer=probe.load_tokenizer(probe.DEFAULT_TOKENIZER)
        manager=TokenizeManager(tokenizer)
        assert manager._dsv4_encoder is None and tokenizer.chat_template
        rows=[]
        for target in (4000,32000,32052):
            messages,ids=probe.make_messages(tokenizer,target,'cpu-left-'+str(target))
            msg=TokenizeMsg(uid=target,text=messages,sampling_params=SamplingParams(),chat_template_kwargs={'enable_thinking':False})
            actual=manager.tokenize([msg])[0].input_ids.tolist()
            assert actual==ids and len(actual)==target
            other,other_ids=probe.make_messages(tokenizer,target,'cpu-right-'+str(target))
            rows.append({'target':target,'actual_frontend_tokens':len(actual),'server_client_ids_equal':True,
                         'prompt_sha256':probe.prompt_sha256(ids),'distinct_prompt_sha256':probe.prompt_sha256(other_ids),
                         'distinct_prompts':messages!=other,'common_prefix_tokens':probe.common_prefix_tokens(ids,other_ids)})
        tokenizer_config=pathlib.Path(probe.DEFAULT_TOKENIZER)/'tokenizer_config.json'
        proof={'state':'passed','tokenizer_path':probe.DEFAULT_TOKENIZER,'renderer':'actual TokenizeManager.tokenize standard template',
                'tokenizer_config_sha256':hashlib.sha256(tokenizer_config.read_bytes()).hexdigest(),'rows':rows}
    except Exception as exc:
        proof={'state':'failed','error':repr(exc),'traceback':traceback.format_exc()}
    with log.open('ab') as output:output.write((json.dumps({'tokenizer_proof':proof},sort_keys=True)+'\n').encode())
rc=result.returncode or (0 if proof['state']=='passed' else 1)
report={'scope':'isolated committed candidate; CPU only; no GPU service or deployment',
         'candidate_commit':commit,'parent':manifest['parent'],'server_tree':str(repo),
         'compiled_extension_links':extensions,'bundle_sha256':'384b350c8216c1150d879d02169b0c01417bd27ad4fbb705d65049ae1f0d86fe',
         'git_blob_files':manifest['git_blob_files'],'command':cmd,
         'pytest_returncode':result.returncode,'returncode':rc,'tokenizer_proof':proof,
         'log':str(log),'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
with (stage/'candidate.json').open('x',encoding='utf-8') as f:json.dump(report,f,indent=2);f.write('\n')
print(log.read_text()[-14000:])
print(json.dumps({'report':str(stage/'candidate.json'),'candidate_commit':commit,'returncode':rc,'log_sha256':report['log_sha256']}))
raise SystemExit(rc)
PY
