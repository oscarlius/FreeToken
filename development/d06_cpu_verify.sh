set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,importlib.util,json,pathlib,subprocess,sys,tarfile,traceback
stage=pathlib.Path('/data2/FreeToken/runs/dev_D06/cpu_23f2e2c')
repo=stage/'repo'
archive=stage/'d06_cpu_f18fc557cb89.tar'
assert hashlib.sha256(archive.read_bytes()).hexdigest()=='72f5190129175a95fa4caaf351ef6b48056c929710c43bda15929f385e8888f7'
assert subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()=='23f2e2caa3395837c9474735ffc83321f3b9b5a1'
with tarfile.open(archive) as tf:
    manifest=json.loads(tf.extractfile('MANIFEST.json').read())
    assert set(tf.getnames())=={'MANIFEST.json',*manifest['files']}
    for name,digest in manifest['files'].items():
        assert not pathlib.PurePosixPath(name).is_absolute() and '..' not in pathlib.PurePosixPath(name).parts
        blob=tf.extractfile(name).read();assert hashlib.sha256(blob).hexdigest()==digest
        dest=repo/name;assert repo.resolve() in dest.resolve().parents
        dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(blob)
log=stage/'d06_cpu_f18fc557cb89.log';assert not log.exists()
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
            msg=TokenizeMsg(uid=target,text=messages,sampling_params=SamplingParams(),
                            chat_template_kwargs={'enable_thinking':False})
            actual=manager.tokenize([msg])[0].input_ids.tolist()
            assert actual==ids and len(actual)==target
            other,other_ids=probe.make_messages(tokenizer,target,'cpu-right-'+str(target))
            rows.append({'target':target,'actual_frontend_tokens':len(actual),
                         'server_client_ids_equal':True,'prompt_sha256':probe.prompt_sha256(ids),
                         'distinct_prompt_sha256':probe.prompt_sha256(other_ids),
                         'distinct_prompts':messages!=other,
                         'common_prefix_tokens':probe.common_prefix_tokens(ids,other_ids)})
        tokenizer_config=pathlib.Path(probe.DEFAULT_TOKENIZER)/'tokenizer_config.json'
        proof={'state':'passed','tokenizer_path':probe.DEFAULT_TOKENIZER,'renderer':'actual TokenizeManager.tokenize standard template',
                'tokenizer_config_sha256':hashlib.sha256(tokenizer_config.read_bytes()).hexdigest(),'rows':rows}
    except Exception as exc:
        proof={'state':'failed','error':repr(exc),'traceback':traceback.format_exc()}
    with log.open('ab') as output:output.write((json.dumps({'tokenizer_proof':proof},sort_keys=True)+'\n').encode())
rc=result.returncode or (0 if proof['state']=='passed' else 1)
report={'scope':'Linux CPU only; CUDA_VISIBLE_DEVICES empty; no model service','archive_sha256':'72f5190129175a95fa4caaf351ef6b48056c929710c43bda15929f385e8888f7','manifest':manifest,'command':cmd,
         'pytest_returncode':result.returncode,'returncode':rc,'tokenizer_proof':proof,
         'log':str(log),'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
receipt=stage/'d06_cpu_f18fc557cb89.json'
with receipt.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2);f.write('\n')
print(log.read_text()[-18000:])
print(json.dumps({'report':str(receipt),'returncode':rc,'log_sha256':report['log_sha256']}))
raise SystemExit(rc)
PY
