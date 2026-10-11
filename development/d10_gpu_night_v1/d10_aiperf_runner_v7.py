"""Full v7 runner interface; v6 plan mechanics with v6 raw gates."""
from __future__ import annotations
import hashlib,importlib.util
from pathlib import Path
HERE=Path(__file__).resolve().parent
def _v6():
 s=importlib.util.spec_from_file_location('d10runner6',HERE/'d10_aiperf_runner_v6.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
INPUT=_v6().INPUT;ORIGINAL=_v6().ORIGINAL;AIPERF=_v6().AIPERF
def argv(endpoint,output,input_file=INPUT):return _v6().argv(endpoint,output,input_file)
def filedry():
 d=_v6().filedry();d['schema']='ft_d10_aiperf_filedry/v4';d.pop('parser_v5_sha256',None);d['parser_v6_sha256']=hashlib.sha256((HERE/'d10_aiperf_parse_v6.py').read_bytes()).hexdigest();return d
def require_admission(path):return _v6().require_admission(path)
def parser():
 s=importlib.util.spec_from_file_location('d10parse6',HERE/'d10_aiperf_parse_v6.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def require_raw_profiles(root):return {0:parser().original_gate(root/'profile0'),1:parser().original_gate(root/'profile1'),2:parser().fixed_gate(root/'profile2'),3:parser().fixed_gate(root/'profile3')}
