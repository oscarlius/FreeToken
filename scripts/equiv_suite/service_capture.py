"""Bounded, opt-in service receipts around the existing sampler observer."""
from __future__ import annotations
import hashlib, json, os, struct
from pathlib import Path
from typing import Any
from .sampler_capture import CaptureError, QueryRegistry, SamplerCapture

SCHEMA = "ft_equiv_service_capture/v2"
ADMISSION_SCHEMA = "ft_equiv_service_admission/v1"
class ServiceCaptureError(ValueError): pass
def _raw(value: object) -> bytes: return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
def _sha(raw: bytes) -> str: return hashlib.sha256(raw).hexdigest()
def _uid(value: object) -> str | int:
    if type(value) not in (str, int): raise ServiceCaptureError("UID must be a string or integer")
    return value
def _label(value: object) -> str:
    if not isinstance(value, str) or not value: raise ServiceCaptureError("logical_label must be a non-empty string")
    return value
def _ids(message: object) -> list[int]:
    import torch
    value = getattr(message, "input_ids", None); integer = {torch.uint8, torch.int8, torch.int16, torch.int32, torch.int64}
    if not isinstance(value, torch.Tensor) or value.device.type != "cpu" or value.ndim != 1 or value.dtype not in integer or value.numel() == 0: raise ServiceCaptureError("UserMsg input_ids must be a non-empty one-dimensional integer CPU tensor")
    result = [int(item) for item in value.detach().contiguous().tolist()]
    if any(item < -(2 ** 31) or item >= 2 ** 31 for item in result): raise ServiceCaptureError("UserMsg input_ids must fit signed int32")
    return result
def _token_sha(values: list[int]) -> str: return _sha(struct.pack(f"<{len(values)}i", *values))
def _sampling(message: object) -> tuple[dict[str, object], str]:
    params = getattr(message, "sampling_params", None)
    values = {"temperature": getattr(params, "temperature", None), "top_k": getattr(params, "top_k", None), "top_p": getattr(params, "top_p", None), "ignore_eos": getattr(params, "ignore_eos", None), "max_tokens": getattr(params, "max_tokens", None), "stop_strs": getattr(params, "stop_strs", None)}
    if type(values["temperature"]) not in (int, float) or type(values["top_k"]) is not int or type(values["top_p"]) not in (int, float) or type(values["ignore_eos"]) is not bool or type(values["max_tokens"]) is not int or values["max_tokens"] < 0 or not isinstance(values["stop_strs"], list) or not all(isinstance(x, str) for x in values["stop_strs"]): raise ServiceCaptureError("UserMsg sampling_params cannot be normalized")
    normalized = {"temperature": float(values["temperature"]), "top_k": values["top_k"], "top_p": float(values["top_p"]), "ignore_eos": values["ignore_eos"], "max_tokens": values["max_tokens"], "stop_strs": list(values["stop_strs"])}
    return normalized, _sha(_raw(normalized))
def _expected(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value: raise ServiceCaptureError("expected queries must be a non-empty explicit list")
    result=[]; seen=set(); per_uid={}; labels={}
    for item in value:
        if not isinstance(item, dict) or set(item) != {"uid", "generation_index", "logical_label"}: raise ServiceCaptureError("expected query must contain only uid, generation_index, and logical_label")
        uid, generation, label = _uid(item["uid"]), item["generation_index"], _label(item["logical_label"])
        if type(generation) is not int or generation < 0: raise ServiceCaptureError("expected generation_index must be a non-negative integer")
        if (uid, generation) in seen: raise ServiceCaptureError("expected queries contain duplicate UID/generation")
        if uid in labels and labels[uid] != label: raise ServiceCaptureError("one UserMsg UID must have one logical_label")
        seen.add((uid, generation)); labels[uid]=label; per_uid.setdefault(uid, []).append(generation); result.append({"uid":uid,"generation_index":generation,"logical_label":label})
    if any(sorted(items) != list(range(len(items))) for items in per_uid.values()): raise ServiceCaptureError("expected generations must be contiguous from zero for each UID")
    return result

class ServiceCaptureAdapter:
    def __init__(self, destination: Path | str, *, expected_queries: list[dict[str, Any]], max_captures: int, max_bytes: int, process_identity: dict | None = None) -> None:
        self.destination=Path(destination); self.expected_queries=_expected(expected_queries); self.registry=QueryRegistry(); self.capture=SamplerCapture(self.destination/"sampler", registry=self.registry, process_identity=process_identity, max_captures=max_captures, max_bytes=max_bytes)
        self._expected_by_uid={}
        for item in self.expected_queries: self._expected_by_uid.setdefault(item["uid"], []).append(item)
        self._bound={}; self._admission_seq=0; self.deliveries=[]; self.errors=[]; self._attached=False; self._sealed=False
    def attach(self, engine: object) -> "ServiceCaptureAdapter":
        if self._attached: raise ServiceCaptureError("service capture is already attached")
        self.capture.attach(engine); self._attached=True; return self
    def logical_label_for_uid(self, uid: object) -> str:
        records=self._expected_by_uid.get(_uid(uid))
        if not records: raise ServiceCaptureError("actual UserMsg UID has no declared logical label")
        return records[0]["logical_label"]
    def _input_source(self, uid: str|int) -> dict[str,str]|None:
        name=str(uid)
        if Path(name).name != name: return None
        path=self.destination/"inputs"/f"{name}.json"
        return {"path":str(Path("inputs")/f"{name}.json"),"sha256":_sha(path.read_bytes())} if path.is_file() and not path.is_symlink() else None
    def admit_user_msg(self, message: object) -> str:
        if self._sealed: raise ServiceCaptureError("service capture is already sealed")
        uid=_uid(getattr(message,"uid",None)); label=self.logical_label_for_uid(uid)
        if uid in self._bound: raise ServiceCaptureError("duplicate UserMsg binding")
        ids=_ids(message); input_sha=_token_sha(ids); sampling,sampling_sha=_sampling(message); self._admission_seq+=1; identity=self.capture.process_identity
        event=_sha(_raw({"pid":identity["pid"],"start_ticks":identity["start_ticks"],"execution_id":identity["execution_id"],"admission_seq":self._admission_seq,"uid_type":type(uid).__name__,"uid":uid,"input_ids_sha256":input_sha}))
        receipt={"schema":ADMISSION_SCHEMA,"admission_seq":self._admission_seq,"uid":uid,"input_ids":ids,"input_ids_sha256":input_sha,"sampling_fields":sampling,"sampling_fields_sha256":sampling_sha,"process_identity":identity,"physical_event_identity":event,"logical_label":label}
        source=self._input_source(uid)
        if source is not None: receipt["input_source_receipt"]=source
        root=self.destination/"admissions"; root.mkdir(parents=True,exist_ok=True)
        if root.is_symlink(): raise ServiceCaptureError("admission receipt root is a symlink")
        path=root/f"admission-{self._admission_seq:06d}.json"; raw=_raw(receipt)
        try:
            with path.open("xb") as handle: handle.write(raw)
        except OSError as error: raise ServiceCaptureError("cannot publish immutable admission receipt") from error
        try: self.registry.bind_query(uid,ids,event)
        except CaptureError as error: self.errors.append(f"indeterminate: {error}"); raise ServiceCaptureError(str(error)) from error
        self._bound[uid]={"logical_label":label,"physical_event_identity":event,"admission_seq":self._admission_seq,"receipt_path":str(path.relative_to(self.destination)),"receipt_sha256":_sha(raw)}
        return event
    def record_observer_error(self, message: str) -> None: self.errors.append(f"indeterminate: {message if isinstance(message,str) and message else 'observer error'}")
    def observe_detokenize(self, message: object) -> None:
        if self._sealed: raise ServiceCaptureError("service capture is already sealed")
        try:
            uid,token,finished=_uid(getattr(message,"uid",None)),getattr(message,"next_token",None),getattr(message,"finished",None)
            if type(token) is not int or token < -(2**31) or token >= 2**31 or type(finished) is not bool: raise ServiceCaptureError("DetokenizeMsg next_token/finished is invalid")
            expected=self._expected_by_uid.get(uid)
            if expected is None or uid not in self._bound: raise ServiceCaptureError("DetokenizeMsg UID has no bound expected query")
            generation=sum(item["uid"]==uid for item in self.deliveries)
            if generation >= len(expected): raise ServiceCaptureError("duplicate or extra DetokenizeMsg delivery")
            physical=self.registry.get(uid)["sampled_tokens"]
            if generation >= len(physical) or token != physical[generation]: raise ServiceCaptureError("DetokenizeMsg does not match physical sampler token")
            self.deliveries.append({"uid":uid,"generation_index":generation,"logical_label":expected[generation]["logical_label"],"physical_event_identity":self._bound[uid]["physical_event_identity"],"next_token":token,"sampled_token_id":physical[generation],"finished":finished,"delivered":True})
        except (CaptureError,ServiceCaptureError) as error: self.errors.append(f"indeterminate: {error}"); raise ServiceCaptureError(str(error)) from error
    def _physical_expected(self) -> list[dict[str,Any]]:
        return [{"uid":uid,"generation_index":generation,"event_identity":info["physical_event_identity"]} for uid,info in self._bound.items() for generation in range(len(self.registry.get(uid)["sampled_tokens"]))]
    def _verify_admissions(self) -> None:
        for uid,info in self._bound.items():
            path=self.destination/info["receipt_path"]
            if path.is_symlink() or not path.is_file() or _sha(path.read_bytes()) != info["receipt_sha256"]: raise ServiceCaptureError("admission receipt SHA binding is invalid")
            try: document=json.loads(path.read_text())
            except (OSError,json.JSONDecodeError) as error: raise ServiceCaptureError("admission receipt is unreadable") from error
            if document.get("schema") != ADMISSION_SCHEMA or document.get("uid") != uid or document.get("physical_event_identity") != info["physical_event_identity"] or document.get("process_identity") != self.capture.process_identity: raise ServiceCaptureError("admission receipt origin binding is invalid")
    def _delivery_extras(self) -> list[dict[str,Any]]:
        extras=[]
        for uid,expected in self._expected_by_uid.items():
            rows=[item for item in self.deliveries if item["uid"]==uid]
            if len(rows)!=len(expected): raise ServiceCaptureError("not every expected query has an actual DetokenizeMsg delivery")
            if any(row["generation_index"]!=index or row["finished"] for index,row in enumerate(rows[:-1])): raise ServiceCaptureError("terminal DetokenizeMsg occurred before the declared final generation")
            if not rows[-1]["finished"]: raise ServiceCaptureError("final declared generation lacks a terminal DetokenizeMsg")
            sampled=self.registry.get(uid)["sampled_tokens"]
            if len(sampled)<len(rows): raise ServiceCaptureError("physical sampler history is shorter than delivered history")
            extras.extend({"uid":uid,"generation_index":gen,"sampled_token_id":token,"delivered":False,"reason":"physical sample after delivered terminal generation"} for gen,token in enumerate(sampled[len(rows):],start=len(rows)))
        return extras
    def _report(self,terminal:str,error:str|None,extras:list[dict[str,Any]])->dict[str,Any]:
        return {"schema":SCHEMA,"admitted":False,"terminal":terminal,"scope":"physical sampler capture plus independently issued DetokenizeMsg delivery","process_identity":self.capture.process_identity,"expected_deliveries":self.expected_queries,"admission_receipts":[{"uid":uid,**info} for uid,info in self._bound.items()],"deliveries":self.deliveries,"un_delivered_samples":extras,"errors":self.errors+self.capture.errors,**({"error":error} if error else {})}
    def _write_report(self,document:dict[str,Any])->None:
        self.destination.mkdir(parents=True,exist_ok=True); target=self.destination/"service_delivery.json"
        if target.exists() or target.is_symlink(): raise ServiceCaptureError("service delivery report path already exists")
        target.write_bytes(_raw(document))
    def finalize(self)->dict[str,Any]:
        if self._sealed: raise ServiceCaptureError("service capture is already sealed")
        self._sealed=True; failure=None; extras=[]; physical=self._physical_expected()
        try:
            if not self._attached or set(self._bound)!=set(self._expected_by_uid): raise ServiceCaptureError("not every expected query has an actual UserMsg binding")
            self._verify_admissions(); extras=self._delivery_extras()
            if self.errors or self.capture.errors: raise ServiceCaptureError("service capture has indeterminate observer errors")
            self.capture.finalize(physical); terminal="complete"
        except (CaptureError,ServiceCaptureError) as error:
            failure=str(error); terminal="failed"; self.errors.append(f"indeterminate: {failure}"); manifest=self.capture.destination/"manifest.json"
            if not manifest.exists() or json.loads(manifest.read_text()).get("terminal")=="open":
                try: self.capture.finalize(physical)
                except CaptureError: pass
            try: extras=self._delivery_extras()
            except ServiceCaptureError: extras=[]
        report=self._report(terminal,failure,extras); self._write_report(report)
        if failure: raise ServiceCaptureError(failure)
        return report

def install_from_env(engine: object)->ServiceCaptureAdapter|None:
    destination=os.environ.get("FT_D16_SERVICE_CAPTURE_DIR")
    if not destination: return None
    expected_path=os.environ.get("FT_D16_SERVICE_CAPTURE_EXPECTED_JSON")
    if not expected_path: raise ServiceCaptureError("FT_D16_SERVICE_CAPTURE_EXPECTED_JSON is required when capture is enabled")
    path=Path(expected_path)
    if path.is_symlink() or not path.is_file(): raise ServiceCaptureError("expected query file must be a regular file")
    try: expected=json.loads(path.read_text()); max_captures=int(os.environ["FT_D16_SERVICE_CAPTURE_MAX_CAPTURES"]); max_bytes=int(os.environ["FT_D16_SERVICE_CAPTURE_MAX_BYTES"])
    except (OSError,json.JSONDecodeError,KeyError,ValueError) as error: raise ServiceCaptureError("expected JSON and explicit positive capture budgets are required") from error
    return ServiceCaptureAdapter(destination,expected_queries=expected,max_captures=max_captures,max_bytes=max_bytes).attach(engine)
