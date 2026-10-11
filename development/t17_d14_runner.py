"""T17 D14 hit-and-continue gate preparation.

This file is deliberately a *preparation* runner.  It has a CPU-only replay
mode and a non-mutating GPU preflight, but it never reserves a GPU or starts a
service.  A future, separately reviewed launcher must consume the emitted
receipt and use the frozen T16 lifecycle to acquire/release the owned process.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
from types import SimpleNamespace
from typing import Any, Callable
import urllib.error
import urllib.request


ROOT = Path("/data2/FreeToken")
ROUNDS = Path("/data2/_shared/runs/ft_rounds")
PARENT = "23f2e2caa3395837c9474735ffc83321f3b9b5a1"
CANDIDATE = "e4f32022a5aa4d8734d87d9f6eb15e98c1edde42"
T16_RID = "E2-R022-gate-D14"
T16_BATCH = 50
T16_BASE_SHA256 = "379948776d42d5429304afb11dafb0d316e641638caf7cad15fb5b5e6be7340f"
T16_LAUNCH_SHA256 = "7e1c05a79b856b6a99c3f8d9422afd7013b9ef0215c78e17427d205f78384dcf"
T16_LAUNCH_PROTOCOL = "t17_owned_launch_protocol.py"
STATE_ROLES = ("conv_states", "recurrent_states", "slot:ple_conv", "slot:ple_ngram_ctx")
BOUNDARY_PLAN = (
    {"name": "start-short-child-8192", "length": 8192, "chunk_start": 8192, "short_tail": 4096},
    {"name": "internal-12416", "length": 12416, "chunk_start": 8193, "short_tail": 4096},
    {"name": "internal-18944", "length": 18944, "chunk_start": 8193, "short_tail": 4096},
    {"name": "aligned-12736", "length": 12736, "chunk_start": 8193, "short_tail": 4096},
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exact_context(ids: list[int], length: int) -> list[int]:
    """Return the two token identities immediately preceding an absolute length."""
    if length < 2 or length > len(ids):
        raise ValueError(f"invalid absolute boundary {length} for {len(ids)} tokens")
    return ids[length - 2:length]


def install_resume_device_dump(scheduler_type: type) -> Callable[..., Any]:
    """Wrap exactly one restore call and export only actual device-source resumes.

    The wrapper snapshots request fields before the original method consumes them.
    It neither forwards the model nor changes request fields, return values, or
    scheduling.  `dump_state` owns the existing FT_DEV_STATE_DUMP guard.
    """
    original = scheduler_type._restore_linear_states

    def wrapped(self: Any, batch: Any) -> Any:
        snapshots = [
            (getattr(req, "uid", ""), getattr(req, "cached_len", 0), src,
             getattr(req, "linear_slot_idx", None))
            for req in batch.reqs
            for src in (getattr(req, "mamba_restore_src", None),)
            if src is not None
        ]
        result = original(self, batch)
        pool = getattr(self.engine, "linear_state_pool", None)
        if pool is not None:
            for uid, cached_len, _src, destination in snapshots:
                pool.dump_state("resume-device", dev_slots=destination,
                                length=int(cached_len or 0), uid=str(uid))
        return result

    scheduler_type._restore_linear_states = wrapped
    return original


# The frozen startup entry writes this exact source and invokes `freetoken.cli`
# with the unmodified original ft argv.  It is intentionally not executed here.
EXACT_ID_PATCH = r'''from dataclasses import dataclass
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
'''

STARTUP_WRAPPER = r'''import os,sys,hashlib
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
'''


def launch_manifest(rid: str, batch: int, source: Path) -> dict[str, Any]:
    """Return bytes which a Linux staging step must freeze before reservation."""
    if not rid or not isinstance(batch, int) or batch < 1:
        raise ValueError("root-assigned non-empty RID and positive batch are required")
    if source.is_symlink() or not source.is_file():
        raise ValueError("T17 runner source must be a regular file")
    return {
        "schema": "ft_t17_d14_frozen_launch/v1", "rid": rid, "batch": batch,
        "candidate_commit": CANDIDATE, "parent_commit": PARENT,
        "runner_sha256": sha256(source),
        "startup_wrapper_sha256": hashlib.sha256(STARTUP_WRAPPER.encode()).hexdigest(),
        "t16_lifecycle": {"runner": "t16_full_tail_base_runner.py", "runner_sha256": T16_BASE_SHA256,
                           "launcher": T16_LAUNCH_PROTOCOL, "launcher_sha256": T16_LAUNCH_SHA256},
        "boundary_plan": BOUNDARY_PLAN, "mamba_host_slots": 0,
        "required_result_fields": ["actual_cached_tokens", "prompt_ids_sha256", "donor_ngram", "resume_ngram",
                                   "cold_text", "hit_text", "state_roles"],
    }


def verify_t16_lifecycle(base_runner: Path, launcher: Path) -> dict[str, str]:
    """Pin the resource gate, lock release, and owned-stop implementation bytes."""
    if any(path.is_symlink() or not path.is_file() for path in (base_runner, launcher)):
        raise ValueError("T16 lifecycle sources must be regular files")
    if sha256(base_runner) != T16_BASE_SHA256 or sha256(launcher) != T16_LAUNCH_SHA256:
        raise ValueError("reviewed T16 lifecycle bytes differ")
    base, launch = base_runner.read_text(encoding="utf-8"), launcher.read_text(encoding="utf-8")
    for marker in ("def gate(", "def lock_take(", "def lock_release(", "def stop("):
        if marker not in base:
            raise ValueError(f"T16 base runner lacks lifecycle marker {marker}")
    for marker in ("def stop_owned_process(", "def reserve_process(", "owned_group_alive("):
        if marker not in launch:
            raise ValueError(f"T16 launcher lacks owned-stop marker {marker}")
    return {"base_runner_sha256": T16_BASE_SHA256, "launcher_sha256": T16_LAUNCH_SHA256}


def freeze_startup_wrapper(directory: Path) -> Path:
    """Create one immutable startup entry in an already-owned staging directory."""
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("startup wrapper staging directory must be a real directory")
    patch = directory / "t17_d14_exact_ids.py"
    with patch.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(EXACT_ID_PATCH)
    patch.chmod(0o444)
    target = directory / "t17_d14_startup.py"
    with target.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(STARTUP_WRAPPER)
    target.chmod(0o444)
    if (target.is_symlink() or patch.is_symlink()
            or sha256(target) != hashlib.sha256(STARTUP_WRAPPER.encode()).hexdigest()
            or sha256(patch) != hashlib.sha256(EXACT_ID_PATCH.encode()).hexdigest()):
        raise ValueError("frozen startup wrapper changed")
    return target


def startup_argv(wrapper: Path, ft_arguments: list[str]) -> list[str]:
    """Preserve the original ft CLI argv; wrapper injection is Python-only."""
    if wrapper.is_symlink() or not wrapper.is_file() or wrapper.stat().st_mode & 0o222:
        raise ValueError("startup wrapper is not frozen")
    if not ft_arguments or ft_arguments[0] != "serve":
        raise ValueError("T17 startup requires the original ft serve argv")
    return ["/data2/FreeToken/venv/bin/python", "-u", str(wrapper), *ft_arguments]


def validate_hit_receipt(receipt: dict[str, Any]) -> None:
    """Reject a run unless it proves the real hit, token identity, text and state roles."""
    if receipt.get("gpu_started") is not True or receipt.get("mamba_host_slots") != 0:
        raise ValueError("receipt is not a device-resume T17 run")
    for case in BOUNDARY_PLAN:
        row = receipt.get("cases", {}).get(case["name"])
        if not isinstance(row, dict):
            raise ValueError(f"missing real boundary case: {case['name']}")
        required = {"prompt_ids_sha256", "actual_cached_tokens", "donor_ngram", "resume_ngram",
                    "expected_ngram", "cold_text", "hit_text", "state_roles"}
        if required - row.keys() or not row["prompt_ids_sha256"] or row["actual_cached_tokens"] <= 0:
            raise ValueError(f"missing actual hit evidence: {case['name']}")
        if row["donor_ngram"] != row["expected_ngram"] or row["resume_ngram"] != row["expected_ngram"]:
            raise ValueError(f"integer ngram identity mismatch: {case['name']}")
        if row["cold_text"] != row["hit_text"]:
            raise ValueError(f"full text mismatch: {case['name']}")
        roles = row["state_roles"]
        if not isinstance(roles, dict) or any(roles.get(role) != "equal" for role in STATE_ROLES):
            raise ValueError(f"state role mismatch or omission: {case['name']}")


def completion_payload(ids: list[int], max_tokens: int) -> dict[str, Any]:
    """The requested exact-ID HTTP payload; current candidate rejects it by design."""
    if not ids or any(type(token) is not int for token in ids) or max_tokens < 1:
        raise ValueError("non-empty integer IDs and positive max_tokens required")
    return {"model": "Qwen3.8-Flash-Next-NVFP4", "prompt": ids, "max_tokens": max_tokens,
            "temperature": 0, "top_p": 1, "stream": False}


def http_completion(base_url: str, payload: dict[str, Any], timeout: int = 1800) -> dict[str, Any]:
    """Capture the exact terminal HTTP response, including a non-2xx error body."""
    request = urllib.request.Request(base_url.rstrip("/") + "/v1/completions",
                                     data=json.dumps(payload, separators=(",", ":")).encode(),
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body, status = response.read(), response.status
    except urllib.error.HTTPError as exc:
        body, status = exc.read(), exc.code
    try:
        decoded = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("completion endpoint did not return JSON") from exc
    return {"status": status, "payload": payload, "response": decoded,
            "response_sha256": hashlib.sha256(body).hexdigest()}


def exact_id_request(base_url: str, ids: list[int], max_tokens: int, timeout: int = 1800,
                     output_path: Path | None = None, observations_path: Path | None = None) -> dict[str, Any]:
    """Use only the frozen wrapper's private endpoint; retain its full raw response."""
    payload = {"input_ids": ids, "max_tokens": max_tokens}
    start = (len(observations_path.read_text(encoding='utf-8').splitlines())
             if observations_path is not None and observations_path.exists() else 0)
    request = urllib.request.Request(base_url.rstrip("/") + "/internal/t17/exact-ids",
                                     data=json.dumps(payload, separators=(",", ":")).encode(),
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body, status = response.read(), response.status
    except urllib.error.HTTPError as exc:
        body, status = exc.read(), exc.code
    try:
        decoded = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        decoded = {"invalid_json_body": body.decode(errors="replace")}
    expected = hashlib.sha256(__import__("struct").pack(f"<{len(ids)}i", *ids)).hexdigest()
    record = {"status": status, "payload": payload, "response": decoded,
              "response_sha256": hashlib.sha256(body).hexdigest(),
              "expected_input_ids_sha256": expected,
              "observation_range": {"start": start,
                  "end": (len(observations_path.read_text(encoding='utf-8').splitlines())
                          if observations_path is not None and observations_path.exists() else start)}}
    if output_path is not None:
        raw = output_path.with_suffix('.response.bin')
        with raw.open('xb') as stream:
            stream.write(body)
        record['raw_response_file'] = raw.name
        with output_path.open('x', encoding='utf-8') as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
    if status != 200 or "detail" in decoded or not isinstance(decoded.get("uid"), int):
        raise RuntimeError("private exact-ID terminal failure: " + json.dumps(record, sort_keys=True))
    if decoded.get("input_ids_sha256") != expected:
        raise ValueError("worker-bound input IDs differ from client IDs")
    return record


def donor_hit_cold(base_url: str, ids: list[int], length: int) -> dict[str, Any]:
    """One live-service arm: donor L+1, exact-prefix hit L+65, then report evidence.

    The caller runs this only after a fresh service for each cold arm; it never
    infers a cache clear from readiness.
    """
    if length + 65 > len(ids) or length < 8192:
        raise ValueError("trace IDs do not cover the required donor/query boundary")
    donor = exact_id_request(base_url, ids[:length + 1], 2)
    hit = exact_id_request(base_url, ids[:length + 65], 128)
    usage = hit["response"].get("usage") or {}
    if usage.get("cached_tokens") != length:
        raise ValueError(f"actual cached length {usage.get('cached_tokens')} != {length}")
    return {"length": length, "expected_ngram": exact_context(ids, length),
            "donor": donor, "hit": hit, "actual_cached_tokens": usage["cached_tokens"],
            "prompt_ids_sha256": hit["response"]["input_ids_sha256"]}


def require_completion_success(record: dict[str, Any]) -> dict[str, Any]:
    if record.get("status") != 200 or record.get("response", {}).get("error"):
        raise RuntimeError("exact-ID completion transport rejected: " + json.dumps(record, sort_keys=True))
    response = record["response"]
    if not response.get("choices") or "usage" not in response:
        raise ValueError("completion response lacks terminal choices or usage")
    return response


def load_dump_record(dump_dir: Path, *, kind: str, length: int, uid: str) -> dict[str, Any]:
    """Find one unambiguous state record and require all four T17 roles."""
    index = dump_dir / "index.jsonl"
    if not index.is_file() or index.is_symlink():
        raise ValueError("missing dump index")
    records = [json.loads(line) for line in index.read_text(encoding="utf-8").splitlines() if line]
    matches = [row for row in records if row.get("kind") == kind and row.get("length") == length
               and str(row.get("uid")) == str(uid)]
    if len(matches) != 1:
        raise ValueError(f"expected one {kind} dump for uid={uid} length={length}, got {len(matches)}")
    row = matches[0]
    files = row.get("files") or {}
    if set(STATE_ROLES) - files.keys():
        raise ValueError("dump record lacks required state roles")
    for name in STATE_ROLES:
        path = dump_dir / files[name]
        relative = Path(files[name])
        if (relative.is_absolute() or '..' in relative.parts or dump_dir.resolve() not in path.resolve().parents
                or path.is_symlink() or not path.is_file()):
            raise ValueError(f"dump file is missing or unsafe: {name}")
    return row


def equal_dump_roles(left_dir: Path, left: dict[str, Any], right_dir: Path, right: dict[str, Any]) -> dict[str, str]:
    """Compare raw CPU tensors exactly; no tolerance is admitted by this gate."""
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("torch is required to compare captured state") from exc
    result = {}
    for role in STATE_ROLES:
        a = torch.load(left_dir / left["files"][role], map_location="cpu", weights_only=True)
        b = torch.load(right_dir / right["files"][role], map_location="cpu", weights_only=True)
        result[role] = "equal" if torch.equal(a, b) else "different"
    if any(value != "equal" for value in result.values()):
        raise ValueError("state tensor difference")
    return result


def sealed_manifest(directory: Path) -> set[str]:
    manifest = directory / "MANIFEST.sha256"
    if directory.is_symlink() or not manifest.is_file() or manifest.is_symlink():
        raise ValueError("T16 evidence or manifest is not a regular file")
    declared: set[str] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, relative = line.split("  ", 1)
        relative = relative.removeprefix('./')
        target = (directory / relative).resolve()
        if directory.resolve() not in target.parents or not target.is_file() or target.is_symlink():
            raise ValueError(f"manifest escapes evidence directory: {relative}")
        if sha256(target) != digest:
            raise ValueError(f"manifest digest mismatch: {relative}")
        declared.add(relative)
    if any(path.is_symlink() or path.stat().st_mode & 0o222 for path in [directory, *directory.rglob("*")]):
        raise ValueError("T16 evidence is not sealed read-only")
    return declared


def t16_prerequisite(rounds: Path = ROUNDS) -> dict[str, Any]:
    """Verify the closed independent T16 review; this does not touch the GPU lock."""
    directory = rounds / T16_RID
    round_json = json.loads((directory / "round.json").read_text(encoding="utf-8"))
    if (round_json.get("round_id") != T16_RID or round_json.get("card") != "T16"
            or round_json.get("base", {}).get("commit") != PARENT
            or round_json.get("experimental", {}).get("candidate_commit") != CANDIDATE
            or not round_json.get("closed_at")):
        raise ValueError("T16 round is absent, unclosed, or binds another candidate")
    gate_name, review_name = f"gate_batch{T16_BATCH}.json", f"review_batch{T16_BATCH}.json"
    gate = json.loads((directory / gate_name).read_text(encoding="utf-8"))
    review_path = directory / review_name
    review = json.loads(review_path.read_text(encoding="utf-8"))
    if (gate.get("proposed_verdict") != "kept" or gate.get("parent_commit") != PARENT
            or gate.get("new_commit") != CANDIDATE or review.get("verdict") != "PASS"
            or review.get("rid") != T16_RID or review.get("batch") != T16_BATCH
            or round_json.get("independent_review_sha256") != sha256(review_path)):
        raise ValueError("T16 measurement or independent review did not pass")
    declared = sealed_manifest(directory)
    required = {gate_name, review_name, "batch.sh"}
    if not required <= declared:
        raise ValueError("T16 sealed manifest lacks gate, review, or batch wrapper")
    return {"round": str(directory), "round_sha256": sha256(directory / "round.json"),
            "gate_sha256": sha256(directory / gate_name), "review_sha256": sha256(review_path)}


# Kept as a literal program so `--cpu-replay` executes on the Linux host using
# its target tokenizer and its sealed historical input, without copying tensors.
CPU_REPLAY = r'''
import hashlib,json,pathlib,runpy,struct,subprocess,sys
root=pathlib.Path('/data2/FreeToken'); tree=root/'wt/e2d14'
round_dir=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R002')
sha=lambda p: hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
assert subprocess.check_output(['git','-C',str(tree),'rev-parse','HEAD'],text=True).strip()=='e4f32022a5aa4d8734d87d9f6eb15e98c1edde42'
assert sha(round_dir/'round.json')=='53b1849cc68584d488ae7f7388e91c169c20575d9bb0f2b64a52d80692c38427'
sys.path[:0]=[str(tree/'python'),str(tree)]; sys.path.append(str(root/'venv/lib/python3.10/site-packages'))
import freetoken,torch
assert freetoken.__file__==str(tree/'python/freetoken/__init__.py')
from freetoken.server.api_models import ChatCompletionRequest
from freetoken.server.openai_api import chat_request_to_genspec
from freetoken.message import TokenizeMsg
from freetoken.tokenizer.tokenize import TokenizeManager
from freetoken.utils import load_tokenizer
builder_path=root/'scripts/agent_trace.py'; builder=runpy.run_path(str(builder_path),run_name='t17_read_only_builder')
trace_path=round_dir.parent/'E1-R003-v2/trace_rev.json'; trace=json.loads(trace_path.read_text())
tokenizer=load_tokenizer(str(root/'models/Qwen3.8-Flash-Next-NVFP4-overlay')); manager=TokenizeManager(tokenizer)
thinking=bool(trace.get('meta',{}).get('params',{}).get('thinking',True)); inputs=[]
for index,record in enumerate(trace['rounds']):
 messages=record['messages']; digest=builder['messages_digest'](messages); assert digest==record['record']['messages_sha']
 payload=builder['build_payload'](messages,'Qwen3.8-Flash-Next-NVFP4',trace.get('tools') or builder['tool_specs'](),thinking,32)
 spec=chat_request_to_genspec(ChatCompletionRequest.model_validate(payload),{})
 msg=TokenizeMsg(uid=index,text=spec.messages,sampling_params=spec.sampling_params,chat_template_kwargs=spec.chat_template_kwargs,tools=spec.template_tools)
 ids=manager.tokenize([msg])[0].input_ids.tolist(); inputs.append((len(ids),ids,index,digest))
checks=[]
for length,expected in ((12416,[1469,17]),(18944,[11,4093]),(12736,[198,248068])):
 rows=[x for x in inputs if x[0]//64*64==length]; assert len(rows)==1
 actual=rows[0][1][length-2:length]; assert actual==expected
 checks.append({'length':length,'actual':actual,'trace_index':rows[0][2],'messages_sha':rows[0][3], 'ids_int32le_sha256':hashlib.sha256(struct.pack('<%di'%len(rows[0][1]),*rows[0][1])).hexdigest()})
assert not torch.cuda.is_initialized()
print(json.dumps({'schema':'ft_t17_d14_cpu_raw_replay/v1','gpu_started':False,'server_files_mutated':False,'commit':'e4f32022a5aa4d8734d87d9f6eb15e98c1edde42','imported_freetoken':freetoken.__file__,'trace_sha256':sha(trace_path),'checks':checks},sort_keys=True))
'''


def cpu_replay(host: str) -> dict[str, Any]:
    env = "CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 TOKENIZERS_PARALLELISM=false"
    command = f"{env} timeout 180s /data2/FreeToken/venv/bin/python -S -c {shlex.quote(CPU_REPLAY)}"
    result = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, command],
                            capture_output=True, text=True, timeout=200)
    if result.returncode:
        raise RuntimeError("CPU replay failed:\n" + result.stderr[-8000:])
    try:
        report = json.loads(result.stdout.splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise RuntimeError("CPU replay produced no JSON receipt") from exc
    if report.get("gpu_started") is not False or report.get("commit") != CANDIDATE:
        raise ValueError("CPU replay receipt is not bound to the D14 candidate")
    return report


T16_PREFLIGHT = r'''
import hashlib,json,pathlib
root=pathlib.Path('/data2/_shared/runs/ft_rounds'); directory=root/'E2-R022-gate-D14'; sha=lambda p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
round_json=json.loads((directory/'round.json').read_text())
assert round_json['round_id']=='E2-R022-gate-D14' and round_json['card']=='T16' and round_json['base']['commit']=='23f2e2caa3395837c9474735ffc83321f3b9b5a1' and round_json['experimental']['candidate_commit']=='e4f32022a5aa4d8734d87d9f6eb15e98c1edde42' and round_json.get('closed_at')
gate_path=directory/'gate_batch50.json'; review_path=directory/'review_batch50.json'; gate=json.loads(gate_path.read_text()); review=json.loads(review_path.read_text())
assert gate['proposed_verdict']=='kept' and gate['parent_commit']=='23f2e2caa3395837c9474735ffc83321f3b9b5a1' and gate['new_commit']=='e4f32022a5aa4d8734d87d9f6eb15e98c1edde42' and review['verdict']=='PASS' and review['rid']=='E2-R022-gate-D14' and review['batch']==50 and round_json['independent_review_sha256']==sha(review_path)
declared=set()
for line in (directory/'MANIFEST.sha256').read_text().splitlines():
 digest,relative=line.split('  ',1); relative=relative.removeprefix('./'); target=(directory/relative).resolve(); assert directory.resolve() in target.parents and target.is_file() and not target.is_symlink() and sha(target)==digest; declared.add(relative)
assert {'gate_batch50.json','review_batch50.json','batch.sh'}<=declared
assert not any(p.is_symlink() or p.stat().st_mode&0o222 for p in [directory,*directory.rglob('*')])
print(json.dumps({'schema':'ft_t17_d14_gpu_preflight/v1','gpu_started':False,'round':str(directory),'round_sha256':sha(directory/'round.json'),'gate_sha256':sha(gate_path),'review_sha256':sha(review_path),'stop_condition':'T16 PASS + independent T17 review required'},sort_keys=True))
'''


def gpu_preflight(host: str) -> dict[str, Any]:
    result = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host,
                             f"/data2/FreeToken/venv/bin/python -S -c {shlex.quote(T16_PREFLIGHT)}"],
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError("T16 is not an accepted prerequisite; no GPU launch is permitted:\n" + result.stderr[-4000:])
    return json.loads(result.stdout.splitlines()[-1])


KNOWN_DUMP_INSPECTION = r'''import json,pathlib,sys
sys.path.append('/data2/FreeToken/venv/lib/python3.10/site-packages')
import torch
root=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R002/RLM/dump'); rows=[json.loads(x) for x in (root/'index.jsonl').read_text().splitlines() if x]
out=[]
for length,expected in ((12416,[1469,17]),(18944,[11,4093]),(12736,[198,248068])):
 found=[r for r in rows if r.get('kind')=='donate' and r.get('length')==length]
 assert len(found)==1, (length,len(found)); row=found[0]; path=root/row['files']['slot:ple_ngram_ctx']; actual=torch.load(path,map_location='cpu',weights_only=True).flatten().tolist()
 out.append({'length':length,'uid':str(row['uid']),'seq':row['seq'],'kind':row['kind'],'actual':actual,'expected':expected,'equal':actual==expected,'file':path.name})
print(json.dumps({'schema':'ft_t17_d14_known_dump_inspection/v1','gpu_started':False,'source':'E2-R002/RLM','rows':out},sort_keys=True))
'''


def inspect_known_dump(host: str) -> dict[str, Any]:
    result = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host,
                             f"CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python -S -c {shlex.quote(KNOWN_DUMP_INSPECTION)}"],
                            capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError("known dump inspection failed:\n" + result.stderr[-4000:])
    report = json.loads(result.stdout.splitlines()[-1])
    if report.get("gpu_started") is not False or [x["equal"] for x in report["rows"]] != [False, False, True]:
        raise ValueError("historical known-wrong dump no longer has the expected semantic signature")
    return report


def cpu_spawn_proof(host: str) -> dict[str, Any]:
    """Run a clean Linux spawn child through the frozen wire decoder and worker hook."""
    import base64
    child = r'''import hashlib,json,multiprocessing,os,sys,tempfile
os.environ['CUDA_VISIBLE_DEVICES']=''
ROOT='/data2/FreeToken/wt/e2d14'; PATCH=__PATCH__
def worker(stage,q):
 sys.path[:0]=[stage,ROOT+'/python',ROOT]; sys.path.append('/data2/FreeToken/venv/lib/python3.10/site-packages')
 import t17_d14_exact_ids
 from freetoken.message.tokenizer import BaseTokenizerMsg,T17ExactIdsMsg
 from freetoken.core import SamplingParams
 wire=T17ExactIdsMsg(uid=41,text='',sampling_params=SamplingParams(max_tokens=7,temperature=0,top_p=1),input_ids_exact=[1469,17,198,248068])
 decoded=BaseTokenizerMsg.decoder(BaseTokenizerMsg.encoder(wire)); from freetoken.tokenizer.tokenize import TokenizeManager
 out=TokenizeManager.__new__(TokenizeManager).tokenize([decoded])[0]
 import torch,struct
 ids=out.input_ids.tolist(); q.put({'uid':out.uid,'numel':len(ids),'ids_int32le_sha256':hashlib.sha256(struct.pack('<%di'%len(ids),*ids)).hexdigest(),'max_tokens':out.sampling_params.max_tokens,'temperature':out.sampling_params.temperature,'cuda_initialized':torch.cuda.is_initialized()})
if __name__=='__main__':
 stage=tempfile.mkdtemp(prefix='t17-spawn-'); open(stage+'/t17_d14_exact_ids.py','w').write(__import__('base64').b64decode(PATCH).decode())
 q=multiprocessing.get_context('spawn').Queue(); p=multiprocessing.get_context('spawn').Process(target=worker,args=(stage,q)); p.start(); result=q.get(timeout=60); p.join(60); assert p.exitcode==0; assert result['uid']==41 and result['numel']==4 and result['max_tokens']==7 and result['temperature']==0 and not result['cuda_initialized']; print(json.dumps({'schema':'ft_t17_d14_cpu_spawn/v1','gpu_started':False,'worker':result},sort_keys=True))
'''.replace('__PATCH__', repr(base64.b64encode(EXACT_ID_PATCH.encode()).decode()))
    program = "import base64,subprocess,tempfile,pathlib; s=" + repr(child) + "; p=pathlib.Path(tempfile.mkdtemp())/'probe.py'; p.write_text(s); r=subprocess.run(['/data2/FreeToken/venv/bin/python','-S',str(p)],capture_output=True,text=True); print(r.stdout,end=''); raise SystemExit(r.returncode)"
    result = subprocess.run(["ssh", "-o", "BatchMode=yes", host,
                             f"CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python -S -c {shlex.quote(program)}"],
                            capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError("CPU spawn proof failed:\n" + result.stderr[-6000:])
    report = json.loads(result.stdout.splitlines()[-1])
    if report.get("gpu_started") is not False or report["worker"].get("cuda_initialized"):
        raise ValueError("spawn proof initialized CUDA")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cpu-replay", action="store_true")
    parser.add_argument("--preflight-gpu", action="store_true")
    parser.add_argument("--prepare-launch", action="store_true")
    parser.add_argument("--validate-receipt", type=Path)
    parser.add_argument("--inspect-known-dump", action="store_true")
    parser.add_argument("--cpu-spawn-proof", action="store_true")
    parser.add_argument("--rid")
    parser.add_argument("--batch", type=int)
    parser.add_argument("--host", default="9")
    args = parser.parse_args()
    selected = sum((args.cpu_replay, args.preflight_gpu, args.prepare_launch, args.validate_receipt is not None,
                    args.inspect_known_dump, args.cpu_spawn_proof))
    if selected != 1:
        parser.error("choose exactly one operation")
    if args.cpu_replay:
        print(json.dumps(cpu_replay(args.host), ensure_ascii=False, sort_keys=True))
        return
    if args.prepare_launch:
        print(json.dumps(launch_manifest(args.rid or "", args.batch or 0, Path(__file__)),
                         ensure_ascii=False, sort_keys=True))
        return
    if args.validate_receipt is not None:
        validate_hit_receipt(json.loads(args.validate_receipt.read_text(encoding="utf-8")))
        print(json.dumps({"schema": "ft_t17_d14_receipt_validation/v1", "accepted": True}, sort_keys=True))
        return
    if args.inspect_known_dump:
        print(json.dumps(inspect_known_dump(args.host), ensure_ascii=False, sort_keys=True))
        return
    if args.cpu_spawn_proof:
        print(json.dumps(cpu_spawn_proof(args.host), ensure_ascii=False, sort_keys=True))
        return
    # This remains intentionally non-mutating: an independent reviewer must
    # validate its output before a separately frozen, owned-stop launcher runs.
    print(json.dumps(gpu_preflight(args.host), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
