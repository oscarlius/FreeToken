import importlib.util,sys,json
from pathlib import Path
import pytest
HERE=Path(__file__).parent;sys.path.insert(0,str(HERE))
import window_resume as r

def test_reuse_is_evidence_only_and_hash_pinned(tmp_path):
    arm=tmp_path/'W98K';arm.mkdir();hashes={};inputs=[]
    for i in range(8):
        p=arm/f'A{i}.api.metrics.json';p.write_text(json.dumps({'input_sha256':str(i),'native_token_sha256':'token','completion_tokens':3}));p.chmod(0o444);hashes[str(p.relative_to(tmp_path))]=r.w.sha(p);inputs.append(str(i))
    p=arm/'serve.log';p.write_text('--moe-cache-auto resolved moe_cache_size=2700 num_pages=1536 (prefill_overlap=True)');p.chmod(0o444);hashes[str(p.relative_to(tmp_path))]=r.w.sha(p)
    assert len(r.prior_rows(tmp_path,{'input_sha256':inputs},hashes)['A'])==8
    hashes['W98K/serve.log']='bad'
    with pytest.raises(RuntimeError,match='differs'):r.prior_rows(tmp_path,{'input_sha256':inputs},hashes)

def test_cleanup_records_stop_error_but_requires_idle(tmp_path):
    class Life:
        def stop_owned_process(self,*a,**k):raise ProcessLookupError('race')
        def owned_group_alive(self,*a):return False
    class D: lifecycle=Life();gpu_idle=staticmethod(lambda:True)
    class P:pid=1
    import socket
    ports=[]
    for _ in range(2):
        with socket.socket() as s:s.bind(('127.0.0.1',0));ports.append(s.getsockname()[1])
    assert r.finish_owned(P(),open(tmp_path/'log','w'),{'port':ports[0],'master_port':ports[1]},D(),tmp_path)
    assert json.loads((tmp_path/'cleanup_receipt.json').read_text())['stop_errors_preserved']
