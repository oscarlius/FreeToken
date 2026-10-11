import hashlib, importlib.util, json, subprocess, sys
from pathlib import Path
from types import SimpleNamespace
import pytest

path=Path(__file__).parents[1]/'d17_frozen_helpers.py'
spec=importlib.util.spec_from_file_location('helpers_fixture_module',path)
helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)

def archive(tmp_path, live):
 originals=tmp_path/'originals';originals.mkdir()
 files={'cold_eq.py':"import sys;sys.path.insert(0,"+repr(str(live))+");from probe_ft_cold32k import build_text;assert build_text()=='OWNED';print('OWNED')\n",
        'probe_ft_cold32k.py':"def build_text():return 'OWNED'\n",
        'ft_probe_ckpt_tax.py':'# fixture tax\n','serve_args_diff.py':'# fixture parser\n'}
 for name,data in files.items():(originals/name).write_text(data)
 md5={name:hashlib.md5((originals/name).read_bytes()).hexdigest() for name in files}
 root=tmp_path/'helpers';helpers.freeze_helpers(root,originals,md5)
 return root,md5

@pytest.mark.parametrize('live_exists',[False,True])
def test_cold_dependency_is_owned_even_when_live_path_wrong_or_missing(tmp_path,live_exists):
 live=tmp_path/'live'
 if live_exists:
  live.mkdir();(live/'probe_ft_cold32k.py').write_text("raise AssertionError('LIVE HELPER USED')")
 root,_=archive(tmp_path,live)
 result=subprocess.run([sys.executable,str(root/'cold_eq.py')],capture_output=True,text=True)
 assert result.returncode==0 and result.stdout.strip()=='OWNED'

@pytest.mark.skipif(__import__('os').name=='nt',reason='POSIX archive binding')
def test_both_protocol_and_runner_resolve_owned_helper_root(tmp_path):
 root,md5=archive(tmp_path,tmp_path/'absent-live')
 class Runner:
  def __init__(self):pass
 protocol={'Runner':Runner,'TOOL_MD5':md5,'SCR':tmp_path/'wrong-live'}
 evidence=helpers.bind_protocol(protocol,root)
 assert set(evidence)==set(helpers.NAMES)
 assert protocol['SCR']==root and Runner.__init__.__globals__['SCR']==root

@pytest.mark.skipif(__import__('os').name=='nt',reason='POSIX archive binding')
def test_changed_owned_helper_is_rejected(tmp_path):
 root,md5=archive(tmp_path,tmp_path/'absent-live')
 class Runner:
  def __init__(self):pass
 changed=root/'raw'/'probe_ft_cold32k.py';changed.chmod(0o644);changed.write_text('tampered');changed.chmod(0o444)
 with pytest.raises(ValueError,match='bytes differ'):
  helpers.bind_protocol({'Runner':Runner,'TOOL_MD5':md5},root)


@pytest.mark.parametrize('bad_helper',['missing','changed'])
def test_case_preflight_loader_rejects_unverified_helpers_before_runtime(monkeypatch,tmp_path,bad_helper):
    gate_path=Path(__file__).parents[1]/'d17_gate_case.py'
    spec=importlib.util.spec_from_file_location('direct_gate_helper_check',gate_path)
    gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
    root,md5=archive(tmp_path,tmp_path/'absent-live')
    (tmp_path/'d17_frozen_helpers.py').write_bytes(path.read_bytes())
    # An isolated protocol fixture tests the actual loader/binder interface.
    (tmp_path/'t16_full_tail_base_runner.py').write_text('TOOL_MD5='+repr(md5)+'\nclass Runner:\n def __init__(self):pass\n')
    bad=root/'raw/probe_ft_cold32k.py'
    if bad_helper=='changed':
        bad.chmod(0o644);bad.write_text('corrupted');bad.chmod(0o444)
    else:
        bad.parent.chmod(0o755);bad.chmod(0o644);bad.unlink();bad.parent.chmod(0o555)
    monkeypatch.setattr(gate,'HERE',tmp_path)
    with pytest.raises(ValueError,match='helper'):
        gate._load_protocol()
