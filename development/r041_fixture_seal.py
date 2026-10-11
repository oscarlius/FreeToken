"""Seal a fixture-only accepted T17 round after raw all28 auditing."""
from __future__ import annotations
import hashlib, importlib.util, json, subprocess
from pathlib import Path

def seal(root: Path, audit: dict, *, close_source: Path, writer: Path, gate_source: Path) -> dict:
    root=Path(root)
    if audit.get('verdict')!='kept_pending_independent_review' or len(audit.get('cases',[]))!=28: raise ValueError('all28 audit required')
    ir=root/'independent_review.json'; ir.write_text(json.dumps(audit,indent=2)+'\n')
    doc={'schema':'ft_round/v2','round_id':root.name,'card':'T17','verdict':'pending_review','retractions':[],'serve':'none','experimental':{'candidate_commit':'e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7'},'results':audit,'independent_review_sha256':hashlib.sha256(ir.read_bytes()).hexdigest(),'fixture_only':True}
    (root/'round.json').write_text(json.dumps(doc,indent=2)+'\n')
    spec=importlib.util.spec_from_file_location('fixture_close',close_source); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); manifest=mod.close(root)
    subprocess.run([str(writer),str(root),'verdict','--new','kept','--reason','fixture','--evidence','result.json','--by','fixture'],check=True,text=True,capture_output=True)
    subprocess.run([str(writer),str(root),'check'],check=True,text=True,capture_output=True)
    spec=importlib.util.spec_from_file_location('fixture_gate',gate_source); gate=importlib.util.module_from_spec(spec); spec.loader.exec_module(gate)
    accepted=gate.verify_accepted_t17(root/'round.json',ir)
    return {'fixture_only':True,'manifest_sha256':manifest,'accepted':accepted}
