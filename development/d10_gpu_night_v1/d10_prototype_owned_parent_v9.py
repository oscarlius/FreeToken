"""V9 retains V8 child execution and replaces only proof consumption."""
from __future__ import annotations
import importlib.util
from pathlib import Path
HERE=Path(__file__).resolve().parent
def load(p,n):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
base=load(HERE/'d10_prototype_owned_parent_v8.py','d10v8body');proof=load(HERE/'d10_v9_proofs.py','d10v9proof')
child=base.child;controller=base.controller;filedry=base.filedry
def require_formal_proofs():return {'t16':proof.round_semantics(proof.T16),'d09':proof.round_semantics(proof.D09),'native':proof.native()}
