import hashlib
import importlib.util
import json
import struct
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("state_review", ROOT / "t20_native_state_review_v1.py")
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ids_sha(ids):
    return hashlib.sha256(struct.pack("<%di" % len(ids), *ids)).hexdigest()


def build_capture(tmp_path, kind="cache"):
    root = tmp_path / "capture"; root.mkdir()
    names = ["control_0", "control_1", "restore_0", "restore_1"] if kind == "parking" else ["cold_0", "cold_1", "warm_0", "warm_1"]
    arms = []
    for number, name in enumerate(names):
        arm = root / name
        ids = [10, 11, 12]
        worker = {"pid": 200 + number, "start_ticks": 300 + number, "execution_id": f"r:{name}:tp0"}
        dump(arm / "input.json", {"input_ids": ids, "max_tokens": 128})
        dump(arm / "admission.json", {"uid": 0, "process_identity": worker})
        dump(arm / "worker.json", {"identity": worker, "live_birth": {"pid": worker["pid"], "start_ticks": worker["start_ticks"]}, "frontend": {"pid": 100 + number}})
        dump(arm / "response.json", {"status": 200, "response": {"uid": 0, "finished": True, "input_ids_sha256": ids_sha(ids), "usage": {"completion_tokens": 128}, "text": "stable response"}})
        dump(arm / "delivery.json", {"terminal": "complete", "process_identity": worker, "deliveries": [{"uid": 0, "generation_index": i, "delivered": True, "sampled_token_id": i} for i in range(128)]})
        entry = {"name": name, "input": f"{name}/input.json", "admission": f"{name}/admission.json", "worker": f"{name}/worker.json", "response": f"{name}/response.json", "delivery": f"{name}/delivery.json"}
        if kind == "cache":
            warm = name.startswith("warm")
            dump(arm / "init.json", {"mode": "warm" if warm else "cold", "execution_id": worker["execution_id"], "priming_requests": 0, "resident_count": 2 if warm else 0, "eligible_layers": [0, 2]})
            dump(arm / "initial_residency.pt", {})
            dump(arm / "stats.json", {"prefill_hit_rows": 2 if warm else 0})
            entry.update(initialization=f"{name}/init.json", initial_residency=f"{name}/initial_residency.pt", terminal_stats=f"{name}/stats.json", state_files={})
            for label in module.LABELS:
                states = {}
                raw = {}
                for role in module.ROLES:
                    blob = (role + label).encode()
                    raw[role] = blob
                    states[role] = {"sha256": hashlib.sha256(blob).hexdigest(), "shape": [len(blob)], "dtype": "fixture"}
                dump(arm / f"{label}.json", {"uid": 0, "label": label, "states": states})
                (arm / f"{label}.pt").write_bytes(b"fixture")
                entry["state_files"][label] = {"json": f"{name}/{label}.json", "pt": f"{name}/{label}.pt"}
        else:
            dump(arm / "trigger.json", {"receipt": {"rows": [{"uid": 0, "generation_index": 7}]}})
            dump(arm / "pause.json", {"response": {"status": "accepted", "request_id": f"request-{number}"}})
            entry.update(trigger=f"{name}/trigger.json", pause=f"{name}/pause.json")
            if name.startswith("restore"):
                torch = pytest.importorskip('torch')
                requests = [{'uid':0,'table_idx':2,'linear_slot_idx':3,'host_slot':4}]
                proof = {'request_id':f'request-{number}','state_transport_bitwise':True,
                         'requests':requests,'pid':worker['pid'],'execution_id':worker['execution_id']}
                dump(arm/'roundtrip.json',proof)
                entry['roundtrip']=f'{name}/roundtrip.json'
                fills={'conv':0,'recurrent':0,'ple_conv':3.5,'ple_ngram_ctx':-1}
                stages={}
                for stage in ('before','host','cleared','restored'):
                    payload={role:torch.full((2,1,3), fills[role] if stage=='cleared' else 5,
                                    dtype=torch.int32 if role=='ple_ngram_ctx' else torch.float32)
                             for role in module.ROLES}
                    target=arm/f'{stage}.pt'; torch.save(payload,target)
                    stages[stage]={'path':target.name,'sha256':digest(target),
                        'states':{role:{'sha256':hashlib.sha256(module._tensor_bytes(value)[0]).hexdigest(),
                                       'shape':list(value.shape),'dtype':str(value.dtype)}
                                  for role,value in payload.items()}}
                dump(arm/'raw_capture_index.json',{'schema':'ft_r040a_native_parking_raw_capture/v2',
                            **proof,'stages':stages,'clear_fill_values':fills})
                entry["raw_capture_index"] = f"{name}/raw_capture_index.json"
        arms.append(entry)
    return root, arms


def pin(tmp_path, root, kind, arms):
    files = {path.relative_to(root).as_posix(): digest(path) for path in root.rglob("*") if path.is_file()}
    path = tmp_path / "pin.json"
    dump(path, {"schema": module.MAP_SCHEMA, "kind": kind, "files": files, "arms": arms})
    return path, digest(path)


def fixture_loader(path):
    if path.name == "initial_residency.pt":
        return [0, 0] if path.parent.name.startswith("warm") else [-1, -1]
    if path.parent.name.startswith("restore_") and path.stem in ("before", "host", "cleared", "restored"):
        return module._torch_loader(path)
    label = path.stem
    return {role: (role + label).encode() for role in module.ROLES}


def test_cache_reviews_full_raw_four_role_state_and_terminal_evidence(tmp_path):
    root, arms = build_capture(tmp_path)
    pin_path, pin_sha = pin(tmp_path, root, "cache", arms)
    result = module.review_native_state(root, map_path=pin_path, map_sha256=pin_sha, kind="cache", state_loader=fixture_loader)
    assert result == {"schema": module.SCHEMA, "kind": "cache", "verdict": "bitwise_pending_independent_review", "arms": ["cold_0", "cold_1", "warm_0", "warm_1"], "input_ids_sha256": ids_sha([10, 11, 12]), "token_count": 128}


def test_cache_rejects_uid_or_raw_role_byte_difference(tmp_path):
    root, arms = build_capture(tmp_path)
    dump(root / "cold_1" / "admission.json", {"uid": 9, "process_identity": {"pid": 201, "start_ticks": 301, "execution_id": "r:cold_1:tp0"}})
    pin_path, pin_sha = pin(tmp_path, root, "cache", arms)
    with pytest.raises(module.NativeStateReviewError, match="UID"):
        module.review_native_state(root, map_path=pin_path, map_sha256=digest(pin_path), kind="cache", state_loader=fixture_loader)


def test_cache_rejects_raw_state_difference_even_when_each_arm_metadata_matches(tmp_path):
    root, arms = build_capture(tmp_path)
    for arm in ("warm_0", "warm_1"):
        path = root / arm / "before_decode.json"
        document = json.loads(path.read_text())
        for role in module.ROLES:
            document["states"][role]["sha256"] = hashlib.sha256((role + "before_decode" + "warm").encode()).hexdigest()
        dump(path, document)
    pin_path, pin_sha = pin(tmp_path, root, "cache", arms)
    def divergent_loader(path):
        if path.name == "initial_residency.pt":
            return [0, 0] if path.parent.name.startswith("warm") else [-1, -1]
        suffix = "warm" if path.parent.name.startswith("warm") and path.stem == "before_decode" else ""
        return {role: (role + path.stem + suffix).encode() for role in module.ROLES}
    with pytest.raises(module.NativeStateReviewError, match="raw cache four-role states differ"):
        module.review_native_state(root, map_path=pin_path, map_sha256=pin_sha, kind="cache", state_loader=divergent_loader)


def test_rejects_short_terminal_output_before_state_claim(tmp_path):
    root, arms = build_capture(tmp_path)
    path = root / "cold_0" / "response.json"
    document = json.loads(path.read_text())
    document["response"]["usage"]["completion_tokens"] = 127
    dump(path, document)
    pin_path, pin_sha = pin(tmp_path, root, "cache", arms)
    with pytest.raises(module.NativeStateReviewError, match="length differs"):
        module.review_native_state(root, map_path=pin_path, map_sha256=pin_sha, kind="cache", state_loader=fixture_loader)


def test_parking_restore_raw_four_stage_positive(tmp_path):
    root, arms = build_capture(tmp_path, "parking")
    pin_path, pin_sha = pin(tmp_path, root, "parking", arms)
    assert module.review_native_state(root, map_path=pin_path, map_sha256=pin_sha, kind="parking", state_loader=fixture_loader)["verdict"] == "bitwise_pending_independent_review"


def test_parking_one_byte_raw_tamper_rejected(tmp_path):
    root, arms = build_capture(tmp_path, "parking")
    pin_path, pin_sha = pin(tmp_path, root, "parking", arms)
    def tampered(path):
        value = fixture_loader(path)
        if path.parent.name == "restore_1" and path.stem == "restored":
            value['conv'].view(__import__('torch').uint8).reshape(-1)[0] ^= 1
        return value
    with pytest.raises(module.NativeStateReviewError, match="raw tensor metadata|D2H/H2D"):
        module.review_native_state(root, map_path=pin_path, map_sha256=pin_sha, kind="parking", state_loader=tampered)


@pytest.mark.parametrize('mutation',['pid','uid','shape','clear_fill','missing_fill'])
def test_parking_rejects_actual_identity_metadata_and_clear_fill_differences(tmp_path,mutation):
    root,arms=build_capture(tmp_path,'parking')
    path=root/'restore_1/raw_capture_index.json'
    index=json.loads(path.read_text())
    if mutation=='pid': index['pid']+=1
    elif mutation=='uid': index['requests'][0]['uid']=9
    elif mutation=='shape': index['stages']['host']['states']['conv']['shape']=[999]
    elif mutation=='clear_fill': index['clear_fill_values']['ple_ngram_ctx']=0
    elif mutation=='missing_fill': del index['clear_fill_values']['ple_conv']
    dump(path,index)
    pin_path,pin_sha=pin(tmp_path,root,'parking',arms)
    with pytest.raises(module.NativeStateReviewError,match='identity|metadata|fill'):
        module.review_native_state(root,map_path=pin_path,map_sha256=pin_sha,kind='parking',state_loader=fixture_loader)


def test_rejects_tampered_or_escape_pinned_map_before_capture_claim(tmp_path):
    root, arms = build_capture(tmp_path)
    pin_path, pin_sha = pin(tmp_path, root, "cache", arms)
    document = json.loads(pin_path.read_text())
    document["arms"][0]["input"] = "../outside.json"
    dump(pin_path, document)
    with pytest.raises(module.NativeStateReviewError, match="unpinned capture path"):
        module.review_native_state(root, map_path=pin_path, map_sha256=digest(pin_path), kind="cache", state_loader=fixture_loader)
