"""External, one-event D10 decode branch probe; never edits candidate source."""
import json, os
from pathlib import Path

def install():
    from freetoken.engine.engine import Engine
    original=Engine._forward_d10_staggered_decode
    emitted=False
    def wrapped(self,*args,**kwargs):
        nonlocal emitted
        if not emitted:
            target=Path(os.environ['FT_D10_BRANCH_EVENT'])
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text(json.dumps({'method':'Engine._forward_d10_staggered_decode','entered':True})+'\n')
            emitted=True
        return original(self,*args,**kwargs)
    Engine._forward_d10_staggered_decode=wrapped
