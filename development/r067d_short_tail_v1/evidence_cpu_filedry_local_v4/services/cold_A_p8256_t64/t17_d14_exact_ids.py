from dataclasses import dataclass
import hashlib,torch
import freetoken.message.tokenizer as wire
from freetoken.message.tokenizer import TokenizeMsg
from freetoken.message.backend import UserMsg
from freetoken.tokenizer.tokenize import TokenizeManager
@dataclass
class T17ExactIdsMsg(TokenizeMsg):
    input_ids_exact:list[int]=None
wire.T17ExactIdsMsg=T17ExactIdsMsg
_tokenize=TokenizeManager.tokenize
def _exact_tokenize(self,msgs):
    normal=[m for m in msgs if not isinstance(m,T17ExactIdsMsg)]
    out=[]
    for m in msgs:
        if isinstance(m,T17ExactIdsMsg):
            ids=m.input_ids_exact
            if not ids or any(type(x) is not int for x in ids): raise ValueError('exact IDs required')
            tensor=torch.tensor(ids,dtype=torch.int32)
            out.append(UserMsg(uid=m.uid,input_ids=tensor,sampling_params=m.sampling_params))
            import os,json,pathlib
            destination=os.environ.get('FT_T17_INPUT_RECEIPTS')
            if destination:
                with (pathlib.Path(destination)/(str(m.uid)+'.json')).open('x') as stream:
                    json.dump({'uid':m.uid,'numel':tensor.numel(),'int32le_sha256':hashlib.sha256(tensor.numpy().tobytes()).hexdigest(),'sampling':m.sampling_params.__dict__},stream)
        else: out.extend(_tokenize(self,[m]))
    return out
TokenizeManager.tokenize=_exact_tokenize
def cpu_probe(queue):
    from freetoken.core import SamplingParams
    from freetoken.message.tokenizer import BaseTokenizerMsg
    from freetoken.scheduler.scheduler import Scheduler
    from freetoken.scheduler.io import SchedulerIOMixin
    from freetoken.engine.engine import Engine
    message=T17ExactIdsMsg(uid=41,text='',sampling_params=SamplingParams(max_tokens=7,temperature=0),input_ids_exact=[1469,17,198,248068])
    decoded=BaseTokenizerMsg.decoder(BaseTokenizerMsg.encoder(message))
    out=TokenizeManager.__new__(TokenizeManager).tokenize([decoded])[0]
    queue.put({'uid':out.uid,'ids':out.input_ids.tolist(),'sampling':out.sampling_params.__dict__,
               'cuda_initialized':torch.cuda.is_initialized(),'scheduler_wrapper':Scheduler._restore_linear_states.__name__,
               'engine_wrapper':Engine._build_layer_major_chunks.__name__,
               'reply_wrapper':SchedulerIOMixin._reply_tokenizer_rank0.__name__,
               'input_wrapper':Scheduler._process_one_msg.__name__})
