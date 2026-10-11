import os,sys,hashlib
assert os.environ.get("FT_DEV_STATE_DUMP"), "T17 requires FT_DEV_STATE_DUMP"
import t17_d14_exact_ids
import t17_d14_observe
t17_d14_observe.startup()
from fastapi import HTTPException
from pydantic import BaseModel
from freetoken.core import SamplingParams
from freetoken.message.tokenizer import T17ExactIdsMsg
from freetoken.server import api_server as _api
class _T17Request(BaseModel):
    input_ids:list[int]; max_tokens:int=128
@_api.app.post('/internal/t17/exact-ids')
async def _t17_exact_ids(req:_T17Request):
    if not req.input_ids or req.max_tokens<1: raise HTTPException(400,'nonempty IDs and max_tokens required')
    state=_api.get_global_state(); uid=state.new_user(); digest=hashlib.sha256(__import__('struct').pack('<%di'%len(req.input_ids),*req.input_ids)).hexdigest()
    await state.send_one(T17ExactIdsMsg(uid=uid,text='',sampling_params=SamplingParams(max_tokens=req.max_tokens,temperature=0,top_p=1,ignore_eos=True),input_ids_exact=req.input_ids))
    text=''; cached=prompt=completion=0
    async for ack in state.wait_for_ack(uid):
        if ack.error: raise HTTPException(400,ack.error)
        text+=ack.incremental_output; cached+=ack.cached_tokens; prompt+=ack.prompt_tokens_delta; completion+=ack.completion_tokens_delta
        if ack.finished: break
    return {'uid':uid,'text':text,'finished':ack.finished,'finish_reason':getattr(ack,'finish_reason',None),'usage':{'prompt_tokens':prompt,'completion_tokens':completion,'cached_tokens':cached},'input_ids_sha256':digest}
from freetoken.cli import main
sys.argv=["ft",*sys.argv[1:]]
if __name__=='__main__':
    if sys.argv[1:]==['--cpu-startup-probe']:
        import multiprocessing,json
        context=multiprocessing.get_context('spawn'); queue=context.Queue()
        process=context.Process(target=t17_d14_exact_ids.cpu_probe,args=(queue,));process.start()
        proof=queue.get(timeout=60);process.join(60)
        assert process.exitcode==0 and proof['ids']==[1469,17,198,248068] and proof['uid']==41 and not proof['cuda_initialized']
        assert proof['scheduler_wrapper']=='restore_observed' and proof['engine_wrapper']=='build_chunks_observed'
        assert proof['reply_wrapper']=='reply_observed' and proof['input_wrapper']=='process_observed'
        print(json.dumps({'schema':'ft_t17_startup_spawn/v1','gpu_started':False,'worker':proof},sort_keys=True))
    else: main()
